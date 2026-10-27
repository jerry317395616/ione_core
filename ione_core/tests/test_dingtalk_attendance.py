"""Offline business-boundary checks; no Frappe database or DingTalk calls."""

import importlib.util
import sys
import types
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch


class ValidationError(Exception):
    pass


def getdate(value=None):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def get_datetime(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def get_time(value):
    return value if isinstance(value, time) else time.fromisoformat(str(value))


frappe = types.ModuleType("frappe")
frappe._ = lambda text: text
frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
frappe.ValidationError = ValidationError
frappe.AuthenticationError = ValidationError
frappe.PermissionError = ValidationError


def throw(message, exception=ValidationError):
    raise exception(message)


frappe.throw = throw
utils = types.ModuleType("frappe.utils")
utils.getdate = getdate
utils.get_datetime = get_datetime
utils.get_time = get_time
utils.now_datetime = lambda: datetime(2026, 10, 22, 18, 1)
spec = importlib.util.spec_from_file_location("attendance_candidate", Path(__file__).parents[1] / "dingtalk_attendance.py")
backend = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils}):
    spec.loader.exec_module(backend)


def shift(name="morning", end="12:00:00", window=15, watermark="2026-10-22 00:00:00"):
    return types.SimpleNamespace(
        name=name, start_time="08:00:00", end_time=end,
        allow_check_out_after_shift_end_time=window, last_sync_of_checkin=watermark,
        process_attendance_after="2026-10-12", process_auto_attendance=MagicMock(),
        enable_auto_attendance=1, auto_update_last_sync=0, absent_buffer_days=1,
        begin_check_in_before_shift_start_time=60,
    )


def complete(day="2026-10-22", times=None):
    times = times or []
    return dict(
        date=day, configured=True, full_employee_scope=True, dry_run=False,
        employee_count=54, mapped=len(times), fetched=len(times), created=0,
        skipped=len(times), errors=[], unmapped=[], skipped_no_actual_time=0,
        items=[dict(time=stamp, log_type="IN") for stamp in times],
    )


class BusinessBoundaries(unittest.TestCase):
    def setUp(self):
        frappe.db = MagicMock()
        frappe.db.exists.return_value = False
        frappe.db.get_value.return_value = None
        frappe.get_all = MagicMock(return_value=[])
        frappe.get_doc = MagicMock()
        frappe.log_error = MagicMock()
        frappe.get_traceback = lambda: "controlled test failure"
        frappe.local = types.SimpleNamespace(site="test.invalid")
        frappe.conf = {}
        frappe.cache = MagicMock()
        frappe.cache.get_value.return_value = None
        self.clock = patch.object(backend, "now_datetime", return_value=datetime(2026, 10, 22, 18, 1))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def settle(self, shifts, result=None):
        by_name = {s.name: s for s in shifts}
        frappe.get_doc.side_effect = lambda kind, name: by_name[name]
        with patch.object(backend, "_validate_attendance_mapping"), patch.object(backend, "_app_configured", return_value=False), patch.object(backend, "_sync", return_value=result if result is not None else complete()) as importer:
            response = backend._sync_attendance_day("2026-10-22", shifts)
        return response, importer

    def test_cli_explicit_path_takes_priority(self):
        frappe.conf["dingtalk_cli_path"] = "/srv/tools/dws"
        with patch.object(backend.shutil, "which") as which:
            self.assertEqual(backend._dingtalk_cli_path(), "/srv/tools/dws")
        which.assert_not_called()

    def test_cli_discovery_uses_service_user_home_without_private_paths(self):
        with patch.dict(backend.os.environ, {}, clear=True), \
                patch.object(backend.os.path, "expanduser", return_value="/srv/service/.local/bin/dws"), \
                patch.object(backend.shutil, "which", side_effect=[None, "/srv/service/.local/bin/dws"]) as which:
            self.assertEqual(backend._dingtalk_cli_path(), "/srv/service/.local/bin/dws")
        self.assertEqual([call.args[0] for call in which.call_args_list], ["dws", "/srv/service/.local/bin/dws"])

    def test_before_18_never_imports_or_advances_same_day(self):
        backend.now_datetime.return_value = datetime(2026, 10, 22, 17, 59)
        with patch.object(backend, "_sync") as importer, self.assertRaises(ValidationError):
            backend._sync_attendance_day("2026-10-22", [shift()])
        importer.assert_not_called()
        frappe.db.set_value.assert_not_called()

    def test_closed_morning_settles_but_late_shift_stays_open(self):
        morning, late = shift(), shift("late", "18:00:00", 30)
        result, _ = self.settle([morning, late])
        self.assertEqual(result["attendance_shifts_processed"], 1)
        self.assertEqual(result["attendance_deferred_shifts"], ["late"])
        self.assertIsNone(result["attendance_complete_through"])
        self.assertEqual(late.last_sync_of_checkin, "2026-10-22 00:00:00")
        late.process_auto_attendance.assert_not_called()
        morning.process_auto_attendance.assert_called_once()
        self.assertEqual(morning.last_sync_of_checkin, datetime(2026, 10, 23))

    def test_exact_window_end_does_not_close(self):
        backend.now_datetime.return_value = datetime(2026, 10, 22, 18, 30)
        late = shift("late", "18:00:00", 30)
        result, _ = self.settle([late])
        self.assertEqual(result["attendance_shifts_processed"], 0)
        frappe.db.set_value.assert_not_called()

    def test_after_late_window_next_pass_closes(self):
        backend.now_datetime.return_value = datetime(2026, 10, 22, 18, 30, 1)
        late = shift("late", "18:00:00", 30)
        result, _ = self.settle([late])
        self.assertEqual(result["attendance_complete_through"], "2026-10-22")
        late.process_auto_attendance.assert_called_once()

    def test_incomplete_full_import_never_releases_any_shift(self):
        result = complete()
        result["errors"] = [{"error": "source unavailable"}]
        with self.assertRaises(ValidationError):
            self.settle([shift()], result)
        frappe.db.set_value.assert_not_called()

    def test_employee_only_import_never_releases_shift(self):
        result = complete()
        result["full_employee_scope"] = False
        with self.assertRaises(ValidationError):
            self.settle([shift()], result)
        frappe.db.set_value.assert_not_called()

    def test_missing_old_day_prevents_date_jump(self):
        with self.assertRaises(ValidationError):
            self.settle([shift(watermark="2026-10-21 00:00:00")])
        frappe.db.set_value.assert_not_called()

    def test_app_api_without_strict_completeness_cannot_release(self):
        with patch.object(backend, "_app_configured", return_value=True), self.assertRaises(ValidationError):
            backend._sync_attendance_day("2026-10-22", [shift()])
        frappe.db.set_value.assert_not_called()

    def test_native_clock_advancement_must_stay_disabled(self):
        bad = shift()
        bad.auto_update_last_sync = 1
        frappe.get_doc.return_value = bad
        with patch.object(backend, "_attendance_shift_names", return_value=[bad.name]), self.assertRaises(ValidationError):
            backend._attendance_shifts()

    def test_reused_import_from_another_date_cannot_release(self):
        with patch.object(backend, "_validate_attendance_mapping"), patch.object(backend, "_app_configured", return_value=False), self.assertRaises(ValidationError):
            backend._sync_attendance_day("2026-10-22", [shift()], imported_result=complete("2026-10-21"))
        frappe.db.set_value.assert_not_called()

    def test_retry_never_rewinds_an_already_advanced_watermark(self):
        current = shift(watermark="2026-10-24 00:00:00")
        self.settle([current])
        self.assertEqual(current.last_sync_of_checkin, "2026-10-24 00:00:00")
        frappe.db.set_value.assert_not_called()

    def test_submitted_same_shift_marks_new_log_for_review(self):
        frappe.get_all.return_value = [{"name": "ATT-1", "shift": "morning"}]
        doc = types.SimpleNamespace(employee="EMP-1", name="CHK-1", shift="morning", db_set=MagicMock())
        self.assertEqual(backend._late_checkin_review(doc, date(2026, 10, 22)), "submitted_attendance")
        doc.db_set.assert_called_once_with("skip_auto_attendance", 1, update_modified=False)
        self.assertEqual(frappe.get_all.call_args.kwargs["filters"]["docstatus"], 1)
        frappe.db.set_value.assert_not_called()

    def test_submitted_morning_does_not_block_afternoon(self):
        frappe.get_all.return_value = [{"name": "ATT-1", "shift": "morning"}]
        doc = types.SimpleNamespace(employee="EMP-1", name="CHK-2", shift="afternoon", db_set=MagicMock())
        self.assertIsNone(backend._late_checkin_review(doc, date(2026, 10, 22)))
        doc.db_set.assert_not_called()

    def test_null_attendance_shift_is_conservatively_protected(self):
        frappe.get_all.return_value = [{"name": "ATT-1", "shift": None}]
        doc = types.SimpleNamespace(employee="EMP-1", name="CHK-2", shift="afternoon", db_set=MagicMock())
        self.assertEqual(backend._late_checkin_review(doc, date(2026, 10, 22)), "submitted_attendance")

    def test_released_day_protects_before_native_attendance_commit(self):
        frappe.db.get_value.return_value = "2026-10-23 00:00:00"
        doc = types.SimpleNamespace(employee="EMP-1", name="CHK-2", shift="afternoon", db_set=MagicMock())
        self.assertEqual(backend._late_checkin_review(doc, date(2026, 10, 22)), "released_shift_day")
        doc.db_set.assert_called_once()

    def stream(self, stamps, result=None):
        with patch.object(backend, "_attendance_shifts", return_value=[shift()]), patch.object(backend, "_employee_mappings", return_value=([{"userid": "ding-1", "employee": "EMP-1"}], "dingtalk_userid")), patch.object(backend, "_sync", return_value=result if result is not None else complete(times=["2026-10-22 08:00:00"])) as importer:
            response = backend.sync_stream_trigger("ding-1", "2026-10-22", check_times=stamps)
        return response, importer

    def test_stream_requires_every_expected_time_visible_not_only_latest(self):
        stamps = [int(datetime(2026, 10, 22, hour).timestamp() * 1000) for hour in (8, 17)]
        with self.assertRaises(ValidationError):
            self.stream(stamps, complete(times=["2026-10-22 17:00:00"]))
        frappe.db.set_value.assert_not_called()

    def test_stream_group_imports_once_and_never_advances_watermark(self):
        stamps = [int(datetime(2026, 10, 22, hour).timestamp() * 1000) for hour in (8, 17)]
        result, importer = self.stream(stamps, complete(times=["2026-10-22 08:00:00", "2026-10-22 17:00:00"]))
        self.assertTrue(result["ok"])
        importer.assert_called_once_with(day=date(2026, 10, 22), dry_run=False, employee="EMP-1", notify=False)
        frappe.db.set_value.assert_not_called()

    def test_stream_rejects_invalid_or_excessive_time_batches(self):
        for stamps in ([], [True], ["2026-10-22 08:00:00"], [1], [1792641600000] * 257):
            with self.subTest(stamps=str(stamps)[:35]), self.assertRaises(ValidationError):
                self.stream(stamps)

    def test_unknown_employee_remains_failure_and_logs_once(self):
        with patch.object(backend, "_attendance_shifts", return_value=[shift()]), patch.object(backend, "_employee_mappings", return_value=([], "dingtalk_userid")):
            with self.assertRaises(ValidationError):
                backend.sync_stream_trigger("new-unknown", "2026-10-22")
            frappe.cache.get_value.return_value = True
            with self.assertRaises(ValidationError):
                backend.sync_stream_trigger("new-unknown", "2026-10-22")
        self.assertEqual(frappe.log_error.call_count, 1)

    def test_periodic_busy_lock_skips_api_calls(self):
        frappe.cache.lock.return_value.acquire.return_value = False
        with patch.object(backend, "_configured", return_value=True), patch.object(backend, "_sync") as importer:
            self.assertEqual(backend.sync_dingtalk_attendance_catchup_job()["skipped"], "sync_busy")
        importer.assert_not_called()

    def test_periodic_reuses_recent_full_imports_under_shared_lock(self):
        frappe.cache.lock.return_value.acquire.return_value = True
        with patch.object(backend, "_configured", return_value=True), patch.object(backend, "_attendance_shifts", return_value=[shift()]), patch.object(backend, "_sync", side_effect=lambda day, **kwargs: complete(str(day))) as importer, patch.object(backend, "_sync_attendance_pending_days", return_value={"days": [], "pending_days": 0}) as settler:
            result = backend.sync_dingtalk_attendance_catchup_job()
        self.assertEqual(result["recent_dates"], ["2026-10-21", "2026-10-22"])
        self.assertEqual(importer.call_count, 2)
        self.assertEqual(set(settler.call_args.kwargs["imported_results"]), {"2026-10-21", "2026-10-22"})
        frappe.cache.lock.assert_called_once_with("dingtalk-attendance:test.invalid", timeout=3600, blocking_timeout=0)
        frappe.cache.lock.return_value.release.assert_called_once()

    def test_catchup_retries_native_after_watermark_already_committed(self):
        closed = shift(watermark="2026-10-23 00:00:00")
        with patch.object(backend, "_sync_attendance_day", return_value={"date": "2026-10-22"}) as settle:
            backend._sync_attendance_pending_days([closed])
        self.assertEqual(settle.call_args.args[0], date(2026, 10, 22))

    def test_failed_late_guard_rolls_back_new_unprotected_log(self):
        doc = types.SimpleNamespace(insert=MagicMock())
        frappe.get_doc.side_effect = None
        frappe.get_doc.return_value = doc
        record = dict(userId="ding-1", userCheckTime="2026-10-22 08:00:00", checkType="OnDuty")
        with patch.object(backend, "_employee_mappings", return_value=([{"userid": "ding-1", "employee": "EMP-1"}], "dingtalk_userid")), patch.object(backend, "_app_configured", return_value=False), patch.object(backend, "_fetch_records_dws", return_value=[record]), patch.object(backend, "_late_checkin_review", side_effect=RuntimeError("guard unavailable")):
            result = backend._sync("2026-10-22", dry_run=False, notify=False)
        self.assertEqual(result["created"], 0)
        self.assertEqual(len(result["errors"]), 1)
        frappe.db.rollback.assert_called_once_with(save_point="dingtalk_checkin_insert")


class ManagementPermissions(unittest.TestCase):
    def setUp(self):
        frappe.session = types.SimpleNamespace(user="operator@example.test")
        frappe.get_roles = MagicMock(return_value=[])
        frappe.conf = {}

    def test_ordinary_hr_and_ai_roles_cannot_read_mapping_or_start_import(self):
        for role in ("I-ONE AI Operator", "I-ONE Manager", "HR Manager", "HR User", "Employee"):
            with self.subTest(role=role):
                frappe.get_roles.return_value = [role]
                with patch.object(backend, "_employee_mappings") as mappings, patch.object(backend, "_sync") as importer:
                    with self.assertRaises(ValidationError):
                        backend.get_dingtalk_attendance_status()
                    with self.assertRaises(ValidationError):
                        backend.sync_dingtalk_attendance(dry_run=0)
                    mappings.assert_not_called()
                    importer.assert_not_called()

    def test_guest_is_rejected_before_roles_or_data_access(self):
        frappe.session.user = "Guest"
        with patch.object(backend, "_employee_mappings") as mappings, patch.object(backend, "_sync") as importer:
            for endpoint in (backend.get_dingtalk_attendance_status, backend.sync_dingtalk_attendance):
                with self.assertRaises(ValidationError):
                    endpoint()
            mappings.assert_not_called()
            importer.assert_not_called()
        frappe.get_roles.assert_not_called()

    def test_administrator_and_system_manager_can_manage_integration(self):
        for user, roles in (("Administrator", []), ("admin@example.test", ["System Manager"])):
            with self.subTest(user=user):
                frappe.session.user = user
                frappe.get_roles.return_value = roles
                with patch.object(backend, "_employee_mappings", return_value=([], "dingtalk_userid")), \
                        patch.object(backend, "_configured", return_value=False), \
                        patch.object(backend, "_app_configured", return_value=False), \
                        patch.object(backend, "_dws_configured", return_value=False), \
                        patch.object(backend, "_sync", return_value={"ok": True}) as importer:
                    self.assertEqual(backend.get_dingtalk_attendance_status()["mapped_employees"], [])
                    self.assertEqual(backend.sync_dingtalk_attendance(day="2026-10-22", dry_run="0"), {"ok": True})
                    importer.assert_called_once_with(day="2026-10-22", dry_run=False, employee=None)


if __name__ == "__main__":
    unittest.main(verbosity=2)

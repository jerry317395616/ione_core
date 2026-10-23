"""Isolated authorization and payload tests; no Frappe database writes."""
import importlib.util
import json
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class PermissionDenied(Exception):
    pass


class ValidationFailed(Exception):
    pass


class RealtimeTests(unittest.TestCase):
    def setUp(self):
        self.frappe = types.ModuleType("frappe")
        self.frappe.conf = {}
        self.frappe.session = types.SimpleNamespace(user="hr@example.test")
        self.frappe.local = types.SimpleNamespace(site="attendance.example.test")
        self.frappe.PermissionError = PermissionDenied
        self.frappe.ValidationError = ValidationFailed
        self.frappe.throw = Mock(side_effect=lambda msg, cls: (_ for _ in ()).throw(cls(msg)))
        self.frappe.whitelist = lambda: lambda func: func
        self.frappe.has_permission = Mock(return_value=True)
        self.frappe.get_roles = Mock(return_value=["HR User"])
        self.frappe.get_list = Mock(return_value=[])
        self.frappe.cache = types.SimpleNamespace(get_value=Mock(return_value={}))
        self.frappe.utils = types.SimpleNamespace(get_system_timezone=lambda: "Asia/Shanghai")
        self.modules = patch.dict(sys.modules, {"frappe": self.frappe})
        self.modules.start()
        spec = importlib.util.spec_from_file_location("tested_realtime", Path(__file__).parents[1] / "dingtalk_realtime.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self):
        self.modules.stop()

    def test_guest_denied_before_any_status_or_employee_read(self):
        self.frappe.session.user = "Guest"
        with patch.object(self.module, "_read_health") as read:
            for operation in (self.module.get_sync_status, lambda: self.module.get_checkin_context(["secret-record"])):
                with self.assertRaises(PermissionDenied):
                    operation()
            read.assert_not_called()
        self.frappe.get_list.assert_not_called()
        self.frappe.cache.get_value.assert_not_called()

    def test_unconfigured_site_does_not_read_machine_wide_health(self):
        with patch.object(Path, "open") as open_file:
            self.assertEqual(self.module._read_health(), {})
        open_file.assert_not_called()

    def test_health_reads_only_configured_path_and_rejects_oversized_data(self):
        with tempfile.TemporaryDirectory() as folder:
            health_path = Path(folder) / "health.json"
            self.frappe.conf["dingtalk_stream_health_path"] = str(health_path)
            health_path.write_text('{"pending": 2}', encoding="utf-8")
            self.assertEqual(self.module._read_health(), {"pending": 2})
            health_path.write_text("x" * (self.module.MAX_HEALTH_BYTES + 1), encoding="utf-8")
            self.assertEqual(self.module._read_health(), {})

    def test_employee_role_cannot_read_service_aggregates(self):
        self.frappe.get_roles.return_value = ["Employee"]
        with patch.object(self.module, "_read_health") as read:
            with self.assertRaises(PermissionDenied):
                self.module.get_sync_status()
            read.assert_not_called()

    def test_hr_without_checkin_permission_is_denied(self):
        self.frappe.has_permission.side_effect = PermissionDenied
        with self.assertRaises(PermissionDenied):
            self.module.get_sync_status()

    def test_status_redacts_paths_identifiers_and_exception_text(self):
        health = {"updated_at": time.time(), "connected": True, "pending": 3,
                  "last_import_success": time.time() - 5,
                  "import_control": {"valid": True, "paused": False, "error": "secret userid"},
                  "process_id": 123, "secret": "private/source/path"}
        self.frappe.cache.get_value.return_value = {
            "last_reconcile_error": "Employee secret-name failed credential secret",
            "last_reconcile_review_count": 2,
            "last_reconcile_success": "secret arbitrary text",
            "last_settlement_success": "2026-10-22 18:00:00",
        }
        with patch.object(self.module, "_read_health", return_value=health):
            result = self.module.get_sync_status()
        self.assertTrue(result["connected"])
        self.assertEqual(result["pending"], 3)
        self.assertTrue(result["reconcile_failed"])
        self.assertEqual(result["last_settlement_success"], "2026-10-22T10:00:00+00:00")
        self.assertIsNone(result["last_reconcile_success"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertNotIn("process_id", result)
        self.frappe.get_list.assert_not_called()

    def test_stale_or_future_heartbeat_never_reports_connected(self):
        for updated in (time.time() - 300, time.time() + 300, None):
            with patch.object(self.module, "_read_health", return_value={"updated_at": updated, "connected": True}):
                result = self.module.get_sync_status()
            self.assertFalse(result["connected"])
            self.assertEqual(result["state"], "unavailable")

    def test_context_only_returns_permission_filtered_checkins_and_employees(self):
        self.frappe.get_list.side_effect = [
            [types.SimpleNamespace(name="visible-checkin", employee="visible-employee", shift="上午班")],
            [types.SimpleNamespace(name="visible-employee", department="测试教学部")],
        ]
        result = self.module.get_checkin_context('["visible-checkin", "hidden-checkin"]')
        self.assertEqual(result, {"visible-checkin": {"department": "测试教学部", "shift": "上午班"}})
        self.assertEqual(self.frappe.get_list.call_args_list[0].args, ("Employee Checkin",))
        self.assertEqual(self.frappe.get_list.call_args_list[1].args, ("Employee",))
        self.assertEqual(self.frappe.get_list.call_args_list[1].kwargs["filters"],
                         {"name": ["in", ["visible-employee"]]})
        for call in self.frappe.get_list.call_args_list:
            self.assertNotIn("ignore_permissions", call.kwargs)

    def test_no_employee_read_does_not_expose_department(self):
        self.frappe.get_list.return_value = [types.SimpleNamespace(name="own-checkin", employee="own-employee", shift="上午班")]
        self.frappe.has_permission.side_effect = lambda doctype, **kwargs: doctype == "Employee Checkin"
        result = self.module.get_checkin_context(["own-checkin"])
        self.assertIsNone(result["own-checkin"]["department"])
        self.assertEqual(self.frappe.get_list.call_count, 1)

    def test_bounded_and_validated_context_input(self):
        for names in (["a"] * 101, "not json", {"a": "b"}, ["a" * 141], [2]):
            with self.assertRaises(ValidationFailed):
                self.module.get_checkin_context(names)
        self.frappe.get_list.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)

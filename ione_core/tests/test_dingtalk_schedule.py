"""Offline opt-in tests; never contact a site or a DingTalk data source."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.frappe = types.ModuleType("frappe")
        self.frappe.conf = {}
        self.backend = types.ModuleType("ione_core.dingtalk_attendance")
        self.backend.sync_dingtalk_attendance_job = Mock(return_value={"daily": True})
        self.backend.sync_dingtalk_attendance_catchup_job = Mock(return_value={"catchup": True})
        self.modules = patch.dict(sys.modules, {
            "frappe": self.frappe,
            "ione_core.dingtalk_attendance": self.backend,
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        spec = importlib.util.spec_from_file_location(
            "tested_dingtalk_schedule", Path(__file__).parents[1] / "dingtalk_schedule.py"
        )
        self.schedule = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.schedule)

    def test_unconfigured_site_never_calls_import_jobs(self):
        for method in (self.schedule.run_daily, self.schedule.run_catchup):
            self.assertEqual(method(), {"ok": True, "skipped": "scheduler_disabled"})
        self.backend.sync_dingtalk_attendance_job.assert_not_called()
        self.backend.sync_dingtalk_attendance_catchup_job.assert_not_called()

    def test_explicit_false_and_invalid_values_remain_disabled(self):
        for value in (False, 0, "0", "false", "off", "", None, [], {}, 2, 1.0):
            with self.subTest(value=value):
                self.frappe.conf["dingtalk_attendance_scheduler_enabled"] = value
                self.assertEqual(self.schedule.run_daily()["skipped"], "scheduler_disabled")
                self.assertEqual(self.schedule.run_catchup()["skipped"], "scheduler_disabled")
        self.backend.sync_dingtalk_attendance_job.assert_not_called()
        self.backend.sync_dingtalk_attendance_catchup_job.assert_not_called()

    def test_enabled_wrappers_preserve_job_results(self):
        for value in (True, 1, "1", "true", "yes", "on"):
            with self.subTest(value=value):
                self.frappe.conf["dingtalk_attendance_scheduler_enabled"] = value
                self.assertEqual(self.schedule.run_daily(), {"daily": True})
                self.assertEqual(self.schedule.run_catchup(), {"catchup": True})

    def test_enabled_but_missing_source_configuration_remains_a_failure(self):
        self.frappe.conf["dingtalk_attendance_scheduler_enabled"] = True
        for job, wrapper in (
            (self.backend.sync_dingtalk_attendance_job, self.schedule.run_daily),
            (self.backend.sync_dingtalk_attendance_catchup_job, self.schedule.run_catchup),
        ):
            job.side_effect = ValueError("DingTalk data source is not configured")
            with self.assertRaisesRegex(ValueError, "not configured"):
                wrapper()
            job.assert_called_once_with()

    def test_disabled_wrappers_do_not_import_the_optional_backend(self):
        with patch.dict(sys.modules, {"ione_core.dingtalk_attendance": None}):
            self.assertEqual(self.schedule.run_daily()["skipped"], "scheduler_disabled")
            self.assertEqual(self.schedule.run_catchup()["skipped"], "scheduler_disabled")


if __name__ == "__main__":
    unittest.main()

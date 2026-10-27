"""Offline cursor checks; native-controller compatibility is tested separately."""

import datetime as dt
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def load_boundary_module():
	frappe = types.ModuleType("frappe")
	utils = types.ModuleType("frappe.utils")
	utils.getdate = lambda value: value if isinstance(value, dt.date) else dt.date.fromisoformat(value)
	frappe.utils = utils
	path = Path(__file__).resolve().parents[1] / "hrms_compat" / "shift_schedule_assignment.py"
	spec = importlib.util.spec_from_file_location("hrms_boundary_offline_test", path)
	module = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils}):
		spec.loader.exec_module(module)
	return module


boundary = load_boundary_module()._processed_cycle_boundary


class ShiftCycleBoundaryTests(unittest.TestCase):
	def test_default_horizon_accounts_for_off_weeks(self):
		for weeks, expected in [(1, "2027-01-10"), (2, "2027-01-17"), (3, "2027-01-24"), (4, "2027-01-31")]:
			with self.subTest(weeks=weeks):
				self.assertEqual(boundary("2026-10-12", None, weeks), dt.date.fromisoformat(expected))

	def test_partial_first_week_stops_at_requested_end(self):
		for weeks in [1, 2, 3, 4]:
			self.assertEqual(boundary("2026-10-12", "2026-10-15", weeks), dt.date(2026, 10, 15))

	def test_completed_active_week_includes_skipped_weeks(self):
		for end in ["2026-10-18", "2026-10-19", "2026-10-25"]:
			with self.subTest(end=end):
				self.assertEqual(boundary("2026-10-12", end, 3), dt.date(2026, 11, 1))

	def test_next_active_week_preserves_partial_window(self):
		self.assertEqual(boundary("2026-10-12", "2026-11-03", 3), dt.date(2026, 11, 3))

	def test_reversed_window_does_not_mark_start_processed(self):
		self.assertEqual(boundary("2026-10-12", "2026-10-11", 3), dt.date(2026, 10, 11))

	def test_date_inputs_cross_leap_day(self):
		self.assertEqual(boundary(dt.date(2028, 2, 23), dt.date(2028, 2, 29), 2), dt.date(2028, 3, 7))


if __name__ == "__main__":
	unittest.main()

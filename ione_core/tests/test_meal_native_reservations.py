"""Check RR fail-safe input coverage without simulating ERPNext's algorithm."""

import copy
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class ValidationFailed(Exception):
	pass


class NativeReservationInputTests(unittest.TestCase):
	def setUp(self):
		self.frappe = types.ModuleType("frappe")
		self.frappe._ = lambda value: value
		self.frappe.throw = lambda message: (_ for _ in ()).throw(ValidationFailed(message))
		self.frappe.db = types.SimpleNamespace(sql=Mock(side_effect=self.query))
		self.snapshot = {
			"Production Plan": [{"name": "PLAN-A", "company": "School A", "docstatus": 1, "status": "Submitted"}],
			"Work Order": [{"name": "WORK-A", "company": "School A", "docstatus": 0}],
			"Material Request Plan Item": [{"name": "RAW-A", "parent": "PLAN-A", "required_bom_qty": "1.2"}],
			"Production Plan Sub Assembly Item": [{"name": "SUB-A", "parent": "PLAN-A", "required_qty": "2", "type_of_manufacturing": "In House"}],
			"Work Order Item": [{"name": "WORK-RAW-A", "parent": "WORK-A", "required_qty": "0.4", "source_warehouse": "RAW"}],
		}
		self.current = copy.deepcopy(self.snapshot)
		self.modules = patch.dict(sys.modules, {"frappe": self.frappe})
		self.modules.start()
		spec = importlib.util.spec_from_file_location("synthetic_native_reservations", Path(__file__).parents[1] / "meal_native_reservations.py")
		self.module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.module)

	def tearDown(self):
		self.modules.stop()

	def query(self, sql, values=None, **kwargs):
		if "information_schema.STATISTICS" in sql:
			return [{"index_name": "company"}]
		for table, rows in (self.current if "FOR UPDATE" in sql else self.snapshot).items():
			if f"FROM `tab{table}`" in sql:
				return copy.deepcopy(rows)
		raise AssertionError(sql)

	def test_same_inputs_lock_parent_company_ranges_and_all_native_children(self):
		proof = self.module.ensure_current_native_reservation_inputs("School A")
		self.assertTrue(proof["locked"])
		calls = self.frappe.db.sql.call_args_list
		locked = [call for call in calls if "FOR UPDATE" in call.args[0]]
		self.assertEqual(len(locked), 5)
		for table in ("Production Plan", "Work Order"):
			query = next(call for call in locked if f"FROM `tab{table}`" in call.args[0])
			self.assertIn("FORCE INDEX (`company`)", query.args[0])
			self.assertIn("WHERE company=%s", query.args[0])
			self.assertNotIn("docstatus=1", query.args[0])
		for table in self.module._CHILDREN:
			self.assertTrue(any(f"FROM `tab{table[0]}`" in call.args[0] for call in locked))
		self.assertFalse(any(call.args[0].lstrip().split()[0].upper() != "SELECT" for call in calls))

	def test_stale_parent_raw_subassembly_and_work_order_inputs_all_refuse(self):
		for table, field, value in (("Production Plan", "status", "Closed"),
			("Material Request Plan Item", "required_bom_qty", "3"),
			("Production Plan Sub Assembly Item", "required_qty", "4"),
			("Work Order", "docstatus", 1),
			("Work Order Item", "source_warehouse", "OTHER")):
			with self.subTest(table=table):
				self.current = copy.deepcopy(self.snapshot)
				self.current[table][0][field] = value
				with self.assertRaisesRegex(ValidationFailed, "刷新页面并重试"):
					self.module.ensure_current_native_reservation_inputs("School A")

	def test_new_company_parent_or_child_phantom_is_detected(self):
		for table in ("Production Plan", "Work Order", "Material Request Plan Item"):
			with self.subTest(table=table):
				self.current = copy.deepcopy(self.snapshot)
				self.current[table].append({"name": "NEW-COMMITTED-ROW"})
				with self.assertRaises(ValidationFailed):
					self.module.ensure_current_native_reservation_inputs("School A")

	def test_own_transaction_writes_visible_in_both_views_are_allowed(self):
		self.snapshot["Production Plan"][0]["status"] = "Closed"
		self.snapshot["Production Plan"].append({"name": "OWN-NEW-PLAN", "company": "School A", "docstatus": 0})
		self.current = copy.deepcopy(self.snapshot)
		self.assertTrue(self.module.ensure_current_native_reservation_inputs("School A")["locked"])

	def test_missing_company_index_blocks_instead_of_unbounded_locking(self):
		self.frappe.db.sql.return_value = []
		self.frappe.db.sql.side_effect = None
		with self.assertRaisesRegex(ValidationFailed, "索引"):
			self.module.ensure_current_native_reservation_inputs("School A")

	def test_empty_company_rejected_before_any_query(self):
		with self.assertRaises(ValidationFailed):
			self.module.ensure_current_native_reservation_inputs("")
		self.frappe.db.sql.assert_not_called()


if __name__ == "__main__":
	unittest.main()

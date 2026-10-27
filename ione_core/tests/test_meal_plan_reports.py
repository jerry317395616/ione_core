"""Draft-report visibility, unknown headcounts and per-child unit boundaries."""

import datetime as dt
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class Invalid(Exception):
	pass


class Denied(Exception):
	pass


class Record(dict):
	def __getattribute__(self, key):
		if dict.__contains__(self, key):
			return dict.__getitem__(self, key)
		return super().__getattribute__(key)

	def __getattr__(self, key):
		if key.startswith("__"):
			raise AttributeError(key)
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value

	def check_permission(self, permission):
		if self.get("denied"):
			raise Denied(permission)


class HistoricalMealReportTests(unittest.TestCase):
	def setUp(self):
		self.frappe = types.ModuleType("frappe")
		self.frappe._ = lambda text: text
		self.frappe._dict = Record
		self.frappe.session = Record(user="planner@example.test")
		self.frappe.AuthenticationError = Denied
		self.frappe.PermissionError = Denied
		self.frappe.throw = lambda text, error=Invalid: (_ for _ in ()).throw(error(text))
		self.frappe.get_list = Mock()
		self.frappe.get_doc = Mock()
		utils = types.ModuleType("frappe.utils")
		utils.getdate = lambda value: value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))
		self.modules = patch.dict(sys.modules, {"frappe": self.frappe, "frappe.utils": utils})
		self.modules.start()
		self.addCleanup(self.modules.stop)
		spec = importlib.util.spec_from_file_location("historical_meal_report", Path(__file__).parents[1] / "meal_plan_reports.py")
		self.module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.module)
		self.documents = {}
		self.plans = []
		for day in range(5):
			for slot_index, slot in enumerate(self.module.SLOTS):
				name = f"PLAN-{day}-{slot_index}"
				item, bom_name = f"DISH-{name}", f"BOM-{name}"
				plan = Record(name=name, docstatus=0, company="School A", custom_is_meal_plan=1,
					custom_meal_batch="HIST-A", custom_meal_week=None,
					custom_meal_date=str(dt.date(2026, 6, 22) + dt.timedelta(days=day)),
					custom_meal_type=slot, custom_meal_menu=f"Menu {name}",
					custom_meal_headcount=0, po_items=[Record(item_code=item, bom_no=bom_name, planned_qty=1)])
				bom = Record(name=bom_name, docstatus=1, is_active=1, company="School A", item=item,
					quantity=1, items=[Record(item_code="MILK", qty=125, uom="g", stock_uom="g", conversion_factor=1)])
				self.documents["Production Plan", name] = plan
				self.documents["BOM", bom_name] = bom
				self.documents["Item", item] = Record(item_name=f"Dish {name}", disabled=0, is_purchase_item=0)
				self.plans.append(plan)
		self.documents["Item", "MILK"] = Record(item_name="Milk")
		self.frappe.get_list.return_value = [plan.name for plan in self.plans]
		self.frappe.get_doc.side_effect = lambda doctype, name: self.documents[doctype, name]

	def context(self, **extra):
		return self.module.report_context({"plan_batch": "HIST-A", **extra})

	def test_complete_draft_batch_returns_ten_rows_and_unknown_totals(self):
		result = self.context()
		self.assertEqual(len(result["rows"]), 10)
		self.assertEqual(len(result["details"]), 25)
		self.assertEqual(str(result["dates"][0]), "2026-06-22")
		for row in result["details"]:
			self.assertIsNone(row["headcount"])
			self.assertIsNone(row["total_qty"])
			self.assertEqual(row["per_child_qty"], 125)
		self.frappe.get_list.assert_called_once_with("Production Plan",
			filters={"custom_meal_batch": "HIST-A", "custom_is_meal_plan": 1, "docstatus": ["<", 2]},
			pluck="name", order_by="custom_meal_date asc, name asc", limit_page_length=26)

	def test_reference_quantity_is_never_interpreted_as_headcount(self):
		self.plans[0].po_items[0].planned_qty = 100
		result = self.context()
		self.assertIsNone(result["rows"][0]["headcount_0"])
		self.assertIsNone(result["details"][0]["total_qty"])
		self.assertEqual(result["details"][0]["per_child_qty"], 125)

	def test_millilitres_stay_separate_and_have_readable_weekly_label(self):
		self.documents["Item", "SOUP"] = Record(item_name="绿豆银耳汤")
		bom = self.documents["BOM", self.plans[-2].po_items[0].bom_no]
		bom.items = [Record(item_code="SOUP", qty=150, uom="Millilitre")]
		result = self.context()
		row = next(row for row in result["rows"] if row["meal_type"] == "午点" and row["row_kind"] == "带量")
		self.assertEqual(row["day_4"], "绿豆银耳汤150ml")
		detail = next(row for row in result["details"] if row["ingredient_code"] == "SOUP")
		self.assertEqual(detail["uom"], "Millilitre")
		self.assertEqual(detail["per_child_qty"], 150)

	def test_duplicate_ingredients_sum_without_dropping_a_source_amount(self):
		bom = self.documents["BOM", self.plans[7].po_items[0].bom_no]
		bom.items = [Record(item_code="MILK", qty=15, uom="g"), Record(item_code="MILK", qty=23, uom="g")]
		result = self.context()
		row = next(row for row in result["rows"] if row["meal_type"] == "午餐" and row["row_kind"] == "带量")
		self.assertEqual(row["day_1"], "Milk38g")

	def test_guest_cannot_read_reports(self):
		self.frappe.session.user = "Guest"
		with self.assertRaises(Denied):
			self.context()
		self.frappe.get_list.assert_not_called()

	def test_no_batch_leaves_normal_week_report_path_unchanged(self):
		self.assertIsNone(self.module.report_context({"week_name": "WEEK-A"}))
		self.frappe.get_list.assert_not_called()

	def test_ambiguous_source_filters_are_rejected(self):
		with self.assertRaises(Invalid):
			self.context(week_name="WEEK-A")
		self.frappe.get_list.assert_not_called()

	def test_inaccessible_batch_is_not_enumerated_using_unrestricted_queries(self):
		self.frappe.get_list.return_value = []
		with self.assertRaises(Denied):
			self.context()
		self.frappe.get_doc.assert_not_called()

	def test_incomplete_or_oversized_visible_batch_is_rejected(self):
		for names in ([plan.name for plan in self.plans[:-1]], [plan.name for plan in self.plans] + ["EXTRA"]):
			self.frappe.get_list.return_value = names
			with self.subTest(length=len(names)), self.assertRaises(Invalid):
				self.context()

	def test_hidden_plan_permission_is_checked_even_after_list_lookup(self):
		self.plans[0].denied = True
		with self.assertRaises(Denied):
			self.context()

	def test_managed_or_cancelled_plan_cannot_bypass_week_snapshot_validation(self):
		self.plans[0].custom_meal_week = "WEEK-A"
		with self.assertRaises(Invalid):
			self.context()
		self.plans[0].custom_meal_week = None
		self.plans[0].docstatus = 2
		with self.assertRaises(Invalid):
			self.context()

	def test_unbound_submitted_plan_remains_readable_without_changing_its_status(self):
		self.plans[0].docstatus = 1
		result = self.context()
		self.assertEqual(len(result["rows"]), 10)
		self.assertIsNone(result["details"][0]["headcount"])
		self.assertEqual(self.plans[0].docstatus, 1)

	def test_companies_and_week_dates_cannot_be_mixed(self):
		self.plans[0].company = "School B"
		with self.assertRaises(Invalid):
			self.context()
		self.plans[0].company = "School A"
		with self.assertRaises(Invalid):
			self.context(week_start="2026-10-26")

	def test_duplicate_date_and_slot_are_not_hidden_by_dictionary_overwrite(self):
		self.plans[1].custom_meal_type = self.plans[0].custom_meal_type
		with self.assertRaises(Invalid):
			self.context()

	def test_bom_and_raw_item_permissions_remain_required(self):
		bom = self.documents["BOM", self.plans[0].po_items[0].bom_no]
		bom.denied = True
		with self.assertRaises(Denied):
			self.context()
		bom.denied = False
		self.documents["Item", "MILK"].denied = True
		with self.assertRaises(Denied):
			self.context()

	def test_different_bom_item_company_or_unsubmitted_bom_is_rejected(self):
		bom = self.documents["BOM", self.plans[0].po_items[0].bom_no]
		for key, value in (("item", "OTHER"), ("company", "School B"), ("docstatus", 0), ("quantity", 2)):
			prior = bom[key]
			bom[key] = value
			with self.subTest(key=key), self.assertRaises(Invalid):
				self.context()
			bom[key] = prior

	def test_invalid_recipe_quantities_do_not_become_zero(self):
		bom = self.documents["BOM", self.plans[0].po_items[0].bom_no]
		for value in (0, -1, "NaN", "Infinity", "missing"):
			bom.items[0].qty = value
			with self.subTest(value=value), self.assertRaises(Invalid):
				self.context()

	def test_single_form_does_not_enumerate_unrelated_plans(self):
		rows = self.module.plan_details(self.plans[0])
		self.assertEqual(len(rows), 1)
		self.frappe.get_list.assert_not_called()

	def test_date_only_link_resolves_visible_historical_batch(self):
		self.frappe.get_list.side_effect = [[], [Record(custom_meal_batch="HIST-A", custom_meal_week=None)] * 5]
		result = self.module.resolve_report_filters({"week_start": "2026-06-22"})
		self.assertEqual(result.plan_batch, "HIST-A")
		self.assertEqual(result.week_start, "2026-06-22")
		self.assertEqual(self.frappe.get_list.call_args_list[0].kwargs["limit_page_length"], 2)

	def test_date_only_formal_week_does_not_reopen_managed_plans_as_history(self):
		self.frappe.get_list.side_effect = [["WEEK-A"], [Record(custom_meal_batch="WEEK-A", custom_meal_week="WEEK-A")]]
		result = self.module.resolve_report_filters({"week_start": "2026-06-22"})
		self.assertEqual(result.week_name, "WEEK-A")
		self.assertFalse(result.get("plan_batch"))

	def test_date_with_no_accessible_source_is_rejected(self):
		self.frappe.get_list.side_effect = [[], [Record(custom_meal_batch="HIDDEN-WEEK", custom_meal_week="HIDDEN-WEEK")]]
		with self.assertRaises(Invalid):
			self.module.resolve_report_filters({"week_start": "2026-06-22"})

	def test_date_does_not_guess_between_multiple_weeks_or_batches(self):
		for weeks, batches in ((["WEEK-A", "WEEK-B"], []), ([], ["HIST-A", "HIST-B"]), (["WEEK-A"], ["HIST-A"])):
			self.frappe.get_list.side_effect = [weeks, [Record(custom_meal_batch=x, custom_meal_week=None) for x in batches]]
			with self.subTest(weeks=weeks, batches=batches), self.assertRaises(Invalid):
				self.module.resolve_report_filters({"week_start": "2026-06-22"})

	def test_explicit_source_does_not_trigger_date_discovery(self):
		for filters in ({"week_name": "WEEK-A", "week_start": "2026-06-22"}, {"plan_batch": "HIST-A"}, {}):
			self.assertEqual(self.module.resolve_report_filters(filters), filters)
		self.frappe.get_list.assert_not_called()

	def test_guest_or_non_monday_date_does_not_discover_schedules(self):
		with self.assertRaises(Invalid):
			self.module.resolve_report_filters({"week_start": "2026-06-23"})
		self.frappe.session.user = "Guest"
		with self.assertRaises(Denied):
			self.module.resolve_report_filters({"week_start": "2026-06-22"})
		self.frappe.get_list.assert_not_called()


if __name__ == "__main__":
	unittest.main()

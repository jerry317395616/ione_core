"""Offline accounting/allocation tests. No site, supplier or stock is modified."""

import importlib.util
import json
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch


class Record(dict):
	__getattr__ = dict.get
	__setattr__ = dict.__setitem__


class MealProcurementTests(unittest.TestCase):
	def setUp(self):
		self.frappe = types.ModuleType("frappe")
		self.frappe._ = lambda message: message
		self.frappe.whitelist = lambda *args, **kwargs: lambda fn: fn
		self.frappe.PermissionError = PermissionError
		self.frappe.throw = Mock(
			side_effect=lambda message, *args: (_ for _ in ()).throw(ValueError(message))
		)
		self.frappe.db = Mock()
		self.frappe.has_permission = Mock(return_value=True)
		self.frappe.get_roles = Mock(return_value=["System Manager"])
		self.frappe.get_precision = Mock(return_value=3)
		self.frappe.get_doc = Mock()
		self.frappe.get_all = Mock(return_value=[])
		self.frappe.new_doc = Mock()
		self.modules = patch.dict(sys.modules, {"frappe": self.frappe})
		self.modules.start()
		self.addCleanup(self.modules.stop)
		spec = importlib.util.spec_from_file_location(
			"tested_meal_procurement", Path(__file__).parents[1] / "meal_procurement.py"
		)
		self.module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.module)
		self.today = patch.object(self.module, "_today", return_value=date(2026, 10, 23))
		self.today.start()
		self.addCleanup(self.today.stop)
		self.week = Record(
			name="MEAL-WEEK-1",
			company="园",
			week_start="2026-10-26",
			week_end="2026-10-30",
			stock_reviewed=1,
			material_request=None,
			docstatus=1,
		)
		self.week.check_permission = Mock()
		self.week.reload = Mock()
		self.week.db_set = Mock()

	def item(self, code="rice", **kwargs):
		values = dict(
			name=code,
			item_name=code,
			custom_meal_procurement_policy="采购",
			stock_uom="g",
			purchase_uom=None,
			uoms=[],
			disabled=0,
			is_purchase_item=1,
			has_batch_no=0,
			min_order_qty=0,
		)
		values.update(kwargs)
		return Record(values)

	def demand(self, qty, day="2026-10-26", code="rice", pp="PP-1"):
		return {
			"meal_date": day,
			"meal_type": "午餐",
			"production_plan": pp,
			"headcount": "257",
			"native": {
				"item_code": code,
				"warehouse": "Stores",
				"uom": "g",
				"required_bom_qty": qty,
				"quantity": qty,
				"from_bom": "BOM-1",
				"main_item_code": "dish",
			},
		}

	def context(self, items=None, stock=0, orders=None, requests=None):
		return {
			"items": items or {"rice": self.item()},
			"bins": {("rice", "Stores"): Record(actual_qty=stock)},
			"purchase_orders": orders or [],
			"requests": requests or [],
			"prices": [],
			"whole_uoms": {},
		}

	def allocate(self, demands, **kwargs):
		rows, warnings, blockers = self.module._allocate(self.week, demands, self.context(**kwargs))
		return [row["public"] for row in rows], warnings, blockers

	def test_stock_is_allocated_once_across_the_week(self):
		rows, _, blockers = self.allocate(
			[self.demand("80"), self.demand("80", "2026-10-27", pp="PP-2")], stock="100"
		)
		self.assertEqual([row["allocated_stock_qty"] for row in rows], ["80", "20"])
		self.assertEqual([row["purchase_qty"] for row in rows], ["0", "60"])
		self.assertEqual(blockers, [])

	def test_reserved_stock_is_not_available(self):
		context = self.context(stock="100")
		context["bins"][("rice", "Stores")].update(reserved_qty="20", reserved_qty_for_production="10")
		rows, _, _ = self.module._allocate(self.week, [self.demand("100")], context)
		self.assertEqual(rows[0]["public"]["purchase_qty"], "30")

	def test_own_native_pp_submission_does_not_change_the_frozen_allocation(self):
		context = self.context(stock="100")
		before, _, _ = self.module._allocate(self.week, [self.demand("80")], context)
		context["bins"][("rice", "Stores")]["reserved_qty_for_production_plan"] = "80"
		context["own_plan_reservations"] = {("rice", "Stores"): self.module._decimal("80")}
		after, _, _ = self.module._allocate(self.week, [self.demand("80")], context)
		self.assertEqual(before[0]["public"], after[0]["public"])

	def test_own_reservation_correction_keeps_other_plans_stock_reserved(self):
		context = self.context(stock="100")
		context["bins"][("rice", "Stores")]["reserved_qty_for_production_plan"] = "130"
		context["own_plan_reservations"] = {("rice", "Stores"): self.module._decimal("100")}
		rows, _, _ = self.module._allocate(self.week, [self.demand("100")], context)
		self.assertEqual(rows[0]["public"]["allocated_stock_qty"], "70")
		self.assertEqual(rows[0]["public"]["purchase_qty"], "30")

	def test_incoming_order_only_covers_meals_after_its_due_date(self):
		order = Record(
			name="PO-ITEM",
			item_code="rice",
			warehouse="Stores",
			schedule_date="2026-10-28",
			qty="60",
			received_qty="10",
			conversion_factor="1",
		)
		rows, _, _ = self.allocate(
			[self.demand("50"), self.demand("80", "2026-10-29", pp="PP-2")], orders=[order]
		)
		self.assertEqual([row["expected_receipt_qty"] for row in rows], ["0", "50"])
		self.assertEqual([row["purchase_qty"] for row in rows], ["50", "30"])

	def test_overdue_orders_and_requests_do_not_masquerade_as_arrivals(self):
		order = Record(
			name="OLD-PO",
			item_code="rice",
			warehouse="Stores",
			schedule_date="2026-09-10",
			qty="6000",
			received_qty=0,
			conversion_factor=1,
		)
		request = Record(
			name="OLD-MR-ITEM",
			material_request="OLD-MR",
			item_code="rice",
			warehouse="Stores",
			schedule_date="2026-09-21",
			stock_qty="1000",
			ordered_qty=0,
			received_qty=0,
		)
		rows, warnings, _ = self.allocate([self.demand("50")], orders=[order], requests=[request])
		self.assertEqual(rows[0]["purchase_qty"], "50")
		self.assertTrue(any("Overdue" in warning for warning in warnings))

	def test_partially_ordered_request_is_not_double_counted_with_its_order(self):
		order = Record(
			name="PO-ITEM",
			item_code="rice",
			warehouse="Stores",
			schedule_date="2026-10-26",
			qty="60",
			received_qty=0,
			conversion_factor=1,
		)
		request = Record(
			name="MR-ITEM",
			material_request="OTHER-MR",
			item_code="rice",
			warehouse="Stores",
			schedule_date="2026-10-26",
			stock_qty="100",
			ordered_qty="60",
			received_qty="20",
		)
		rows, _, _ = self.allocate([self.demand("120")], orders=[order], requests=[request])
		self.assertEqual(rows[0]["expected_receipt_qty"], "60")
		self.assertEqual(rows[0]["already_requested_qty"], "40")
		self.assertEqual(rows[0]["purchase_qty"], "20")

	def test_decimal_rounding_and_pack_surplus_are_not_lost_or_bought_twice(self):
		item = self.item(purchase_uom="kg", uoms=[Record(uom="kg", conversion_factor="1000")])
		rows, _, _ = self.allocate(
			[self.demand("0.1"), self.demand("0.2", "2026-10-27", pp="PP-2")], items={"rice": item}
		)
		self.assertEqual(rows[0]["purchase_qty"], "0.001")
		self.assertEqual(rows[0]["purchase_stock_qty"], "1")
		self.assertEqual(rows[1]["purchase_qty"], "0")
		self.assertEqual(rows[1]["planned_surplus_used_qty"], "0.2")

	def test_an_unverified_volume_mass_conversion_is_blocked(self):
		item = self.item(purchase_uom="ml", uoms=[])
		rows, _, blockers = self.allocate([self.demand("50")], items={"rice": item})
		self.assertEqual(rows[0]["status"], "needs_conversion")
		self.assertEqual(rows[0]["purchase_qty"], "0")
		self.assertTrue(blockers)

	def test_kitchen_water_is_excluded_by_item_policy_not_item_name(self):
		item = self.item(
			code="ANY-CODE", item_name="Water", custom_meal_procurement_policy="厨房用水", is_purchase_item=0
		)
		rows, _, blockers = self.allocate([self.demand("50", code="ANY-CODE")], items={"ANY-CODE": item})
		self.assertEqual(rows[0]["status"], "kitchen_water")
		self.assertEqual(rows[0]["required_qty"], "50")
		self.assertEqual(rows[0]["purchase_qty"], "0")
		self.assertEqual(blockers, [])

	def test_unknown_procurement_policy_requires_a_decision(self):
		item = self.item(custom_meal_procurement_policy=None)
		rows, _, blockers = self.allocate([self.demand("50")], items={"rice": item})
		self.assertEqual(rows[0]["status"], "needs_policy")
		self.assertTrue(blockers)

	def test_missing_prices_do_not_block_a_quantity_request(self):
		rows, warnings, blockers = self.allocate([self.demand("50")])
		self.assertEqual(rows[0]["price_status"], "unquoted")
		self.assertEqual(rows[0]["purchase_qty"], "50")
		self.assertEqual(blockers, [])
		self.assertTrue(any("quotations" in warning for warning in warnings))

	def test_another_submitted_week_is_not_treated_as_consumed_just_because_its_dates_passed(self):
		self.frappe.get_all.return_value = [
			Record(
				name="PREVIOUS-WEEK",
				procurement_snapshot=json.dumps({"rows": [{"allocated_stock_qty": "100"}]}),
			)
		]
		self.assertEqual(self.module._other_stock_commitments(self.week), ["PREVIOUS-WEEK"])
		filters = self.frappe.get_all.call_args.kwargs["filters"]
		self.assertEqual(filters["docstatus"], 1)
		self.assertEqual(filters["name"], ["!=", self.week.name])

	def test_nonfinite_quantities_are_rejected(self):
		for value in ("NaN", "Infinity", "-Infinity"):
			with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite"):
				self.module._decimal(value)

	def test_authorized_repeated_create_returns_same_request_under_lock(self):
		self.week.material_request = "MR-ALREADY-CREATED"
		self.week.meals = [Record(production_plan="PP-1")]
		plan = Record(mr_items=[Record(name="SOURCE-1", item_code="rice")], check_permission=Mock())
		request = Record(
			name=self.week.material_request,
			docstatus=0,
			check_permission=Mock(),
			company="园",
			material_request_type="Purchase",
			items=[Record(production_plan="PP-1", material_request_plan_item="SOURCE-1", item_code="rice")],
		)
		self.frappe.get_doc.side_effect = [self.week, plan, request]
		result = self.module.create_material_request(self.week.name)
		self.assertEqual(result, {"material_request": request.name, "name": request.name, "created": False})
		self.frappe.new_doc.assert_not_called()
		self.assertIn("FOR UPDATE", self.frappe.db.sql.call_args.args[0])

	def test_read_only_week_purchase_manager_can_use_the_controlled_purchase_action(self):
		self.frappe.get_roles.return_value = ["Purchase Manager"]
		self.week.check_permission.side_effect = lambda access: (
			(_ for _ in ()).throw(AssertionError("week write must not be needed"))
			if access != "read"
			else None
		)
		plan = Record(check_permission=Mock())
		self.module._check_create_permission(self.week, [plan])
		plan.check_permission.assert_called_once_with("write")

	def test_a_forged_link_to_another_weeks_request_is_rejected(self):
		plan = Record(mr_items=[Record(name="SOURCE-1", item_code="rice")])
		other_request = Record(
			company="园",
			material_request_type="Purchase",
			items=[
				Record(
					production_plan="OTHER-PP", material_request_plan_item="OTHER-SOURCE", item_code="rice"
				)
			],
		)
		with self.assertRaisesRegex(ValueError, "does not belong"):
			self.module._verify_existing_request(self.week, other_request, {"PP-1": plan})

	def test_purchase_permission_is_required_even_for_retry(self):
		self.frappe.get_doc.return_value = self.week
		self.frappe.has_permission.return_value = False
		with self.assertRaisesRegex(ValueError, "permission"):
			self.module.create_material_request(self.week.name)
		self.frappe.new_doc.assert_not_called()

	def test_frozen_basis_change_prevents_request_creation(self):
		self.frappe.get_doc.return_value = self.week
		self.week.procurement_snapshot = json.dumps({"basis_hash": "old"})
		with patch.object(
			self.module, "_compute", return_value=({}, [], {"basis_hash": "new"}, {"blockers": []})
		):
			with self.assertRaisesRegex(ValueError, "changed after review"):
				self.module.create_material_request(self.week.name)
		self.frappe.new_doc.assert_not_called()

	def test_native_source_rows_cannot_be_silently_changed_after_submission(self):
		demand = self.demand("50")
		public = {
			"production_plan": "PP-1",
			"purchase_uom": "g",
			"purchase_qty": "40",
			"required_qty": "50",
			"status": "purchase",
		}
		plan = Record(
			name="PP-1",
			docstatus=1,
			mr_items=[Record(**demand["native"], name="NATIVE-ROW", requested_qty=0)],
		)
		with self.assertRaisesRegex(ValueError, "Frozen Production Plan"):
			self.module._find_source_rows({"PP-1": plan}, [{"native": demand["native"], "public": public}])

	def test_create_preserves_native_links_and_only_inserts_a_draft(self):
		demand = self.demand("50")
		public = {
			"production_plan": "PP-1",
			"purchase_uom": "g",
			"stock_uom": "g",
			"conversion_factor": "1",
			"purchase_qty": "50",
			"required_qty": "50",
			"status": "purchase",
			"item_code": "rice",
			"warehouse": "Stores",
			"meal_date": "2026-10-26",
		}
		plan = Record(
			name="PP-1",
			docstatus=1,
			mr_items=[Record(**demand["native"], name="NATIVE-ROW", requested_qty=0)],
			check_permission=Mock(),
		)
		self.week.procurement_snapshot = json.dumps({"basis_hash": "frozen"})
		self.frappe.get_doc.return_value = self.week
		request = Mock(name="request")
		request.name = "MR-NEW"
		self.frappe.new_doc.return_value = request
		computed = (
			{"PP-1": plan},
			[{"native": demand["native"], "public": public}],
			{"basis_hash": "frozen"},
			{"blockers": []},
		)
		with patch.object(self.module, "_compute", return_value=computed):
			result = self.module.create_material_request(self.week.name)
		self.assertEqual(result["material_request"], "MR-NEW")
		item = request.append.call_args.args[1]
		self.assertEqual(item["production_plan"], "PP-1")
		self.assertEqual(item["material_request_plan_item"], "NATIVE-ROW")
		self.assertIsInstance(item["qty"], float)
		self.assertIsInstance(item["conversion_factor"], float)
		self.assertEqual(item["qty"] * item["conversion_factor"], 50.0)
		request.insert.assert_called_once_with()
		request.submit.assert_not_called()
		self.frappe.db.commit.assert_not_called()
		self.week.db_set.assert_called_once_with(
			{"material_request": "MR-NEW", "status": "采购申请已生成"}, update_modified=False
		)


if __name__ == "__main__":
	unittest.main()

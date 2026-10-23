"""Physical ownership accounting tests; native PR/SE/SLE integration runs separately."""

import importlib.util
import json
import sys
import types
import unittest
from contextvars import ContextVar
from pathlib import Path
from unittest.mock import Mock, patch


class Row(dict):
	__getattr__ = dict.get
	__setattr__ = dict.__setitem__


class Doc:
	def __init__(self, **values):
		self.__dict__.update(values)
		self.check_permission = Mock()
		self.get_doc_before_save = Mock(return_value=None)

	def get(self, key, default=None):
		return self.__dict__.get(key, default)


class MealStockClaimTests(unittest.TestCase):
	def setUp(self):
		self.frappe = types.ModuleType("frappe")
		self.frappe._ = lambda message: message
		self.frappe._dict = Row
		self.frappe.whitelist = lambda *a, **kw: lambda function: function
		self.frappe.throw = lambda message, *a: (_ for _ in ()).throw(ValueError(message))
		self.frappe.db = Mock()
		self.docs, self.receipts, self.entries, self.adjustments, self.sles = {}, [], [], [], {}
		self.bin = Row(
			item_code="rice", warehouse="Stores", actual_qty=80, reserved_qty_for_production_plan=200
		)
		self.modules = patch.dict(sys.modules, {"frappe": self.frappe})
		self.modules.start()
		self.addCleanup(self.modules.stop)
		folder = Path(__file__).parents[1]
		spec = importlib.util.spec_from_file_location(
			"ione_core.meal_procurement", folder / "meal_procurement.py"
		)
		self.procurement = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.procurement)
		adjustments = types.ModuleType("ione_core.meal_adjustments")
		adjustments._APPLYING = ContextVar("test_apply", default=None)
		adjustments.get_effective_meals = lambda week, **kwargs: week.meals
		self.kitchen = types.ModuleType("ione_core.meal_kitchen")
		self.kitchen._ledger = Mock()
		self.kitchen.verify_week_kitchen_reconciled = Mock(return_value={"reconciled": True})
		self.dependencies = patch.dict(
			sys.modules,
			{
				"ione_core.meal_procurement": self.procurement,
				"ione_core.meal_adjustments": adjustments,
				"ione_core.meal_kitchen": self.kitchen,
			},
		)
		self.dependencies.start()
		self.addCleanup(self.dependencies.stop)
		spec = importlib.util.spec_from_file_location("tested_claims", folder / "meal_stock_claims.py")
		self.module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.module)
		self.today = patch.object(self.module, "_today", return_value=self.procurement._date("2026-10-23"))
		self.today.start()
		self.addCleanup(self.today.stop)
		for name, start, allocated, version in (("A", "2026-10-26", 80, 1), ("B", "2026-11-02", 0, 2)):
			source = Doc(name="SRC-" + name, item_code="rice", warehouse="Stores", required_bom_qty=100)
			plan = Doc(
				name="PP-" + name,
				company="Garden",
				custom_meal_week=name,
				custom_meal_adjustment=None,
				docstatus=1,
				status="Open",
				mr_items=[source],
			)
			self.docs[("Production Plan", plan.name)] = plan
			row = {
				"production_plan": plan.name,
				"item_code": "rice",
				"warehouse": "Stores",
				"required_qty": "100",
				"allocated_stock_qty": str(allocated),
			}
			if version == 2:
				row["new_physical_claim_qty"] = "0"
			basis = {
				"version": version,
				"company": "Garden",
				"week_start": start,
				"week_end": str(self.procurement._date(start) + __import__("datetime").timedelta(days=4)),
				"rows": [row],
				"bom_sources": [],
			}
			week = Doc(
				name=name,
				company="Garden",
				week_start=start,
				week_end=basis["week_end"],
				raw_material_warehouse="Stores",
				kitchen_warehouse="Kitchen",
				docstatus=1,
				meals=[Doc(production_plan=plan.name, service_suspended=0)],
				procurement_snapshot=json.dumps(dict(basis, basis_hash=self.procurement._hash(basis))),
			)
			self.docs[("Meal Planning Week", name)] = week
			self.docs[("Material Request", "MR-" + name)] = Doc(
				name="MR-" + name,
				company="Garden",
				docstatus=1,
				material_request_type="Purchase",
				custom_meal_adjustment=None,
				items=[
					Doc(
						name="MRI-" + name,
						item_code="rice",
						warehouse="Stores",
						production_plan=plan.name,
						material_request_plan_item=source.name,
					)
				],
			)
			self.docs[("Purchase Order", "PO-" + name)] = Doc(
				name="PO-" + name,
				company="Garden",
				docstatus=1,
				custom_meal_week=name,
				items=[
					Doc(
						name="POI-" + name,
						item_code="rice",
						warehouse="Stores",
						material_request="MR-" + name,
						material_request_item="MRI-" + name,
					)
				],
			)
		self.frappe.get_doc = Mock(side_effect=lambda dt, name, **kw: self.docs[(dt, name)])
		self.frappe.db.sql.side_effect = self.sql

	def sql(self, query, args=None, **kwargs):
		if "tabCompany" in query:
			return [Row(name="Garden")]
		if "tabMeal Planning Week" in query:
			return [Row(name="A"), Row(name="B")]
		if "tabMeal Plan Adjustment" in query:
			return self.adjustments if args[0] == "A" else []
		if "tabWork Order" in query:
			return []
		if "tabPurchase Receipt" in query:
			return self.receipts
		if "tabStock Ledger Entry" in query:
			return self.sles.get(tuple(args[:3]), [])
		if "tabStock Entry" in query:
			return [Row(name=name) for name in self.entries]
		if "tabBin" in query:
			return [self.bin]
		self.fail("Unexpected SQL " + query)

	def context(self, name="B"):
		return self.module.build_claim_context(self.docs[("Meal Planning Week", name)], ["rice"], ["Stores"])

	def receipt(self, owner, quantity, suffix=""):
		name = "PR-" + owner + suffix
		row = Row(
			name=name,
			detail="PRI-" + owner + suffix,
			item_code="rice",
			warehouse="Stores",
			stock_qty=quantity,
			is_return=int(quantity < 0),
			purchase_order="PO-" + owner,
			purchase_order_item="POI-" + owner,
		)
		self.receipts.append(row)
		self.sles[("Purchase Receipt", row.name, row.detail)] = [
			Row(name="SLE-" + name, item_code="rice", warehouse="Stores", actual_qty=quantity)
		]
		self.bin.actual_qty += quantity

	def issue(self, quantity, free=0, suffix=""):
		name = "SE-A" + suffix
		daily = Doc(
			name="DAY-A",
			company="Garden",
			meal_week="A",
			source_warehouse="Stores",
			kitchen_warehouse="Kitchen",
		)
		self.docs[("Meal Kitchen Day", daily.name)] = daily
		entry = Doc(
			name=name,
			custom_meal_week="A",
			custom_meal_kitchen_day=daily.name,
			custom_meal_action="领用",
			items=[Doc(item_code="rice", s_warehouse="Stores", t_warehouse="Kitchen", transfer_qty=quantity)],
		)
		if free:
			proof = {
				"version": 1,
				"week": "A",
				"entry": name,
				"warehouse": "Stores",
				"items": [
					{
						"item_code": "rice",
						"qty": str(quantity),
						"own_taken": str(quantity - free),
						"free_taken": str(free),
					}
				],
			}
			entry.custom_meal_raw_claim_snapshot = dict(proof, proof_hash=self.module._hash(proof))
		self.docs[("Stock Entry", name)] = entry
		self.entries.append(name)
		self.bin.actual_qty -= quantity

	def test_advance_week_does_not_use_prior_week_opening_eighty(self):
		context = self.context()
		own, free, public = self.module.physical_pools(context, {("rice", "Stores"): self.bin})
		self.assertTrue(context["advance"])
		self.assertEqual(own.get(("rice", "Stores"), 0), 0)
		self.assertEqual(free[("rice", "Stores")], 0)
		self.assertEqual(public[0]["other_week_claim_qty"], "80")

	def test_an_independent_raw_warehouse_can_allocate_its_own_eighty(self):
		week = self.docs[("Meal Planning Week", "A")]
		week.raw_material_warehouse = "Other Stores"
		basis = json.loads(week.procurement_snapshot)
		basis["rows"][0]["warehouse"] = "Other Stores"
		basis["basis_hash"] = self.module._hash(
			{key: value for key, value in basis.items() if key != "basis_hash"}
		)
		week.procurement_snapshot = json.dumps(basis)
		self.docs[("Production Plan", "PP-A")].mr_items[0].warehouse = "Other Stores"
		self.bin.reserved_qty_for_production_plan = 100
		context = self.context()
		self.assertFalse(context["advance"])
		_, free, _ = self.module.physical_pools(context, {("rice", "Stores"): self.bin})
		self.assertEqual(free[("rice", "Stores")], 80)

	def test_b_arrival_is_not_available_to_a(self):
		self.receipt("B", 100)
		own, free, _ = self.module.physical_pools(self.context("A"), {("rice", "Stores"): self.bin})
		self.assertEqual(own[("rice", "Stores")], 80)
		self.assertEqual(free[("rice", "Stores")], 0)
		with self.assertRaisesRegex(ValueError, "不能领走"):
			self.module.assert_week_raw_stock_available(
				self.docs[("Meal Planning Week", "A")], {"rice": 81}, "SE-new"
			)

	def test_interleaved_arrivals_and_a_issue_preserve_b_hundred(self):
		self.receipt("B", 100)
		self.receipt("A", 20)
		self.issue(100)
		context = self.context()
		self.assertEqual(context["own"][("rice", "Stores")], 100)
		self.assertEqual(context["other"].get(("rice", "Stores"), 0), 0)
		self.assertEqual(self.bin.actual_qty, 100)
		self.kitchen._ledger.assert_called_with(
			self.docs[("Meal Kitchen Day", "DAY-A")], lock=False, verify_sle=True
		)

	def test_return_reduces_only_receiving_week_claim(self):
		self.receipt("B", 100)
		self.receipt("B", -10, "-return")
		context = self.context()
		self.assertEqual(context["own"][("rice", "Stores")], 90)
		self.assertEqual(context["other"][("rice", "Stores")], 80)

	def test_extra_issue_records_free_claim_once_then_moves_it_to_kitchen(self):
		self.receipt("B", 100)
		self.receipt("A", 20)
		self.issue(100)
		self.bin.actual_qty += 20
		proof = self.module.assert_week_raw_stock_available(
			self.docs[("Meal Planning Week", "A")], {"rice": 10}, "SE-extra"
		)
		self.assertEqual(proof["items"][0]["free_taken"], "10")
		self.issue(10, free=10, suffix="-extra")
		own, free, _ = self.module.physical_pools(self.context("A"), {("rice", "Stores"): self.bin})
		self.assertEqual(own.get(("rice", "Stores"), 0), 0)
		self.assertEqual(free[("rice", "Stores")], 10)

	def test_reused_opening_stock_does_not_become_a_new_claim(self):
		row = {
			"production_plan": "PP-A",
			"item_code": "rice",
			"warehouse": "Stores",
			"required_qty": "100",
			"allocated_stock_qty": "80",
			"allocated_owned_stock_qty": "80",
			"new_physical_claim_qty": "0",
		}
		self.assertEqual(self.module._opening([row], 2, {"PP-A"})[("rice", "Stores")], 0)

	def test_legacy_v1_eighty_becomes_opening_without_modifying_snapshot(self):
		before = self.docs[("Meal Planning Week", "A")].procurement_snapshot
		self.assertEqual(self.context("A")["own"][("rice", "Stores")], 80)
		self.assertEqual(self.docs[("Meal Planning Week", "A")].procurement_snapshot, before)

	def test_ordinary_pp_reservations_are_not_removed(self):
		self.bin.actual_qty = 130
		self.bin.reserved_qty_for_production_plan = 250
		_, free, _ = self.module.physical_pools(self.context("A"), {("rice", "Stores"): self.bin})
		self.assertEqual(free[("rice", "Stores")], 0)

	def test_claims_cannot_be_silently_clipped_to_insufficient_physical_stock(self):
		self.receipt("B", 100)
		self.bin.actual_qty = 100
		with self.assertRaisesRegex(ValueError, "超过账面可用库存"):
			self.module.physical_pools(self.context("A"), {("rice", "Stores"): self.bin})

	def test_missing_receipt_ledger_blocks_ownership(self):
		self.receipt("B", 100)
		self.sles.clear()
		with self.assertRaisesRegex(ValueError, "缺少匹配"):
			self.context()

	def test_wrong_receipt_ledger_quantity_blocks_ownership(self):
		self.receipt("B", 100)
		self.sles[("Purchase Receipt", "PR-B", "PRI-B")][0].actual_qty = 99
		with self.assertRaisesRegex(ValueError, "库存流水不一致"):
			self.context()

	def test_wrong_native_order_week_cannot_reassign_arrival(self):
		self.receipt("B", 100)
		self.docs[("Purchase Order", "PO-B")].custom_meal_week = "A"
		with self.assertRaisesRegex(ValueError, "归属链不一致"):
			self.context()

	def test_forged_frozen_allocation_is_not_trusted(self):
		week = self.docs[("Meal Planning Week", "A")]
		data = json.loads(week.procurement_snapshot)
		data["rows"][0]["allocated_stock_qty"] = "180"
		week.procurement_snapshot = json.dumps(data)
		with self.assertRaisesRegex(ValueError, "校验失败"):
			self.context()

	def test_unproved_extra_issue_fails_closed_with_negative_claim(self):
		self.issue(81)
		with self.assertRaisesRegex(ValueError, "负余额"):
			self.context()

	def test_lock_false_ownership_audit_has_no_locking_query(self):
		self.context()
		self.assertTrue(all("FOR UPDATE" not in call.args[0] for call in self.frappe.db.sql.call_args_list))

	def test_projected_own_return_preserves_prior_week_stock(self):
		self.receipt("B", 100)
		item = Row(
			item_code="rice",
			warehouse="Stores",
			stock_qty=-10,
			purchase_order="PO-B",
			purchase_order_item="POI-B",
		)
		doc = Doc(name="RETURN", company="Garden", posting_date="2026-10-23", items=[item])
		self.module.before_submit_purchase_receipt(doc)

	def test_return_cannot_borrow_another_week_when_own_claim_is_exhausted(self):
		self.receipt("B", 100)
		item = Row(
			item_code="rice",
			warehouse="Stores",
			stock_qty=-101,
			purchase_order="PO-B",
			purchase_order_item="POI-B",
		)
		doc = Doc(name="RETURN", company="Garden", posting_date="2026-10-23", items=[item])
		with self.assertRaisesRegex(ValueError, "本周剩余归属实物不足"):
			self.module.before_submit_purchase_receipt(doc)

	def test_unmapped_return_cannot_take_any_claimed_stock(self):
		self.receipt("B", 100)
		item = Row(item_code="rice", warehouse="Stores", stock_qty=-1)
		doc = Doc(name="RETURN", company="Garden", posting_date="2026-10-23", items=[item])
		with self.assertRaisesRegex(ValueError, "超过账面可用库存"):
			self.module.before_submit_purchase_receipt(doc)

	def test_ordinary_internal_receipt_cannot_move_another_weeks_claim_out(self):
		item = Row(item_code="rice", warehouse="Other", from_warehouse="Stores", stock_qty=1)
		doc = Doc(name="INTERNAL", company="Garden", posting_date="2026-10-23", items=[item])
		doc.get_source_warehouse_qty = Mock(return_value=1)
		with self.assertRaisesRegex(ValueError, "超过账面可用库存"):
			self.module.before_submit_purchase_receipt(doc)
		doc.get_source_warehouse_qty.assert_called_once_with(item, 1.0)

	def test_cancel_internal_receipt_cannot_remove_claimed_target_stock(self):
		item = Row(item_code="rice", warehouse="Stores", from_warehouse="Other", stock_qty=1)
		doc = Doc(name="INTERNAL", company="Garden", posting_date="2026-10-23", items=[item])
		doc.get_source_warehouse_qty = Mock(return_value=1)
		self.docs[("Purchase Receipt", doc.name)] = doc
		with self.assertRaisesRegex(ValueError, "超过账面可用库存"):
			self.module.before_cancel_purchase_receipt(doc)

	def test_internal_rejected_source_projection_uses_native_quantity(self):
		self.bin.actual_qty += 4
		item = Row(
			item_code="rice",
			warehouse="Other",
			from_warehouse="Stores",
			stock_qty=3,
			rejected_qty=2,
			rejected_warehouse="Rejected",
			conversion_factor=1,
		)
		doc = Doc(name="INTERNAL", company="Garden", posting_date="2026-10-23", items=[item])
		doc.get_source_warehouse_qty = Mock(return_value=5)
		with self.assertRaisesRegex(ValueError, "超过账面可用库存"):
			self.module.before_submit_purchase_receipt(doc)
		doc.get_source_warehouse_qty.assert_called_once_with(item, 3.0)

	def test_cancel_cannot_add_inventory_legs_or_change_serial_batch_source(self):
		fields = {
			"rejected_qty": 1,
			"rejected_warehouse": "Other",
			"from_warehouse": "Other",
			"serial_and_batch_bundle": "OTHER-BUNDLE",
			"rejected_serial_and_batch_bundle": "OTHER-REJECTED-BUNDLE",
			"serial_no": "OTHER-SERIAL",
			"batch_no": "OTHER-BATCH",
		}
		for field, value in fields.items():
			with self.subTest(field=field):
				stored = Doc(name="PR", company="Garden", items=[Row(item_code="rice", stock_qty=1)])
				incoming = Doc(name="PR", company="Garden", items=[Row(item_code="rice", stock_qty=1)])
				incoming.items[0][field] = value
				self.docs[("Purchase Receipt", "PR")] = stored
				with self.assertRaisesRegex(ValueError, "取消收货前不能改写"):
					self.module.before_cancel_purchase_receipt(incoming)

	def test_owned_internal_receipt_cannot_create_an_unprovable_multiwarehouse_claim(self):
		item = Row(
			item_code="rice",
			warehouse="Stores",
			from_warehouse="Other",
			stock_qty=1,
			purchase_order="PO-B",
			purchase_order_item="POI-B",
		)
		doc = Doc(name="INTERNAL", company="Garden", posting_date="2026-10-23", items=[item])
		doc.get_source_warehouse_qty = Mock(return_value=1)
		with self.assertRaisesRegex(ValueError, "内部调拨"):
			self.module.before_submit_purchase_receipt(doc)

	def test_cancel_cannot_change_any_ledger_relevant_receipt_header(self):
		fields = {
			"company": "Other",
			"supplier": "Other supplier",
			"currency": "USD",
			"conversion_rate": 2,
			"posting_date": "2026-10-22",
			"posting_time": "10:00:00",
			"set_posting_time": 1,
			"is_return": 1,
			"return_against": "OTHER",
			"owner": "other@example.test",
			"creation": "2026-10-01",
			"set_warehouse": "Other",
			"set_from_warehouse": "Other",
			"rejected_warehouse": "Other",
			"is_subcontracted": 1,
			"supplier_warehouse": "Other",
		}
		for field, value in fields.items():
			with self.subTest(field=field):
				stored = Doc(name="PR", company="Garden", items=[])
				incoming = Doc(name="PR", company="Garden", items=[])
				setattr(incoming, field, value)
				self.docs[("Purchase Receipt", "PR")] = stored
				with self.assertRaisesRegex(ValueError, "取消收货前不能改写"):
					self.module.before_cancel_purchase_receipt(incoming)


if __name__ == "__main__":
	unittest.main()

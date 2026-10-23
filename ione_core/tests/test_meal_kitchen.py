"""Synthetic kitchen quantities, provenance, approval and reconciliation tests."""

import copy
import importlib.util
import json
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch


class ValidationFailed(Exception):
	pass


class PermissionDenied(Exception):
	pass


class Row(dict):
	def __getattr__(self, key):
		if key.startswith("__"):
			raise AttributeError(key)
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value


class Doc:
	def __init__(self, **values):
		self.__dict__.update(values)
		self.previous = None
		self.flags = types.SimpleNamespace()
		self.check_permission = Mock()
		self.db_set = Mock()
		self.save = Mock(return_value=self)

	def __getattr__(self, key):
		if key.startswith("__"):
			raise AttributeError(key)
		return None

	def get(self, key, default=None):
		return self.__dict__.get(key, default)

	def set(self, key, value):
		setattr(self, key, value)

	def get_doc_before_save(self):
		return self.previous

	def as_dict(self):
		return {
			key: value
			for key, value in self.__dict__.items()
			if key not in ("previous", "flags", "check_permission", "db_set", "save")
		}


class KitchenTests(unittest.TestCase):
	def setUp(self):
		self.frappe = types.ModuleType("frappe")
		self.frappe._ = lambda value: value
		self.frappe._dict = Row
		self.frappe.session = types.SimpleNamespace(user="approver@example.test")
		self.frappe.get_roles = Mock(return_value=["Stock Manager"])
		self.frappe.has_permission = Mock(return_value=True)
		self.frappe.ValidationError = ValidationFailed
		self.frappe.PermissionError = PermissionDenied
		self.frappe.throw = lambda message, cls=ValidationFailed: (_ for _ in ()).throw(cls(message))
		self.frappe.whitelist = lambda **kwargs: lambda function: function
		self.frappe.get_doc = Mock()
		self.frappe.get_all = Mock(return_value=[])
		self.frappe.get_cached_doc = Mock()
		self.frappe.new_doc = Mock()
		self.frappe.as_json = lambda value: json.dumps(value, default=str)
		self.frappe.db = types.SimpleNamespace(
			sql=Mock(return_value=[]), exists=Mock(return_value=False), get_value=Mock()
		)
		self.current_date = "2026-10-30"
		self.utils = types.ModuleType("frappe.utils")
		self.utils.today = lambda: self.current_date
		self.utils.now_datetime = lambda: "2026-10-30 18:00:00"
		self.reservations = types.ModuleType("ione_core.meal_native_reservations")
		self.reservations.ensure_current_native_reservation_inputs = Mock()
		self.modules = patch.dict(
			sys.modules,
			{
				"frappe": self.frappe,
				"frappe.utils": self.utils,
				"ione_core.meal_native_reservations": self.reservations,
			},
		)
		self.modules.start()
		spec = importlib.util.spec_from_file_location(
			"synthetic_meal_kitchen", Path(__file__).parents[1] / "meal_kitchen.py"
		)
		self.module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.module)
		self.day = Doc(
			name="synthetic-day",
			meal_week="synthetic-week",
			meal_date="2026-10-26",
			company="School A",
			source_warehouse="Raw A",
			kitchen_warehouse="Kitchen A",
			docstatus=0,
			owner="clerk@example.test",
			items=[Row(item_code="rice", planned_qty=10, stock_uom="g")],
			meals=[
				Row(
					meal_type=slot, planned_headcount=20, actual_headcount=20, actual_confirmed=1, reason=None
				)
				for slot in self.module.SLOTS
			],
		)
		self.week = Doc(
			name="synthetic-week",
			company="School A",
			raw_material_warehouse="Raw A",
			kitchen_warehouse="Kitchen A",
			week_start="2026-10-26",
			week_end="2026-10-30",
			docstatus=1,
			kitchen_reconciled=0,
			kitchen_reconciled_at=None,
			kitchen_reconciliation_snapshot=None,
		)
		self.frappe.get_doc.return_value = self.week
		self.item = Row(
			name="rice",
			item_name="Synthetic ingredient",
			stock_uom="g",
			disabled=0,
			is_stock_item=1,
			custom_meal_procurement_policy="采购",
			has_batch_no=0,
			has_serial_no=0,
		)
		self.frappe.get_cached_doc.side_effect = lambda doctype, name: (
			Row(must_be_whole_number=0) if doctype == "UOM" else self.item
		)

	def tearDown(self):
		self.modules.stop()

	def entry(self, name, action, qty, ref=None, status=1, code="rice"):
		source = "Raw A" if action == "领用" else "Kitchen A"
		target = "Kitchen A" if action == "领用" else ("Raw A" if action == "退料" else None)
		purpose = "Material Transfer" if action in ("领用", "退料") else "Material Issue"
		return Row(
			name=name,
			company="School A",
			custom_meal_week="synthetic-week",
			custom_meal_kitchen_day="synthetic-day",
			custom_meal_action=action,
			posting_date="2026-10-26",
			docstatus=status,
			purpose=purpose,
			stock_entry_type=purpose,
			items=[
				Row(
					name=f"{name}-row",
					item_code=code,
					stock_uom="g",
					uom="g",
					qty=qty,
					transfer_qty=qty,
					conversion_factor=1,
					s_warehouse=source,
					t_warehouse=target,
					custom_meal_issue_detail=ref,
				)
			],
		)

	def closed_entries(self):
		return [
			self.entry("issue", "领用", 10),
			self.entry("consume", "耗用", 7, "issue-row"),
			self.entry("loss", "损耗", 1, "issue-row"),
			self.entry("return", "退料", 2, "issue-row"),
		]

	def facts(self, entries=None):
		return self.module._entry_facts(self.day, entries if entries is not None else self.closed_entries())

	def execution(self, facts=None):
		facts = facts or self.facts()
		facts["drafts"] = []
		facts["stock_ledger"] = [{"entry": "consume", "actual_qty": "-7"}] if facts["entries"] else []
		with (
			patch.object(self.module, "_week", return_value=self.week),
			patch.object(self.module, "_warehouses"),
			patch.object(self.module, "_verify_effective_source"),
			patch.object(self.module, "_ledger", return_value=facts),
		):
			return self.module._day_execution(self.day)

	def test_import_has_no_data_access(self):
		self.frappe.get_doc.assert_not_called()
		self.frappe.db.sql.assert_not_called()

	def test_real_transfer_consumption_loss_and_return_close_one_shared_balance(self):
		result = self.facts()["totals"]["rice"]
		self.assertEqual(
			result,
			{
				"issued_qty": Decimal(10),
				"consumed_qty": Decimal(7),
				"loss_qty": Decimal(1),
				"returned_qty": Decimal(2),
				"balance_qty": Decimal(0),
			},
		)

	def test_loss_cannot_be_deducted_again_after_consumption(self):
		entries = [
			self.entry("issue", "领用", 10),
			self.entry("consume", "耗用", 10, "issue-row"),
			self.entry("loss", "损耗", 1, "issue-row"),
		]
		with self.assertRaises(ValidationFailed):
			self.facts(entries)

	def test_return_and_consumption_combined_cannot_exceed_source(self):
		with self.assertRaises(ValidationFailed):
			self.facts(
				[
					self.entry("issue", "领用", 10),
					self.entry("consume", "耗用", 8, "issue-row"),
					self.entry("return", "退料", 3, "issue-row"),
				]
			)

	def test_return_cannot_reference_another_day_or_unsubmitted_issue(self):
		for entries in (
			[self.entry("return", "退料", 1, "other-row")],
			[self.entry("issue", "领用", 10, status=0), self.entry("return", "退料", 1, "issue-row")],
		):
			with self.assertRaises(ValidationFailed):
				self.facts(entries)

	def test_source_company_warehouse_item_and_units_are_validated(self):
		for target, field, value in (
			("header", "company", "Other company"),
			("header", "custom_meal_week", "Other week"),
			("row", "s_warehouse", "Other warehouse"),
			("row", "item_code", "unplanned"),
			("row", "uom", "kg"),
			("row", "conversion_factor", 1000),
		):
			entry = self.entry("issue", "领用", 10)
			(entry if target == "header" else entry["items"][0])[field] = value
			with self.assertRaises(ValidationFailed):
				self.facts([entry])

	def test_fifo_retains_exact_source_line_and_never_reserves_drafts(self):
		facts = self.facts(
			[
				self.entry("first", "领用", 5),
				self.entry("second", "领用", 5),
				self.entry("consume", "耗用", 2, "first-row"),
			]
		)
		self.assertEqual(
			self.module._allocate_sources(facts, {"rice": Decimal(7)}),
			[("rice", Decimal(3), "first-row"), ("rice", Decimal(4), "second-row")],
		)
		with self.assertRaises(ValidationFailed):
			self.module._allocate_sources(facts, {"rice": Decimal(9)})

	def test_native_stock_ledger_must_match_each_entry_detail_and_warehouse(self):
		facts = self.facts()
		rows = []
		for entry in facts["entries"]:
			for row in entry["items"]:
				rows.append(
					Row(
						name="synthetic-sle",
						voucher_no=entry.name,
						voucher_detail_no=row.name,
						warehouse=row.s_warehouse,
						item_code=row.item_code,
						actual_qty=-row.qty,
					)
				)
				if row.t_warehouse:
					rows.append(
						Row(
							name="synthetic-sle",
							voucher_no=entry.name,
							voucher_detail_no=row.name,
							warehouse=row.t_warehouse,
							item_code=row.item_code,
							actual_qty=row.qty,
						)
					)
		self.frappe.db.sql.return_value = rows
		self.assertEqual(len(self.module._verify_sle(self.day, facts, lock=True)), 6)
		self.assertIn("FOR UPDATE", self.frappe.db.sql.call_args.args[0])
		rows[0].actual_qty = -999
		with self.assertRaises(ValidationFailed):
			self.module._verify_sle(self.day, facts)
		self.frappe.db.sql.return_value = []
		with self.assertRaises(ValidationFailed):
			self.module._verify_sle(self.day, facts)

	def test_unconfirmed_default_zero_does_not_count_as_actual_stoppage(self):
		self.day.meals[0].actual_confirmed = 0
		self.day.meals[0].actual_headcount = 0
		with self.assertRaises(ValidationFailed):
			self.execution()

	def test_confirmed_zero_or_changed_headcount_requires_a_reason(self):
		for actual in (0, 19, 21):
			self.day.meals[0].actual_headcount = actual
			with self.assertRaises(ValidationFailed):
				self.execution()
			self.day.meals[0].reason = "Confirmed actual attendance difference"
			self.assertTrue(self.execution()["actual_meals"])
			self.day.meals[0].reason = None

	def test_no_stock_execution_cannot_prove_positive_meals(self):
		with self.assertRaises(ValidationFailed):
			self.execution(self.facts([]))

	def test_fully_confirmed_stoppage_with_reasons_can_close_without_fake_stock(self):
		for row in self.day.meals:
			row.actual_headcount = 0
			row.reason = "Confirmed full-day closure"
		proof = self.execution(self.facts([]))
		self.assertEqual(proof["stock_ledger"], [])
		self.assertTrue(all(row["actual_headcount"] == 0 for row in proof["actual_meals"]))

	def test_open_balance_and_pending_drafts_block_daily_close(self):
		with self.assertRaises(ValidationFailed):
			self.execution(self.facts([self.entry("issue", "领用", 10)]))
		facts = self.facts()
		facts.update(drafts=[self.entry("draft", "损耗", 1, "issue-row", status=0)], stock_ledger=[])
		with (
			patch.object(self.module, "_week", return_value=self.week),
			patch.object(self.module, "_warehouses"),
			patch.object(self.module, "_verify_effective_source"),
			patch.object(self.module, "_ledger", return_value=facts),
		):
			with self.assertRaises(ValidationFailed):
				self.module._day_execution(self.day)

	def test_future_daily_and_weekly_closure_is_forbidden(self):
		self.current_date = "2026-10-23"
		with self.assertRaises(ValidationFailed):
			self.module._day_execution(self.day)
		with self.assertRaises(ValidationFailed):
			self.module._week_execution(self.week)
		self.frappe.db.sql.assert_not_called()

	def test_clerk_role_can_prepare_but_cannot_submit_or_self_approve(self):
		self.frappe.get_roles.return_value = ["膳食业务经办员"]
		self.module._role()
		with self.assertRaises(PermissionDenied):
			self.module.before_submit_day(self.day)
		self.frappe.get_roles.return_value = ["System Manager"]
		self.frappe.session.user = self.day.owner
		with self.assertRaises(PermissionDenied):
			self.module.before_submit_day(self.day)

	def test_guest_is_denied_before_day_lookup(self):
		self.frappe.session.user = "Guest"
		with self.assertRaises(PermissionDenied):
			self.module.get_kitchen_day("synthetic-week", "2026-10-26")
		self.frappe.get_doc.assert_not_called()

	def test_invalid_quantity_or_injected_warehouse_cannot_create_a_draft(self):
		for items in (
			[{"item_code": "rice", "qty": "NaN"}],
			[{"item_code": "rice", "qty": -1}],
			[{"item_code": "rice", "qty": 1, "s_warehouse": "other"}],
			[{"item_code": "unknown", "qty": 1}],
		):
			with self.assertRaises(ValidationFailed):
				self.module._input_items(self.day, items)
		self.frappe.new_doc.assert_not_called()

	def test_candidate_submission_rechecks_current_balance_under_day_lock(self):
		entry = self.entry("candidate", "退料", 1, "issue-row")
		doc = Doc(**dict(entry))
		doc.owner = "clerk@example.test"
		doc.items = [Doc(**dict(row)) for row in entry["items"]]
		doc.previous = Doc(**doc.as_dict())
		facts = self.facts()
		facts["drafts"] = []
		with (
			patch.object(self.module, "_day", return_value=self.day) as load_day,
			patch.object(self.module, "_week", return_value=self.week),
			patch.object(self.module, "_warehouses"),
			patch.object(self.module, "_verify_effective_source"),
			patch.object(self.module, "_ledger", return_value=facts) as ledger,
		):
			with self.assertRaises(ValidationFailed):
				self.module.validate_stock_entry(doc)
			load_day.assert_called_once_with(self.day.name, lock=True)
			self.assertTrue(ledger.call_args.kwargs["lock"])

	def test_stock_entry_owner_cannot_submit_even_with_system_manager_role(self):
		entry = self.entry("candidate", "领用", 1)
		doc = Doc(**dict(entry))
		doc.owner = self.frappe.session.user
		doc.previous = Doc(**doc.as_dict())
		with self.assertRaises(PermissionDenied):
			self.module.validate_stock_entry(doc)

	def test_stock_entry_cannot_clear_day_or_change_owner_to_bypass_approval(self):
		for field, value in (("custom_meal_kitchen_day", None), ("owner", "another@example.test")):
			entry = self.entry("candidate", "领用", 1, status=0)
			doc = Doc(**dict(entry))
			doc.owner = "clerk@example.test"
			doc.previous = Doc(**doc.as_dict())
			setattr(doc, field, value)
			with self.assertRaises(ValidationFailed):
				self.module.validate_stock_entry(doc)

	def test_dependent_stock_draft_blocks_issue_cancellation(self):
		entry = self.entry("issue", "领用", 10)
		doc = Doc(**dict(entry))
		doc.items = [Doc(**dict(row)) for row in entry["items"]]
		with (
			patch.object(self.module, "_day", return_value=self.day),
			patch.object(self.module, "_week", return_value=self.week),
			patch.object(
				self.module,
				"_read_entries",
				return_value=[entry, self.entry("draft-return", "退料", 1, "issue-row", status=0)],
			),
		):
			with self.assertRaises(ValidationFailed):
				self.module.before_cancel_stock_entry(doc)

	def test_future_unexecuted_close_uses_native_close_not_stock_or_manufacture(self):
		plan = Doc(
			name="synthetic-pp",
			custom_meal_week=self.week.name,
			company="School A",
			custom_meal_date="2026-10-30",
			custom_meal_type="早餐",
			docstatus=1,
			status="Submitted",
		)
		plan.set_status = Mock()
		self.frappe.get_doc.return_value = plan
		with patch.object(self.module, "_week", return_value=self.week):
			self.assertEqual(self.module.close_meal_plan(plan), plan.name)
		plan.set_status.assert_called_once_with(close=True)
		self.frappe.new_doc.assert_not_called()
		plan.custom_meal_date = "2026-10-29"
		with patch.object(self.module, "_week", return_value=self.week):
			with self.assertRaises(ValidationFailed):
				self.module.close_meal_plan(plan)

	def test_work_order_blocks_nonmanufacturing_close(self):
		self.frappe.db.sql.return_value = [("actual-work-order",)]
		plan = Doc(name="synthetic-pp", docstatus=1, status="Submitted")
		plan.set_status = Mock()
		with self.assertRaises(ValidationFailed):
			self.module._native_close(plan)
		plan.set_status.assert_not_called()

	def test_stale_native_reservation_snapshot_blocks_closing_before_any_native_write(self):
		plan = Doc(name="synthetic-pp", company=self.week.company, docstatus=1, status="Submitted")
		plan.set_status = Mock()
		self.reservations.ensure_current_native_reservation_inputs.side_effect = ValidationFailed(
			"Refresh request"
		)
		with self.assertRaises(ValidationFailed):
			self.module._native_close(plan)
		plan.set_status.assert_not_called()
		self.reservations.ensure_current_native_reservation_inputs.assert_called_once_with(self.week.company)

	def test_reconciled_flag_without_frozen_real_evidence_does_not_unlock_next_week(self):
		self.week.kitchen_reconciled = 1
		self.week.kitchen_reconciled_at = "2026-10-30 18:00:00"
		self.week.kitchen_reconciliation_snapshot = '{"forged":true}'
		with (
			patch.object(self.module, "_week", return_value=self.week),
			patch.object(
				self.module,
				"_week_execution",
				return_value={"week_name": self.week.name, "days": [], "closed_plans": []},
			),
			patch.object(self.module, "_procurement_proof", return_value={"settled": True}),
		):
			with self.assertRaises(ValidationFailed):
				self.module.verify_week_kitchen_reconciled(self.week)

	def test_unsettled_procurement_does_not_write_reconciled_flag(self):
		purchasing = types.ModuleType("ione_core.meal_purchasing")
		purchasing.verify_week_procurement_settled = Mock(return_value={"settled": False})
		with (
			patch.dict(sys.modules, {"ione_core.meal_purchasing": purchasing}),
			patch.object(self.module, "_week", return_value=self.week),
			patch.object(
				self.module,
				"_week_execution",
				return_value={"week_name": self.week.name, "days": [], "closed_plans": []},
			),
		):
			with self.assertRaises(ValidationFailed):
				self.module.reconcile_kitchen_week(self.week.name)
		self.week.db_set.assert_not_called()

	def test_day_plan_refresh_invalidates_actual_confirmation_instead_of_reusing_old_menu(self):
		new_meals = [Row(meal_type=slot, planned_headcount=21) for slot in self.module.SLOTS]
		new_items = [Row(item_code="rice", planned_qty=11, stock_uom="g")]
		with (
			patch.object(self.module, "_effective_day", return_value=(new_meals, new_items)),
			patch.object(self.module, "_read_entries", return_value=[]),
		):
			self.assertTrue(self.module._refresh_day_plan(self.day, self.week))
		self.assertTrue(
			all(not row["actual_confirmed"] and row["actual_headcount"] == 0 for row in self.day.meals)
		)
		self.assertEqual(self.day.items, new_items)
		self.day.save.assert_called_once()

	def test_submitted_day_cannot_be_rewritten_through_allow_on_submit_fields(self):
		self.day.docstatus = 1
		with self.assertRaises(ValidationFailed):
			self.module.before_update_after_submit_day(self.day)

	def test_changed_plan_cannot_refresh_a_day_with_existing_stock_documents(self):
		meals = [Row(meal_type=slot, planned_headcount=21) for slot in self.module.SLOTS]
		with (
			patch.object(self.module, "_effective_day", return_value=(meals, self.day.items)),
			patch.object(
				self.module, "_read_entries", return_value=[self.entry("draft", "领用", 1, status=0)]
			),
		):
			with self.assertRaises(ValidationFailed):
				self.module._refresh_day_plan(self.day, self.week)
		self.day.save.assert_not_called()

	def test_effective_menu_uses_frozen_stock_quantities_and_omits_only_frozen_water(self):
		adjustments = types.ModuleType("ione_core.meal_adjustments")
		planning = types.ModuleType("ione_core.meal_planning")
		planning._recipe_signature = Mock(return_value="recipe")
		meals = [
			Row(
				meal_date=self.day.meal_date,
				meal_type=slot,
				planned_headcount=20,
				production_plan=f"pp-{slot}",
				recipe_hash="recipe",
				frozen_requirements=[
					{
						"item_code": "rice",
						"required_qty": "2",
						"policy": "采购",
						"warehouse": "Raw A",
						"stock_uom": "g",
					},
					{
						"item_code": "water",
						"required_qty": "1",
						"policy": "厨房用水",
						"warehouse": "Raw A",
						"stock_uom": "g",
					},
				],
			)
			for slot in self.module.SLOTS
		]
		adjustments.get_effective_meals = Mock(return_value=meals)
		plans = {
			row.production_plan: Doc(
				name=row.production_plan,
				docstatus=1,
				company="School A",
				custom_meal_week=self.week.name,
				custom_meal_date=self.day.meal_date,
				custom_meal_type=row.meal_type,
				po_items=[Row(planned_qty=20)],
			)
			for row in meals
		}
		self.frappe.get_doc.side_effect = lambda doctype, name, **kwargs: plans[name]
		water = Row(
			name="water",
			disabled=0,
			is_stock_item=0,
			stock_uom="g",
			custom_meal_procurement_policy="厨房用水",
		)
		self.frappe.get_cached_doc.side_effect = lambda doctype, name: water if name == "water" else self.item
		with patch.dict(
			sys.modules, {"ione_core.meal_adjustments": adjustments, "ione_core.meal_planning": planning}
		):
			_, items = self.module._effective_day(self.week, self.day.meal_date)
			self.assertEqual(items, [{"item_code": "rice", "planned_qty": 10.0, "stock_uom": "g"}])
			meals[0].planned_headcount = 0
			_, stopped = self.module._effective_day(self.week, self.day.meal_date)
			self.assertEqual(stopped[0]["planned_qty"], 8.0)
			self.item.custom_meal_procurement_policy = "厨房用水"
			with self.assertRaises(ValidationFailed):
				self.module._effective_day(self.week, self.day.meal_date)

	def test_native_close_of_all_daily_plans_is_frozen_and_revalidated(self):
		self.day.prepared_by = self.day.owner
		self.day.approved_by = self.frappe.session.user
		self.day.approved_at = "2026-10-30 18:00:00"
		self.day.docstatus = 1
		proof = self.execution()
		plans = [
			Doc(name="old-plan", docstatus=1, status="Closed"),
			Doc(name="replacement-plan", docstatus=1, status="Submitted"),
		]
		for plan in plans:
			plan.set_status = Mock(side_effect=lambda close, plan=plan: setattr(plan, "status", "Closed"))
		with (
			patch.object(
				self.module, "_day_execution", side_effect=lambda *args, **kwargs: copy.deepcopy(proof)
			),
			patch.object(self.module, "_day_plans", return_value=plans),
			patch.object(self.module, "_week", return_value=self.week),
		):
			self.module.on_submit_day(self.day)
			stored = self.day.db_set.call_args.args[0]["execution_snapshot"]
			self.day.execution_snapshot = stored
			verified = self.module._verified_day(self.day)
			self.assertEqual(verified["ledger_hash"], json.loads(stored)["ledger_hash"])
			self.assertEqual(json.loads(stored)["closed_plans"], ["old-plan", "replacement-plan"])
			plans[0].set_status.assert_not_called()
			plans[1].set_status.assert_called_once_with(close=True)
			self.day.execution_snapshot = '{"forged":true}'
			with self.assertRaises(ValidationFailed):
				self.module._verified_day(self.day)

	def test_existing_identical_action_draft_is_returned_without_creating_another(self):
		draft = self.entry("existing-draft", "领用", 2, status=0)
		facts = self.facts([])
		facts["drafts"] = [draft]
		with (
			patch.object(self.module, "_day", return_value=self.day),
			patch.object(self.module, "_week", return_value=self.week),
			patch.object(self.module, "_verify_effective_source"),
			patch.object(self.module, "_ledger", return_value=facts),
		):
			result = self.module.create_kitchen_stock_entry(
				self.day.name, "领用", [{"item_code": "rice", "qty": 2}]
			)
		self.assertEqual(result, {"stock_entry": draft.name, "created": False})
		self.frappe.new_doc.assert_not_called()

	def test_future_stock_entry_submission_is_forbidden_before_ledger_reads(self):
		self.current_date = "2026-10-23"
		entry = self.entry("candidate", "领用", 1)
		doc = Doc(**dict(entry))
		doc.owner = "clerk@example.test"
		doc.previous = Doc(**doc.as_dict())
		with (
			patch.object(self.module, "_day", return_value=self.day),
			patch.object(self.module, "_week", return_value=self.week),
			patch.object(self.module, "_warehouses"),
			patch.object(self.module, "_verify_effective_source"),
			patch.object(self.module, "_ledger") as ledger,
		):
			with self.assertRaises(ValidationFailed):
				self.module.validate_stock_entry(doc)
			ledger.assert_not_called()

	def test_kitchen_configuration_is_idempotent_and_never_moves_stock(self):
		with (
			patch.object(self.module, "_week", return_value=self.week) as load,
			patch.object(self.module, "_warehouses"),
		):
			result = self.module.configure_kitchen_warehouse(self.week.name, "Kitchen A")
			self.assertFalse(result["changed"])
			self.week.db_set.assert_not_called()
			result = self.module.configure_kitchen_warehouse(self.week.name, "Kitchen B")
			self.assertTrue(result["changed"])
			load.assert_called_with(self.week.name, lock=True)
		self.week.db_set.assert_called_once_with("kitchen_warehouse", "Kitchen B", update_modified=False)
		self.frappe.new_doc.assert_not_called()

	def test_any_existing_kitchen_record_blocks_changing_week_warehouse(self):
		self.frappe.db.sql.return_value = [("existing-kitchen-day",)]
		with (
			patch.object(self.module, "_week", return_value=self.week),
			patch.object(self.module, "_warehouses"),
		):
			with self.assertRaises(ValidationFailed):
				self.module.configure_kitchen_warehouse(self.week.name, "Kitchen B")
		self.week.db_set.assert_not_called()
		self.frappe.get_roles.return_value = ["膳食业务经办员"]
		with self.assertRaises(PermissionDenied):
			self.module.configure_kitchen_warehouse(self.week.name, "Kitchen B")

	def test_only_exact_frozen_suspended_recipe_draft_is_exempt_from_closing(self):
		plan = Doc(
			name="suspended-draft",
			docstatus=0,
			mr_items=[],
			custom_meal_date=self.day.meal_date,
			custom_meal_type="早餐",
		)
		meal = Row(
			production_plan=plan.name,
			meal_date=self.day.meal_date,
			meal_type="早餐",
			service_suspended=1,
			planned_headcount=0,
			recipe_hash="frozen",
		)
		adjustments = types.ModuleType("ione_core.meal_adjustments")
		adjustments.get_effective_meals = Mock(return_value=[meal])
		planning = types.ModuleType("ione_core.meal_planning")
		planning._recipe_signature = Mock(return_value="frozen")
		with patch.dict(
			sys.modules, {"ione_core.meal_adjustments": adjustments, "ione_core.meal_planning": planning}
		):
			self.assertTrue(self.module._is_suspended_draft(self.week, plan))
			meal.service_suspended = 0
			self.assertFalse(self.module._is_suspended_draft(self.week, plan))
			meal.service_suspended = 1
			meal.planned_headcount = 1
			self.assertFalse(self.module._is_suspended_draft(self.week, plan))
			meal.planned_headcount = 0
			planning._recipe_signature.return_value = "tampered"
			with self.assertRaises(ValidationFailed):
				self.module._is_suspended_draft(self.week, plan)

	def test_stock_cancellation_cannot_erase_the_day_or_rewrite_original_quantity(self):
		entry = self.entry("issue", "领用", 10)
		for field, value in (
			("custom_meal_kitchen_day", None),
			("items", [Row(entry["items"][0], qty=9, transfer_qty=9)]),
		):
			doc = Doc(**dict(entry))
			doc.previous = Doc(**doc.as_dict())
			setattr(doc, field, value)
			with self.assertRaises(ValidationFailed):
				self.module.before_cancel_stock_entry(doc)

	def test_open_day_sees_a_concurrently_committed_existing_day_instead_of_creating_another(self):
		# A plain RR snapshot cannot see the day committed while waiting for its
		# Week lock. Current reads must find it without re-reading its link from
		# that old snapshot or trying to insert a second unique day.
		stale_week = copy.deepcopy(self.week)
		stale_week.kitchen_warehouse = "Old kitchen"
		self.frappe.db.sql.side_effect = lambda query, values, **kwargs: (
			[Row(name=self.day.name)] if "LIMIT 2 FOR UPDATE" in query else []
		)
		self.frappe.get_doc.side_effect = lambda doctype, name, **kwargs: (
			self.day if doctype == "Meal Kitchen Day" and kwargs.get("for_update") else None
		)
		with (
			patch.object(
				self.module, "_week", side_effect=lambda value, lock=False: self.week if lock else stale_week
			),
			patch.object(self.module, "_refresh_day_plan", return_value=False),
		):
			result = self.module.get_kitchen_day(self.week.name, self.day.meal_date)
		self.assertEqual(result, {"name": self.day.name, "created": False, "plan_refreshed": False})
		self.frappe.db.get_value.assert_not_called()
		self.frappe.get_all.assert_not_called()
		self.frappe.new_doc.assert_not_called()

	def test_execution_uses_a_committed_replacement_plan_missing_from_the_old_snapshot(self):
		adjustments = types.ModuleType("ione_core.meal_adjustments")
		planning = types.ModuleType("ione_core.meal_planning")
		planning._recipe_signature = Mock(return_value="replacement-frozen")
		meals = [
			Row(meal_date=self.day.meal_date, meal_type=slot, planned_headcount=0)
			for slot in self.module.SLOTS
		]
		meals[0].update(
			planned_headcount=20,
			production_plan="replacement-pp",
			recipe_hash="replacement-frozen",
			frozen_requirements=[
				{
					"item_code": "rice",
					"required_qty": "3",
					"policy": "采购",
					"warehouse": "Raw A",
					"stock_uom": "g",
				}
			],
		)
		adjustments.get_effective_meals = Mock(side_effect=lambda week, lock=False: meals if lock else [])
		plan = Doc(
			name="replacement-pp",
			docstatus=1,
			company=self.week.company,
			custom_meal_week=self.week.name,
			custom_meal_date=self.day.meal_date,
			custom_meal_type="早餐",
			po_items=[Row(planned_qty=20)],
		)

		def current_plan(doctype, name, **kwargs):
			if doctype == "Production Plan" and name == plan.name and kwargs.get("for_update"):
				return plan
			raise LookupError("Replacement plan is not visible in the old consistent snapshot")

		self.frappe.get_doc.side_effect = current_plan
		with patch.dict(
			sys.modules, {"ione_core.meal_adjustments": adjustments, "ione_core.meal_planning": planning}
		):
			_, items = self.module._effective_day(self.week, self.day.meal_date, lock=True)
		self.assertEqual(items, [{"item_code": "rice", "planned_qty": 3.0, "stock_uom": "g"}])

	def test_a_concurrently_reconciled_week_blocks_stock_creation_despite_an_old_snapshot(self):
		current_week = copy.deepcopy(self.week)
		current_week.kitchen_reconciled = 1
		with (
			patch.object(self.module, "_day", return_value=self.day),
			patch.object(
				self.module,
				"_week",
				side_effect=lambda value, lock=False: current_week if lock else self.week,
			),
			patch.object(self.module, "_ledger") as ledger,
		):
			with self.assertRaises(ValidationFailed):
				self.module.create_kitchen_stock_entry(
					self.day.name, "领用", [{"item_code": "rice", "qty": 1}]
				)
		ledger.assert_not_called()
		self.frappe.new_doc.assert_not_called()

	def test_week_reconciliation_reads_newly_committed_days_and_replacement_plans(self):
		days = {
			f"day-{i}": Doc(
				**{**self.day.as_dict(), "name": f"day-{i}", "meal_date": f"2026-10-{26 + i}", "docstatus": 1}
			)
			for i in range(5)
		}
		plan = Doc(
			name="replacement-pp",
			company=self.week.company,
			custom_meal_week=self.week.name,
			custom_meal_date="2026-10-30",
			custom_meal_type="早餐",
			docstatus=1,
			status="Closed",
		)

		def current_rows(query, values, **kwargs):
			if not query.endswith("FOR UPDATE"):
				return []
			if "FROM `tabMeal Kitchen Day`" in query:
				return [Row(name=name) for name in days]
			if "FROM `tabProduction Plan`" in query:
				return [Row(plan.as_dict())]
			return []

		def current_doc(doctype, name, **kwargs):
			if not kwargs.get("for_update"):
				raise LookupError("Not visible in old snapshot")
			return days[name] if doctype == "Meal Kitchen Day" else plan

		self.frappe.db.sql.side_effect = current_rows
		self.frappe.get_doc.side_effect = current_doc
		with patch.object(
			self.module,
			"_verified_day",
			side_effect=lambda day, lock=False: (
				{"name": day.name, "meal_date": day.meal_date, "ledger_hash": "proof"} if lock else None
			),
		):
			proof = self.module._week_execution(self.week, lock=True)
		self.assertEqual(len(proof["days"]), 5)
		self.assertEqual(proof["closed_plans"], [plan.name])
		self.frappe.get_all.assert_not_called()


if __name__ == "__main__":
	unittest.main(verbosity=2)

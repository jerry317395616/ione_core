"""Gross-weight acknowledgement and source integrity using synthetic documents."""

import datetime as dt
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ione_core.tests.test_meal_adjustments import Doc, PermissionDenied, ValidationFailed, digest, load_json


class Request(Doc):
	@property
	def items(self):
		return self["items"]


class MealWeightTests(unittest.TestCase):
	def setUp(self):
		self.frappe = types.ModuleType("frappe")
		self.frappe._ = lambda value: value
		self.frappe.ValidationError = ValidationFailed
		self.frappe.PermissionError = PermissionDenied
		self.frappe.throw = lambda message, cls=ValidationFailed: (_ for _ in ()).throw(cls(message))
		self.frappe.whitelist = lambda **kwargs: lambda function: function
		self.frappe.session = Doc(user="reviewer@example.test")
		self.frappe.get_roles = Mock(return_value=["Purchase Manager"])
		self.frappe.get_doc = Mock()
		self.frappe.as_json = lambda value: json.dumps(value, default=str)
		self.frappe.db = Doc(sql=Mock())
		self.utils = types.ModuleType("frappe.utils")
		self.utils.now_datetime = lambda: dt.datetime(2026, 10, 23, 12)
		self.planning = types.ModuleType("ione_core.meal_planning")
		self.planning._json = load_json
		self.planning._digest = digest
		self.planning._recipe_signature = Mock(return_value="recipe-A")
		self.week = Doc(name="WEEK-A", company="School A", docstatus=1, kitchen_reconciled=0,
			meals=[Doc(production_plan=f"PLAN-{i}") for i in range(25)],
			population_snapshot=json.dumps({"recipe_hashes": {f"PLAN-{i}": f"recipe-{i}" for i in range(25)}}),
			procurement_snapshot="{}", requirement_weight_basis="待确认", requirement_weight_snapshot=None)
		self.week.reload = Mock(return_value=self.week)
		self.week.db_set = Mock(side_effect=lambda values, **kwargs: self.week.update(values))
		self.planning._week = Mock(return_value=self.week)
		self.adjustments = types.ModuleType("ione_core.meal_adjustments")
		self.adjustments.get_effective_meals = Mock(return_value=[])
		self.modules = patch.dict(sys.modules, {"frappe": self.frappe, "frappe.utils": self.utils,
			"ione_core.meal_planning": self.planning, "ione_core.meal_adjustments": self.adjustments})
		self.modules.start()
		spec = importlib.util.spec_from_file_location("synthetic_meal_weights", Path(__file__).parents[1] / "meal_weights.py")
		self.module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.module)

	def tearDown(self):
		self.modules.stop()

	def confirm(self):
		return self.module.confirm_requirement_weight_basis(self.week.name)

	def test_numbers_reject_nonfinite_and_malformed_values(self):
		for value in ("NaN", "Infinity", "-Infinity", "bad", {"value": 1}):
			with self.subTest(value=value), self.assertRaises(ValidationFailed):
				self.module._number(value)
		self.assertEqual(str(self.module._number("0.125")), "0.125")

	def test_confirmation_requires_manager_and_never_assumes_yield(self):
		self.frappe.get_roles.return_value = ["膳食业务经办员"]
		with self.assertRaises(PermissionDenied):
			self.confirm()
		self.frappe.get_roles.return_value = ["Purchase Manager"]
		with self.assertRaises(ValidationFailed):
			self.module.confirm_requirement_weight_basis(self.week.name, basis="可食部净重")
		self.week.db_set.assert_not_called()

	def test_confirmation_requires_initialized_whole_week(self):
		self.week.meals = []
		with self.assertRaises(ValidationFailed):
			self.confirm()
		self.week.db_set.assert_not_called()

	def test_confirmation_records_hash_basis_actor_and_is_idempotent(self):
		result = self.confirm()
		self.assertFalse(result["already_confirmed"])
		proof = load_json(self.week.requirement_weight_snapshot)
		self.assertEqual(proof["basis"], "采购毛重")
		self.assertEqual(proof["confirmed_by"], self.frappe.session.user)
		self.assertEqual(proof["baseline_recipe_hashes"], load_json(self.week.population_snapshot)["recipe_hashes"])
		self.assertEqual(proof["proof_hash"], digest({key: value for key, value in proof.items() if key != "proof_hash"}))
		self.assertTrue(self.confirm()["already_confirmed"])
		self.week.db_set.assert_called_once()

	def test_lock_reload_rechecks_cancellation_and_reconciliation(self):
		for field, value in (("docstatus", 2), ("kitchen_reconciled", 1)):
			with self.subTest(field=field):
				self.week.docstatus = 1
				self.week.kitchen_reconciled = 0
				self.week.reload.side_effect = lambda key=field, target=value: self.week.update({key: target})
				with self.assertRaises(ValidationFailed):
					self.confirm()
		self.week.db_set.assert_not_called()

	def test_forged_or_foreign_proof_rejected(self):
		self.confirm()
		original = self.week.requirement_weight_snapshot
		for field, value in (("week", "OTHER"), ("company", "School B"), ("basis", "可食部净重"), ("confirmed_by", ""), ("proof_hash", "forged")):
			with self.subTest(field=field):
				proof = load_json(original)
				proof[field] = value
				self.week.requirement_weight_snapshot = json.dumps(proof)
				with self.assertRaises(ValidationFailed):
					self.module.verify_purchase_weight_basis(self.week)

	def test_changed_baseline_and_current_recipe_rejected(self):
		self.confirm()
		original = self.week.population_snapshot
		self.week.population_snapshot = "{}"
		with self.assertRaises(ValidationFailed):
			self.module.verify_purchase_weight_basis(self.week)
		self.week.population_snapshot = original
		self.adjustments.get_effective_meals.return_value = [Doc(service_suspended=0, planned_headcount=257,
			production_plan="PLAN-A", recipe_hash="recipe-A")]
		self.planning._recipe_signature.return_value = "changed-recipe"
		with self.assertRaises(ValidationFailed):
			self.module.verify_purchase_weight_basis(self.week)

	def source_request(self, adjustment=False):
		plan = Doc(name="PLAN-A", custom_meal_week=self.week.name, custom_meal_adjustment="CHANGE-A" if adjustment else None,
			mr_items=[Doc(name="SOURCE-A", item_code="ING-A", warehouse="RAW", required_bom_qty="10.125")])
		request = Request(company="School A", items=[Doc(item_code="ING-A", production_plan=plan.name,
			material_request_plan_item="SOURCE-A", qty="2.5")])
		frozen = [{"production_plan": plan.name, "item_code": "ING-A", "warehouse": "RAW", "required_qty": "10.125"}]
		revision = Doc(docstatus=1, meal_week=self.week.name, applied_snapshot=json.dumps({"requirements": frozen}))
		self.week.procurement_snapshot = json.dumps({"rows": frozen})
		self.frappe.get_doc.side_effect = lambda doctype, name: plan if doctype == "Production Plan" else revision
		return plan, request, revision

	def test_gross_requirement_proof_accepts_net_purchase_after_stock_deduction(self):
		self.confirm()
		_plan, request, _revision = self.source_request()
		self.assertTrue(self.module.verify_purchase_weight_basis(self.week, [request])["confirmed"])

	def test_foreign_request_missing_native_source_and_changed_gross_rejected(self):
		self.confirm()
		plan, request, _revision = self.source_request()
		for modify, restore in (
			(lambda: setattr(request, "company", "School B"), lambda: setattr(request, "company", "School A")),
			(lambda: setattr(plan, "custom_meal_week", "OTHER"), lambda: setattr(plan, "custom_meal_week", self.week.name)),
			(lambda: setattr(request.items[0], "material_request_plan_item", "MISSING"), lambda: setattr(request.items[0], "material_request_plan_item", "SOURCE-A")),
			(lambda: setattr(plan.mr_items[0], "required_bom_qty", "20"), lambda: setattr(plan.mr_items[0], "required_bom_qty", "10.125")),
		):
			modify()
			with self.assertRaises(ValidationFailed):
				self.module.verify_purchase_weight_basis(self.week, [request])
			restore()

	def test_adjusted_plan_uses_submitted_adjustment_gross_snapshot(self):
		self.confirm()
		_plan, request, revision = self.source_request(adjustment=True)
		self.assertTrue(self.module.verify_purchase_weight_basis(self.week, [request])["confirmed"])
		revision.docstatus = 0
		with self.assertRaises(ValidationFailed):
			self.module.verify_purchase_weight_basis(self.week, [request])


if __name__ == "__main__":
	unittest.main()

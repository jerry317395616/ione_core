"""Synthetic single-meal revision checks; no site, users or stock are changed."""

import copy
import datetime as dt
import hashlib
import importlib.util
import json
import sys
import types
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch


class ValidationFailed(Exception):
	pass


class PermissionDenied(Exception):
	pass


class Doc(dict):
	def __init__(self, values=None, **kwargs):
		super().__init__(values or {}, **kwargs)
		object.__setattr__(self, "previous", None)
		object.__setattr__(self, "allowed", True)

	def __getattr__(self, key):
		if key.startswith("__"):
			raise AttributeError(key)
		return self.get(key)

	def __setattr__(self, key, value):
		if key in ("previous", "allowed"):
			object.__setattr__(self, key, value)
		else:
			self[key] = value

	def get_doc_before_save(self):
		return self.previous

	def is_new(self):
		return bool(self.get("__islocal"))

	def check_permission(self, permission):
		if not self.allowed:
			raise PermissionDenied(permission)

	def as_dict(self):
		return dict(self)


def getdate(value):
	if isinstance(value, dt.datetime):
		return value.date()
	return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))


def digest(value):
	return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def load_json(value):
	return value if isinstance(value, dict) else json.loads(value or "{}")


class MealAdjustmentTests(unittest.TestCase):
	def setUp(self):
		self.frappe = types.ModuleType("frappe")
		self.frappe._ = lambda value: value
		self.frappe._dict = Doc
		self.frappe.ValidationError = ValidationFailed
		self.frappe.PermissionError = PermissionDenied
		self.frappe.throw = lambda message, cls=ValidationFailed: (_ for _ in ()).throw(cls(message))
		self.frappe.whitelist = lambda **kwargs: lambda function: function
		self.frappe.session = Doc(user="reviewer@example.test")
		self.frappe.get_roles = Mock(return_value=["食谱审核员"])
		self.frappe.has_permission = Mock(return_value=True)
		self.frappe.get_all = Mock(return_value=[])
		self.frappe.get_doc = Mock()
		self.frappe.get_cached_doc = Mock(return_value=Doc(disabled=0, is_purchase_item=0))
		self.frappe.as_json = lambda value: json.dumps(value, default=str)
		self.frappe.db = Doc(exists=Mock(return_value=False), sql=Mock(), get_value=Mock(return_value="operator@example.test"))
		self.frappe.db.get_value.side_effect = lambda doctype, name, field, **kwargs: "2026-10-23 12:00:00" if field == "creation" else "operator@example.test"
		self.utils = types.ModuleType("frappe.utils")
		self.utils.cint = lambda value: int(value or 0)
		self.utils.getdate = getdate
		self.utils.get_datetime = lambda value: value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(str(value))
		self.utils.today = lambda: "2026-10-23"
		self.utils.now_datetime = lambda: dt.datetime(2026, 10, 23, 12)
		self.planning = types.ModuleType("ione_core.meal_planning")
		self.planning._json = load_json
		self.planning._digest = digest
		self.planning._planner = Mock()
		self.week = Doc(name="WEEK-A", company="School A", docstatus=1, kitchen_reconciled=0,
			week_start="2026-10-26", week_end="2026-10-30", population_snapshot="{}", procurement_snapshot="{}", meals=[])
		self.planning._week = Mock(return_value=self.week)
		self.weights = types.ModuleType("ione_core.meal_weights")
		self.weights.verify_purchase_weight_basis = Mock(return_value={"confirmed": True})
		self.claims = types.ModuleType("ione_core.meal_stock_claims")
		self.claims.lock_claim_scope = Mock()
		self.modules = patch.dict(sys.modules, {"frappe": self.frappe, "frappe.utils": self.utils,
			"ione_core.meal_planning": self.planning, "ione_core.meal_weights": self.weights,
			"ione_core.meal_stock_claims": self.claims})
		self.modules.start()
		spec = importlib.util.spec_from_file_location("synthetic_meal_adjustments", Path(__file__).parents[1] / "meal_adjustments.py")
		self.module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.module)
		self.meal = Doc(meal_date="2026-10-26", meal_type="午餐", production_plan="PLAN-A",
			planned_headcount=257, service_suspended=0, menu="Dish A", recipe_hash="recipe-A", adjustment=None)
		self.week.meals = [self.meal]
		self.doc = Doc(name="CHANGE-A", owner="operator@example.test", creation="2026-10-23 12:00:00", meal_week=self.week.name,
			meal_date=self.meal.meal_date, meal_type=self.meal.meal_type, docstatus=0,
			source_plan="PLAN-A", source_adjustment=None, source_snapshot=json.dumps(self.module._state(self.meal)),
			target_headcount=250, service_suspended=0, reason="Confirmed meal leave", review_notes="Reviewed",
			dishes=[Doc(bom_no="BOM-A")], replacement_plan=None, material_request=None, applied_snapshot=None,
			purchase_change_summary=None)
		self.bom = Doc(name="BOM-A", docstatus=1, is_active=1, quantity=1, company="School A", item="DISH-A")
		self.frappe.get_doc.return_value = self.bom

	def tearDown(self):
		self.modules.stop()

	def current(self):
		return patch.object(self.module, "_current", return_value=(self.week, self.meal))

	def test_nonfinite_fractional_negative_and_implicit_zero_headcounts_rejected(self):
		with self.current():
			for value in ("NaN", "Infinity", "1.5", -1, 0, "bad"):
				with self.subTest(value=value), self.assertRaises(ValidationFailed):
					self.doc.target_headcount = value
					self.module.validate_adjustment(self.doc)

	def test_explicit_whole_meal_stop_requires_zero_and_reason(self):
		with self.current():
			self.doc.update(service_suspended=1, target_headcount=0, dishes=[])
			self.module.validate_adjustment(self.doc)
			self.doc.target_headcount = 1
			with self.assertRaises(ValidationFailed):
				self.module.validate_adjustment(self.doc)
			self.doc.update(target_headcount=0, reason="  ")
			with self.assertRaises(ValidationFailed):
				self.module.validate_adjustment(self.doc)

	def test_manual_creation_and_source_or_result_forgery_rejected(self):
		self.doc.__islocal = True
		with self.assertRaises(ValidationFailed):
			self.module.validate_adjustment(self.doc)
		self.doc.__islocal = False
		for field in self.module._SOURCE + self.module._RESULT:
			with self.subTest(field=field):
				self.doc.previous = copy.deepcopy(self.doc)
				original = self.doc.get(field)
				self.doc[field] = "forged"
				with self.assertRaises(ValidationFailed):
					self.module.validate_adjustment(self.doc)
				self.doc[field] = original

	def test_stale_source_snapshot_rejected(self):
		self.doc.source_snapshot = "{}"
		with self.current(), self.assertRaises(ValidationFailed):
			self.module.validate_adjustment(self.doc)

	def test_foreign_unapproved_inactive_or_non_single_child_bom_rejected(self):
		with self.current():
			for field, value in (("company", "School B"), ("docstatus", 0), ("is_active", 0), ("quantity", 100)):
				with self.subTest(field=field):
					original = self.bom[field]
					self.bom[field] = value
					with self.assertRaises(ValidationFailed):
						self.module.validate_adjustment(self.doc)
					self.bom[field] = original
			self.frappe.get_cached_doc.return_value = Doc(disabled=0, is_purchase_item=1)
			with self.assertRaises(ValidationFailed):
				self.module.validate_adjustment(self.doc)

	def test_duplicate_or_missing_dishes_rejected(self):
		with self.current():
			for dishes in ([], [Doc(bom_no="BOM-A"), Doc(bom_no="BOM-A")]):
				self.doc.dishes = dishes
				with self.assertRaises(ValidationFailed):
					self.module.validate_adjustment(self.doc)

	def test_current_rejects_past_outside_week_closed_week_and_executed_day(self):
		with patch.object(self.module, "get_effective_meals", return_value=[self.meal]):
			self.module._current(self.doc)
			for date in ("2026-10-22", "2026-11-02"):
				self.doc.meal_date = date
				with self.assertRaises(ValidationFailed):
					self.module._current(self.doc)
			self.doc.meal_date = self.meal.meal_date
			self.week.kitchen_reconciled = 1
			with self.assertRaises(ValidationFailed):
				self.module._current(self.doc)
			self.week.kitchen_reconciled = 0
			for doctype in ("Meal Kitchen Day", "Stock Entry"):
				self.frappe.db.exists.side_effect = lambda name, filters, target=doctype: name == target
				with self.assertRaises(ValidationFailed):
					self.module._current(self.doc)

	def test_owner_cannot_approve_even_as_administrator(self):
		self.frappe.session.user = self.doc.owner
		self.frappe.get_roles.return_value = ["System Manager"]
		with self.assertRaises(PermissionDenied):
			self.module.before_submit_adjustment(self.doc)
		self.frappe.db.sql.assert_not_called()

	def test_existing_adjustment_owner_cannot_be_reassigned(self):
		self.doc.previous = copy.deepcopy(self.doc)
		self.doc.owner = "another-operator@example.test"
		with self.assertRaises(PermissionDenied):
			self.module.validate_adjustment(self.doc)
		with self.module._managed(), self.assertRaises(PermissionDenied):
			self.module.validate_adjustment(self.doc)

	def test_submit_uses_locked_original_owner_to_reject_forged_self_approval(self):
		self.frappe.session.user = "operator@example.test"
		self.frappe.get_roles.return_value = ["System Manager"]
		self.doc.owner = "another-operator@example.test"
		with self.assertRaises(PermissionDenied):
			self.module.before_submit_adjustment(self.doc)
		self.frappe.db.get_value.assert_called_with("Meal Plan Adjustment", self.doc.name, "owner", for_update=True)
		self.weights.verify_purchase_weight_basis.assert_not_called()

	def test_existing_adjustment_creation_cannot_be_moved_before_prior_revision(self):
		self.doc.previous = copy.deepcopy(self.doc)
		self.doc.creation = "2026-10-22 12:00:00"
		with self.assertRaisesRegex(PermissionDenied, "回放顺序"):
			self.module.validate_adjustment(self.doc)
		with self.module._managed(), self.assertRaises(PermissionDenied):
			self.module.validate_adjustment(self.doc)

	def test_submit_rechecks_database_creation_even_without_old_document_validation(self):
		self.doc.creation = "2026-10-22 12:00:00"
		with patch.object(self.module, "validate_adjustment") as validate, self.assertRaisesRegex(PermissionDenied, "创建时间与原始记录"):
			self.module.before_submit_adjustment(self.doc)
		validate.assert_not_called()
		self.frappe.db.get_value.assert_called_with("Meal Plan Adjustment", self.doc.name, "creation", for_update=True)

	def test_approval_locks_week_and_requires_real_reason_and_review_notes(self):
		with patch.object(self.module, "validate_adjustment") as validate:
			self.module.before_submit_adjustment(self.doc)
			self.frappe.db.sql.assert_called_once()
			validate.assert_called_once_with(self.doc, lock=True)
			self.weights.verify_purchase_weight_basis.assert_called_once_with(self.week.name)
		self.doc.review_notes = "  "
		with self.assertRaises(ValidationFailed):
			self.module.before_submit_adjustment(self.doc)

	def test_after_submit_save_and_cancellation_cannot_rewrite_history(self):
		for function in (self.module.before_update_after_submit_adjustment, self.module.before_cancel_adjustment):
			with self.assertRaises(ValidationFailed):
				function(self.doc)

	def test_effective_meals_preserve_and_verify_revision_chain(self):
		self.week.population_snapshot = json.dumps({"recipe_hashes": {"PLAN-A": "recipe-A"}})
		self.frappe.db.exists.return_value = True
		proof = {"week": self.week.name, "adjustment": self.doc.name, "source": self.module._state(self.meal),
			"effective_meal": {**self.module._state(self.meal), "planned_headcount": 250, "production_plan": "PLAN-B", "recipe_hash": "recipe-B"},
			"requirements": [{"production_plan": "PLAN-B", "item_code": "ING-A"}]}
		revision = Doc(name=self.doc.name, meal_date=self.meal.meal_date, meal_type=self.meal.meal_type, applied_snapshot=json.dumps(proof))
		self.frappe.get_all.return_value = [revision]
		actual = self.module.get_effective_meals(self.week)[0]
		self.assertEqual(actual.planned_headcount, 250)
		self.assertEqual(actual.production_plan, "PLAN-B")
		self.assertEqual(actual.adjustment, self.doc.name)
		self.assertEqual(actual.frozen_requirements, proof["requirements"])
		self.assertEqual(self.week.meals[0].production_plan, "PLAN-A")
		proof["source"]["planned_headcount"] = 999
		revision.applied_snapshot = json.dumps(proof)
		with self.assertRaises(ValidationFailed):
			self.module.get_effective_meals(self.week)

	def revision_after_snapshot(self):
		self.week.population_snapshot = json.dumps({"recipe_hashes": {"PLAN-A": "recipe-A"}})
		proof = {"week": self.week.name, "adjustment": "EARLIER-APPROVAL", "source": self.module._state(self.meal),
			"effective_meal": {**self.module._state(self.meal), "planned_headcount": 250,
				"production_plan": "PLAN-B", "recipe_hash": "recipe-B"}, "requirements": []}
		return Doc(name=proof["adjustment"], meal_date=self.meal.meal_date, meal_type=self.meal.meal_type,
			applied_snapshot=json.dumps(proof))

	def test_execution_current_read_sees_revision_hidden_from_consistent_snapshot(self):
		revision = self.revision_after_snapshot()
		self.frappe.db.exists.return_value = True
		self.frappe.get_all.return_value = []
		self.frappe.db.sql.return_value = [revision]
		self.frappe.get_doc.return_value = self.week
		self.assertEqual(self.module.get_effective_meals(self.week)[0].planned_headcount, 257)
		self.assertEqual(self.module.get_effective_meals(self.week, lock=True)[0].planned_headcount, 250)
		self.frappe.get_doc.assert_called_with("Meal Planning Week", self.week.name, for_update=True)
		query = self.frappe.db.sql.call_args.args[0]
		self.assertIn("FOR UPDATE", query)
		self.assertIn("docstatus=1", query)

	def test_locked_approval_rejects_source_changed_after_request_snapshot(self):
		revision = self.revision_after_snapshot()
		self.frappe.db.exists.return_value = True
		self.frappe.get_all.return_value = []
		self.frappe.get_doc.side_effect = lambda doctype, *args, **kwargs: self.week if doctype == "Meal Planning Week" else self.bom
		self.frappe.db.sql.side_effect = lambda query, *args, **kwargs: [revision] if "FROM `tabMeal Plan Adjustment`" in query else []
		with self.assertRaisesRegex(ValidationFailed, "其他变更"):
			self.module.validate_adjustment(self.doc, lock=True)
		self.frappe.get_all.assert_not_called()

	def test_locked_approval_sees_stock_execution_hidden_from_snapshot(self):
		self.frappe.get_doc.return_value = self.week
		self.frappe.db.exists.return_value = False
		self.frappe.db.sql.side_effect = lambda query, *args, **kwargs: [("ACTUAL-SE",)] if "FROM `tabStock Entry`" in query else []
		with self.assertRaisesRegex(ValidationFailed, "实际厨房出入库"):
			self.module._current(self.doc, lock=True)

	def test_quantity_differences_merge_same_ingredient_and_exclude_kitchen_water(self):
		before = [{"item_code": "ING-A", "warehouse": "RAW", "stock_uom": "kg", "required_qty": "1.2"},
			{"item_code": "ING-A", "warehouse": "RAW", "stock_uom": "kg", "required_qty": "0.3"},
			{"item_code": "WATER", "warehouse": "RAW", "stock_uom": "L", "required_qty": "100", "policy": "厨房用水"}]
		after = [{"item_code": "ING-A", "warehouse": "RAW", "stock_uom": "kg", "required_qty": "1.1"}]
		self.assertEqual(self.module._changed_quantities(before, after), [{"item_code": "ING-A", "warehouse": "RAW", "uom": "kg", "old_gross_qty": "1.5", "new_gross_qty": "1.1", "gross_difference": "-0.4"}])

	def test_application_retains_document_permission_contract_in_temporary_week(self):
		class Attributes(dict):
			__getattr__ = dict.get
			__setattr__ = dict.__setitem__

		self.frappe._dict = Attributes
		self.planning._managed = nullcontext
		self.planning._plan_values = Mock()
		self.planning._recipe_signature = Mock(return_value="recipe-A")
		kitchen = types.ModuleType("ione_core.meal_kitchen")
		kitchen.close_meal_plan = Mock()
		procurement = types.ModuleType("ione_core.meal_procurement")
		def prepare(proxy):
			self.assertTrue(callable(proxy.check_permission), "temporary week must keep permission checks")
			proxy.check_permission("read")
			self.assertIsNone(proxy.material_request)
			return {"snapshot": {"rows": []}, "plans": {}, "blockers": [], "warnings": []}
		procurement.prepare_adjustment_procurement = Mock(side_effect=prepare)
		self.week.material_request = "BASE-MR"
		self.week.add_comment = Mock()
		self.doc.update(service_suspended=1, target_headcount=0)
		self.doc.db_set = Mock(side_effect=lambda values, **kwargs: self.doc.update(values))
		self.frappe.get_doc.return_value = Doc(name="PLAN-A", docstatus=1, status="Closed")
		with patch.dict(sys.modules, {"ione_core.meal_kitchen": kitchen, "ione_core.meal_procurement": procurement}), self.current(), patch.object(self.module, "get_effective_meals", return_value=[self.meal]):
			self.module.on_submit_adjustment(self.doc)
		self.assertEqual(self.week.material_request, "BASE-MR")
		self.assertEqual(self.week.meals[0].planned_headcount, 257)
		self.assertIsNone(self.module._APPLYING.get())
		proof = load_json(self.doc.applied_snapshot)
		self.assertEqual(proof["effective_meal"]["planned_headcount"], 0)
		self.assertEqual(proof["effective_meal"]["service_suspended"], 1)

	def test_delta_request_preserves_operator_ownership_and_restores_reviewer(self):
		request = Mock()
		self.frappe.get_doc.return_value = request
		self.frappe.set_user = Mock(side_effect=lambda user: setattr(self.frappe.session, "user", user))
		result = self.module._create_delta_request(self.doc, self.week, Doc(name="PLAN-B", mr_items=[]), [])
		self.assertIs(result, request)
		self.assertEqual(self.frappe.set_user.call_args_list[0].args, (self.doc.owner,))
		self.assertEqual(self.frappe.session.user, "reviewer@example.test")
		request.insert.assert_called_once_with()
		request.submit.assert_not_called()
		self.frappe.has_permission.return_value = False
		with self.assertRaises(PermissionDenied):
			self.module._create_delta_request(self.doc, self.week, Doc(name="PLAN-B", mr_items=[]), [])
		self.assertEqual(self.frappe.session.user, "reviewer@example.test")


if __name__ == "__main__":
	unittest.main()

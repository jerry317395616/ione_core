"""Isolated meal workflow invariants, using synthetic documents only."""

import ast
import copy
import datetime as dt
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


class AuthenticationFailed(Exception):
	pass


class Doc(dict):
	def __init__(self, values=None, **kwargs):
		super().__init__(values or {}, **kwargs)
		object.__setattr__(self, "previous", None)
		object.__setattr__(self, "allowed", True)
		object.__setattr__(self, "saved", 0)

	def __getattr__(self, key):
		if key.startswith("__"):
			raise AttributeError(key)
		return self.get(key)

	def __setattr__(self, key, value):
		if key in ("previous", "allowed", "saved"):
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

	def set(self, key, value):
		self[key] = value

	def save(self, **kwargs):
		self.saved += 1
		return self

	def reload(self):
		return self

	def append(self, field, values):
		self[field].append(Doc(values))

	def insert(self, **kwargs):
		self.name = kwargs.get("set_name", self.get("name"))
		return self


def getdate(value):
	if isinstance(value, dt.datetime):
		return value.date()
	return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))


class MealPlanningTests(unittest.TestCase):
	def setUp(self):
		self.frappe = types.ModuleType("frappe")
		self.frappe._ = lambda value: value
		self.frappe.session = types.SimpleNamespace(user="planner@example.test")
		self.frappe.AuthenticationError = AuthenticationFailed
		self.frappe.PermissionError = PermissionDenied
		self.frappe.ValidationError = ValidationFailed
		self.frappe.throw = lambda message, cls=ValidationFailed: (_ for _ in ()).throw(cls(message))
		self.frappe.whitelist = lambda **kwargs: lambda function: function
		self.frappe.get_roles = Mock(return_value=["食谱编排员"])
		self.frappe.get_doc = Mock()
		self.frappe.as_json = lambda value: json.dumps(value, default=str)
		self.frappe.cache = types.SimpleNamespace(lock=Mock(side_effect=lambda *args, **kwargs: nullcontext()))
		self.frappe.db = types.SimpleNamespace(get_value=Mock(return_value="operator@example.test"), exists=Mock(return_value=False))
		self.utils = types.ModuleType("frappe.utils")
		self.utils.getdate = getdate
		self.utils.cint = lambda value: int(value or 0)
		self.utils.now_datetime = lambda: dt.datetime(2026, 10, 23, 12, 0)
		self.modules = patch.dict(sys.modules, {"frappe": self.frappe, "frappe.utils": self.utils})
		self.modules.start()
		spec = importlib.util.spec_from_file_location("synthetic_meal_planning", Path(__file__).parents[1] / "meal_planning.py")
		self.module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.module)
		self.warehouse = Doc(company="School A", is_group=0, disabled=0)
		self.frappe.get_doc.side_effect = lambda doctype, name: self.warehouse if doctype == "Warehouse" else self.week
		self.week = self.make_week()

	def tearDown(self):
		self.modules.stop()

	def make_week(self, meals=True):
		week = Doc(name="synthetic-week", owner="operator@example.test", company="School A", week_start="2026-10-26", week_end="2026-10-30", raw_material_warehouse="Raw A", academic_year="2026-2027", academic_term="Autumn", revision=1, source_week=None, docstatus=0, population_snapshot="{}", population_as_of=None, population_basis="expected", material_request=None, procurement_snapshot=None, stock_reviewed=0, meals=[])
		if meals:
			for index in range(5):
				for slot in self.module.SLOTS:
					week.meals.append(Doc(meal_date=str(dt.date(2026, 10, 26) + dt.timedelta(days=index)), meal_type=slot, source_plan="synthetic-source", production_plan=f"synthetic-pp-{index}-{slot}", base_student_count=257, excluded_count=0, planned_headcount=257, menu="Demo dish", adjustment_reason=None))
		return week

	def previous(self):
		self.week.previous = copy.deepcopy(self.week)

	def test_empty_new_week_can_be_saved_before_initialization(self):
		self.week = self.make_week(meals=False)
		self.week.population_snapshot = None
		self.week.population_basis = None
		self.module.validate_week(self.week)
		self.assertEqual(self.week.status, "待编排")
		self.assertEqual(getdate(self.week.week_end), dt.date(2026, 10, 30))

	def test_copy_reads_approved_effective_meals_instead_of_original_references(self):
		source = self.make_week()
		source.name = "synthetic-source-week"
		self.week.source_week = source.name
		effective = copy.deepcopy(source.meals)
		effective[0].production_plan = "synthetic-approved-replacement"
		adjustments = types.ModuleType("ione_core.meal_adjustments")
		adjustments.get_effective_meals = Mock(return_value=effective)
		with patch.dict(sys.modules, {"ione_core.meal_adjustments": adjustments}), patch.object(self.module, "_week", return_value=source):
			plans = self.module._source_plans(self.week)
		self.assertEqual(plans[0][2], "synthetic-approved-replacement")
		self.assertNotEqual(plans[0][2], source.meals[0].production_plan)

	def test_initial_rows_require_managed_initialization(self):
		with self.assertRaises(ValidationFailed):
			self.module.validate_week(self.week)
		with self.module._managed():
			self.module.validate_week(self.week)
		self.assertEqual(self.week.status, "编排草稿")

	def test_native_amendment_clears_previous_demand_and_requires_cancelled_source(self):
		source = self.make_week()
		source.name = "synthetic-cancelled-week"
		source.docstatus = 2
		source.revision = 4
		self.week.update({
			"__islocal": 1, "amended_from": source.name, "company": "School B",
			"week_start": "2026-11-02", "raw_material_warehouse": "Unrelated warehouse",
			"academic_year": "wrong-year", "academic_term": "wrong-term",
			"stock_reviewed": 1, "material_request": "old-request",
			"population_snapshot": '{"old-roster":true}', "population_basis": "old basis",
			"population_as_of": "2026-10-01 12:00:00", "procurement_snapshot": '{"old-demand":true}',
		})
		with patch.object(self.module, "_week", return_value=source) as load_source:
			self.module.validate_week(self.week)
			load_source.assert_called_once_with(source.name, "amend")
		self.assertEqual(self.week.source_week, source.name)
		self.assertEqual(self.week.template_week_start, source.week_start)
		self.assertEqual(self.week.revision, 5)
		self.assertEqual(self.week.meals, [])
		self.assertEqual(self.week.stock_reviewed, 0)
		for field in ("population_snapshot", "population_basis", "population_as_of", "material_request", "procurement_snapshot"):
			self.assertIsNone(self.week[field])
		for field in ("company", "week_start", "raw_material_warehouse", "academic_year", "academic_term"):
			self.assertEqual(self.week[field], source[field])
		self.assertEqual(self.week.status, "待编排")
		self.assertTrue(self.week.active_week_key)
		source.docstatus = 1
		with patch.object(self.module, "_week", return_value=source):
			with self.assertRaises(ValidationFailed):
				self.module.validate_week(self.week)

	def test_active_week_key_is_maintained_by_server_and_released_on_cancel(self):
		self.previous()
		self.week.active_week_key = "forged-key"
		self.module.validate_week(self.week)
		self.assertNotEqual(self.week.active_week_key, "forged-key")
		self.assertEqual(len(self.week.active_week_key), 64)
		self.previous()
		self.week.docstatus = 2
		self.module.validate_week(self.week)
		self.assertIsNone(self.week.active_week_key)

	def test_week_requires_monday_and_exact_25_distinct_slots(self):
		self.week.week_start = "2026-10-27"
		with self.assertRaises(ValidationFailed):
			self.module.validate_week(self.week)
		self.week = self.make_week()
		self.previous()
		self.week.meals.pop()
		with self.assertRaises(ValidationFailed):
			self.module.validate_week(self.week)
		self.week = self.make_week()
		self.previous()
		self.week.meals[-1].meal_type = self.week.meals[-2].meal_type
		with self.assertRaises(ValidationFailed):
			self.module.validate_week(self.week)

	def test_existing_meals_cannot_be_cleared_to_orphan_production_plans(self):
		self.previous()
		self.week.meals = []
		with self.assertRaises(ValidationFailed):
			self.module.validate_week(self.week)

	def test_readonly_population_and_bound_plan_fields_cannot_be_forged(self):
		for field, value in (("stock_reviewed", 1), ("population_snapshot", '{"forged":1}'), ("company", "School B")):
			self.week = self.make_week()
			self.previous()
			self.week[field] = value
			with self.assertRaises(ValidationFailed):
				self.module.validate_week(self.week)
		for field, value in (("base_student_count", 999), ("planned_headcount", 999), ("production_plan", "unrelated-plan")):
			self.week = self.make_week()
			self.previous()
			self.week.meals[0][field] = value
			with self.assertRaises(ValidationFailed):
				self.module.validate_week(self.week)

	def test_exclusion_requires_reason_and_a_whole_nonnegative_count_below_population(self):
		for excluded in (-1, "1.5", 257, "NaN", "Infinity"):
			self.week = self.make_week()
			self.previous()
			self.week.meals[0].excluded_count = excluded
			self.week.meals[0].adjustment_reason = "Confirmed meal absence"
			with self.assertRaises(ValidationFailed):
				self.module.validate_week(self.week)
		self.week = self.make_week()
		self.previous()
		self.week.meals[0].excluded_count = 1
		with self.assertRaises(ValidationFailed):
			self.module.validate_week(self.week)

	def test_exclusion_updates_bound_dish_quantities_and_invalidates_stock_review(self):
		self.week.stock_reviewed = 1
		self.week.procurement_snapshot = '{"old":1}'
		self.previous()
		self.week.meals[0].excluded_count = 7
		self.week.meals[0].adjustment_reason = "Confirmed absence"
		plans = {}
		for meal in self.week.meals:
			plans[meal.production_plan] = Doc(docstatus=0, po_items=[Doc(planned_qty=257), Doc(planned_qty=257)], mr_items=[Doc(quantity=10)])
		with patch.object(self.module, "_bound_plan", side_effect=lambda doc, row: plans[row.production_plan]):
			self.module.validate_week(self.week)
		self.assertEqual(self.week.meals[0].planned_headcount, 250)
		self.assertEqual([row.planned_qty for row in plans[self.week.meals[0].production_plan].po_items], [250, 250])
		self.assertEqual(self.week.stock_reviewed, 0)
		self.assertIsNone(self.week.procurement_snapshot)
		self.assertEqual(self.week.revision, 2)

	def test_adjusting_headcount_after_submission_or_request_is_rejected(self):
		for values in ({"docstatus": 1}, {"material_request": "synthetic-mr"}):
			self.week = self.make_week()
			self.week.update(values)
			self.previous()
			self.week.meals[0].excluded_count = 1
			self.week.meals[0].adjustment_reason = "Confirmed absence"
			with self.assertRaises(ValidationFailed):
				self.module.validate_week(self.week)

	def test_guest_is_denied_before_document_access(self):
		self.frappe.session.user = "Guest"
		with self.assertRaises(AuthenticationFailed):
			self.module.refresh_population("synthetic-week")
		self.frappe.get_doc.assert_not_called()

	def test_refresh_requires_both_document_write_and_planning_role(self):
		self.frappe.get_roles.return_value = ["Employee"]
		with patch.object(self.module, "_population") as population:
			with self.assertRaises(PermissionDenied):
				self.module.refresh_population("synthetic-week")
			population.assert_not_called()
		self.frappe.get_roles.return_value = ["食谱编排员"]
		self.week.allowed = False
		with self.assertRaises(PermissionDenied):
			self.module.refresh_population("synthetic-week")

	def test_initialization_creates_25_dated_plans_from_new_education_counts(self):
		self.week = self.make_week(meals=False)
		self.week.template_week_start = "2026-10-12"
		source = Doc(name="synthetic-source", po_items=[Doc(item_code="synthetic-dish", bom_no="synthetic-bom", stock_uom="portion", warehouse="Finished A", description="Demo dish")])
		created = []
		def load_doc(*args):
			if isinstance(args[0], dict):
				values = copy.deepcopy(args[0])
				values["po_items"] = [Doc(row) for row in values["po_items"]]
				plan = Doc(values)
				created.append(plan)
				return plan
			return self.week if args[0] == "Meal Planning Week" else source
		self.frappe.get_doc.side_effect = load_doc
		self.frappe.db.get_value.return_value = "Demo dish"
		population = {str(day): {"total": 257, "roster_hash": "synthetic-hash"} for day in self.module._dates(self.week)}
		sources = [(dt.date(2026, 10, 12) + dt.timedelta(days=day), slot, f"source-{day}-{slot}") for day in range(5) for slot in self.module.SLOTS]
		with patch.object(self.module, "_population", return_value=population), patch.object(self.module, "_source_plans", return_value=sources), patch.object(self.module, "_recipe_signature", return_value="recipe-hash"), patch.object(self.module, "share_linked_plans") as share:
			result = self.module.initialize_week(self.week.name)
			share.assert_called_once_with(self.week)
		self.assertEqual(result["meals"], 25)
		self.assertEqual(len(created), 25)
		self.assertEqual(len({plan.name for plan in created}), 25)
		self.assertEqual({plan.custom_meal_headcount for plan in created}, {257})
		self.assertEqual({row.planned_qty for plan in created for row in plan.po_items}, {257})
		self.assertEqual({getdate(plan.custom_meal_date) for plan in created}, set(self.module._dates(self.week)))
		self.assertEqual(set(plan.custom_meal_type for plan in created), set(self.module.SLOTS))
		self.assertEqual(self.week.stock_reviewed, 0)

	def test_refresh_updates_every_meal_and_clears_previous_stock_review(self):
		self.week.stock_reviewed = 1
		self.week.procurement_snapshot = '{"reviewed_basis_hash":"old"}'
		self.week.meals[0].excluded_count = 2
		self.week.meals[0].adjustment_reason = "Confirmed absence"
		plans = {row.production_plan: Doc(docstatus=0, po_items=[Doc(planned_qty=257)], mr_items=[Doc(quantity=10)]) for row in self.week.meals}
		population = {str(day): {"total": 260, "roster_hash": "new"} for day in self.module._dates(self.week)}
		with patch.object(self.module, "_population", return_value=population), patch.object(self.module, "_bound_plan", side_effect=lambda doc, row: plans[row.production_plan]):
			self.module.refresh_population(self.week.name)
		self.assertEqual(self.week.meals[0].planned_headcount, 258)
		self.assertEqual(self.week.meals[1].planned_headcount, 260)
		self.assertEqual(plans[self.week.meals[0].production_plan].po_items[0].planned_qty, 258)
		self.assertEqual(self.week.stock_reviewed, 0)
		self.assertIsNone(self.week.procurement_snapshot)

	def test_submit_checks_review_hash_before_submitting_any_production_plan(self):
		self.week.stock_reviewed = 1
		self.week.docstatus = 1  # Frappe runs before_submit with the parent already set to 1.
		population = {str(day): {"total": 257, "roster_hash": "same"} for day in self.module._dates(self.week)}
		self.week.population_snapshot = json.dumps({"dates": population, "recipe_hashes": {row.production_plan: "recipe" for row in self.week.meals}})
		self.week.procurement_snapshot = '{"reviewed_basis_hash":"reviewed"}'
		plans = {row.production_plan: Doc(name=row.production_plan, docstatus=0, po_items=[Doc(planned_qty=257)]) for row in self.week.meals}
		for plan in plans.values():
			plan.flags = types.SimpleNamespace(ignore_permissions=False)
			plan.submit = Mock(side_effect=lambda plan=plan: plan.update(docstatus=1))
		procurement = types.ModuleType("ione_core.meal_procurement")
		def prepare(parent):
			self.assertEqual(parent.docstatus, 1)
			self.assertTrue(all(plan.docstatus == 0 for plan in plans.values()))
			return {"blockers": [], "plans": {name: [Doc(quantity=10)] for name in plans}, "snapshot": {"basis_hash": "changed"}}
		procurement.prepare_procurement_rows = Mock(side_effect=prepare)
		reservation = types.ModuleType("ione_core.meal_native_reservations")
		reservation.ensure_current_native_reservation_inputs = Mock()
		with patch.dict(sys.modules, {"ione_core.meal_procurement": procurement, "ione_core.meal_native_reservations": reservation}), patch.object(self.module, "verify_purchase_weight_basis", return_value={"confirmed": True}), patch.object(self.module, "_population", return_value=population), patch.object(self.module, "_bound_plan", side_effect=lambda doc, row: plans[row.production_plan]), patch.object(self.module, "_recipe_signature", return_value="recipe"):
			with self.assertRaises(ValidationFailed):
				self.module.submit_week(self.week)
			self.assertTrue(all(plan.docstatus == 0 and plan.saved == 0 for plan in plans.values()))
			reservation.ensure_current_native_reservation_inputs.assert_not_called()
			self.week.procurement_snapshot = '{"reviewed_basis_hash":"changed"}'
			self.module.submit_week(self.week)
			reservation.ensure_current_native_reservation_inputs.assert_called_once_with(self.week.company)
		self.assertTrue(all(plan.docstatus == 1 and plan.saved == 1 for plan in plans.values()))
		self.assertEqual(self.week.status, "已审核")
		self.assertEqual(json.loads(self.week.procurement_snapshot)["basis_hash"], "changed")

	def production_plan(self):
		return Doc(company="School A", custom_meal_week="synthetic-week", custom_meal_date="2026-10-26", custom_meal_type="早餐", custom_meal_headcount=257, for_warehouse="Raw A", docstatus=0, po_items=[Doc(item_code="synthetic-dish", bom_no="synthetic-bom", planned_qty=257, warehouse="Finished A")], mr_items=[])

	def test_production_plan_cannot_detach_itself_to_bypass_management(self):
		plan = self.production_plan()
		plan.previous = copy.deepcopy(plan)
		plan.custom_meal_week = None
		plan.po_items[0].planned_qty = 999
		with self.assertRaises(ValidationFailed):
			self.module.validate_production_plan(plan)

	def test_managed_production_plan_cannot_be_submitted_independently(self):
		plan = self.production_plan()
		plan.previous = copy.deepcopy(plan)
		plan.docstatus = 1
		with self.assertRaises(ValidationFailed):
			self.module.validate_production_plan(plan)

	def test_managed_production_plan_cannot_be_cancelled_independently(self):
		plan = self.production_plan()
		plan.docstatus = 1
		plan.previous = copy.deepcopy(plan)
		plan.docstatus = 2
		with self.assertRaises(ValidationFailed):
			self.module.validate_production_plan(plan)

	def test_production_plan_unchanged_save_and_managed_update_are_allowed(self):
		plan = self.production_plan()
		plan.previous = copy.deepcopy(plan)
		self.module.validate_production_plan(plan)
		with self.module._managed():
			plan.po_items[0].planned_qty = 250
			self.module.validate_production_plan(plan)

	def test_native_lifecycle_hooks_cover_cancel_and_submitted_updates(self):
		# Frappe skips validate for cancel and update_after_submit. Check the
		# lifecycle wiring as well as calling the guard directly above.
		tree = ast.parse((Path(__file__).parents[1] / "hooks.py").read_text(encoding="utf-8"))
		assignment = next(node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "doc_events" for target in node.targets))
		events = ast.literal_eval(assignment.value)["Production Plan"]
		for event in ("validate", "before_cancel", "before_update_after_submit"):
			self.assertEqual(events.get(event), "ione_core.meal_planning.validate_production_plan")

	def test_submit_requires_stock_review_before_population_or_procurement(self):
		with patch.object(self.module, "_population") as population:
			with self.assertRaises(ValidationFailed):
				self.module.submit_week(self.week)
			population.assert_not_called()

	def test_existing_week_owner_cannot_be_reassigned_even_by_managed_update(self):
		self.previous()
		self.week.owner = "another-operator@example.test"
		with self.assertRaises(PermissionDenied):
			self.module.validate_week(self.week)
		with self.module._managed(), self.assertRaises(PermissionDenied):
			self.module.validate_week(self.week)

	def test_submit_rechecks_original_owner_to_reject_forged_self_approval(self):
		self.frappe.session.user = "operator@example.test"
		self.week.owner = "another-operator@example.test"
		with patch.object(self.module, "_population") as population, self.assertRaises(PermissionDenied):
			self.module.submit_week(self.week)
		population.assert_not_called()
		self.frappe.db.get_value.assert_called_with("Meal Planning Week", self.week.name, "owner", for_update=True)
		self.week.owner = "operator@example.test"
		with self.assertRaises(PermissionDenied):
			self.module.submit_week(self.week)


if __name__ == "__main__":
	unittest.main(verbosity=2)

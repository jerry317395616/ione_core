"""Synthetic roster tests; never connect to a site or use real child records."""

import copy
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class ValidationFailed(Exception):
	pass


class PermissionDenied(Exception):
	pass


class PopulationTests(unittest.TestCase):
	def setUp(self):
		self.data = {
			"Company": [{"name": "School A"}],
			"Academic Year": [{"name": "2026-2027", "year_start_date": "2026-09-01", "year_end_date": "2027-08-31", "company": None}],
			"Academic Term": [{"name": "Autumn", "academic_year": "2026-2027", "term_start_date": "2026-09-01", "term_end_date": "2027-01-15", "company": None}],
			"Program": [{"name": "Education", "company": None}],
			"Student Batch Name": [
				{"name": "Group A", "company": "School A", "disabled": 0, "start_date": None, "end_date": None},
				{"name": "Group B", "company": "School A", "disabled": 0, "start_date": None, "end_date": None},
			],
			"Student": [self.student("synthetic-001", "Group A"), self.student("synthetic-002", "Group B")],
		}
		self.groups = [
			{"name": "Old A", "batch": "Group A", "disabled": 0, "docstatus": 0, "academic_year": "2026-2027", "academic_term": "Autumn", "program": "Education"},
			{"name": "Old B", "batch": "Group B", "disabled": 0, "docstatus": 0, "academic_year": "2026-2027", "academic_term": "Autumn", "program": "Education"},
		]
		self.members = [
			{"student": "synthetic-001", "parent": "Old A", "parenttype": "Student Group", "active": 1},
			{"student": "synthetic-002", "parent": "Old B", "parenttype": "Student Group", "active": 1},
		]
		self.field_exists = True
		self.frappe = types.ModuleType("frappe")
		self.frappe.ValidationError = ValidationFailed
		self.frappe.PermissionError = PermissionDenied
		self.frappe.throw = lambda message, cls: (_ for _ in ()).throw(cls(message))
		self.frappe.get_all = Mock(side_effect=self.get_all)
		self.frappe.get_meta = Mock(return_value=types.SimpleNamespace(has_field=lambda field: self.field_exists))
		self.frappe.get_roles = Mock(return_value=["System Manager"])
		self.frappe.db = types.SimpleNamespace(
			sql=Mock(side_effect=self.sql), table_exists=Mock(return_value=True),
			set_value=Mock(), savepoint=Mock(), rollback=Mock(),
		)
		self.modules = patch.dict(sys.modules, {"frappe": self.frappe})
		self.modules.start()
		spec = importlib.util.spec_from_file_location("synthetic_meal_population", Path(__file__).parents[1] / "meal_population.py")
		self.module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.module)

	def tearDown(self):
		self.modules.stop()

	@staticmethod
	def student(name, batch=None, **values):
		row = {"name": name, "custom_student_batch": batch, "enabled": 1, "alumni": 0, "docstatus": 0, "joining_date": None, "date_of_leaving": None}
		row.update(values)
		return row

	def get_all(self, doctype, fields, **kwargs):
		self.assertEqual(kwargs, {"limit_page_length": 0})
		return [{key: copy.deepcopy(row.get(key)) for key in fields} for row in self.data[doctype]]

	def sql(self, statement, **kwargs):
		self.assertEqual(kwargs, {"as_dict": True})
		if "FROM tabStudent ORDER" in statement:
			return copy.deepcopy(self.data["Student"])
		if "FROM `tabStudent Batch Name`" in statement:
			return copy.deepcopy(self.data["Student Batch Name"])
		if "FROM `tabStudent Group Student`" in statement:
			return copy.deepcopy(self.members)
		if "FROM `tabStudent Group`" in statement:
			return copy.deepcopy(self.groups)
		raise AssertionError(statement)

	def snapshot(self, **kwargs):
		return self.module.get_population_snapshot("School A", "2026-10-26", **kwargs)

	def migration(self, **kwargs):
		return self.module.migrate_legacy_student_batches("School A", "2026-2027", "Autumn", **kwargs)

	def empty_targets(self):
		for student in self.data["Student"]:
			student["custom_student_batch"] = None
		for batch in self.data["Student Batch Name"]:
			batch["company"] = None

	def test_import_performs_no_database_reads(self):
		self.frappe.get_all.assert_not_called()
		self.frappe.get_meta.assert_not_called()
		self.frappe.db.sql.assert_not_called()

	def test_aggregate_privacy_and_normal_read_never_uses_legacy_tables(self):
		result = self.snapshot()
		self.assertEqual(result["total"], 2)
		self.assertEqual(result["classes"], [{"student_batch": "Group A", "count": 1}, {"student_batch": "Group B", "count": 1}])
		self.assertEqual(result["academic_term"], "Autumn")
		self.assertIn("预计", result["basis"])
		self.assertNotIn("synthetic-", json.dumps(result))
		self.assertNotIn("Student Group", json.dumps(result))
		self.frappe.db.sql.assert_not_called()
		self.frappe.db.set_value.assert_not_called()

	def test_hash_is_order_independent_and_changes_with_roster_or_day(self):
		first = self.snapshot()["roster_hash"]
		self.data["Student"].reverse()
		self.assertEqual(self.snapshot()["roster_hash"], first)
		self.data["Student"][0]["custom_student_batch"] = "Group A"
		self.assertNotEqual(self.snapshot()["roster_hash"], first)
		other_day = self.module.get_population_snapshot("School A", "2026-10-27")["roster_hash"]
		self.assertNotEqual(other_day, self.snapshot()["roster_hash"])

	def test_status_and_enrollment_date_boundaries(self):
		self.data["Student"] += [
			self.student("disabled", "Group A", enabled=0), self.student("alumni", "Group A", alumni=1),
			self.student("cancelled", "Group A", docstatus=2),
			self.student("future", "Group A", joining_date="2026-10-27"),
			self.student("left-today", "Group A", date_of_leaving="2026-10-26"),
			self.student("joins-today", "Group A", joining_date="2026-10-26"),
			self.student("leaves-tomorrow", "Group A", date_of_leaving="2026-10-27"),
		]
		self.assertEqual(self.snapshot()["total"], 4)

	def test_explicit_other_company_is_filtered(self):
		self.data["Student Batch Name"][1]["company"] = "School B"
		self.assertEqual(self.snapshot()["total"], 1)

	def test_missing_or_invalid_student_batch_fails_without_leaking_identifier(self):
		for invalid in (None, "unknown-group"):
			self.data["Student"][0]["custom_student_batch"] = invalid
			with self.assertRaises(ValidationFailed) as error:
				self.snapshot()
			self.assertNotIn("synthetic-001", str(error.exception))

	def test_unassigned_students_cannot_be_silently_excluded_as_another_company(self):
		self.data["Student"] += [self.student("unassigned")]
		with self.assertRaises(ValidationFailed):
			self.snapshot()

	def test_batch_company_disabled_dates_and_reversed_dates_fail(self):
		for values in (
			{"company": None}, {"disabled": 1}, {"start_date": "2026-10-27"},
			{"end_date": "2026-10-25"}, {"start_date": "2026-10-27", "end_date": "2026-10-25"},
		):
			batch = self.data["Student Batch Name"][0]
			original = batch.copy()
			batch.update(values)
			with self.assertRaises(ValidationFailed):
				self.snapshot()
			batch.clear()
			batch.update(original)

	def test_batch_dates_are_inclusive(self):
		self.data["Student Batch Name"][0].update(start_date="2026-10-26", end_date="2026-10-26")
		self.assertEqual(self.snapshot()["total"], 2)

	def test_student_reversed_dates_and_duplicate_records_fail(self):
		self.data["Student"][0].update(joining_date="2026-10-20", date_of_leaving="2026-10-01")
		with self.assertRaises(ValidationFailed):
			self.snapshot()
		self.data["Student"][0].update(joining_date=None, date_of_leaving=None)
		self.data["Student"].append(copy.deepcopy(self.data["Student"][0]))
		with self.assertRaises(ValidationFailed):
			self.snapshot()

	def test_missing_field_cannot_fall_back_to_legacy_data(self):
		self.field_exists = False
		with self.assertRaises(ValidationFailed):
			self.snapshot()
		self.frappe.db.sql.assert_not_called()

	def test_period_dates_company_mismatch_and_ambiguous_term_fail(self):
		with self.assertRaises(ValidationFailed):
			self.module.get_population_snapshot("School A", "2027-01-20")
		with self.assertRaises(ValidationFailed):
			self.snapshot(academic_year="wrong-year")
		self.data["Academic Term"].append(dict(self.data["Academic Term"][0], name="Overlap"))
		with self.assertRaises(ValidationFailed):
			self.snapshot()
		self.assertEqual(self.snapshot(academic_term="Autumn")["total"], 2)
		self.data["Academic Year"][0]["company"] = "School B"
		with self.assertRaises(ValidationFailed):
			self.snapshot()

	def test_default_migration_is_read_only_even_before_field_creation(self):
		self.empty_targets()
		self.field_exists = False
		result = self.migration()
		self.assertTrue(result["dry_run"])
		self.assertEqual(result["mapped_students"], 2)
		self.assertEqual(result["student_fields_to_fill"], 2)
		self.assertEqual(result["batch_companies_to_fill"], 2)
		self.assertEqual(result["company_basis"], "single_company_site")
		self.assertNotIn("synthetic-", json.dumps(result))
		self.frappe.db.set_value.assert_not_called()
		self.frappe.db.savepoint.assert_not_called()
		self.assertTrue(all("FOR UPDATE" not in call.args[0] for call in self.frappe.db.sql.call_args_list))

	def test_migration_write_requires_role_and_literal_boolean(self):
		self.frappe.get_roles.return_value = ["Education Manager"]
		with self.assertRaises(PermissionDenied):
			self.migration(dry_run=False)
		self.frappe.get_all.assert_not_called()
		for bad in ("false", "0", 0, None):
			with self.assertRaises(ValidationFailed):
				self.migration(dry_run=bad)
		self.frappe.db.set_value.assert_not_called()

	def test_migration_only_fills_empty_fields_and_does_not_commit(self):
		self.data["Student"][0]["custom_student_batch"] = None
		self.data["Student Batch Name"][0]["company"] = None
		result = self.migration(dry_run=False)
		self.assertFalse(result["dry_run"])
		self.assertEqual(result["student_fields_to_fill"], 1)
		self.assertEqual(result["batch_companies_to_fill"], 1)
		self.assertEqual(self.frappe.db.set_value.call_args_list[0].args, ("Student Batch Name", "Group A", "company", "School A"))
		self.assertEqual(self.frappe.db.set_value.call_args_list[1].args, ("Student", "synthetic-001", "custom_student_batch", "Group A"))
		self.assertEqual(self.frappe.db.set_value.call_count, 2)
		self.frappe.db.savepoint.assert_called_once()

	def test_idempotent_migration_makes_no_writes(self):
		result = self.migration(dry_run=False)
		self.assertEqual(result["student_fields_to_fill"], 0)
		self.assertEqual(result["batch_companies_to_fill"], 0)
		self.frappe.db.set_value.assert_not_called()

	def test_conflicting_existing_batch_is_never_overwritten(self):
		self.data["Student"][0]["custom_student_batch"] = "Group B"
		with self.assertRaises(ValidationFailed):
			self.migration(dry_run=False)
		self.frappe.db.set_value.assert_not_called()

	def test_legacy_duplicate_or_orphan_links_fail_before_writing(self):
		for member in (
			copy.deepcopy(self.members[0]),
			{"student": "missing", "parent": "Old A", "parenttype": "Student Group", "active": 1},
			{"student": "synthetic-001", "parent": "missing", "parenttype": "Student Group", "active": 1},
		):
			self.members.append(member)
			with self.assertRaises(ValidationFailed):
				self.migration(dry_run=False)
			self.members.pop()
		self.frappe.db.set_value.assert_not_called()

	def test_multiple_legacy_groups_must_not_collapse_to_one_batch(self):
		self.groups[1]["batch"] = "Group A"
		with self.assertRaises(ValidationFailed):
			self.migration(dry_run=False)
		self.frappe.db.set_value.assert_not_called()

	def test_multi_company_inference_requires_evidence_for_every_group(self):
		self.empty_targets()
		self.data["Company"].append({"name": "School B"})
		self.data["Student Batch Name"][0]["company"] = "School A"
		with self.assertRaises(ValidationFailed):
			self.migration(dry_run=False)
		self.frappe.db.set_value.assert_not_called()
		self.data["Program"][0]["company"] = "School A"
		self.assertEqual(self.migration()["company_basis"], "education_company_links")

	def test_cross_company_legacy_context_fails(self):
		self.data["Program"][0]["company"] = "School B"
		with self.assertRaises(ValidationFailed):
			self.migration(dry_run=False)
		self.frappe.db.set_value.assert_not_called()

	def test_missing_active_student_assignment_fails_migration_preflight(self):
		self.data["Student"].append(self.student("unmapped"))
		with self.assertRaises(ValidationFailed):
			self.migration(dry_run=False)
		self.frappe.db.set_value.assert_not_called()

	def test_failed_write_rolls_back_to_savepoint(self):
		self.empty_targets()
		self.frappe.db.set_value.side_effect = [None, RuntimeError("simulated failure")]
		with self.assertRaises(RuntimeError):
			self.migration(dry_run=False)
		self.frappe.db.rollback.assert_called_once_with(save_point="meal_student_batch_migration")


if __name__ == "__main__":
	unittest.main(verbosity=2)

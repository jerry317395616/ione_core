"""Native employee directory integration on a paused, email-muted test site."""

import unittest
from unittest.mock import patch
from uuid import uuid4

import frappe

from ione_core import console_employees as E


class EmployeeDirectoryTests(unittest.TestCase):
	def setUp(self):
		assert (
			frappe.local.site.startswith("test_") and frappe.conf.mute_emails and frappe.conf.pause_scheduler
		)
		frappe.set_user("Administrator")
		frappe.db.savepoint("employee_directory_case")
		self.commit = patch.object(frappe.db, "commit", side_effect=AssertionError("Unexpected commit"))
		self.commit.start()
		self.addCleanup(self.rollback)
		self.code = "ED-" + uuid4().hex[:10]
		self.company, self.other = frappe.get_all("Company", pluck="name", limit=2)
		self.gender = frappe.get_all("Gender", pluck="name", limit=1)[0]

	def rollback(self):
		self.commit.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="employee_directory_case")
		frappe.clear_cache()

	def user(self, tag, roles):
		return (
			frappe.get_doc(
				dict(
					doctype="User",
					email=f"{self.code}-{tag}@example.invalid".lower(),
					first_name=self.code,
					user_type="System User",
					send_welcome_email=0,
					roles=[dict(role=role) for role in roles],
				)
			)
			.insert()
			.name
		)

	def scoped_role(self, *, directory=True, edit=True):
		from frappe.permissions import setup_custom_perms
		from rehab.system_admin_bootstrap import RULE_FIELDS

		role = frappe.get_doc(dict(doctype="Role", role_name=self.code, desk_access=1)).insert().name
		perms = [
			("Company", dict(read=1)),
			("Department", dict(read=1)),
			("Gender", dict(read=1)),
			("Designation", dict(select=1)),
			("Employee", dict(select=1)),
			("User", dict(read=1)),
		]
		if directory:
			perms.append((E.ACCESS, dict(read=1, create=int(edit), write=int(edit))))
		for dt, rights in perms:
			setup_custom_perms(dt)
			rules = dict.fromkeys(RULE_FIELDS, 0) | rights
			frappe.get_doc(
				dict(
					doctype="Custom DocPerm",
					parent=dt,
					parenttype="DocType",
					parentfield="permissions",
					role=role,
					**rules,
				)
			).insert(ignore_permissions=True)
		actor = self.user("actor", [role])
		frappe.clear_cache()
		return actor

	def employee(self, **values):
		return E.save(
			dict(
				values=dict(
					first_name=self.code,
					gender=self.gender,
					company=self.company,
					date_of_birth="1990-01-01",
					date_of_joining="2025-01-01",
					employee_number=self.code,
				)
				| values
			)
		)

	def department(self, company, suffix):
		from frappe.utils.nestedset import get_root_of

		return (
			frappe.get_doc(
				dict(
					doctype="Department",
					department_name=self.code + suffix,
					company=company,
					parent_department=get_root_of("Department"),
				)
			)
			.insert()
			.name
		)

	def test_directory_role_can_create_and_edit_without_hr_access(self):
		actor = self.scoped_role()
		department = self.department(self.company, "home")
		post = frappe.get_doc(dict(doctype="Designation", designation_name=self.code)).insert().name
		frappe.set_user(actor)
		self.assertIn(post, {row["value"] for row in E.options("designation", self.code)})
		prior_users = frappe.db.count("User")
		created = self.employee(department=department, designation=post)
		self.assertEqual(frappe.db.count("User"), prior_users)
		self.assertIsNone(frappe.db.get_value("Employee", created["name"], "user_id"))
		self.assertFalse(frappe.has_permission("Employee", "read", doc=created["name"]))
		self.assertFalse(frappe.has_permission("Employee", "write", doc=created["name"]))
		self.assertEqual(E.listing(employee_number=self.code)["total"], 1)
		self.assertEqual(E.detail(created["name"])["doc"]["department"], department)
		E.save(dict(**created, values={"first_name": self.code + " edited"}))
		with self.assertRaises(frappe.TimestampMismatchError):
			E.save(dict(**created, values={"first_name": "stale"}))

	def test_sensitive_fields_and_lifecycle_changes_are_not_basic_edits(self):
		created = self.employee()
		actor = self.scoped_role()
		frappe.set_user(actor)
		view = E.detail(created["name"])["doc"]
		for field in ("bank_ac_no", "ctc", "status", "user_id", "create_user_automatically"):
			with self.assertRaises(frappe.ValidationError):
				E.save(dict(**created, values={field: "forged"}))
			if field != "status":
				self.assertNotIn(field, view)

	def test_company_and_department_limit_applies_to_list_and_edit(self):
		dept = self.department(self.company, "visible")
		hidden_dept = self.department(self.company, "hidden")
		visible = self.employee(department=dept)
		hidden = self.employee(department=hidden_dept, employee_number=self.code + "2")
		actor = self.scoped_role()
		for dt, name in (("Company", self.company), ("Department", dept)):
			frappe.get_doc(
				dict(doctype="User Permission", user=actor, allow=dt, for_value=name, apply_to_all_doctypes=1)
			).insert()
		frappe.clear_cache()
		frappe.set_user(actor)
		self.assertEqual({r.name for r in E.listing(keyword=self.code)["data"]}, {visible["name"]})
		with self.assertRaises(frappe.PermissionError):
			E.detail(hidden["name"])
		with self.assertRaises(frappe.PermissionError):
			self.employee(company=self.other, department="")
		with self.assertRaises(frappe.PermissionError):
			self.employee(department="", employee_number=self.code + "3")

	def test_duplicate_code_and_cross_company_department_rejected(self):
		self.employee()
		with self.assertRaisesRegex(frappe.ValidationError, "已存在此工号"):
			self.employee()
		dept = self.department(self.other, "other")
		with self.assertRaisesRegex(frappe.ValidationError, "本公司"):
			self.employee(department=dept, employee_number=self.code + "2")

	def test_resignation_checks_active_reports_and_requires_date(self):
		employee = self.employee()
		report = self.employee(employee_number=self.code + "2", reports_to=employee["name"])
		frappe.set_user(self.scoped_role())
		command = dict(**employee, status="Left", relieving_date="2026-01-01", confirmed=True)
		self.assertTrue(E.preview_status(employee["name"])["has_active_reports"])
		with self.assertRaisesRegex(frappe.ValidationError, "直属下属"):
			E.set_status(command)
		E.save(dict(**report, values={"reports_to": ""}))
		with self.assertRaises(frappe.ValidationError):
			E.set_status({**command, "relieving_date": ""})
		E.set_status(command)
		self.assertEqual(frappe.db.get_value("Employee", employee["name"], "status"), "Left")

	def test_linked_status_changes_require_native_maintenance_and_fresh_account_version(self):
		user = self.user("linked", ["Rehab Therapist"])
		native = frappe.get_doc(
			dict(
				doctype="Employee",
				first_name=self.code,
				gender=self.gender,
				company=self.company,
				date_of_birth="1990-01-01",
				date_of_joining="2025-01-01",
				user_id=user,
			)
		).insert()
		frappe.set_user(self.scoped_role())
		before_user = str(frappe.db.get_value("User", user, "modified"))
		updated = E.save(
			dict(
				name=native.name, modified=str(native.modified), values={"first_name": self.code + " updated"}
			)
		)
		self.assertEqual(str(frappe.db.get_value("User", user, "modified")), before_user)
		self.assertFalse(E.preview_status(native.name)["can_status"])
		cmd = dict(**updated, status="Suspended", account_modified=before_user, confirmed=True)
		with self.assertRaises(frappe.PermissionError):
			E.set_status(cmd)
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.TimestampMismatchError):
			E.set_status({**cmd, "account_modified": "stale"})
		E.set_status(cmd)
		self.assertFalse(frappe.db.get_value("User", user, "enabled"))

	def test_select_only_without_directory_grant_does_not_open_directory(self):
		frappe.set_user(self.scoped_role(directory=False))
		with self.assertRaises(frappe.PermissionError):
			E.listing()

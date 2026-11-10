import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class TestConsoleDepartments(TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe.whitelist = lambda **kwargs: lambda fn: fn
		for name in ["ValidationError", "PermissionError", "TimestampMismatchError"]:
			setattr(self.frappe, name, type(name, (Exception,), {}))

		def fail(message, kind):
			raise kind(message)

		self.frappe.throw = fail
		self.frappe.db = Mock()
		self.frappe.db.exists.return_value = False
		self.frappe.cache = Mock()
		self.doc = SimpleNamespace(
			name="QA - A",
			company="A",
			department_name="QA",
			parent_department="Root",
			is_group=0,
			disabled=0,
			lft=2,
			rgt=5,
			modified="v1",
			has_permission=Mock(return_value=True),
			check_permission=Mock(),
			update=Mock(),
			save=Mock(),
		)
		self.frappe.get_doc = Mock(return_value=self.doc)
		management = ModuleType("ione_core.console_role_management")
		management.no_store = lambda value: value
		management.payload = lambda data, fields: data
		roles = ModuleType("ione_core.console_roles")
		roles.RoleReadQuery = Mock()
		roles.integer = lambda value, minimum, maximum: int(value)
		navigation = ModuleType("ione_core.navigation")
		navigation.NavigationPolicy = Mock()
		navigation.require_staff = Mock()
		self.modules = patch.dict(
			sys.modules,
			{
				"frappe": self.frappe,
				"ione_core.console_role_management": management,
				"ione_core.console_roles": roles,
				"ione_core.navigation": navigation,
			},
		)
		self.modules.start()
		self.addCleanup(self.modules.stop)
		spec = importlib.util.spec_from_file_location(
			"department_subject", Path(__file__).parents[1] / "console_departments.py"
		)
		self.api = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.api)
		self.permissions = dict(
			can_read=True,
			can_edit=True,
			can_delete=True,
			write_fields=list(self.api.FIELDS),
			read_fields=list(self.api.FIELDS),
		)
		for name, value in [
			("access", (self.permissions, None)),
			("root_name", "Root"),
			("query", [SimpleNamespace(name=self.doc.name)]),
			("lock_tree", None),
		]:
			p = patch.object(self.api, name, return_value=value)
			p.start()
			self.addCleanup(p.stop)

	def test_system_root_is_immutable_even_for_full_crud_actor(self):
		self.doc.parent_department = ""
		flags = self.api.flags(self.doc, self.permissions)
		self.assertTrue(flags["is_root"])
		self.assertFalse(any(flags[right] for right in ["can_edit", "can_rename", "can_delete"]))

	def test_select_permission_cannot_bypass_scoped_read(self):
		with patch.object(self.api, "query", return_value=[]), self.assertRaises(self.frappe.PermissionError):
			self.api.checked("Hidden")
		self.frappe.get_doc.assert_not_called()

	def test_stale_write_is_rejected_before_native_save(self):
		with self.assertRaises(self.frappe.TimestampMismatchError):
			self.api.save_department(
				{"department": self.doc.name, "modified": "old", "values": {"disabled": 1}}
			)
		self.doc.save.assert_not_called()

	def test_identity_and_internal_tree_fields_are_never_mass_assignable(self):
		for field in ["department_name", "company", "lft", "rgt", "owner", "ignore_permissions"]:
			with self.subTest(field=field), self.assertRaises(self.frappe.PermissionError):
				self.api.values_of({field: "forbidden"}, self.permissions, self.doc)

	def test_parent_must_be_active_group_in_same_company(self):
		for changes in [dict(company="B"), dict(is_group=0), dict(disabled=1)]:
			parent = SimpleNamespace(
				**(dict(name="Other", company="A", is_group=1, disabled=0, lft=10) | changes)
			)
			with (
				self.subTest(changes=changes),
				patch.object(self.api, "checked", return_value=parent),
				self.assertRaises(self.frappe.ValidationError),
			):
				self.api.values_of({"parent_department": "Other"}, self.permissions, self.doc)

	def test_self_and_descendant_parent_are_rejected(self):
		for lft in [2, 3, 5]:
			parent = SimpleNamespace(name="Child", company="A", is_group=1, disabled=0, lft=lft)
			with (
				patch.object(self.api, "checked", return_value=parent),
				self.assertRaises(self.frappe.ValidationError),
			):
				self.api.values_of({"parent_department": "Child"}, self.permissions, self.doc)

	def test_group_with_children_cannot_be_converted_to_leaf(self):
		self.frappe.db.exists.return_value = True
		with self.assertRaises(self.frappe.ValidationError):
			self.api.values_of({"is_group": 0}, self.permissions, self.doc)

	def test_sensitive_change_needs_matching_preview_and_preserves_native_save(self):
		with (
			patch.object(self.api, "preview_data", return_value=(self.doc, {"disabled": 1}, ["Confirm"])),
			patch.object(self.api, "intent", return_value="intent"),
		):
			self.frappe.cache.get_value.return_value = "different"
			with self.assertRaises(self.frappe.TimestampMismatchError):
				self.api.save_department({"token": "a" * 64})
			self.doc.save.assert_not_called()
			self.frappe.cache.get_value.return_value = "intent"
			self.api.save_department({"token": "a" * 64})
		self.doc.update.assert_called_once_with({"disabled": 1})
		self.doc.save.assert_called_once_with()

	def test_delete_confirmation_and_references_cannot_be_bypassed(self):
		with self.assertRaises(self.frappe.ValidationError):
			self.api.delete_department(
				{"department": self.doc.name, "modified": "v1", "confirm_name": "wrong"}
			)
		with (
			patch.object(self.api, "has_links", return_value=True),
			self.assertRaises(self.frappe.ValidationError),
		):
			self.api.delete_department(
				{"department": self.doc.name, "modified": "v1", "confirm_name": self.doc.name}
			)

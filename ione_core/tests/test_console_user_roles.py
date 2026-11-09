import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class TestConsoleUserRoles(TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe.whitelist = lambda **kwargs: lambda fn: fn
		self.frappe.PermissionError = type("PermissionError", (Exception,), {})
		self.frappe.ValidationError = type("ValidationError", (Exception,), {})
		self.frappe.TimestampMismatchError = type("TimestampMismatchError", (Exception,), {})
		self.frappe.throw = lambda message, kind: self.raise_error(message, kind)
		self.frappe.local = SimpleNamespace(response_headers={})
		self.frappe.clear_cache = Mock()
		self.doc = SimpleNamespace(
			name="target@example.test",
			full_name="Target",
			email="target@example.test",
			enabled=1,
			user_type="System User",
			modified="v1",
			roles=[SimpleNamespace(role="Desk")],
			role_profiles=[],
			role_profile_name=None,
			check_permission=Mock(),
			has_permission=Mock(return_value=True),
			save=Mock(),
		)
		self.doc.set = lambda field, rows: setattr(self.doc, field, [SimpleNamespace(**row) for row in rows])
		self.frappe.get_doc = Mock(return_value=self.doc)
		self.creation = ModuleType("ione_core.console_user_creation")
		self.creation.assignable_roles = Mock(
			return_value=[
				SimpleNamespace(name="Desk", desk_access=1),
				SimpleNamespace(name="Portal", desk_access=0),
			]
		)
		self.creation.field_error = lambda field, text: self.raise_error(text, self.frappe.ValidationError)
		navigation = ModuleType("ione_core.navigation")
		navigation.NavigationPolicy = Mock()
		navigation.require_staff = Mock()
		utils = ModuleType("frappe.utils")
		utils.get_datetime = lambda value: value
		self.modules = patch.dict(
			sys.modules,
			{
				"frappe": self.frappe,
				"ione_core.console_user_creation": self.creation,
				"ione_core.navigation": navigation,
				"frappe.utils": utils,
			},
		)
		self.modules.start()
		spec = importlib.util.spec_from_file_location(
			"console_user_roles_test_subject", Path(__file__).parents[1] / "console_user_roles.py"
		)
		self.api = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.api)
		self.permissions = {
			"can_view": True,
			"can_edit": True,
			"profile_write": True,
			"profile_read": True,
			"is_administrator": False,
		}
		self.access = patch.object(self.api, "access", return_value=self.permissions)
		self.access.start()
		self.body = {
			"user": self.doc.name,
			"modified": "v1",
			"mode": "direct",
			"roles": ["Desk"],
			"role_profiles": [],
		}

	def tearDown(self):
		self.access.stop()
		self.modules.stop()

	@staticmethod
	def raise_error(message, kind):
		raise kind(message)

	def test_native_document_save_and_target_cache_invalidation(self):
		self.api.save_user_roles(self.body)
		self.doc.check_permission.assert_any_call("read")
		self.doc.check_permission.assert_any_call("write")
		self.doc.save.assert_called_once_with()
		self.frappe.clear_cache.assert_called_once_with(user=self.doc.name)
		self.assertEqual([row.role for row in self.doc.roles], ["Desk"])

	def test_readonly_and_record_write_restrictions_are_enforced_server_side(self):
		self.permissions["can_edit"] = False
		with self.assertRaises(self.frappe.PermissionError):
			self.api.save_user_roles(self.body)
		self.permissions["can_edit"] = True
		self.doc.has_permission.return_value = False
		with self.assertRaises(self.frappe.PermissionError):
			self.api.save_user_roles(self.body)
		self.doc.save.assert_not_called()

	def test_stale_versions_and_forged_fields_cannot_overwrite_users(self):
		with self.assertRaises(self.frappe.TimestampMismatchError):
			self.api.save_user_roles(self.body | {"modified": "v0"})
		with self.assertRaises(self.frappe.ValidationError):
			self.api.save_user_roles(self.body | {"enabled": 0})
		self.doc.save.assert_not_called()

	def test_loss_of_last_desk_role_requires_explicit_boolean_confirmation(self):
		with self.assertRaises(self.frappe.ValidationError):
			self.api.save_user_roles(self.body | {"roles": ["Portal"]})
		with self.assertRaises(self.frappe.ValidationError):
			self.api.save_user_roles(self.body | {"roles": [], "confirm_loss_of_desk_access": 1})
		self.api.save_user_roles(self.body | {"roles": [], "confirm_loss_of_desk_access": True})
		self.doc.save.assert_called_once_with()

	def test_profile_mode_clears_manual_roles_and_uses_native_profile_sync(self):
		with patch.object(
			self.api,
			"profile_options",
			return_value=[{"name": "Profile", "roles": ["Desk"], "available": True}],
		):
			self.api.save_user_roles(
				self.body | {"mode": "profiles", "roles": [], "role_profiles": ["Profile"]}
			)
		self.assertEqual(self.doc.roles, [])
		self.assertEqual([row.role_profile for row in self.doc.role_profiles], ["Profile"])

	def test_leaving_profile_mode_detaches_profile_before_direct_role_save(self):
		self.doc.role_profiles = [SimpleNamespace(role_profile="Profile")]
		self.doc.role_profile_name = "Profile"
		self.api.save_user_roles(self.body)
		self.assertEqual(self.doc.role_profiles, [])
		self.assertIsNone(self.doc.role_profile_name)

	def test_protected_users_and_unavailable_roles_cannot_be_changed(self):
		self.doc.name = "Administrator"
		with self.assertRaises(self.frappe.PermissionError):
			self.api.save_user_roles(self.body | {"user": "Administrator"})
		self.doc.name = self.body["user"]
		with self.assertRaises(self.frappe.ValidationError):
			self.api.save_user_roles(self.body | {"roles": ["All"]})
		self.doc.save.assert_not_called()

	def test_no_role_read_permission_stops_before_target_is_loaded(self):
		self.permissions["can_view"] = False
		with self.assertRaises(self.frappe.PermissionError):
			self.api.get_user_roles(self.body["user"])
		self.frappe.get_doc.assert_not_called()

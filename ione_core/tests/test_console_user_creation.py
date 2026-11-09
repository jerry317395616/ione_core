import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class TestConsoleUserCreation(TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe.whitelist = lambda **kwargs: lambda fn: fn
		self.frappe._ = lambda text: text
		self.frappe.ValidationError = type("ValidationError", (Exception,), {})
		self.frappe.PermissionError = type("PermissionError", (Exception,), {})
		self.frappe.DuplicateEntryError = type("DuplicateEntryError", (Exception,), {})
		self.frappe.throw = lambda message, error: self.raise_error(message, error)
		self.frappe.local = SimpleNamespace(response={}, response_headers={})
		self.frappe.conf = {}
		self.frappe.db = SimpleNamespace(exists=Mock(return_value=False))
		self.frappe.has_permission = Mock(return_value=True)
		self.perms = [SimpleNamespace(role="Creator", permlevel=0, create=1, write=1)]
		self.frappe.get_meta = Mock(
			return_value=SimpleNamespace(
				permissions=self.perms,
				get_field=lambda field: SimpleNamespace(permlevel=1 if field == "roles" else 0),
			)
		)
		self.frappe.get_doc = Mock(side_effect=self.make_doc)
		self.frappe.get_all = Mock(return_value=[SimpleNamespace(name="Desk Role", desk_access=1)])
		self.policy = SimpleNamespace(administrator=False, roles={"Creator"})
		navigation = ModuleType("ione_core.navigation")
		navigation.require_staff = Mock()
		navigation.NavigationPolicy = Mock(return_value=self.policy)
		self.navigation = navigation
		utils = ModuleType("frappe.utils")
		utils.validate_email_address = lambda value: value if "@" in value else None
		user = ModuleType("frappe.core.doctype.user.user")
		user.get_all_roles = Mock(return_value=["Desk Role"])
		self.modules = patch.dict(
			sys.modules,
			{
				"frappe": self.frappe,
				"ione_core.navigation": navigation,
				"frappe.utils": utils,
				"frappe.core.doctype.user.user": user,
			},
		)
		self.modules.start()
		spec = importlib.util.spec_from_file_location(
			"console_user_creation_test_subject", Path(__file__).parents[1] / "console_user_creation.py"
		)
		self.api = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.api)
		self.payload = {
			"email": " New@Example.test ",
			"first_name": "Test",
			"enabled": True,
			"credential_mode": "password",
			"password": "test-only-long-password!A8",
			"password_confirm": "test-only-long-password!A8",
		}

	def tearDown(self):
		self.modules.stop()

	@staticmethod
	def raise_error(message, error):
		raise error(message)

	def make_doc(self, data):
		self.doc = SimpleNamespace(
			name=data["email"],
			username=data["username"] or "generated",
			enabled=data["enabled"],
			user_type="System User" if data["roles"] else "Website User",
			flags=SimpleNamespace(email_sent=False),
			insert=Mock(),
		)
		return self.doc

	def test_create_permission_does_not_imply_role_assignment_or_expose_role_catalog(self):
		options = self.api.get_creation_options()
		self.assertTrue(options["can_create"])
		self.assertFalse(options["can_assign_roles"])
		self.assertEqual(options["roles"], [])
		self.frappe.get_all.assert_not_called()

	def test_native_insert_is_used_without_permission_bypass_and_no_password_is_returned(self):
		result = self.api.create_user(self.payload)
		self.doc.insert.assert_called_once_with()
		self.assertEqual(result["name"], "new@example.test")
		self.assertFalse(result["can_login_console"])
		self.assertNotIn("password", result)
		data = self.frappe.get_doc.call_args.args[0]
		self.assertEqual(data["send_welcome_email"], 0)
		self.assertEqual(data["roles"], [])
		self.assertNotIn("ignore_permissions", data)

	def test_no_create_or_nonstaff_access_is_denied_before_document_insert(self):
		self.frappe.has_permission.return_value = False
		with self.assertRaises(self.frappe.PermissionError):
			self.api.create_user(self.payload)
		self.frappe.get_doc.assert_not_called()

	def test_forced_roles_and_hidden_fields_are_rejected(self):
		with self.assertRaises(self.frappe.PermissionError):
			self.api.create_user(self.payload | {"roles": ["Desk Role"]})
		for field, value in [
			("user_type", "System User"),
			("flags", {"ignore_permissions": True}),
			("owner", "Administrator"),
			("role_profiles", []),
		]:
			with self.subTest(field=field), self.assertRaises(self.frappe.ValidationError):
				self.api.create_user(self.payload | {field: value})
		self.frappe.get_doc.assert_not_called()

	def test_role_field_write_permission_enables_native_filtered_role_choices(self):
		self.perms.append(SimpleNamespace(role="Creator", permlevel=1, create=0, write=1))
		self.assertTrue(self.api.get_creation_options()["can_assign_roles"])
		result = self.api.create_user(self.payload | {"roles": ["Desk Role", "Desk Role"]})
		self.assertTrue(result["can_login_console"])
		self.assertEqual(self.frappe.get_doc.call_args.args[0]["roles"], [{"role": "Desk Role"}])

	def test_duplicate_email_and_password_confirmation_have_field_errors(self):
		self.frappe.db.exists.side_effect = lambda dt, filters: dt == "User"
		with self.assertRaises(self.frappe.ValidationError):
			self.api.create_user(self.payload)
		self.assertIn("email", self.frappe.local.response["field_errors"])
		self.frappe.db.exists.side_effect = None
		with self.assertRaises(self.frappe.ValidationError):
			self.api.create_user(self.payload | {"password_confirm": "different"})
		self.assertIn("password_confirm", self.frappe.local.response["field_errors"])

	def test_unconfigured_invitation_cannot_create_a_passwordless_account(self):
		with self.assertRaises(self.frappe.ValidationError):
			self.api.create_user(
				self.payload | {"credential_mode": "invitation", "password": None, "password_confirm": None}
			)
		self.frappe.get_doc.assert_not_called()

	def test_native_invitation_failure_is_not_returned_as_success(self):
		self.frappe.db.exists.side_effect = lambda dt, filters: dt == "Email Account"
		with self.assertRaises(self.frappe.ValidationError):
			self.api.create_user(
				self.payload | {"credential_mode": "invitation", "password": None, "password_confirm": None}
			)
		self.doc.insert.assert_called_once_with()
		self.assertIn("credential_mode", self.frappe.local.response["field_errors"])

	def test_muted_mail_and_disabled_roles_do_not_enable_creation_features(self):
		self.frappe.conf["mute_emails"] = True
		self.frappe.db.exists.return_value = True
		self.assertFalse(self.api.get_creation_options()["email_invitation_available"])
		self.policy.roles.clear()
		self.assertFalse(self.api.get_creation_options()["can_create"])

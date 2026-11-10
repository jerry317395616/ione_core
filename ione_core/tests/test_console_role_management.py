import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class TestConsoleRoleManagement(TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe.whitelist = lambda **kwargs: lambda fn: fn
		for name in ("ValidationError", "PermissionError", "TimestampMismatchError"):
			setattr(self.frappe, name, type(name, (Exception,), {}))
		self.frappe.throw = lambda message, kind: self.raise_error(message, kind)
		self.frappe.local = SimpleNamespace(response_headers={})
		self.frappe.session = SimpleNamespace(user="manager@example.test", sid="session")
		self.frappe.get_roles = Mock(return_value=["Manager"])
		self.frappe.clear_cache = Mock()
		self.frappe.cache = Mock()
		self.frappe.db = SimpleNamespace(
			exists=Mock(return_value=False), after_commit=SimpleNamespace(add=Mock())
		)
		self.doc = SimpleNamespace(
			name="Target",
			modified="v1",
			disabled=0,
			desk_access=1,
			home_page=None,
			restrict_to_domain=None,
			two_factor_auth=0,
			check_permission=Mock(),
			has_permission=Mock(return_value=True),
			save=Mock(),
			insert=Mock(),
			db_set=Mock(),
		)
		self.doc.update = lambda values: [setattr(self.doc, key, value) for key, value in values.items()]
		self.doc.insert.return_value = self.doc
		self.frappe.get_doc = Mock(return_value=self.doc)
		self.frappe.delete_doc = Mock()
		self.frappe.rename_doc = Mock(return_value="Renamed")
		rename_module = ModuleType("frappe.model.rename_doc")
		rename_module.rename_doc = self.frappe.rename_doc
		listing = ModuleType("ione_core.console_roles")
		listing.RoleReadQuery = Mock()
		listing.get_role = Mock()
		listing.get_readable_role = lambda role, for_update=False: self.frappe.get_doc(
			"Role", role, for_update=for_update
		)
		listing.get_roles = Mock()
		listing.require_reader = Mock()
		listing.present = lambda row: {**row, "is_reserved": row["name"] in {"System Manager", "Desk User"}}
		navigation = ModuleType("ione_core.navigation")
		navigation.NavigationPolicy = Mock()
		utils = ModuleType("frappe.utils")
		utils.get_datetime = lambda value: value
		utils.now = lambda: "v2"
		self.modules = patch.dict(
			sys.modules,
			{
				"frappe": self.frappe,
				"frappe.model.rename_doc": rename_module,
				"frappe.utils": utils,
				"ione_core.console_roles": listing,
				"ione_core.navigation": navigation,
			},
		)
		self.modules.start()
		spec = importlib.util.spec_from_file_location(
			"role_management_subject", Path(__file__).parents[1] / "console_role_management.py"
		)
		self.api = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.api)
		self.permissions = {
			"can_create": True,
			"can_edit": True,
			"can_delete": True,
			"write_fields": list(self.api.FIELDS),
			"create_fields": list(self.api.FIELDS),
		}
		self.access = patch.object(self.api, "access", return_value=self.permissions)
		self.access.start()

	def tearDown(self):
		self.access.stop()
		self.modules.stop()

	@staticmethod
	def raise_error(message, kind):
		raise kind(message)

	def change(self, **values):
		return {"role": "Target", "modified": "v1", "values": values}

	def test_create_uses_native_insert_without_permission_bypasses(self):
		self.api.create_role({"values": {"role_name": " New ", "disabled": False}})
		self.frappe.get_doc.assert_called_once_with({"doctype": "Role", "role_name": "New", "disabled": 0})
		self.doc.insert.assert_called_once_with()

	def test_plain_save_locks_record_and_uses_native_save(self):
		self.api.save_role(self.change(home_page="/console"))
		self.frappe.get_doc.assert_called_with("Role", "Target", for_update=True)
		self.doc.save.assert_called_once_with()
		self.assertEqual(self.doc.home_page, "/console")
		self.frappe.db.after_commit.add.assert_called_once_with(self.frappe.clear_cache)

	def test_fixed_role_names_do_not_grant_write_and_native_record_permissions_apply(self):
		self.doc.name = "康复系统管理员"
		self.doc.has_permission.return_value = False
		self.assertFalse(self.api.actions(self.doc, self.permissions)["can_edit"])
		with self.assertRaises(self.frappe.PermissionError):
			self.api.save_role(self.change(home_page="/console"))
		self.doc.save.assert_not_called()

	def test_reserved_and_current_session_roles_cannot_be_deleted_or_renamed(self):
		for name in ("System Manager", "Desk User", "Manager"):
			self.doc.name = name
			flags = self.api.actions(self.doc, self.permissions)
			self.assertFalse(flags["can_delete"])
			self.assertFalse(flags["can_rename"])
		self.doc.name = "Manager"
		self.assertTrue(self.api.actions(self.doc, self.permissions)["can_edit"])

	def test_current_role_critical_changes_are_rejected_but_other_settings_are_allowed(self):
		self.doc.name = "Manager"
		for values in ({"disabled": 1}, {"desk_access": 0}, {"restrict_to_domain": "Other"}):
			with self.subTest(values=values), self.assertRaises(self.frappe.PermissionError):
				self.api.check_self(self.doc, values)
		self.api.check_self(self.doc, {"home_page": "/console", "two_factor_auth": 1})

	def test_builtin_administrator_does_not_treat_every_ordinary_role_as_its_only_access_role(self):
		self.frappe.session.user = "Administrator"
		self.frappe.get_roles.return_value = ["Target"]
		flags = self.api.actions(self.doc, self.permissions)
		self.assertFalse(flags["self_protected"])
		self.assertTrue(flags["can_delete"])
		self.assertTrue(flags["can_rename"])

	def test_own_non_desk_role_can_keep_its_existing_access_flag_when_editing_other_fields(self):
		self.doc.name = "Manager"
		self.doc.desk_access = 0
		self.api.check_self(self.doc, {"desk_access": 0, "home_page": "/console"})

	def test_confirmation_tokens_must_be_strings_even_for_ordinary_edits(self):
		with self.assertRaises(self.frappe.ValidationError):
			self.api.save_role({**self.change(home_page="/console"), "confirmation_token": {"invalid": True}})
		self.doc.save.assert_not_called()

	def test_rejects_stale_versions_before_mutation(self):
		with self.assertRaises(self.frappe.TimestampMismatchError):
			self.api.save_role({**self.change(home_page="/console"), "modified": "old"})
		self.doc.save.assert_not_called()

	def test_unknown_flags_names_and_invalid_field_values_are_rejected(self):
		for values in (
			{"ignore_permissions": True},
			{"role_name": "Injected"},
			{"disabled": "1"},
			{"desk_access": 2},
			{"home_page": "https://outside.example"},
			{"home_page": "//outside.example"},
			{"home_page": "/\\outside"},
		):
			with self.subTest(values=values), self.assertRaises(self.frappe.ValidationError):
				self.api.values_of(values, self.permissions, self.doc)
		with self.assertRaises(self.frappe.ValidationError):
			self.api.delete_role(
				{"role": "Target", "modified": "v1", "confirm_name": "Target", "force": True}
			)

	def test_field_write_permissions_and_domain_selection_are_enforced(self):
		limited = {**self.permissions, "write_fields": ["home_page"]}
		with self.assertRaises(self.frappe.PermissionError):
			self.api.values_of({"desk_access": 0}, limited, self.doc)
		with (
			patch.object(self.api, "domains", return_value=[]),
			self.assertRaises(self.frappe.PermissionError),
		):
			self.api.values_of({"restrict_to_domain": "Hidden"}, self.permissions, self.doc)

	def test_sensitive_save_requires_a_matching_preview_and_consumes_it_on_success(self):
		with (
			patch.object(self.api, "associations", return_value=[]),
			patch.object(self.api, "intent", return_value="intent"),
		):
			with self.assertRaises(self.frappe.ValidationError):
				self.api.save_role(self.change(desk_access=False))
			self.doc.save.assert_not_called()
			self.frappe.cache.get_value.return_value = "changed-intent"
			with self.assertRaises(self.frappe.ValidationError):
				self.api.save_role({**self.change(desk_access=False), "confirmation_token": "token"})
			self.frappe.cache.get_value.return_value = "intent"
			self.api.save_role({**self.change(desk_access=False), "confirmation_token": "token"})
			self.doc.save.assert_called_once_with()
			self.frappe.cache.delete_value.assert_called_once()

	def test_preview_is_short_lived_and_reports_only_authorized_summary(self):
		with (
			patch.object(self.api, "associations", return_value=[]),
			patch.object(self.api, "intent", return_value="intent"),
			patch.object(self.api, "preview_summary", return_value={"visible_users": 0, "restricted": True}),
		):
			result = self.api.preview_change(self.change(disabled=True))
			self.assertTrue(result["reasons"])
			self.assertTrue(result["restricted"])
			self.assertEqual(self.frappe.cache.set_value.call_args.kwargs["expires_in_sec"], 300)
			self.assertIn(self.frappe.session.user, self.frappe.cache.set_value.call_args.args[0])
		self.doc.save.assert_not_called()

	def test_delete_checks_confirmation_references_and_calls_native_delete_without_force(self):
		data = {"role": "Target", "modified": "v1", "confirm_name": "Target"}
		with self.assertRaises(self.frappe.ValidationError):
			self.api.delete_role({**data, "confirm_name": "wrong"})
		with (
			patch.object(self.api, "has_references", return_value=True),
			self.assertRaises(self.frappe.ValidationError),
		):
			self.api.delete_role(data)
		self.frappe.delete_doc.assert_not_called()
		with patch.object(self.api, "has_references", return_value=False):
			self.api.delete_role(data)
		self.frappe.delete_doc.assert_called_once_with(
			"Role", "Target", force=False, ignore_permissions=False, ignore_missing=False
		)

	def test_rename_uses_native_link_updates_without_merge_or_forced_permissions(self):
		self.api.rename_role(
			{"role": "Target", "modified": "v1", "new_name": " Renamed ", "confirm_name": "Target"}
		)
		self.frappe.rename_doc.assert_called_once_with(
			"Role", "Target", "Renamed", force=False, merge=False, ignore_permissions=False, show_alert=False
		)
		self.doc.db_set.assert_called_once_with("modified", "v2")
		self.doc.save.assert_not_called()

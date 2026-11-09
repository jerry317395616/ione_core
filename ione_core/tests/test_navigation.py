from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class Record(dict):
	def __getattr__(self, key):
		return self.get(key)


def link(name, kind="DocType", **extra):
	return {"key": kind + "|" + name, "type": "Link", "link_type": kind, "link_to": name, **extra}


def sidebar(app, module, *rows):
	return {"app": app, "module": module, "items": list(rows)}


class TestNavigation(TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe.whitelist = lambda **kwargs: lambda method: method
		self.frappe.session = SimpleNamespace(user="staff@example.test")
		self.frappe.get_roles = Mock(return_value=["Care Administrator", "All", "Guest", "Desk User"])
		self.frappe.get_all = Mock(return_value=[])
		self.frappe.has_permission = Mock(return_value=True)
		self.frappe.get_module_app = Mock(
			side_effect=lambda name: {"Core": "frappe", "Accounts": "erpnext", "Healthcare": "healthcare"}[
				name
			]
		)
		self.frappe.db = SimpleNamespace(get_value=Mock(side_effect=self.value))
		self.frappe.get_cached_doc = Mock(side_effect=self.document)
		self.frappe._ = lambda value: value
		self.frappe.AuthenticationError = type("AuthenticationError", (Exception,), {})
		self.frappe.PermissionError = type("PermissionError", (Exception,), {})
		self.frappe.throw = lambda message, kind: self.fail_request(message, kind)
		self.permissions = ModuleType("frappe.permissions")
		self.permissions.AUTOMATIC_ROLES = ("Guest", "All", "Desk User")
		self.permissions.get_valid_perms = Mock(return_value=[Record(parent="User", read=1)])
		self.utils = ModuleType("frappe.desk.utils")
		self.utils.is_item_allowed = Mock(return_value=True)
		self.views = ModuleType("frappe.desk.desk_views")
		self.views.DeskViews = Mock(return_value=SimpleNamespace())
		self.module_utils = ModuleType("frappe.utils.modules")
		self.module_utils.get_module_placement = self.frappe.get_module_app
		self.sidebar_module = ModuleType("frappe.desk.doctype.sidebar.sidebar")
		self.sidebar_module.shell_slug = lambda name: name.lower().replace(" ", "-")
		self.sidebar_module.get_module_landing_route = Mock(return_value="/desk/user")
		self.owners = {"User": "Core", "Account": "Accounts", "Patient": "Healthcare", "ledger": "Accounts"}
		self.documents = {}
		self.staff = Record(enabled=1, user_type="System User")
		self.native_apps = ModuleType("frappe.apps")
		self.native_apps.get_docked_apps = Mock(return_value=set())
		self.boot = ModuleType("frappe.boot")
		self.boot.get_app_rail_host_map = Mock(return_value={})
		self.boot.get_app_data = Mock(
			return_value=[
				{"app_name": "frappe", "on_apps_screen": False},
				{"app_name": "erpnext", "on_apps_screen": True},
			]
		)
		self.boot.build_entity_module_map = Mock(return_value={"User": "Users"})
		self.sidebar_module.build_canonical_shells = Mock(return_value=({}, "Users"))
		self.dock = ModuleType("frappe.desk.doctype.dock.dock")
		self.dock.get_app_entry_set = Mock(
			return_value=[
				{"link_type": "Sidebar", "link_to": "Users"},
				{"link_type": "Sidebar", "link_to": "Accounts"},
			]
		)
		self.installed = ModuleType("frappe.core.doctype.installed_applications.installed_applications")
		self.installed.get_setup_wizard_completed_apps = Mock(
			return_value=["frappe", "erpnext", "healthcare"]
		)
		self.installed.get_setup_wizard_not_required_apps = Mock(return_value=[])
		self.frappe.get_active_apps = Mock(return_value=["frappe", "erpnext", "healthcare"])
		self.frappe.get_hooks = Mock(
			side_effect=lambda key, app_name: [
				{"name": app_name, "title": app_name, "route": "/desk/" + app_name}
			]
		)
		self.desktop = ModuleType("ione_core.desktop_i18n")
		self.desktop.get_hidden_apps = Mock(return_value=set())
		self.module_patch = patch.dict(
			sys.modules,
			{
				"frappe": self.frappe,
				"frappe.permissions": self.permissions,
				"frappe.desk.utils": self.utils,
				"frappe.desk.desk_views": self.views,
				"frappe.utils.modules": self.module_utils,
				"frappe.desk.doctype.sidebar.sidebar": self.sidebar_module,
				"frappe.apps": self.native_apps,
				"frappe.boot": self.boot,
				"frappe.desk.doctype.dock.dock": self.dock,
				"frappe.core.doctype.installed_applications.installed_applications": self.installed,
				"ione_core.desktop_i18n": self.desktop,
			},
		)
		self.module_patch.start()
		spec = importlib.util.spec_from_file_location(
			"navigation_test_subject", Path(__file__).parents[1] / "navigation.py"
		)
		self.api = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.api)

	def tearDown(self):
		self.module_patch.stop()

	@staticmethod
	def fail_request(message, kind):
		raise kind(message)

	def value(self, doctype, name, field, **kwargs):
		if doctype == "User" and isinstance(field, list):
			return self.staff
		if field == "module":
			return self.owners.get(name)
		return None

	def document(self, kind, name):
		return Record(
			{
				"roles": [],
				"links": [],
				"shortcuts": [],
				"quick_lists": [],
				"charts": [],
				"cards": [],
				"number_cards": [],
			}
			| self.documents.get((kind, name), {})
		)

	def test_business_roles_exclude_automatic_and_disabled_roles(self):
		self.frappe.get_roles.return_value += ["Disabled Role", "Accounts User"]
		self.frappe.get_all.return_value = ["Disabled Role"]
		policy = self.api.NavigationPolicy()
		self.assertEqual(policy.roles, {"Care Administrator", "Accounts User"})
		self.assertEqual(set(self.permissions.get_valid_perms.call_args.kwargs["roles"]), policy.roles)

	def test_no_explicit_roles_never_falls_back_to_automatic_permissions(self):
		self.frappe.get_roles.return_value = ["All", "Guest", "Desk User"]
		policy = self.api.NavigationPolicy()
		self.assertFalse(policy.allows("DocType", "User"))
		self.permissions.get_valid_perms.assert_not_called()

	def test_native_document_denial_still_wins(self):
		policy = self.api.NavigationPolicy()
		self.frappe.has_permission.return_value = False
		self.assertFalse(policy.allows("DocType", "User"))

	def test_native_domain_or_sidebar_denial_still_wins(self):
		self.utils.is_item_allowed.return_value = False
		self.assertFalse(self.api.NavigationPolicy().allows("DocType", "User"))

	def test_user_permission_does_not_open_erpnext_through_curated_user_link(self):
		policy = self.api.NavigationPolicy()
		source = {
			"Users": sidebar("frappe", "Users", link("User")),
			"Setup": sidebar("erpnext", "Setup", link("User")),
			"Accounts": sidebar("erpnext", "Accounts", link("Account")),
			"Healthcare": sidebar("healthcare", "Healthcare", link("Patient")),
		}
		before = repr(source)
		self.assertEqual(set(policy.filter_sidebars(source)), {"Users"})
		self.assertEqual(repr(source), before)

	def test_combined_grants_open_owning_apps_and_keep_native_curations(self):
		self.permissions.get_valid_perms.return_value += [Record(parent="Account", read=1)]
		policy = self.api.NavigationPolicy()
		source = {
			"Users": sidebar("frappe", "Users", link("User")),
			"Setup": sidebar("erpnext", "Setup", link("User")),
			"Accounts": sidebar("erpnext", "Accounts", link("Account")),
		}
		self.assertEqual(set(policy.filter_sidebars(source)), set(source))

	def test_help_is_kept_in_business_shell_but_cannot_open_an_empty_shell(self):
		policy = self.api.NavigationPolicy()
		source = {
			"Users": sidebar("frappe", "Users", link("User"), link("Help", "URL")),
			"Empty": sidebar("frappe", "Empty", link("Help", "URL")),
		}
		result = policy.filter_sidebars(source)
		self.assertEqual(set(result), {"Users"})
		self.assertEqual(len(result["Users"]["items"]), 2)

	def test_select_or_higher_permission_level_does_not_invent_read_access(self):
		# get_valid_perms already restricts permlevel=0; only read grants anchor list navigation.
		self.permissions.get_valid_perms.return_value = [Record(parent="Patient", read=0, select=1)]
		self.assertFalse(self.api.NavigationPolicy().allows("DocType", "Patient"))

	def test_workspace_cannot_open_an_app_from_a_foreign_grant(self):
		self.documents[("Workspace", "Home")] = {"shortcuts": [Record(type="DocType", link_to="User")]}
		policy = self.api.NavigationPolicy()
		self.assertTrue(policy.allows("Workspace", "Home"))
		self.assertFalse(policy.allows("Workspace", "Home", "erpnext"))
		self.assertEqual(
			policy.filter_sidebars({"Setup": sidebar("erpnext", "Setup", link("Home", "Workspace"))}), {}
		)

	def test_workspace_cycles_and_help_links_cannot_establish_membership(self):
		self.documents[("Workspace", "Home")] = {"links": [Record(link_type="Workspace", link_to="Home")]}
		policy = self.api.NavigationPolicy()
		self.assertFalse(policy.allows("Workspace", "Home"))
		self.assertFalse(policy.allows("URL", "https://example.test"))

	def test_report_requires_effective_reference_doctype_access(self):
		self.documents[("Report", "ledger")] = {"ref_doctype": "Account"}
		self.assertFalse(self.api.NavigationPolicy().allows("Report", "ledger"))
		self.permissions.get_valid_perms.return_value = [Record(parent="Account", read=1)]
		self.assertTrue(self.api.NavigationPolicy().allows("Report", "ledger", "erpnext"))

	def test_page_needs_an_explicit_role_in_addition_to_native_access(self):
		self.documents[("Page", "care")] = {"roles": [Record(role="Desk User")]}
		self.assertFalse(self.api.NavigationPolicy().allows("Page", "care"))
		self.documents[("Page", "care")] = {"roles": [Record(role="Care Administrator")]}
		self.assertTrue(self.api.NavigationPolicy().allows("Page", "care"))

	def test_administrator_keeps_native_sidebars_unchanged(self):
		self.frappe.session.user = "Administrator"
		source = {"Users": sidebar("frappe", "Users", link("User"))}
		self.assertIs(self.api.NavigationPolicy().filter_sidebars(source), source)

	def test_native_section_grouping_survives_intervening_root_item(self):
		rows = [
			{"type": "Section Break", "key": "first", "label": "First"},
			link("User", child=1),
			link("Account"),
			link("Patient", child=1),
			{"type": "Section Break", "key": "empty", "label": "Empty"},
		]
		pruned = self.api.prune_sections(rows)
		self.assertEqual(len(pruned), 4)
		tree = self.api.sidebar_navigation(pruned, "Users")
		self.assertEqual([node["type"] for node in tree], ["section", "item"])
		self.assertEqual(len(tree[0]["children"]), 2)

	def test_registration_respects_active_docked_hidden_and_setup_state(self):
		policy = self.api.NavigationPolicy()
		sidebars = {"Users": sidebar("frappe", "Users"), "Accounts": sidebar("erpnext", "Accounts")}
		self.assertEqual(
			[a["name"] for a in self.api.registered_apps(policy, sidebars)], ["frappe", "erpnext"]
		)
		self.native_apps.get_docked_apps.return_value = {"erpnext"}
		self.assertEqual([a["name"] for a in self.api.registered_apps(policy, sidebars)], ["frappe"])
		self.desktop.get_hidden_apps.return_value = {"frappe"}
		self.assertEqual(self.api.registered_apps(policy, sidebars), [])
		self.desktop.get_hidden_apps.return_value = set()
		self.installed.get_setup_wizard_completed_apps.return_value = []
		self.assertEqual(self.api.registered_apps(policy, sidebars), [])

	def test_disabled_website_and_guest_accounts_cannot_discover_apps(self):
		for staff in (
			Record(enabled=0, user_type="System User"),
			Record(enabled=1, user_type="Website User"),
		):
			self.staff = staff
			with self.assertRaises(self.frappe.PermissionError):
				self.api.get_apps()
		self.frappe.session.user = "Guest"
		with self.assertRaises(self.frappe.AuthenticationError):
			self.api.get_apps()

	def test_refresh_without_app_data_rebuilds_apps_and_drops_hidden_sidebars(self):
		policy = self.api.NavigationPolicy()
		sidebars = {
			"Users": sidebar("frappe", "Users", link("User")),
			"Accounts": sidebar("erpnext", "Accounts", link("Account")),
		}
		payload = {"module_sidebars": sidebars}
		with (
			patch.object(self.api, "projection", return_value=(policy, sidebars)),
			patch.object(
				self.api, "registered_apps", return_value=[{"name": "frappe", "route": "/desk/users"}]
			),
		):
			self.api.filter_boot(payload)
		self.assertEqual(list(payload["module_sidebars"]), ["Users"])
		self.assertEqual([app["app_name"] for app in payload["app_data"]], ["frappe"])
		self.assertTrue(payload["app_data"][0]["on_apps_screen"])
		self.assertEqual(payload["app_data"][0]["dock"], [{"link_type": "Sidebar", "link_to": "Users"}])
		self.boot.get_app_data.assert_called_once_with()

	def test_companion_grant_opens_host_without_creating_a_separate_app_slot(self):
		self.boot.get_app_rail_host_map.return_value = {"companion": "erpnext"}
		self.native_apps.get_docked_apps.return_value = {"companion"}
		sidebars = {"Companion": sidebar("companion", "Companion", link("Account"))}
		apps = self.api.registered_apps(self.api.NavigationPolicy(), sidebars)
		self.assertEqual([app["name"] for app in apps], ["erpnext"])

	def test_landing_uses_native_entity_route_instead_of_guessing_from_module_name(self):
		rows = [link("User")]
		apps = self.api.registered_apps(
			self.api.NavigationPolicy(), {"Users": sidebar("frappe", "Users", *rows)}
		)
		self.assertEqual(apps[0]["route"], "/desk/user")
		self.sidebar_module.get_module_landing_route.assert_called_once_with(rows)
		self.sidebar_module.get_module_landing_route.return_value = None
		apps = self.api.registered_apps(
			self.api.NavigationPolicy(), {"Users": sidebar("frappe", "Users", *rows)}
		)
		self.assertEqual(apps[0]["route"], "/desk")

	def test_unlisted_app_is_denied_even_when_requested_directly(self):
		with patch.object(self.api, "projection", return_value=(self.api.NavigationPolicy(), {})):
			with self.assertRaises(self.frappe.PermissionError):
				self.api.get_application("erpnext")

	def test_console_target_identifies_the_document_independently_of_its_display_label(self):
		source = {"Users": sidebar("frappe", "Users", link("User", label="Localized account label"))}
		with (
			patch.object(self.api, "projection", return_value=(self.api.NavigationPolicy(), source)),
			patch.object(
				self.api, "registered_apps", return_value=[{"name": "frappe", "title": "Framework"}]
			),
		):
			item = self.api.get_application("frappe")["modules"][0]["items"][0]
		self.assertEqual(item["target"], {"type": "DocType", "name": "User"})

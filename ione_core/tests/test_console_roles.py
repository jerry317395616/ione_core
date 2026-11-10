import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class Row(dict):
	def __getattr__(self, name):
		return self.get(name)


class TestConsoleRoles(TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe.whitelist = lambda **kwargs: lambda fn: fn
		self.frappe._ = lambda value: {"System Manager": "系统管理员"}.get(value, value)
		self.frappe.PermissionError = type("PermissionError", (Exception,), {})
		self.frappe.ValidationError = type("ValidationError", (Exception,), {})
		self.frappe.throw = lambda message, kind: self.raise_error(message, kind)
		self.frappe.local = SimpleNamespace(response_headers={})
		self.row = Row(name="System Manager", role_name="System Manager", disabled=0, desk_access=1)
		self.query = Mock()
		engine = ModuleType("frappe.database.query")
		engine.Engine = type("Engine", (), {"get_query": self.query})
		self.navigation = ModuleType("ione_core.navigation")
		self.navigation.require_staff = Mock()
		self.policy = SimpleNamespace(administrator=False, allows=Mock(return_value=True))
		self.navigation.NavigationPolicy = Mock(return_value=self.policy)
		role = ModuleType("frappe.core.doctype.role.role")
		role.STANDARD_ROLES = ("Administrator", "System Manager", "Script Manager", "All", "Guest")
		permissions = ModuleType("frappe.permissions")
		permissions.AUTOMATIC_ROLES = ("All", "Guest", "Desk User", "Administrator")
		self.modules = patch.dict(
			sys.modules,
			{
				"frappe": self.frappe,
				"frappe.database.query": engine,
				"frappe.core.doctype.role.role": role,
				"frappe.permissions": permissions,
				"ione_core.navigation": self.navigation,
			},
		)
		self.modules.start()
		spec = importlib.util.spec_from_file_location(
			"console_roles_test_subject", Path(__file__).parents[1] / "console_roles.py"
		)
		self.api = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.api)

	def tearDown(self):
		self.modules.stop()

	@staticmethod
	def raise_error(message, kind):
		raise kind(message)

	def results(self, *batches):
		self.query.side_effect = [Mock(run=Mock(return_value=batch)) for batch in batches]

	def test_list_and_total_share_native_filters_with_safe_fields_and_stable_paging(self):
		self.results([self.row], [Row(total=23)])
		result = self.api.get_roles(current="2", page_size="10", disabled="0", desk_access="0")
		self.assertEqual(result["total"], 23)
		self.assertEqual(result["data"][0]["label"], "系统管理员")
		self.assertTrue(result["data"][0]["is_reserved"])
		rows, count = [call.kwargs for call in self.query.call_args_list]
		self.assertEqual(rows["offset"], 10)
		self.assertEqual(rows["limit"], 10)
		self.assertEqual(rows["order_by"], "role_name asc, name asc")
		self.assertEqual(rows["filters"], {"disabled": 0, "desk_access": 0})
		self.assertEqual(set(rows["fields"]), set(self.api.LIST_FIELDS))
		for key in ("table", "filters", "ignore_permissions", "db_query_compat"):
			self.assertEqual(rows[key], count[key])
		self.assertFalse(rows["ignore_permissions"])
		self.assertEqual(self.frappe.local.response_headers["Cache-Control"], "private, no-store")

	def test_translated_search_uses_only_permission_checked_visible_names(self):
		other = Row(name="Private Role", role_name="Private Role")
		self.results([self.row, other], [self.row], [Row(total=1)])
		self.api.get_roles(keyword=" 系统管理员 ")
		search, rows, count = [call.kwargs for call in self.query.call_args_list]
		self.assertFalse(search["ignore_permissions"])
		self.assertEqual(search["fields"], ["name", "role_name"])
		self.assertEqual(rows["filters"], {"name": ["in", ["System Manager"]]})
		self.assertEqual(rows["filters"], count["filters"])

	def test_identifiers_and_wildcard_characters_match_literally(self):
		for keyword in ("system manager", "SYSTEM MANAGER", "_"):
			self.query.reset_mock()
			self.results([self.row], [self.row], [Row(total=1)])
			result = self.api.get_roles(keyword=keyword)
			if keyword == "_":
				self.assertEqual(result["data"], [])
				self.assertEqual(self.query.call_count, 1)
			else:
				self.assertEqual(result["total"], 1)

	def test_guests_and_callers_without_role_read_cannot_query_any_names_or_counts(self):
		self.policy.allows.return_value = False
		with self.assertRaises(self.frappe.PermissionError):
			self.api.get_roles(keyword="系统")
		with self.assertRaises(self.frappe.PermissionError):
			self.api.get_role("System Manager")
		self.query.assert_not_called()
		self.policy.allows.return_value = True
		self.navigation.require_staff.side_effect = self.frappe.PermissionError
		with self.assertRaises(self.frappe.PermissionError):
			self.api.get_roles()
		self.query.assert_not_called()

	def test_rejects_invalid_filters_paging_and_sort_injection(self):
		for data in (
			{"page_size": 101},
			{"current": 0},
			{"current": "1.5"},
			{"disabled": 2},
			{"desk_access": "yes"},
			{"keyword": []},
			{"keyword": "a" * 121},
			{"sort_field": "owner;drop table Role"},
			{"sort_order": "desc;--"},
		):
			with self.subTest(data=data), self.assertRaises(self.frappe.ValidationError):
				self.api.get_roles(**data)
		self.query.assert_not_called()

	def test_detail_checks_document_and_field_permissions_and_excludes_unrelated_data(self):
		values = {**self.row, "home_page": "/console", "owner": "private", "secret": "private"}
		doc = Mock()
		doc.as_dict.return_value = values
		doc.apply_fieldlevel_read_permissions.side_effect = lambda: values.pop("home_page")
		self.frappe.get_doc = Mock(return_value=doc)
		result = self.api.get_role("System Manager")
		doc.check_permission.assert_called_once_with("read")
		doc.apply_fieldlevel_read_permissions.assert_called_once()
		self.assertNotIn("home_page", result)
		self.assertNotIn("owner", result)
		self.assertNotIn("secret", result)
		self.assertEqual(result["name"], "System Manager")
		self.assertEqual(result["label"], "系统管理员")

	def test_detail_document_denial_prevents_field_projection(self):
		doc = Mock()
		doc.check_permission.side_effect = self.frappe.PermissionError
		self.frappe.get_doc = Mock(return_value=doc)
		with self.assertRaises(self.frappe.PermissionError):
			self.api.get_role("System Manager")
		doc.apply_fieldlevel_read_permissions.assert_not_called()
		doc.as_dict.assert_not_called()

	def test_detail_uses_the_same_strict_query_scope_as_the_list(self):
		doc = Mock()
		self.frappe.get_doc = Mock(return_value=doc)
		self.results([])
		with self.assertRaises(self.frappe.PermissionError):
			self.api.get_role("Hidden Role")
		doc.apply_fieldlevel_read_permissions.assert_not_called()
		doc.as_dict.assert_not_called()
		self.assertFalse(self.query.call_args.kwargs["ignore_permissions"])

	def test_native_reserved_rules_include_automatic_roles_without_classifying_custom_names(self):
		self.assertTrue(self.api.present(Row(name="Desk User"))["is_reserved"])
		self.assertFalse(self.api.present(Row(name="康复系统管理员", is_custom=0))["is_reserved"])

	def test_owner_only_read_is_not_relaxed_by_link_selection(self):
		self.assertTrue(
			self.api.RoleReadQuery().requires_owner_constraint(
				{"read": 1, "select": 1, "if_owner": {"read": 0}}
			)
		)
		self.assertFalse(self.api.RoleReadQuery().requires_owner_constraint({"read": 1, "if_owner": {}}))

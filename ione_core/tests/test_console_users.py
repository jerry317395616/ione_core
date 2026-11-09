import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class TestConsoleUsers(TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe.whitelist = lambda **kwargs: lambda method: method
		self.frappe._ = lambda value: value
		self.frappe.ValidationError = type("ValidationError", (Exception,), {})
		self.frappe.PermissionError = type("PermissionError", (Exception,), {})
		self.frappe.throw = lambda message, error: self.raise_error(message, error)
		self.frappe.local = SimpleNamespace(response_headers={})
		self.frappe.get_list = Mock(
			side_effect=[[{"name": "visible@example.test"}], [SimpleNamespace(total=21)]]
		)
		self.query = Mock(
			side_effect=[
				Mock(run=Mock(return_value=[{"name": "visible@example.test"}])),
				Mock(run=Mock(return_value=[SimpleNamespace(total=21)])),
			]
		)
		self.engine_module = ModuleType("frappe.database.query")
		self.engine_module.Engine = type("Engine", (), {"get_query": self.query})
		self.navigation = ModuleType("ione_core.navigation")
		self.navigation.require_staff = Mock()
		self.policy = SimpleNamespace(administrator=False, allows=Mock(return_value=True))
		self.navigation.NavigationPolicy = Mock(return_value=self.policy)
		self.modules = patch.dict(
			sys.modules,
			{
				"frappe": self.frappe,
				"ione_core.navigation": self.navigation,
				"frappe.database.query": self.engine_module,
			},
		)
		self.modules.start()
		spec = importlib.util.spec_from_file_location(
			"console_users_test_subject", Path(__file__).parents[1] / "console_users.py"
		)
		self.api = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.api)

	def tearDown(self):
		self.modules.stop()

	@staticmethod
	def raise_error(message, error):
		raise error(message)

	def test_rows_and_totals_keep_identical_permission_conditions_and_fixed_safe_fields(self):
		result = self.api.get_users(
			current="2",
			page_size="10",
			enabled="0",
			user_type="System User",
			keyword=" test ",
			sort_field="full_name",
			sort_order="ascend",
		)
		self.assertEqual(result, {"data": [{"name": "visible@example.test"}], "total": 21, "success": True})
		rows, count = [call.kwargs for call in self.query.call_args_list]
		self.assertEqual(rows["offset"], 10)
		self.assertEqual(rows["limit"], 10)
		self.assertEqual(rows["order_by"], "full_name asc, name asc")
		self.assertEqual(rows["filters"], {"enabled": 0, "user_type": "System User"})
		for key in ("filters", "or_filters", "ignore_permissions"):
			self.assertEqual(rows[key], count[key])
		self.assertFalse(rows["ignore_permissions"])
		self.assertEqual(
			set(rows["fields"]),
			{"name", "full_name", "username", "email", "enabled", "user_type", "modified"},
		)
		self.assertEqual(self.frappe.local.response_headers["Cache-Control"], "private, no-store")

	def test_denied_user_cannot_read_rows_or_counts(self):
		self.policy.allows.return_value = False
		with self.assertRaises(self.frappe.PermissionError):
			self.api.get_users()
		self.frappe.get_list.assert_not_called()
		self.query.assert_not_called()

	def test_staff_boundary_is_checked_before_queries(self):
		self.navigation.require_staff.side_effect = self.frappe.PermissionError
		with self.assertRaises(self.frappe.PermissionError):
			self.api.get_users()
		self.frappe.get_list.assert_not_called()
		self.query.assert_not_called()

	def test_rejects_sort_injection_and_unbounded_or_invalid_requests(self):
		for args in (
			{"sort_field": "modified;drop table User"},
			{"sort_order": "desc;--"},
			{"current": 0},
			{"current": "1.5"},
			{"page_size": 101},
			{"enabled": 2},
			{"user_type": "Super User"},
			{"keyword": "a" * 121},
		):
			with self.subTest(args=args), self.assertRaises(self.frappe.ValidationError):
				self.api.get_users(**args)
		self.frappe.get_list.assert_not_called()
		self.query.assert_not_called()

	def test_search_wildcards_are_literal(self):
		self.api.get_users(keyword="_%")
		self.assertTrue(
			all(
				value == ["like", "%\\_\\%%"]
				for value in self.query.call_args_list[0].kwargs["or_filters"].values()
			)
		)

	def test_unrestricted_link_selection_does_not_relax_owner_only_reading(self):
		self.assertTrue(
			self.api.UserReadQuery().requires_owner_constraint(
				{"read": 1, "select": 1, "if_owner": {"read": 0}}
			)
		)
		self.assertFalse(
			self.api.UserReadQuery().requires_owner_constraint({"read": 1, "if_owner": {"write": 0}})
		)

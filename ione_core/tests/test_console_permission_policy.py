import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class TestConsolePermissionPolicy(TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe.PermissionError = type("PermissionError", (Exception,), {})
		self.frappe.throw = lambda message, kind: self.raise_error(message, kind)
		self.frappe.db = SimpleNamespace(exists=Mock(return_value=True))
		self.frappe.get_installed_apps = lambda: ["frappe", "rehab", "ione_core"]
		self.frappe.get_all = Mock()
		self.frappe.get_active_domains = lambda: ["Healthcare"]
		roles = ModuleType("ione_core.console_roles")
		roles.require_reader = Mock()
		roles.get_readable_role = Mock(return_value=SimpleNamespace(name="Therapist", disabled=0))
		roles.present = lambda row: {"is_reserved": row["name"] in {"System Manager", "All"}}
		navigation = ModuleType("ione_core.navigation")
		self.policy = SimpleNamespace(administrator=False, roles={"Unrelated manager"})
		navigation.NavigationPolicy = lambda: self.policy
		self.modules = patch.dict(
			sys.modules,
			{"frappe": self.frappe, "ione_core.console_roles": roles, "ione_core.navigation": navigation},
		)
		self.modules.start()
		spec = importlib.util.spec_from_file_location(
			"permission_policy_subject", Path(__file__).parents[1] / "console_permission_policy.py"
		)
		self.api = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.api)
		self.frappe.get_all.side_effect = self.query
		self.grants = []
		self.native_roles = roles

	def tearDown(self):
		self.modules.stop()

	@staticmethod
	def raise_error(message, kind):
		raise kind(message)

	def query(self, doctype, **kwargs):
		if doctype == "Module Def":
			return [
				SimpleNamespace(name="Clinical", app_name="rehab"),
				SimpleNamespace(name="Core", app_name="frappe"),
				SimpleNamespace(name="Uninstalled", app_name="missing"),
			]
		if doctype == self.api.GRANT:
			return self.grants
		if doctype == self.api.MODULE:
			return ["Clinical", "Core", "Uninstalled"]
		return []

	def test_role_crud_alone_does_not_create_permission_administration_authority(self):
		self.assertEqual(self.api.authority()["view_modules"], set())
		with self.assertRaises(self.frappe.PermissionError):
			self.api.role_scope("Therapist")

	def test_explicit_grant_uses_enabled_actor_roles_and_valid_business_modules(self):
		self.grants = [SimpleNamespace(name="grant", can_edit=1)]
		scope = self.api.authority()
		self.assertEqual(scope["view_modules"], {"Clinical"})
		self.assertEqual(scope["edit_modules"], {"Clinical"})
		query = self.frappe.get_all.call_args_list[0].kwargs
		self.assertEqual(query["filters"], {"enabled": 1, "manager_role": ["in", ["Unrelated manager"]]})

	def test_read_only_delegation_cannot_write(self):
		self.grants = [SimpleNamespace(name="grant", can_edit=0)]
		scope = self.api.authority()
		self.assertTrue(self.api.capabilities()["can_view"])
		self.assertFalse(self.api.can_edit(scope, True, "Clinical"))

	def test_native_supervisor_has_full_scope_without_a_hospital_role_name(self):
		self.policy.roles = {"System Manager"}
		self.assertTrue(self.api.authority()["supervisor"])
		self.api.require_supervisor()
		self.policy.roles = {"康复系统管理员"}
		with self.assertRaises(self.frappe.PermissionError):
			self.api.require_supervisor()

	def test_scope_control_records_reserved_and_custom_user_type_roles_are_protected(self):
		self.policy.administrator = True
		self.assertFalse(self.api.role_scope("System Manager")[2])
		self.native_roles.get_readable_role.return_value.disabled = 1
		self.assertFalse(self.api.role_scope("Therapist")[2])

	def test_scope_records_and_child_tables_are_not_delegated_as_business_targets(self):
		rows = [
			SimpleNamespace(name="Patient", module="Clinical", restrict_to_domain="Healthcare"),
			SimpleNamespace(name=self.api.GRANT, module="Clinical", restrict_to_domain=None),
			SimpleNamespace(name="Education", module="Clinical", restrict_to_domain="Education"),
		]
		self.frappe.get_all.side_effect = lambda dt, **kw: rows
		self.assertEqual(
			[
				row.name
				for row in self.api.allowed_doctypes({"supervisor": False, "view_modules": {"Clinical"}})
			],
			["Patient"],
		)
		self.assertEqual(self.frappe.get_all.call_args.kwargs["filters"]["istable"], 0)

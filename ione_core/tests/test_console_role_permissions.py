import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class Row(dict):
	__getattr__ = dict.get
	__setattr__ = dict.__setitem__


class TestConsoleRolePermissions(TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe.whitelist = lambda **kwargs: lambda fn: fn
		for name in ("ValidationError", "PermissionError", "TimestampMismatchError"):
			setattr(self.frappe, name, type(name, (Exception,), {}))
		self.frappe.throw = lambda message, kind: self.raise_error(message, kind)
		self.frappe._ = lambda value: value
		self.frappe.session = SimpleNamespace(user="manager@example.test", sid="session")
		self.frappe.db = SimpleNamespace(get_value=Mock(), after_commit=SimpleNamespace(add=Mock()))
		self.frappe.cache = SimpleNamespace(get_value=Mock(), set_value=Mock(), delete_value=Mock())
		self.frappe.get_all = Mock(return_value=[])
		self.frappe.delete_doc = Mock()
		self.document = SimpleNamespace(update=Mock(), save=Mock(), permissions=[])
		self.document.set = lambda field, values: setattr(
			self.document, field, [Row(value) for value in values]
		)
		self.frappe.new_doc = Mock(return_value=self.document)
		self.frappe.get_doc = Mock(return_value=self.document)
		self.frappe.get_meta = Mock(return_value=SimpleNamespace(has_field=lambda name: True))
		state = ModuleType("frappe.app_state")
		state.is_disabled_app_filtering_active = Mock(return_value=False)
		state.is_module_disabled = Mock(return_value=False)
		permissions = ModuleType("frappe.permissions")
		permissions.get_rights = lambda dt: [
			"read",
			"write",
			"create",
			"submit",
			"cancel",
			"export",
			"report",
		]
		permissions.setup_custom_perms = Mock()
		policy = ModuleType("ione_core.console_permission_policy")
		self.role = SimpleNamespace(name="Target", modified="r1")
		self.scope = {"supervisor": False, "edit_modules": {"Clinical"}}
		policy.role_scope = Mock(return_value=(self.scope, self.role, True))
		policy.allowed_doctypes = Mock(return_value=[SimpleNamespace(name="Patient", module="Clinical")])
		policy.can_edit = lambda scope, editable, module: editable and module in scope["edit_modules"]
		management = ModuleType("ione_core.console_role_management")
		management.no_store = lambda value: value
		management.payload = lambda data, keys: data
		management.preview_summary = Mock(return_value={"visible_users": 0})
		native = ModuleType("frappe.core.doctype.doctype.doctype")
		native.validate_permissions = Mock()
		native.clear_permissions_cache = Mock()
		self.native = native
		self.modules = patch.dict(
			sys.modules,
			{
				"frappe": self.frappe,
				"frappe.app_state": state,
				"frappe.permissions": permissions,
				"ione_core.console_permission_policy": policy,
				"ione_core.console_role_management": management,
				"frappe.core.doctype.doctype.doctype": native,
			},
		)
		self.modules.start()
		spec = importlib.util.spec_from_file_location(
			"permission_subject", Path(__file__).parents[1] / "console_role_permissions.py"
		)
		self.api = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.api)
		self.copy = permissions.setup_custom_perms
		self.policy = policy
		self.rights = self.api.all_rights("Patient")
		self.context = {
			"doctype": "Patient",
			"version": "v1",
			"rights": self.rights,
			"rules": [],
			"levels": [
				{
					"level": 0,
					"rights": self.rights,
					"owner_rights": [right for right in self.rights if right != "report"],
				},
				{"level": 1, "rights": ["read", "write", "mask"], "owner_rights": ["read", "write", "mask"]},
			],
		}

	def tearDown(self):
		self.modules.stop()

	@staticmethod
	def raise_error(message, kind):
		raise kind(message)

	def rule(self, level=0, owner=0, **rights):
		return {
			"permlevel": level,
			"if_owner": owner,
			"rights": {right: rights.get(right, 0) for right in self.rights},
		}

	def change(self, **updates):
		return {
			"role": "Target",
			"changes": [{"doctype": "Patient", "version": "v1", "rules": [self.rule(read=1)]}],
			**updates,
		}

	def test_empty_custom_role_rules_do_not_fall_back_to_standard_role_grants(self):
		rows = {"DocPerm": [Row(role="Target", read=1)], "Custom DocPerm": [Row(role="Other", read=1)]}
		self.assertEqual(self.api.rules_for(rows, "Target", self.rights), [])

	def test_read_and_lock_queries_produce_same_snapshot_despite_native_child_order(self):
		values = [Row(name="second", role="Other"), Row(name="first", role="Target")]
		self.frappe.get_all.return_value = values
		self.frappe.qb = SimpleNamespace(get_query=Mock())
		self.frappe.qb.get_query.return_value.run.return_value = list(reversed(values))
		self.assertEqual(
			self.api.digest(self.api.rows_for("Patient")),
			self.api.digest(self.api.rows_for("Patient", lock=True)),
		)

	def test_disabled_app_rules_follow_native_effective_fallback(self):
		with patch.object(self.api, "is_disabled_app_filtering_active", return_value=True):
			rows = {
				"DocPerm": [Row(role="Target", read=1)],
				"Custom DocPerm": [Row(role="Other", read=1, is_app_disabled=1)],
			}
			self.assertEqual(self.api.rules_for(rows, "Target", self.rights)[0]["rights"]["read"], 1)

	def test_owner_and_field_levels_are_distinct_rules(self):
		rules = [self.rule(1, read=1, write=1), self.rule(owner=1, read=1), self.rule(read=1)]
		self.assertEqual(
			[self.api.rule_key(row) for row in self.api.normalized_rules(rules, self.context)],
			[(0, 0), (0, 1), (1, 0)],
		)

	def test_duplicate_scope_and_owner_at_higher_level_are_rejected(self):
		for rules in [[self.rule(read=1)] * 2, [self.rule(1, owner=1, read=1)]]:
			with self.assertRaises(self.frappe.ValidationError):
				self.api.normalized_rules(rules, self.context)

	def test_level_one_needs_level_zero_and_rejects_new_document_create(self):
		for rules in [[self.rule(1, read=1)], [self.rule(read=1), self.rule(1, read=1, create=1)]]:
			with self.assertRaises(self.frappe.ValidationError):
				self.api.normalized_rules(rules, self.context)

	def test_rejects_unknown_fields_incomplete_rights_and_truthy_strings(self):
		for rule in [
			{**self.rule(read=1), "ignore_permissions": True},
			{"permlevel": 0, "if_owner": 0, "rights": {"read": 1}},
			self.rule(read="1"),
			self.rule(read=True),
		]:
			with self.assertRaises(self.frappe.ValidationError):
				self.api.normalized_rules([rule], self.context)

	def test_owner_report_and_empty_rules_require_explicit_removal(self):
		for rule in [self.rule(owner=1, read=1, report=1), self.rule(export=1)]:
			with self.assertRaises(self.frappe.ValidationError):
				self.api.normalized_rules([rule], self.context)
		self.assertEqual(self.api.normalized_rules([], self.context), [])

	def test_native_validation_receives_only_target_role_without_saving_schema(self):
		self.api.validate_native("Patient", "Target", [self.rule(read=1)])
		self.native.validate_permissions.assert_called_once_with(self.document)
		self.assertEqual({row.role for row in self.document.permissions}, {"Target"})
		self.document.save.assert_not_called()

	def test_native_normalization_cannot_silently_change_confirmed_intent(self):
		self.native.validate_permissions.side_effect = lambda doc: doc.permissions[0].update(write=1)
		with self.assertRaises(self.frappe.ValidationError):
			self.api.validate_native("Patient", "Target", [self.rule(read=1)])

	def test_scope_checks_cannot_be_replaced_by_role_crud(self):
		with self.assertRaises(self.frappe.PermissionError):
			self.api.target_scope("Target", "User")
		self.policy.allowed_doctypes.return_value = []
		with self.assertRaises(self.frappe.PermissionError):
			self.api.prepare(self.change())

	def test_reserved_or_disabled_role_is_read_only(self):
		self.policy.role_scope.return_value = (self.scope, self.role, False)
		with self.assertRaises(self.frappe.PermissionError):
			self.api.prepare(self.change())

	def test_stale_snapshot_is_rejected_before_any_mutation(self):
		with patch.object(self.api, "context_for", return_value={**self.context, "version": "v2"}):
			with self.assertRaises(self.frappe.TimestampMismatchError):
				self.api.prepare(self.change(), lock=True)
		self.copy.assert_not_called()
		self.frappe.db.get_value.assert_called_once_with("Role", "Target", "name", for_update=True)

	def test_first_override_copies_all_defaults_and_only_saves_selected_role(self):
		self.frappe.get_all.return_value = [Row(name="other", role="Other", permlevel=0, if_owner=0, read=1)]
		self.api.persist("Patient", "Target", [self.rule(read=1)])
		self.copy.assert_called_once_with("Patient")
		self.document.save.assert_called_once_with(ignore_permissions=True)
		self.frappe.delete_doc.assert_not_called()
		self.document.update.assert_any_call(
			{"role": "Target", "permlevel": 0, "if_owner": 0, **self.rule(read=1)["rights"]}
		)

	def test_revocation_deletes_only_target_role_and_retains_other_roles(self):
		self.frappe.get_all.return_value = [
			Row(name="other", role="Other", permlevel=0, if_owner=0),
			Row(name="target", role="Target", permlevel=0, if_owner=0),
		]
		self.api.persist("Patient", "Target", [])
		self.frappe.delete_doc.assert_called_once_with(
			"Custom DocPerm", "target", ignore_permissions=True, force=True
		)

	def test_last_rule_cannot_be_deleted_and_reactivate_default_permissions(self):
		self.frappe.get_all.return_value = [Row(name="target", role="Target", permlevel=0, if_owner=0)]
		with self.assertRaises(self.frappe.ValidationError):
			self.api.persist("Patient", "Target", [])
		self.frappe.delete_doc.assert_not_called()

	def test_confirmation_is_bound_to_actor_session_and_exact_intent(self):
		baseline = self.api.intent(self.role, [self.change()])
		self.frappe.session.sid = "another-session"
		self.assertNotEqual(baseline, self.api.intent(self.role, [self.change()]))

	def test_expired_confirmation_never_writes(self):
		with patch.object(
			self.api,
			"prepare",
			return_value=({"token": "a" * 64}, self.role, [{"doctype": "Patient", "after": []}]),
		):
			with self.assertRaises(self.frappe.TimestampMismatchError):
				self.api.save_permissions({})
		self.copy.assert_not_called()

	def test_successful_save_clears_permission_cache_after_commit_and_consumes_token(self):
		changes = [{"doctype": "Patient", "after": [self.rule(read=1)]}]
		self.frappe.cache.get_value.return_value = self.api.intent(self.role, changes)
		with (
			patch.object(self.api, "prepare", return_value=({"token": "b" * 64}, self.role, changes)),
			patch.object(self.api, "persist") as persist,
		):
			self.assertEqual(self.api.save_permissions({})["saved"], 1)
			persist.assert_called_once()
		self.native.clear_permissions_cache.assert_called_once_with("Patient")
		self.frappe.db.after_commit.add.assert_called_once()
		self.frappe.cache.delete_value.assert_called_once()

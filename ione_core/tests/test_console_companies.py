import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class TestConsoleCompanies(TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe.whitelist = lambda **kwargs: lambda fn: fn
		for name in ["ValidationError", "PermissionError", "TimestampMismatchError"]:
			setattr(self.frappe, name, type(name, (Exception,), {}))
		self.frappe.throw = lambda message, kind: self.raise_error(message, kind)
		self.doc = SimpleNamespace(
			name="QA Company",
			modified="v1",
			get=lambda field: "old" if field == "country" else None,
			update=Mock(),
			save=Mock(),
			insert=Mock(),
			check_permission=Mock(),
		)
		self.frappe.new_doc = Mock(return_value=self.doc)
		self.frappe.get_doc = Mock(return_value=self.doc)
		management = ModuleType("ione_core.console_role_management")
		management.no_store = lambda value: value
		management.payload = lambda data, fields: data
		roles = ModuleType("ione_core.console_roles")
		roles.RoleReadQuery = Mock()
		roles.integer = lambda value, minimum, maximum: int(value)
		nav = ModuleType("ione_core.navigation")
		nav.NavigationPolicy = Mock()
		nav.require_staff = Mock()
		self.modules = patch.dict(
			sys.modules,
			{
				"frappe": self.frappe,
				"ione_core.console_role_management": management,
				"ione_core.console_roles": roles,
				"ione_core.navigation": nav,
			},
		)
		self.modules.start()
		spec = importlib.util.spec_from_file_location(
			"company_subject", Path(__file__).parents[1] / "console_companies.py"
		)
		self.api = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.api)
		self.permissions = {
			"can_read": True,
			"can_edit": True,
			"can_create": True,
			"create_fields": list(self.api.FIELDS),
			"write_fields": [field for field in self.api.FIELDS if field not in self.api.IMMUTABLE],
		}
		self.meta = SimpleNamespace(
			get_field=lambda field: SimpleNamespace(length=140, reqd=False, options="FIFO\nMoving Average")
		)
		self.access = patch.object(self.api, "access", return_value=(self.permissions, self.meta))
		self.access.start()
		self.query = patch.object(self.api, "query", return_value=[SimpleNamespace(name="QA Company")])
		self.query.start()

	def tearDown(self):
		self.query.stop()
		self.access.stop()
		self.modules.stop()

	@staticmethod
	def raise_error(message, kind):
		raise kind(message)

	def test_create_uses_native_insert_without_bypasses(self):
		self.api.create_company({"values": {"company_name": " New Company ", "abbr": "NC"}})
		self.doc.update.assert_called_once_with({"company_name": "New Company", "abbr": "NC"})
		self.doc.insert.assert_called_once_with()

	def test_save_locks_native_document_checks_write_and_preserves_lifecycle(self):
		self.api.save_company({"company": "QA Company", "modified": "v1", "values": {"tax_id": "new"}})
		self.frappe.get_doc.assert_called_once_with("Company", "QA Company", for_update=True)
		self.doc.check_permission.assert_any_call("read")
		self.doc.check_permission.assert_any_call("write")
		self.doc.save.assert_called_once_with()

	def test_stale_save_is_rejected_before_update(self):
		with self.assertRaises(self.frappe.TimestampMismatchError):
			self.api.save_company({"company": "QA Company", "modified": "old", "values": {"tax_id": "new"}})
		self.doc.save.assert_not_called()

	def test_select_does_not_relax_company_read_scope(self):
		with patch.object(self.api, "query", return_value=[]):
			with self.assertRaises(self.frappe.PermissionError):
				self.api.checked_company("Hidden Company")
		self.frappe.get_doc.assert_not_called()

	def test_identity_financial_defaults_and_bypass_fields_cannot_be_changed(self):
		for values in [
			{"company_name": "Renamed"},
			{"abbr": "NEW"},
			{"is_group": 1},
			{"default_receivable_account": "secret"},
			{"ignore_permissions": True},
		]:
			with self.assertRaises(self.frappe.PermissionError):
				self.api.values_of({"values": values}, self.permissions, self.meta, self.doc)

	def test_link_changes_need_an_option_within_native_scope(self):
		with patch.object(self.api, "link_options", return_value=[]):
			with self.assertRaises(self.frappe.PermissionError):
				self.api.values_of(
					{"values": {"parent_company": "Hidden parent"}}, self.permissions, self.meta, self.doc
				)

	def test_unchanged_existing_link_is_not_cleared_when_lookup_rights_change(self):
		with patch.object(self.api, "link_options") as lookup:
			self.assertEqual(
				self.api.values_of({"values": {"country": "old"}}, self.permissions, self.meta, self.doc),
				{"country": "old"},
			)
			lookup.assert_not_called()

	def test_link_validation_uses_raw_identity_without_translated_text_filter(self):
		module = ModuleType("frappe.desk.search")
		module.search_link = Mock(return_value=[{"value": "United States", "label": "美国"}])
		with patch.dict(sys.modules, {"frappe.desk.search": module}):
			self.assertEqual(
				self.api.link_options("country", "United States", exact=True)[0]["value"], "United States"
			)
		self.assertEqual(module.search_link.call_args.args, ("Country", ""))
		self.assertEqual(module.search_link.call_args.kwargs["filters"], {"name": "United States"})

	def test_read_only_actor_cannot_write_or_create(self):
		self.permissions.update(can_edit=False, can_create=False)
		with self.assertRaises(self.frappe.PermissionError):
			self.api.create_company({"values": {"abbr": "X"}})
		with self.assertRaises(self.frappe.PermissionError):
			self.api.save_company({"company": "QA Company", "modified": "v1", "values": {"tax_id": "new"}})

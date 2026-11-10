import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


class Flags(dict):
	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value


class TestPermissionCache(TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe.cache = SimpleNamespace(get_value=Mock(return_value="revision-one"), set_value=Mock())
		self.frappe.client_cache = SimpleNamespace(clear_cache=Mock())
		self.frappe.local = SimpleNamespace(
			site="qa.test", role_permissions={"Company": 0}, request_cache={"old": True}
		)
		self.frappe.flags = Flags()
		self.frappe.db = SimpleNamespace(
			after_commit=SimpleNamespace(add=Mock()), after_rollback=SimpleNamespace(add=Mock())
		)
		self.modules = patch.dict(sys.modules, {"frappe": self.frappe})
		self.modules.start()
		spec = importlib.util.spec_from_file_location(
			"permission_cache_subject", Path(__file__).parents[1] / "permission_cache.py"
		)
		self.api = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(self.api)

	def tearDown(self):
		self.modules.stop()

	def test_revision_bypasses_request_cache_and_discards_stale_worker_metadata(self):
		self.api.ensure_current()
		self.frappe.cache.get_value.assert_called_with(self.api.REVISION_KEY, use_local_cache=False)
		self.frappe.client_cache.clear_cache.assert_called_once()
		self.assertEqual(self.frappe.local.role_permissions, {})
		self.assertEqual(self.frappe.local.request_cache, {})

	def test_unchanged_revision_does_not_flush_worker_on_every_request(self):
		self.api.ensure_current()
		self.api.ensure_current()
		self.frappe.client_cache.clear_cache.assert_called_once()
		self.frappe.cache.get_value.return_value = "revision-two"
		self.api.ensure_current()
		self.assertEqual(self.frappe.client_cache.clear_cache.call_count, 2)

	def test_site_and_process_are_both_part_of_revision_state(self):
		self.api.ensure_current()
		self.frappe.local.site = "other.test"
		self.api.ensure_current()
		with patch.object(self.api.os, "getpid", return_value=-1):
			self.api.ensure_current()
		self.assertEqual(self.frappe.client_cache.clear_cache.call_count, 3)

	def test_changes_are_coalesced_and_published_only_after_commit(self):
		self.api.schedule_refresh()
		self.api.schedule_refresh()
		self.frappe.cache.set_value.assert_not_called()
		self.frappe.db.after_commit.add.assert_called_once_with(self.api.publish_revision)
		self.api.publish_revision()
		self.frappe.cache.set_value.assert_called_once()
		self.assertFalse(self.frappe.flags.ione_permission_revision_pending)

	def test_rollback_cancels_revision_without_publishing(self):
		self.api.schedule_refresh()
		self.frappe.db.after_rollback.add.call_args.args[0]()
		self.assertFalse(self.frappe.flags.get("ione_permission_revision_pending"))
		self.frappe.cache.set_value.assert_not_called()

	def test_custom_permission_deletion_invalidates_parent_before_new_revision(self):
		native = ModuleType("frappe.core.doctype.doctype.doctype")
		ordered = Mock()
		native.clear_permissions_cache = ordered.clear_parent
		self.frappe.cache.set_value = ordered.publish
		self.api.schedule_refresh(SimpleNamespace(doctype="Custom DocPerm", parent="Company"), "after_delete")
		with patch.dict(sys.modules, {"frappe.core.doctype.doctype.doctype": native}):
			self.api.publish_revision()
		self.assertEqual(ordered.mock_calls[0].args, ("Company",))
		self.assertEqual(ordered.mock_calls[1].args[0], self.api.REVISION_KEY)
		self.assertNotIn("ione_permission_doctypes", self.frappe.flags)

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ione_core import suite_file_access as access


class BaseFile:
	def is_downloadable(self):
		return "native"


class TestFile(access.PrivateFileDownload, BaseFile):
	__test__ = False
	is_private = True
	owner = "uploader@example.invalid"
	name = "fixture-file"
	attached_to_doctype = "Patient"
	attached_to_name = "synthetic-record"


class TestSuiteFileAccess(unittest.TestCase):
	def setUp(self):
		self.file = TestFile()
		self.session = SimpleNamespace(user="another@example.invalid")
		self.reference = Mock()
		self.reference.has_permission.return_value = False
		self.app_patch = patch.object(access.frappe, "get_installed_apps", return_value=["frappe", "suite"])
		self.session_patch = patch.object(access.frappe, "session", self.session)
		self.ref_patch = patch.object(access.frappe, "get_lazy_doc", return_value=self.reference)
		self.share_patch = patch.object(access.share, "get_shared", return_value=[])
		self.apps = self.app_patch.start()
		self.session_patch.start()
		self.read_ref = self.ref_patch.start()
		self.share = self.share_patch.start()
		for patcher in (self.app_patch, self.session_patch, self.ref_patch, self.share_patch):
			self.addCleanup(patcher.stop)

	def test_existing_reference_permission_controls_direct_private_download(self):
		self.assertFalse(self.file.is_downloadable())
		self.reference.has_permission.assert_called_with("read", user=self.session.user)
		self.reference.has_permission.return_value = True
		self.assertTrue(self.file.is_downloadable())

	def test_private_owner_and_explicit_frappe_share(self):
		self.share.return_value = [self.file.name]
		self.assertTrue(self.file.is_downloadable())
		self.share.assert_called_with(
			"File", filters=[["share_name", "=", self.file.name]], rights=["read"], user=self.session.user
		)
		self.session.user = self.file.owner
		self.share.return_value = []
		self.assertTrue(self.file.is_downloadable())
		self.read_ref.assert_not_called()

	def test_guest_cannot_use_explicit_shares(self):
		self.session.user = "Guest"
		self.assertFalse(self.file.is_downloadable())
		self.share.assert_not_called()

	def test_missing_parent_and_sites_without_suite(self):
		self.read_ref.side_effect = access.frappe.DoesNotExistError
		self.assertFalse(self.file.is_downloadable())
		self.apps.return_value = ["frappe"]
		self.assertEqual(self.file.is_downloadable(), "native")

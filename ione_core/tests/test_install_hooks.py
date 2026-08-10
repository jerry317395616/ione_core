from __future__ import annotations

import sys
from types import ModuleType
from unittest import TestCase
from unittest.mock import MagicMock, patch

sys.modules.setdefault("frappe", ModuleType("frappe"))

from ione_core.setup import install  # noqa: E402
from ione_core.setup.install import after_app_install, set_chinese_locale_defaults  # noqa: E402


class TestInstallHooks(TestCase):
	@patch("ione_core.setup.install.install_translation_bundle")
	def test_wiki_install_imports_translation_bundle(self, install_bundle):
		after_app_install("wiki")

		install_bundle.assert_called_once_with()

	@patch("ione_core.setup.install.install_translation_bundle")
	def test_unrelated_app_install_does_not_import_translation_bundle(self, install_bundle):
		after_app_install("erpnext")

		install_bundle.assert_not_called()

	def test_new_site_defaults_to_chinese(self):
		database = MagicMock()
		database.exists.return_value = True
		with patch.object(install.frappe, "db", database, create=True):
			set_chinese_locale_defaults()

		database.set_single_value.assert_called_once_with("System Settings", "language", "zh")
		database.set_value.assert_called_once_with(
			"User",
			"Administrator",
			"language",
			"zh",
			update_modified=False,
		)

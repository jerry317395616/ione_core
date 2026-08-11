from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

sys.modules.setdefault("frappe", ModuleType("frappe"))

from ione_core.desktop_i18n import ensure_desktop_app_labels, localize_app_titles  # noqa: E402
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

	def test_desktop_app_labels_are_localized(self):
		database = MagicMock()
		database.exists.return_value = True
		cache = MagicMock()
		icon = SimpleNamespace(name="Frappe Framework", label="Frappe Framework", app="frappe")
		with (
			patch.object(install.frappe, "db", database, create=True),
			patch.object(install.frappe, "cache", cache, create=True),
			patch.object(install.frappe, "get_all", return_value=[icon], create=True),
		):
			result = ensure_desktop_app_labels()

		self.assertEqual(result, {"updated": 1})
		database.set_value.assert_called_once_with(
			"Desktop Icon",
			"Frappe Framework",
			"label",
			"框架",
			update_modified=False,
		)
		cache.delete_key.assert_any_call("desktop_icons")
		cache.delete_key.assert_any_call("bootinfo")

	def test_apps_desktop_title_is_localized_in_bootinfo(self):
		bootinfo = MagicMock()
		bootinfo.app_data = [
			{"app_name": "frappe", "app_title": "Frappe Framework"},
			{"app_name": "ione_core", "app_title": "I-ONE AI"},
		]

		localize_app_titles(bootinfo)

		self.assertEqual(bootinfo.app_data[0]["app_title"], "框架")
		self.assertEqual(bootinfo.app_data[1]["app_title"], "I-ONE AI")

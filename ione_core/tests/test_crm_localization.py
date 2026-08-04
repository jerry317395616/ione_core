from pathlib import Path
from unittest import TestCase

from ione_core.translation_overrides import read_translation_catalog
from ione_core.web_injection import (
	CRM_I18N_ASSET,
	CRM_I18N_MARKER,
	inject_crm_i18n_asset,
	is_crm_html_response,
)


class TestCrmLocalization(TestCase):
	def test_catalog_contains_crm_labels(self):
		catalog = read_translation_catalog()
		expected = {
			"Call Logs": "通话记录",
			"Continue": "继续",
			"Getting started": "入门指南",
			"Help centre": "帮助中心",
			"Skip all": "全部跳过",
			"Start now": "立即开始",
			"Welcome to Frappe CRM": "欢迎使用客户关系管理",
		}
		for source, translation in expected.items():
			with self.subTest(source=source):
				self.assertEqual(catalog[(source, "")], translation)

	def test_runtime_patch_covers_untranslated_frappe_ui_labels(self):
		script = (
			Path(__file__).parents[1] / "public" / "js" / "crm_i18n_20260804.js"
		).read_text(encoding="utf-8")
		for source in (
			"Getting started",
			"Start now",
			"Help centre",
			"of",
			"Skip all",
			"Call Logs",
		):
			with self.subTest(source=source):
				self.assertIn(f'["{source}",', script)
		self.assertIn("window.__ione_crm_i18n_loaded = true", script)
		self.assertIn("steps(?:\\s+completed)?", script)
		self.assertIn("%\\s+completed", script)

	def test_injection_is_limited_to_chinese_crm_html(self):
		base = {
			"path": "/crm/leads",
			"method": "GET",
			"status_code": 200,
			"content_type": "text/html; charset=utf-8",
			"language": "zh-CN",
		}
		self.assertTrue(is_crm_html_response(**base))
		for field, value in (
			("path", "/desk"),
			("method", "POST"),
			("status_code", 404),
			("content_type", "application/json"),
			("language", "en"),
		):
			case = {**base, field: value}
			with self.subTest(field=field):
				self.assertFalse(is_crm_html_response(**case))

	def test_asset_is_injected_once(self):
		html = "<html><body><div id='app'></div></body></html>"
		localized = inject_crm_i18n_asset(html)
		self.assertIn(CRM_I18N_MARKER, localized)
		self.assertIn(CRM_I18N_ASSET, localized)
		self.assertIn('type="module"', localized)
		self.assertEqual(inject_crm_i18n_asset(localized), localized)

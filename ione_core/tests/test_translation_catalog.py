import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ione_core.translation_catalog import (
	_translation_from_row,
	html_tags,
	is_translation_candidate,
	merge_translations_into_csv,
	placeholders,
	requires_chinese_text,
	validate_translation,
)


class TestTranslationCatalog(TestCase):
	def test_preserves_frappe_and_template_placeholders(self):
		source = "{0} assigned %(count)s rows to ${values.owner} and {{ doc.name }}"
		translation = "{0} 已将 %(count)s 行分配给 ${values.owner} 和 {{ doc.name }}"

		self.assertEqual(placeholders(source), placeholders(translation))
		self.assertEqual(validate_translation(source, translation), [])

	def test_detects_placeholder_loss(self):
		self.assertEqual(
			validate_translation("Created {0} records", "已创建记录"),
			["placeholders changed"],
		)

	def test_preserves_html_tags(self):
		source = "<strong>Warning</strong><br>Try again"
		translation = "<strong>警告</strong><br>请重试"

		self.assertEqual(html_tags(source), html_tags(translation))
		self.assertEqual(validate_translation(source, translation), [])

	def test_rejects_minified_bundle_fragments(self):
		self.assertFalse(
			is_translation_candidate(
				'function(e,n,s){exports=function(){return createElement("div")}}'
			)
		)
		self.assertFalse(is_translation_candidate("),M=_($compiledBundle)"))
		self.assertFalse(
			is_translation_candidate("\n\n[File truncated to fit the context window.]")
		)
		self.assertFalse(is_translation_candidate(')} at ${t(e.datetime).format("'))
		self.assertFalse(is_translation_candidate("$dayjs"))
		self.assertFalse(is_translation_candidate(".tar.gz"))
		self.assertFalse(is_translation_candidate("1:N"))

	def test_keeps_normal_labels_and_help_text(self):
		self.assertTrue(is_translation_candidate("Accounts Payable Ageing"))
		self.assertTrue(is_translation_candidate("<p>Choose a company to continue.</p>"))

	def test_accepts_common_model_response_field_names(self):
		self.assertEqual(_translation_from_row({"id": 0, "translation": "保存"}), "保存")
		self.assertEqual(
			_translation_from_row({"id": 0, "translated_text": "保存"}),
			"保存",
		)

	def test_requires_actual_chinese_for_business_labels(self):
		self.assertTrue(requires_chinese_text("Accounts Payable Ageing"))
		self.assertEqual(
			validate_translation("Accounts Payable Ageing", "Accounts Payable Ageing"),
			["translation contains no Chinese text"],
		)

	def test_allows_product_names_and_technical_literals(self):
		for source in ("Frappe", "ERPNext", "API", "https://example.com", "YYYY-MM-DD"):
			with self.subTest(source=source):
				self.assertFalse(requires_chinese_text(source))
				self.assertEqual(validate_translation(source, source), [])

	def test_merges_checkpoint_into_frappe_csv(self):
		with TemporaryDirectory() as directory:
			root = Path(directory)
			checkpoint = root / "translations.json"
			catalog = root / "zh.csv"
			checkpoint.write_text(
				json.dumps({"Save": "保存", "Search": "搜索"}, ensure_ascii=False),
				encoding="utf-8",
			)
			catalog.write_text("Save,旧保存\nCancel,取消\n", encoding="utf-8")

			result = merge_translations_into_csv(str(checkpoint), str(catalog), overwrite=True)

			self.assertEqual(result, {"total": 3, "added": 1, "updated": 1})
			self.assertIn("Save,保存", catalog.read_text(encoding="utf-8"))

	def test_merge_preserves_hand_edited_translations_by_default(self):
		with TemporaryDirectory() as directory:
			root = Path(directory)
			checkpoint = root / "translations.json"
			catalog = root / "zh.csv"
			checkpoint.write_text(
				json.dumps({"Save": "机器保存", "Search": "搜索"}, ensure_ascii=False),
				encoding="utf-8",
			)
			catalog.write_text("Save,人工保存\nCancel,取消\n", encoding="utf-8")

			result = merge_translations_into_csv(str(checkpoint), str(catalog))

			self.assertEqual(result, {"total": 3, "added": 1, "updated": 0})
			self.assertIn("Save,人工保存", catalog.read_text(encoding="utf-8"))

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from ione_core.translation_catalog import (
	_translate_batch_resilient,
	_translation_from_row,
	audit_translation_values,
	html_tags,
	is_translation_candidate,
	merge_translations_into_csv,
	placeholders,
	requires_chinese_text,
	translate_missing_catalog,
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

	def test_literal_double_braces_are_not_treated_as_jinja_placeholders(self):
		source = "Special Characters except '{{' and '}}' are not allowed in {0}"
		translation = "{0} 中不允许使用 '{{' 和 '}}' 特殊字符"

		self.assertEqual(placeholders(source), placeholders(translation))
		self.assertEqual(validate_translation(source, translation), [])

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
		self.assertFalse(is_translation_candidate("on_update_after_submit"))
		self.assertFalse(is_translation_candidate("router-link"))
		self.assertFalse(is_translation_candidate("update:modelValue"))
		self.assertFalse(is_translation_candidate("bootstrap.ndjson"))
		self.assertFalse(is_translation_candidate("system | user | assistant | tool"))
		self.assertFalse(is_translation_candidate("durationchange"))
		self.assertFalse(is_translation_candidate("svg"))
		self.assertFalse(is_translation_candidate(";zs[Bs]===!0&&console.error("))
		self.assertFalse(is_translation_candidate("@jane"))
		self.assertFalse(is_translation_candidate("&lt;head&gt; HTML"))
		self.assertFalse(is_translation_candidate("pCLUCUMOCD"))

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
		for source in (
			"Frappe",
			"ERPNext",
			"API",
			"AAAA",
			"AmazonRoute53",
			"BigQuery",
			"Classplus",
			"Cloudflare",
			"Flow / Qwen",
			"Geoapify",
			"GitHub ID",
			"Google Analytics ID",
			"Google Classroom",
			"Google Meet",
			"github",
			"HL7 v2",
			"Helvetica Neue",
			"Hetzner",
			"I ONE AI",
			"IONE CDI",
			"IONE Flow AI",
			"Instagram",
			"Javascript",
			"Jinja",
			"Kajabi",
			"Keycloak",
			"LinkedIn",
			"Linode",
			"Markdown",
			"Meilisearch",
			"Namecheap",
			"Nomatim",
			"Notion",
			"Office 365",
			"Outlook.com",
			"Plausible",
			"Pipedrive",
			"REST API",
			"REST JSON",
			"Robots.txt",
			"Rust",
			"SNOMED CT",
			"Sqlite",
		"Sendgrid",
		"Sentry",
		"Sigstore Rekor",
		"Shopify",
		"Skype",
			"Stalwart/JMAP",
			"Supabase",
			"Teachmint",
			"Thinkific",
			"Vercel",
			"Verdana",
			"Webhook",
			"Websocket",
			"X (Twitter)",
			"Xero",
			"Zoho CRM",
			"Zapier",
			"Microsoft Teams",
			"PayPal",
			"Slack",
			"Twilio",
			"twitter",
			"WhatsApp",
			"YouTube",
			"youtube",
			"CRM-DEAL-.YYYY.-",
			"https://example.com",
			"YYYY-MM-DD",
			"dd/mm/yyyy",
			"vscode",
			"exchangerate-api",
			"fawazahmed-exchange-api",
		):
			with self.subTest(source=source):
				self.assertFalse(requires_chinese_text(source))
				self.assertEqual(validate_translation(source, source), [])

	@patch("ione_core.translation_catalog.time.sleep")
	@patch("ione_core.translation_catalog._request_translations")
	def test_resilient_batch_only_retries_invalid_messages(self, request, _sleep):
		request.side_effect = [
			{"Save": "保存", "Search": "Search"},
			{"Search": "搜索"},
		]

		translated, failures = _translate_batch_resilient(
			object(), "http://model", "secret", "model", ["Save", "Search"]
		)

		self.assertEqual(translated, {"Save": "保存", "Search": "搜索"})
		self.assertEqual(failures, {})
		self.assertEqual(request.call_args_list[1].args[-1], ["Search"])

	@patch("ione_core.translation_catalog.time.sleep")
	@patch("ione_core.translation_catalog._request_translations")
	def test_resilient_batch_does_not_split_validation_failures(self, request, _sleep):
		request.return_value = {"Search": "Search", "Save": "Save"}

		translated, failures = _translate_batch_resilient(
			object(), "http://model", "secret", "model", ["Search", "Save"]
		)

		self.assertEqual(translated, {})
		self.assertEqual(
			failures,
			{
				"Search": "translation contains no Chinese text",
				"Save": "translation contains no Chinese text",
			},
		)
		self.assertEqual(request.call_count, 3)

	@patch("ione_core.translation_catalog.collect_missing_messages", return_value=["Save"])
	def test_complete_checkpoint_is_normalized_without_loading_a_model(self, _messages):
		with TemporaryDirectory() as directory:
			checkpoint = Path(directory) / "translations.json"
			failure_file = checkpoint.with_suffix(".json.failures")
			checkpoint.write_text(
				json.dumps(
					{"Save": "\u4fdd\u5b58", "Unused": "\u672a\u4f7f\u7528"},
					ensure_ascii=False,
				),
				encoding="utf-8",
			)
			failure_file.write_text(
				json.dumps({"Unused": "old failure"}),
				encoding="utf-8",
			)

			with patch.dict(sys.modules, {"frappe": object(), "requests": object()}):
				result = translate_missing_catalog(output_file=str(checkpoint))

			self.assertEqual(result["remaining_messages"], 0)
			self.assertEqual(result["failed_messages"], 0)
			self.assertEqual(
				json.loads(checkpoint.read_text(encoding="utf-8")),
				{"Save": "\u4fdd\u5b58"},
			)
			self.assertEqual(json.loads(failure_file.read_text(encoding="utf-8")), {})

	def test_audit_reports_missing_invalid_and_extra_messages(self):
		result = audit_translation_values(
			["Save", "Search", "Frappe", "$dayjs"],
			{
				"Save": "保存",
				"Search": "Search",
				"Frappe": "Frappe",
				"Unused": "未使用",
			},
		)

		self.assertEqual(result["candidate_messages"], 2)
		self.assertEqual(result["translated_messages"], 1)
		self.assertEqual(result["missing_messages"], 0)
		self.assertEqual(result["invalid_messages"], 1)
		self.assertEqual(result["extra_messages"], 2)
		self.assertIn("Search", result["invalid_sample"])

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

	def test_merge_excludes_artifacts_and_rejects_invalid_translations(self):
		with TemporaryDirectory() as directory:
			root = Path(directory)
			checkpoint = root / "translations.json"
			catalog = root / "zh.csv"
			checkpoint.write_text(
				json.dumps(
					{
						"Save": "保存",
						"@jane": "@jane",
						"Search": "Search",
					},
					ensure_ascii=False,
				),
				encoding="utf-8",
			)

			with self.assertRaisesRegex(ValueError, "Search"):
				merge_translations_into_csv(str(checkpoint), str(catalog))

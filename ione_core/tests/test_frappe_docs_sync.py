from unittest import TestCase

from ione_core.frappe_docs_sync import (
	ProductSpec,
	QwenMarkdownTranslator,
	SourceNode,
	TranslationInputTooLargeError,
	_build_published_content,
	_content_source_hash,
	_destination_route,
	_docs_get,
	_expected_source_hierarchy,
	_extract_markdown_document,
	_extract_title_translations,
	_is_probably_untranslated_title,
	_protect_markdown_literals,
	_protected_literal_tokens,
	_restore_markdown_literals,
	_rewrite_internal_links,
	_source_hash,
	_split_markdown,
	_translated_markdown_body,
	_translation_fidelity_issues,
	discover_product,
	fetch_source_page,
	parse_sidebar,
)


class TestFrappeDocsSync(TestCase):
	def test_flow_model_base_url_can_be_overridden(self):
		class FlowModel:
			base_url = "https://old.example.test/v1"
			model_id = "openai/qwen-test"

			def get_password(self, _fieldname):
				return "secret"

		from unittest.mock import patch

		with patch("ione_core.translation_catalog._get_flow_model", return_value=FlowModel()):
			translator = QwenMarkdownTranslator.from_flow_model(
				base_url_override="http://10.144.133.1:1234/v1"
			)

		self.assertEqual(translator.base_url, "http://10.144.133.1:1234/v1")

	def test_title_translation_parser_accepts_compatible_keys_and_ignores_bad_rows(self):
		content = (
			'[{"id": 0, "translation": "介绍"}, '
			'{"id": "1", "translated_title": "设置"}, '
			'{"id": 2, "title": "Missing translation"}, '
			'{"id": 99, "translation": "Unexpected"}]'
		)

		self.assertEqual(
			_extract_title_translations(content, {0, 1, 2}),
			{0: "介绍", 1: "设置"},
		)

	def test_qwen_translation_disables_thinking_mode(self):
		class Response:
			def raise_for_status(self):
				return None

			def json(self):
				return {"choices": [{"message": {"content": "译文"}}]}

		class Session:
			def __init__(self):
				self.payload = None

			def post(self, _url, **kwargs):
				self.payload = kwargs["json"]
				return Response()

		session = Session()
		translator = QwenMarkdownTranslator("http://qwen.test/v1", "secret", "qwen", session)

		self.assertEqual(translator._chat("translate"), "译文")
		self.assertEqual(session.payload["chat_template_kwargs"], {"enable_thinking": False})

	def test_docs_request_retries_transient_network_failure(self):
		from unittest.mock import patch

		import requests

		class Response:
			url = "https://docs.frappe.io/builder/introduction"
			content = b"documentation"

			def raise_for_status(self):
				return None

		class Session:
			def __init__(self):
				self.calls = 0
				self.headers = {}
				self.trust_env = True

			def get(self, _url, **_kwargs):
				self.calls += 1
				if self.calls == 1:
					raise requests.Timeout("temporary")
				return Response()

		session = Session()
		with patch("ione_core.frappe_docs_sync.time.sleep"):
			response = _docs_get("https://docs.frappe.io/builder/introduction", session)

		self.assertEqual(response.content, b"documentation")
		self.assertEqual(session.calls, 2)
		self.assertFalse(session.trust_env)

	def test_source_fetch_falls_back_to_official_markdown(self):
		import requests

		class Response:
			url = "https://docs.frappe.io/erpnext/module-settings.md"
			content = b"markdown"
			text = (
				'---\ntitle: "Module Settings"\n'
				'url: "https://docs.frappe.io/erpnext/module-settings"\n---\n\n'
				"Configure [System Settings](/erpnext/system-settings) for your organization."
			)

			def raise_for_status(self):
				return None

		class Session:
			def __init__(self):
				self.headers = {}
				self.trust_env = True
				self.urls = []

			def get(self, url, **_kwargs):
				self.urls.append(url)
				if not url.endswith(".md"):
					raise requests.TooManyRedirects("loop")
				return Response()

		session = Session()
		title, markdown, source_url = fetch_source_page(
			"erpnext/module-settings", session=session
		)

		self.assertEqual(title, "Module Settings")
		self.assertEqual(source_url, "https://docs.frappe.io/erpnext/module-settings")
		self.assertIn(
			"](https://docs.frappe.io/erpnext/system-settings)",
			markdown,
		)
		self.assertEqual(
			session.urls,
			[
				"https://docs.frappe.io/erpnext/module-settings",
				"https://docs.frappe.io/erpnext/module-settings.md",
			],
		)

	def test_extracts_markdown_frontmatter_and_media_urls(self):
		title, markdown, source_url = _extract_markdown_document(
			'---\ntitle: "Enrollment\\n"\n'
			'url: "https://docs.frappe.io/education/enrollment"\n---\n\n'
			"# Enrollment\n\n![Example](/files/enrollment.png)\n\n"
			'<iframe src="/files/example.html"></iframe>',
			"https://docs.frappe.io/education/enrollment",
		)

		self.assertEqual(title, "Enrollment")
		self.assertEqual(source_url, "https://docs.frappe.io/education/enrollment")
		self.assertIn("https://docs.frappe.io/files/enrollment.png", markdown)
		self.assertIn('src="https://docs.frappe.io/files/example.html"', markdown)

	def test_accepts_an_official_heading_only_document(self):
		title, markdown, source_url = _extract_markdown_document(
			"# Final Assessment Grades",
			"https://docs.frappe.io/education/final-assessment-grades",
		)

		self.assertEqual(title, "Final Assessment Grades")
		self.assertEqual(markdown, "# Final Assessment Grades")
		self.assertEqual(
			source_url,
			"https://docs.frappe.io/education/final-assessment-grades",
		)

	def test_discovers_print_designer_from_the_official_repository_fallback(self):
		from unittest.mock import patch

		spec = ProductSpec(
			"print-designer",
			"Frappe Print Designer 中文文档",
			"print-designer",
			"https://docs.frappe.io/print-designer/introduction",
			"print-designer-zh-docs",
		)
		with patch("ione_core.frappe_docs_sync._docs_get", side_effect=ValueError("missing")):
			nodes = discover_product(spec)

		self.assertEqual(len(nodes), 1)
		self.assertEqual(nodes[0].source_route, "print-designer/introduction")

	def test_published_fallback_content_has_clear_provenance(self):
		content = _build_published_content(
			"# Print Designer",
			"https://github.com/frappe/print_designer/blob/develop/README.md",
			"a" * 64,
		)

		self.assertIn("Frappe 官方项目说明", content)
		self.assertEqual(_translated_markdown_body(content), "# Print Designer")

	def test_parses_nested_sidebar_without_flattening(self):
		html = (
			'<aside class="wiki-sidebar"><ul class="wiki-tree">'
			'<li class="wiki-item is-group">'
			'<button data-route="builder/introduction"><span class="wiki-title">Getting Started</span></button>'
			"<div><ul>"
			'<li class="wiki-item is-page"><a data-route="builder/introduction"><span class="wiki-title">Introduction</span></a></li>'
			'<li class="wiki-item is-group"><button><span class="wiki-title">Editing</span></button><ul>'
			'<li class="wiki-item is-page"><a data-route="builder/data-script"><span class="wiki-title">Data Script</span></a></li>'
			"</ul></li>"
			"</ul></div>"
			"</li>"
			'<li class="wiki-item is-page"><a data-route="crm/introduction"><span class="wiki-title">Wrong Space</span></a></li>'
			"</ul></aside>"
		)

		tree = parse_sidebar(html, "builder")

		self.assertEqual([node.title for node in tree], ["Getting Started"])
		self.assertEqual([node.title for node in tree[0].children], ["Introduction", "Editing"])
		self.assertEqual(tree[0].children[1].children[0].source_route, "builder/data-script")

	def test_destination_route_preserves_source_path(self):
		spec = ProductSpec("framework", "Framework", "framework", "", "framework-zh-docs")
		self.assertEqual(
			_destination_route(spec, "framework/user/en/api/rest"),
			"framework-zh-docs/user/en/api/rest",
		)

	def test_protected_markdown_round_trip(self):
		source = (
			"Run `bench migrate`. See [Docs](https://docs.frappe.io/framework).\n\n"
			"<kbd>Ctrl</kbd>\n\n```python\nprint('hello')\n```"
		)
		protected, literals = _protect_markdown_literals(source)
		self.assertNotIn("bench migrate", protected)
		self.assertNotIn("https://docs.frappe.io", protected)
		self.assertNotIn("<kbd>", protected)
		self.assertEqual(_restore_markdown_literals(protected, literals), source)

	def test_markdown_translation_retries_when_literal_is_missing(self):
		from unittest.mock import patch

		translator = QwenMarkdownTranslator("http://qwen.test/v1", "secret", "qwen")
		responses = iter(["缺少占位符", "保留 [[[IONE_LITERAL_0001]]] 的译文"])
		translator._chat = lambda _prompt: next(responses)

		with patch("ione_core.frappe_docs_sync.time.sleep"):
			translated = translator._translate_markdown_chunk(
				"Keep [[[IONE_LITERAL_0001]]]", 1, 1
			)

		self.assertEqual(translated, "保留 [[[IONE_LITERAL_0001]]] 的译文")
		self.assertEqual(
			_protected_literal_tokens(translated),
			["[[[IONE_LITERAL_0001]]]"],
		)

	def test_markdown_translation_retries_when_structure_is_missing(self):
		from unittest.mock import patch

		translator = QwenMarkdownTranslator("http://qwen.test/v1", "secret", "qwen")
		responses = iter(["只有正文", "# 标题\n\n完整正文"])
		translator._chat = lambda _prompt: next(responses)

		with patch("ione_core.frappe_docs_sync.time.sleep"):
			translated = translator._translate_markdown_chunk("# Title\n\nFull text", 1, 1)

		self.assertEqual(translated, "# 标题\n\n完整正文")

	def test_markdown_translation_splits_a_chunk_after_retries_fail(self):
		translator = QwenMarkdownTranslator("http://qwen.test/v1", "secret", "qwen")
		source = "\n\n".join(f"Paragraph {index}: " + "x" * 180 for index in range(8))
		calls = []

		def translate(text, _index, _total):
			calls.append(len(text))
			if len(text) > 500:
				raise ValueError("simulated truncation")
			return text

		translator._translate_markdown_chunk = translate
		translated = translator._translate_markdown_chunk_resilient(source, 1, 1)

		self.assertEqual(translated, source)
		self.assertTrue(any(length > 500 for length in calls))
		self.assertTrue(any(length <= 500 for length in calls[1:]))

	def test_markdown_chunks_respect_target_size_for_normal_blocks(self):
		source = "alpha\n\n" + "beta " * 20 + "\n\ngamma"
		chunks = _split_markdown(source, 40)
		self.assertGreater(len(chunks), 1)
		self.assertEqual("".join(chunk.separator_before + chunk.text for chunk in chunks), source)

	def test_markdown_chunks_preserve_long_table_line_boundaries(self):
		source = "| A | B |\n|---|---|\n" + "\n".join(f"| {index} | value |" for index in range(20))
		chunks = _split_markdown(source, 80)

		self.assertGreater(len(chunks), 1)
		self.assertEqual("".join(chunk.separator_before + chunk.text for chunk in chunks), source)
		self.assertTrue(all(chunk.separator_before in {"", "\n"} for chunk in chunks))

	def test_markdown_chunks_hard_split_an_oversized_single_line(self):
		source = "| " + "very-long-cell-value " * 2_000 + "|"
		chunks = _split_markdown(source, 500)

		self.assertGreater(len(chunks), 1)
		self.assertTrue(all(len(chunk.text) <= 500 for chunk in chunks))
		self.assertEqual("".join(chunk.separator_before + chunk.text for chunk in chunks), source)

	def test_markdown_translation_protects_heading_and_blockquote_prefixes(self):
		source = "# Heading\n\n> Important note"
		protected, literals = _protect_markdown_literals(source)

		self.assertNotIn("# ", protected)
		self.assertNotIn("> ", protected)
		self.assertEqual(_restore_markdown_literals(protected, literals), source)

	def test_markdown_translation_splits_an_oversized_request_error(self):
		translator = QwenMarkdownTranslator("http://qwen.test/v1", "secret", "qwen")
		source = "Paragraph one " * 99 + "Paragraph one\n\n" + "Paragraph two " * 99 + "Paragraph two"

		def translate(text, _index, _total):
			if len(text) > 1_000:
				raise TranslationInputTooLargeError("simulated context limit")
			return text

		translator._translate_markdown_chunk = translate
		translated = translator._translate_markdown_chunk_resilient(source, 1, 1)

		self.assertEqual(translated, source)

	def test_source_hash_marker_round_trip(self):
		hash_value = "a" * 64
		content = _build_published_content("# 标题", "https://docs.frappe.io/builder/introduction", hash_value)
		self.assertEqual(_content_source_hash(content), hash_value)
		self.assertEqual(_translated_markdown_body(content), "# 标题")

	def test_brand_titles_are_not_reported_as_untranslated(self):
		self.assertFalse(_is_probably_untranslated_title("Meta", "Meta"))
		self.assertFalse(_is_probably_untranslated_title("WhatsApp", "WhatsApp"))

	def test_source_hash_ignores_cloudflare_email_protection_key(self):
		first = "[Email](https://docs.frappe.io/cdn-cgi/l/email-protection#1234abcd)"
		second = "[Email](https://docs.frappe.io/cdn-cgi/l/email-protection#deadbeef)"

		self.assertEqual(_source_hash("Contact", first), _source_hash("Contact", second))

	def test_translation_fidelity_accepts_preserved_structure(self):
		source = (
			"# Report\n\nUse this report to review detailed accounting entries and balances. "
			* 5
			+ "\n\n- First item\n- Second item\n\n"
			+ "| Field | Value |\n| --- | --- |\n| Status | Open |\n\n"
			+ "![Chart](https://docs.frappe.io/files/chart.png)\n\n> Important note\n\n"
			+ "```python\nprint('ok')\n```"
		)
		translated = (
			"# 报表\n\n使用此报表查看详细的会计分录和余额。" * 5
			+ "\n\n- 第一项\n- 第二项\n\n"
			+ "| 字段 | 值 |\n| --- | --- |\n| 状态 | 打开 |\n\n"
			+ "![图表](https://docs.frappe.io/files/chart.png)\n\n> 重要说明\n\n"
			+ "```python\nprint('ok')\n```"
		)

		self.assertEqual(_translation_fidelity_issues(source, translated), [])

	def test_translation_fidelity_flags_truncated_content(self):
		source = (
			"# Report\n\nUse this report to review detailed accounting entries and balances. "
			* 8
			+ "\n\n- First item\n- Second item\n\n"
			+ "| Field | Value |\n| --- | --- |\n| Status | Open |\n\n"
			+ "![Chart](https://docs.frappe.io/files/chart.png)\n\n> Important note"
		)
		issues = _translation_fidelity_issues(source, "# 报表\n\n摘要")

		self.assertTrue(any(issue.startswith("images:") for issue in issues))
		self.assertTrue(any(issue.startswith("table_rows:") for issue in issues))
		self.assertTrue(any(issue.startswith("list_items:") for issue in issues))
		self.assertTrue(any(issue.startswith("blockquotes:") for issue in issues))
		self.assertTrue(any(issue.startswith("prose_length:") for issue in issues))

	def test_untranslated_title_detection_preserves_technical_names(self):
		self.assertTrue(_is_probably_untranslated_title("Introduction", "Introduction"))
		self.assertFalse(_is_probably_untranslated_title("Introduction", "介绍"))
		self.assertFalse(_is_probably_untranslated_title("REST API", "REST API"))

	def test_internal_links_use_wiki_public_route(self):
		markdown = "See [Data Script](https://docs.frappe.io/builder/data-script)."
		result = _rewrite_internal_links(
			markdown,
			{"builder/data-script": "builder-zh-docs/data-script"},
		)
		self.assertEqual(result, "See [Data Script](/builder-zh-docs/data-script).")

	def test_internal_links_repair_legacy_wiki_spa_routes(self):
		markdown = "See [Data Script](/wiki/builder-zh-docs/data-script)."
		result = _rewrite_internal_links(
			markdown,
			{"builder/data-script": "builder-zh-docs/data-script"},
		)
		self.assertEqual(result, "See [Data Script](/builder-zh-docs/data-script).")

	def test_internal_links_repair_cross_product_legacy_routes(self):
		markdown = "See [REST API](/wiki/framework-zh-docs/user/en/api/rest)."
		result = _rewrite_internal_links(markdown, {})
		self.assertEqual(result, "See [REST API](/framework-zh-docs/user/en/api/rest).")

	def test_expected_hierarchy_preserves_nested_parentage(self):
		spec = ProductSpec("builder", "Builder", "builder", "", "builder-zh-docs")
		tree = [
			SourceNode(
				"Scripting",
				"group",
				"builder/scripting",
				[SourceNode("Data Script", "page", "builder/data-script", identity="builder/data-script")],
				"group:builder:0001:scripting",
			)
		]

		hierarchy = _expected_source_hierarchy(spec, tree)

		self.assertEqual(hierarchy["group:builder:0001:scripting"]["parent"], "root:builder")
		self.assertEqual(hierarchy["builder/data-script"]["parent"], "group:builder:0001:scripting")

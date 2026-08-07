from unittest import TestCase

from ione_core.frappe_docs_sync import (
	ProductSpec,
	QwenMarkdownTranslator,
	SourceNode,
	_build_published_content,
	_content_source_hash,
	_destination_route,
	_docs_get,
	_expected_source_hierarchy,
	_extract_title_translations,
	_is_probably_untranslated_title,
	_protect_markdown_literals,
	_protected_literal_tokens,
	_restore_markdown_literals,
	_rewrite_internal_links,
	_split_markdown,
	_translated_markdown_body,
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

	def test_source_hash_marker_round_trip(self):
		hash_value = "a" * 64
		content = _build_published_content("# 标题", "https://docs.frappe.io/builder/introduction", hash_value)
		self.assertEqual(_content_source_hash(content), hash_value)
		self.assertEqual(_translated_markdown_body(content), "# 标题")

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
		self.assertEqual(result, "See [Data Script](/wiki/builder-zh-docs/data-script).")

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

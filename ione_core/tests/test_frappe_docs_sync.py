from unittest import TestCase

from ione_core.frappe_docs_sync import (
	ProductSpec,
	QwenMarkdownTranslator,
	_build_published_content,
	_content_source_hash,
	_destination_route,
	_protect_markdown_literals,
	_restore_markdown_literals,
	_rewrite_internal_links,
	_split_markdown,
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
		source = "Run `bench migrate`.\n\n```python\nprint('hello')\n```"
		protected, literals = _protect_markdown_literals(source)
		self.assertNotIn("bench migrate", protected)
		self.assertEqual(_restore_markdown_literals(protected, literals), source)

	def test_markdown_chunks_respect_target_size_for_normal_blocks(self):
		chunks = _split_markdown("alpha\n\n" + "beta " * 20 + "\n\ngamma", 40)
		self.assertGreater(len(chunks), 1)
		self.assertEqual("\n\n".join(chunks), "alpha\n\n" + "beta " * 20 + "\n\ngamma")

	def test_source_hash_marker_round_trip(self):
		hash_value = "a" * 64
		content = _build_published_content("# 标题", "https://docs.frappe.io/builder/introduction", hash_value)
		self.assertEqual(_content_source_hash(content), hash_value)

	def test_internal_links_use_wiki_public_route(self):
		markdown = "See [Data Script](https://docs.frappe.io/builder/data-script)."
		result = _rewrite_internal_links(
			markdown,
			{"builder/data-script": "builder-zh-docs/data-script"},
		)
		self.assertEqual(result, "See [Data Script](/wiki/builder-zh-docs/data-script).")

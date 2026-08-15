from __future__ import annotations

import json
from unittest import TestCase

from ione_core.mcp.slides import build_presentation_slides, normalize_slide_specs


class TestMCPSlides(TestCase):
	def sample_slides(self):
		return [
			{"kind": "cover", "title": "区域医疗协同方案", "subtitle": "面向客户的汇报版本"},
			{
				"kind": "content",
				"title": "客户需求",
				"bullets": ["建立统一数据底座", "提升运营分析效率"],
			},
			{
				"kind": "metrics",
				"title": "预期价值",
				"metrics": [{"value": "30%", "label": "效率提升", "detail": "以试点验收口径为准"}],
			},
			{"kind": "closing", "title": "下一步", "bullets": ["确认范围", "启动试点"]},
		]

	def test_builds_editable_frappe_slide_elements(self):
		result = build_presentation_slides(self.sample_slides())
		self.assertEqual(len(result), 4)
		for slide in result:
			elements = json.loads(slide["elements"])
			self.assertTrue(elements)
			self.assertTrue(all(element.get("id") for element in elements))
			self.assertEqual(slide["transition"], "Fade")

	def test_escapes_untrusted_business_text(self):
		slides = self.sample_slides()
		slides[1]["bullets"] = ["<script>alert('x')</script>"]
		elements = build_presentation_slides(slides)[1]["elements"]
		self.assertNotIn("<script>", elements)
		self.assertIn("&lt;script&gt;", elements)

	def test_rejects_too_few_slides(self):
		with self.assertRaisesRegex(ValueError, "at least 4 slides"):
			normalize_slide_specs(self.sample_slides()[:3])

	def test_rejects_unsupported_layout(self):
		slides = self.sample_slides()
		slides[1]["kind"] = "freeform"
		with self.assertRaisesRegex(ValueError, "unsupported kind"):
			normalize_slide_specs(slides)

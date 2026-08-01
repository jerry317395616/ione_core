from __future__ import annotations

import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ione_core.translation_overrides import build_translation_sync_plan, read_translation_catalog


class TestTranslationOverrides(TestCase):
	def test_catalog_reader_supports_context_and_escaped_newlines(self):
		with TemporaryDirectory() as directory:
			path = Path(directory) / "zh.csv"
			with path.open("w", encoding="utf-8", newline="") as handle:
				writer = csv.writer(handle)
				writer.writerow(["Hello", "你好"])
				writer.writerow(["Line\\nTwo", "两\\n行", "Button"])

			catalog = read_translation_catalog(path)

		self.assertEqual(catalog[("Hello", "")], "你好")
		self.assertEqual(catalog[("Line\nTwo", "Button")], "两\n行")

	def test_catalog_reader_rejects_malformed_rows(self):
		with TemporaryDirectory() as directory:
			path = Path(directory) / "zh.csv"
			path.write_text("one,two,three,four\n", encoding="utf-8")
			with self.assertRaisesRegex(ValueError, "expected 2 or 3 columns"):
				read_translation_catalog(path)

	def test_sync_plan_is_idempotent_and_removes_duplicate_keys(self):
		catalog = {("Home", ""): "首页", ("Save", "Button"): "保存"}
		existing = [
			{
				"name": "OLD-HOME",
				"source_text": "Home",
				"translated_text": "主页",
				"context": None,
				"creation": "2026-01-01",
			},
			{
				"name": "NEW-HOME",
				"source_text": "Home",
				"translated_text": "首页",
				"context": "",
				"creation": "2026-02-01",
			},
		]

		plan = build_translation_sync_plan(catalog, existing)

		self.assertEqual(plan["updates"], [("OLD-HOME", "首页")])
		self.assertEqual(plan["duplicates"], ["NEW-HOME"])
		self.assertEqual(plan["inserts"], [(('Save', 'Button'), "保存")])

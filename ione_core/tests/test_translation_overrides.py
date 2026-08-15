from __future__ import annotations

import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ione_core.translation_overrides import (
	build_translation_sync_plan,
	merge_site_translations,
	read_translation_catalog,
	write_translation_catalog,
)


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

	def test_catalog_writer_round_trips_context_and_newlines(self):
		catalog = {
			("Hello", ""): "你好",
			("Line\nTwo", "Button"): "第一行\n第二行",
		}
		with TemporaryDirectory() as directory:
			path = Path(directory) / "zh.csv"
			write_translation_catalog(catalog, path)

			self.assertEqual(read_translation_catalog(path), catalog)

	def test_site_merge_preserves_curated_values_and_appends_sorted_missing_rows(self):
		catalog = {("Home", ""): "主页"}
		rows = [
			{"source_text": "Save", "translated_text": "保存", "context": "Button"},
			{"source_text": "Home", "translated_text": "首页", "context": ""},
			{"source_text": "Line\\nTwo", "translated_text": "第一行\\n第二行", "context": ""},
		]

		merged, stats = merge_site_translations(catalog, rows)

		self.assertEqual(merged[("Home", "")], "主页")
		self.assertEqual(merged[("Line\nTwo", "")], "第一行\n第二行")
		self.assertEqual(merged[("Save", "Button")], "保存")
		self.assertEqual(stats, {"site_unique": 3, "added": 2, "overwritten": 0})

	def test_site_merge_can_explicitly_replace_packaged_values(self):
		merged, stats = merge_site_translations(
			{("Home", ""): "主页"},
			[{"source_text": "Home", "translated_text": "首页", "context": ""}],
			overwrite=True,
		)

		self.assertEqual(merged[("Home", "")], "首页")
		self.assertEqual(stats["overwritten"], 1)

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
		self.assertEqual(plan["inserts"], [(("Save", "Button"), "保存")])

	def test_sync_plan_prefers_exact_newline_key_over_escaped_legacy_duplicate(self):
		catalog = {("Line\nTwo", ""): "First\nSecond"}
		existing = [
			{
				"name": "OLD-ESCAPED",
				"source_text": "Line\\nTwo",
				"translated_text": "First\\nSecond",
				"context": "",
				"creation": "2026-01-01",
			},
			{
				"name": "NEW-EXACT",
				"source_text": "Line\nTwo",
				"translated_text": "First\nSecond",
				"context": "",
				"creation": "2026-02-01",
			},
		]

		plan = build_translation_sync_plan(catalog, existing)

		self.assertEqual(plan["updates"], [])
		self.assertEqual(plan["duplicates"], ["OLD-ESCAPED"])

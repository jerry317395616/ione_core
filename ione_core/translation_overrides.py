from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

TranslationKey = tuple[str, str]


def read_translation_catalog(path: str | Path | None = None) -> dict[TranslationKey, str]:
	"""Read the packaged Frappe CSV catalog keyed by source text and context."""
	catalog_path = Path(path) if path else Path(__file__).with_name("translations") / "zh.csv"
	catalog: dict[TranslationKey, str] = {}
	with catalog_path.open(encoding="utf-8-sig", newline="") as handle:
		for line_number, row in enumerate(csv.reader(handle), start=1):
			if not row:
				continue
			if len(row) not in {2, 3}:
				raise ValueError(f"invalid translation row {line_number}: expected 2 or 3 columns")
			source = row[0].replace("\\n", "\n")
			translated = row[1].replace("\\n", "\n")
			context = row[2].strip() if len(row) == 3 else ""
			if not source or not translated:
				raise ValueError(f"invalid translation row {line_number}: source and translation are required")
			catalog[(source, context)] = translated
	return catalog


def build_translation_sync_plan(
	catalog: Mapping[TranslationKey, str],
	existing_rows: Iterable[Any],
) -> dict[str, list[Any]]:
	"""Build an idempotent plan and collapse duplicate site overrides."""
	grouped: dict[TranslationKey, list[Any]] = defaultdict(list)
	for row in existing_rows:
		key = (str(_row_value(row, "source_text") or ""), str(_row_value(row, "context") or ""))
		if key in catalog:
			grouped[key].append(row)

	inserts: list[tuple[TranslationKey, str]] = []
	updates: list[tuple[str, str]] = []
	duplicates: list[str] = []
	for key, translated in catalog.items():
		rows = sorted(
			grouped.get(key, ()),
			key=lambda row: (
				str(_row_value(row, "creation") or ""),
				str(_row_value(row, "name") or ""),
			),
		)
		if not rows:
			inserts.append((key, translated))
			continue
		keeper = rows[0]
		if str(_row_value(keeper, "translated_text") or "") != translated:
			updates.append((str(_row_value(keeper, "name")), translated))
		duplicates.extend(str(_row_value(row, "name")) for row in rows[1:])

	return {"inserts": inserts, "updates": updates, "duplicates": duplicates}


def sync_translation_overrides(language: str = "zh") -> dict[str, int]:
	"""Synchronize packaged translations as deterministic site-level overrides."""
	import frappe
	from frappe.core.doctype.translation.translation import clear_user_translation_cache
	from frappe.utils import now_datetime, sanitize_html

	if not frappe.db.exists("DocType", "Translation"):
		return {"catalog": 0, "inserted": 0, "updated": 0, "duplicates_removed": 0}

	catalog = {key: sanitize_html(value) for key, value in read_translation_catalog().items()}
	existing = frappe.get_all(
		"Translation",
		filters={"language": language},
		fields=["name", "source_text", "translated_text", "context", "creation"],
		limit_page_length=0,
	)
	plan = build_translation_sync_plan(catalog, existing)

	for name, translated in plan["updates"]:
		frappe.db.set_value(
			"Translation",
			name,
			"translated_text",
			translated,
			update_modified=False,
		)

	if plan["duplicates"]:
		frappe.db.delete("Translation", {"name": ["in", plan["duplicates"]]})

	now = now_datetime()
	insert_rows = []
	for (source, context), translated in plan["inserts"]:
		insert_rows.append(
			(
				frappe.generate_hash(length=16),
				"Administrator",
				now,
				now,
				"Administrator",
				0,
				0,
				language,
				source,
				translated,
				context or None,
				0,
			)
		)
	if insert_rows:
		frappe.db.bulk_insert(
			"Translation",
			fields=[
				"name",
				"owner",
				"creation",
				"modified",
				"modified_by",
				"docstatus",
				"idx",
				"language",
				"source_text",
				"translated_text",
				"context",
				"contributed",
			],
			values=insert_rows,
			ignore_duplicates=True,
			chunk_size=1000,
		)

	if insert_rows or plan["updates"] or plan["duplicates"]:
		clear_user_translation_cache(language)
		frappe.clear_cache()

	return {
		"catalog": len(catalog),
		"inserted": len(insert_rows),
		"updated": len(plan["updates"]),
		"duplicates_removed": len(plan["duplicates"]),
	}


def _row_value(row: Any, fieldname: str) -> Any:
	if isinstance(row, Mapping):
		return row.get(fieldname)
	return getattr(row, fieldname, None)

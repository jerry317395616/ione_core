from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ione_core.translation_bundle import (
	BUNDLE_SCHEMA_VERSION,
	_document_depth,
	_entries_hash,
	_gzip_bytes,
	_load_manifest,
	_match_existing_document,
	_read_payload,
	_safe_filename,
)


class TestTranslationBundle(TestCase):
	def test_gzip_payload_is_deterministic_and_readable(self):
		payload = {"schema_version": BUNDLE_SCHEMA_VERSION, "title": "中文文档"}
		raw = json.dumps(payload, ensure_ascii=False).encode()

		first = _gzip_bytes(raw)
		second = _gzip_bytes(raw)

		self.assertEqual(first, second)
		with TemporaryDirectory() as directory:
			path = Path(directory) / "space.json.gz"
			path.write_bytes(first)
			self.assertEqual(_read_payload(path), payload)

	def test_manifest_validates_file_and_bundle_checksums(self):
		payload = {"schema_version": BUNDLE_SCHEMA_VERSION, "documents": []}
		compressed = _gzip_bytes(json.dumps(payload).encode())
		entry = {
			"route": "docs-zh",
			"file": "docs-zh.json.gz",
			"sha256": hashlib.sha256(compressed).hexdigest(),
			"documents": 0,
			"pages": 0,
			"groups": 0,
		}
		manifest = {
			"schema_version": BUNDLE_SCHEMA_VERSION,
			"bundle_sha256": _entries_hash([entry]),
			"spaces": [entry],
			"summary": {"spaces": 1, "documents": 0, "pages": 0, "groups": 0},
		}
		with TemporaryDirectory() as directory:
			root = Path(directory)
			(root / entry["file"]).write_bytes(compressed)
			(root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

			self.assertEqual(_load_manifest(root), manifest)

			(root / entry["file"]).write_bytes(compressed + b"broken")
			with self.assertRaisesRegex(ValueError, "checksum mismatch"):
				_load_manifest(root)

	def test_document_depth_rejects_cycles(self):
		parents = {"root": None, "section": "root", "page": "section"}
		self.assertEqual(_document_depth("page", parents, {}), 2)

		with self.assertRaisesRegex(ValueError, "cycle"):
			_document_depth("a", {"a": "b", "b": "a"}, {})

	def test_existing_document_prefers_source_then_key_then_route(self):
		row = {"source_path": "docs/a", "doc_key": "key-a", "route": "route-a"}
		self.assertEqual(
			_match_existing_document(
				row,
				{"docs/a": "SOURCE"},
				{"key-a": "KEY"},
				{"route-a": "ROUTE"},
			),
			"SOURCE",
		)

	def test_safe_filename_keeps_portable_route_characters(self):
		self.assertEqual(_safe_filename("ERPNext 中文文档/v17"), "erpnext-v17")

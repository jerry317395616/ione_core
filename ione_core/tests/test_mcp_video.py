from unittest import TestCase

from ione_core.mcp.video import manifest_hash, normalize_video_manifest


class DealVideoManifestTest(TestCase):
	def sample_manifest(self):
		return {
			"title": "智慧医疗运营方案",
			"customer": "示例医院",
			"template": "medical-enterprise",
			"aspect_ratio": "16:9",
			"scenes": [
				{"kind": "cover", "title": "智慧医疗运营方案", "duration_seconds": 5},
				{"kind": "context", "title": "建设背景", "duration_seconds": 5},
				{"kind": "challenge", "title": "核心挑战", "duration_seconds": 5},
				{"kind": "solution", "title": "总体方案", "duration_seconds": 5},
				{"kind": "value", "title": "预期价值", "duration_seconds": 5},
				{"kind": "closing", "title": "携手共建", "duration_seconds": 5},
			],
		}

	def test_normalizes_bounded_manifest(self):
		manifest = normalize_video_manifest(self.sample_manifest())

		self.assertEqual(manifest["duration_seconds"], 30)
		self.assertEqual(manifest["scenes"][0]["code"], "scene-01")
		self.assertEqual(manifest["scenes"][-1]["kind"], "closing")

	def test_rejects_executable_scene_kind(self):
		manifest = self.sample_manifest()
		manifest["scenes"][2]["kind"] = "javascript"

		with self.assertRaisesRegex(ValueError, "unsupported kind"):
			normalize_video_manifest(manifest)

	def test_rejects_remote_asset_payload(self):
		manifest = self.sample_manifest()
		manifest["scenes"][1]["asset_file"] = "https://example.com/tracker.png"

		with self.assertRaisesRegex(ValueError, "attached Frappe File"):
			normalize_video_manifest(manifest)

	def test_hash_changes_with_source_version(self):
		manifest = self.sample_manifest()

		self.assertNotEqual(manifest_hash(manifest, "v1"), manifest_hash(manifest, "v2"))

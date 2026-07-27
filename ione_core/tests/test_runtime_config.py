from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ione_core.runtime_config import ensure_web_request_timeout


class TestRuntimeConfig(TestCase):
	def test_updates_only_web_program_timeout(self):
		content = """[program:frappe-bench-frappe-web]
command=gunicorn --workers 2 --timeout 120 --graceful-timeout 30 frappe.app:application

[program:frappe-bench-frappe-worker]
command=bench worker --timeout 300
"""
		with TemporaryDirectory() as directory:
			path = Path(directory) / "supervisor.conf"
			path.write_text(content, encoding="utf-8")

			self.assertTrue(ensure_web_request_timeout(path, timeout=900))
			updated = path.read_text(encoding="utf-8")

		self.assertIn("--timeout 900 --graceful-timeout 30", updated)
		self.assertIn("bench worker --timeout 300", updated)

	def test_is_idempotent(self):
		content = """[program:frappe-bench-frappe-web]
command=gunicorn --timeout 900 frappe.app:application
"""
		with TemporaryDirectory() as directory:
			path = Path(directory) / "supervisor.conf"
			path.write_text(content, encoding="utf-8")

			self.assertFalse(ensure_web_request_timeout(path, timeout=900))
			self.assertEqual(path.read_text(encoding="utf-8"), content)

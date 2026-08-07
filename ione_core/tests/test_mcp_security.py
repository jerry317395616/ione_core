import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from ione_core.mcp.audit import request_summary
from ione_core.mcp.security import permitted_fields, sanitize_for_audit, validate_text_file


class TestMCPSecurity(TestCase):
	def test_reads_permitted_fields_from_frappe_model(self):
		frappe = ModuleType("frappe")
		frappe.session = SimpleNamespace(user="integration@example.com")
		frappe_model = ModuleType("frappe.model")
		calls = []

		def get_permitted_fields(doctype, parenttype=None, user=None, permission_type=None):
			calls.append((doctype, parenttype, user, permission_type))
			return ["subject", "industry"]

		frappe_model.get_permitted_fields = get_permitted_fields
		with patch.dict(sys.modules, {"frappe": frappe, "frappe.model": frappe_model}):
			result = permitted_fields("CRM Lead", "read")

		self.assertEqual(result, {"subject", "industry"})
		self.assertEqual(calls, [("CRM Lead", None, "integration@example.com", "read")])

	def test_masks_nested_secrets_in_audit_data(self):
		result = sanitize_for_audit(
			{"name": "CRM-LEAD-1", "api_key": "secret", "nested": {"token": "token-value"}}
		)
		self.assertIn('"name": "CRM-LEAD-1"', result)
		self.assertNotIn("secret", result)
		self.assertNotIn("token-value", result)

	def test_accepts_safe_text_attachment(self):
		name, payload = validate_text_file("analysis.md", "方案")
		self.assertEqual(name, "analysis.md")
		self.assertEqual(payload, "方案".encode())

	def test_rejects_executable_attachment(self):
		with self.assertRaisesRegex(ValueError, "Only"):
			validate_text_file("payload.py", "print('x')")

	def test_strips_path_from_attachment_name(self):
		name, _ = validate_text_file(str(Path("folder") / "report.txt"), "ok")
		self.assertEqual(name, "report.txt")

	def test_audit_summary_does_not_store_document_or_attachment_content(self):
		result = request_summary(
			{
				"doctype": "CRM Lead",
				"data": {"first_name": "Sensitive Name", "email": "private@example.com"},
				"content": "private report body",
			}
		)
		self.assertIn("first_name", result)
		self.assertNotIn("Sensitive Name", result)
		self.assertNotIn("private report body", result)

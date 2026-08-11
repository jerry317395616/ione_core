import base64
import io
import sys
import zipfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from ione_core.mcp.audit import request_summary
from ione_core.mcp.security import (
	doctype_allowed_by_scope,
	extract_docx_text,
	permitted_fields,
	sanitize_for_audit,
	validate_docx_file,
	validate_text_file,
)


class TestMCPSecurity(TestCase):
	def test_applies_site_exact_allow_and_deny_lists(self):
		frappe = ModuleType("frappe")
		frappe.session = SimpleNamespace(user="integration@example.com")
		frappe.local = SimpleNamespace()
		frappe.conf = {
			"ione_mcp_allowed_doctypes": ["Sales Order", "Tongjianyun Recipe"],
			"ione_mcp_denied_doctypes": ["Tongjianyun Recipe"],
		}
		with patch.dict(sys.modules, {"frappe": frappe}):
			self.assertTrue(doctype_allowed_by_scope("Sales Order"))
			self.assertFalse(doctype_allowed_by_scope("Tongjianyun Recipe"))
			self.assertFalse(doctype_allowed_by_scope("Purchase Order"))

	def test_actor_uses_integration_user_scope(self):
		frappe = ModuleType("frappe")
		frappe.session = SimpleNamespace(user="operator@example.com")
		frappe.local = SimpleNamespace(ione_mcp_integration_user="integration@example.com")
		frappe.conf = {
			"ione_mcp_allowed_doctype_prefixes_by_user": {
				"integration@example.com": ["Tongjianyun"]
			}
		}
		with patch.dict(sys.modules, {"frappe": frappe}):
			self.assertTrue(doctype_allowed_by_scope("Tongjianyun Recipe"))
			self.assertFalse(doctype_allowed_by_scope("Sales Order"))

	def test_limits_doctypes_for_configured_mcp_user(self):
		frappe = ModuleType("frappe")
		frappe.session = SimpleNamespace(user="tongjianyun-agent@example.com")
		frappe.conf = {
			"ione_mcp_allowed_doctype_prefixes_by_user": {
				"tongjianyun-agent@example.com": ["Tongjianyun"]
			}
		}
		with patch.dict(sys.modules, {"frappe": frappe}):
			self.assertTrue(doctype_allowed_by_scope("Tongjianyun Child"))
			self.assertFalse(doctype_allowed_by_scope("CRM Lead"))
			self.assertTrue(doctype_allowed_by_scope("CRM Lead", user="another@example.com"))

	def test_accepts_json_encoded_mcp_scope(self):
		frappe = ModuleType("frappe")
		frappe.session = SimpleNamespace(user="tongjianyun-agent@example.com")
		frappe.conf = {
			"ione_mcp_allowed_doctype_prefixes_by_user": (
				'{"tongjianyun-agent@example.com": "Tongjianyun"}'
			)
		}
		with patch.dict(sys.modules, {"frappe": frappe}):
			self.assertTrue(doctype_allowed_by_scope("Tongjianyun Recipe"))
			self.assertFalse(doctype_allowed_by_scope("User"))

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

	def test_accepts_structurally_valid_word_attachment(self):
		buffer = io.BytesIO()
		with zipfile.ZipFile(buffer, "w") as archive:
			archive.writestr("[Content_Types].xml", "<Types />")
			archive.writestr("word/document.xml", "<document />")
		content = base64.b64encode(buffer.getvalue()).decode("ascii")

		name, payload = validate_docx_file("folder/proposal.docx", content)

		self.assertEqual(name, "proposal.docx")
		self.assertEqual(payload, buffer.getvalue())

	def test_rejects_invalid_word_attachment(self):
		with self.assertRaisesRegex(ValueError, "valid Base64"):
			validate_docx_file("proposal.docx", "not-base64")
		with self.assertRaisesRegex(ValueError, "Only .docx"):
			validate_docx_file("proposal.pdf", base64.b64encode(b"pdf").decode("ascii"))

	def test_audit_summary_does_not_store_word_content(self):
		secret_content = base64.b64encode(b"sensitive proposal").decode("ascii")
		result = request_summary(
			{
				"doctype": "CRM Deal",
				"document_name": "CRM-DEAL-1",
				"content_base64": secret_content,
			}
		)
		self.assertIn("characters", result)
		self.assertNotIn(secret_content, result)

	def test_extracts_text_from_word_attachment(self):
		buffer = io.BytesIO()
		with zipfile.ZipFile(buffer, "w") as archive:
			archive.writestr("[Content_Types].xml", "<Types />")
			archive.writestr(
				"word/document.xml",
				'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
				"<w:body><w:p><w:r><w:t>客户需求</w:t></w:r></w:p>"
				"<w:p><w:r><w:t>建设统一数据平台</w:t></w:r></w:p></w:body></w:document>",
			)
		self.assertEqual(extract_docx_text(buffer.getvalue()), "客户需求\n建设统一数据平台")

	def test_audit_summary_does_not_store_slide_content(self):
		result = request_summary(
			{"deal": "CRM-DEAL-1", "slides": [{"kind": "cover", "title": "Sensitive plan"}]}
		)
		self.assertIn('"count": 1', result)
		self.assertNotIn("Sensitive plan", result)

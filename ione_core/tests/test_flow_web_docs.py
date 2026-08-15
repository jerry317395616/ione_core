from unittest import TestCase
from unittest.mock import patch

from ione_core.integrations.flow_web_docs import _extract_document, _validate_target_url


class TestFlowWebDocs(TestCase):
	@patch("ione_core.integrations.flow_web_docs.socket.getaddrinfo")
	def test_accepts_public_frappe_document_url(self, getaddrinfo):
		getaddrinfo.return_value = [(2, 1, 6, "", ("104.21.52.32", 443))]

		url = _validate_target_url("https://docs.frappe.io/erpnext/introduction#overview")

		self.assertEqual(url, "https://docs.frappe.io/erpnext/introduction")

	def test_rejects_non_frappe_hosts(self):
		with self.assertRaisesRegex(ValueError, "Only docs.frappe.io"):
			_validate_target_url("https://example.com/private")

	@patch("ione_core.integrations.flow_web_docs.socket.getaddrinfo")
	def test_rejects_private_dns_result(self, getaddrinfo):
		getaddrinfo.return_value = [(2, 1, 6, "", ("127.0.0.1", 443))]

		with self.assertRaisesRegex(ValueError, "non-public"):
			_validate_target_url("https://docs.frappe.io/erpnext/introduction")

	def test_extracts_article_and_normalizes_relative_links(self):
		html = """
		<html><head><title>Ignored | Frappe</title></head><body>
		<nav>Navigation</nav>
		<main><article class="prose">
		<h1>Introduction</h1>
		<p>ERPNext is a complete business management solution with useful modules.</p>
		<p><a href="/erpnext/accounting">Read accounting documentation</a>.</p>
		<script>alert('ignore')</script>
		</article></main>
		</body></html>
		"""

		title, markdown = _extract_document(html, "https://docs.frappe.io/erpnext/introduction")

		self.assertEqual(title, "Introduction")
		self.assertIn("# Introduction", markdown)
		self.assertIn("https://docs.frappe.io/erpnext/accounting", markdown)
		self.assertNotIn("alert", markdown)

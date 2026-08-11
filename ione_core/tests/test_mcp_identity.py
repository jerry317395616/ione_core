import sys
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from ione_core.mcp.identity import actor_context, as_verified_actor


class AuthenticationError(Exception):
	pass


class TestMCPActorIdentity(TestCase):
	def frappe_module(self, *, required=True):
		frappe = ModuleType("frappe")
		frappe.session = SimpleNamespace(user="integration@example.com")
		frappe.local = SimpleNamespace(site="child.example")
		frappe.conf = {"ione_mcp_require_actor_token": required}
		frappe.AuthenticationError = AuthenticationError
		frappe.throw = lambda message, exc=Exception: (_ for _ in ()).throw(exc(message))
		frappe.set_user = lambda user: setattr(frappe.session, "user", user)
		return frappe

	def test_actor_context_switches_and_restores_user(self):
		frappe = self.frappe_module()
		with (
			patch.dict(sys.modules, {"frappe": frappe}),
			patch("ione_core.mcp.identity.resolve_actor_user", return_value="operator@example.com"),
		):
			with actor_context("signed-token") as actor:
				self.assertEqual(actor, "operator@example.com")
				self.assertEqual(frappe.session.user, "operator@example.com")
				self.assertEqual(
					frappe.local.ione_mcp_integration_user, "integration@example.com"
				)
		self.assertEqual(frappe.session.user, "integration@example.com")
		self.assertFalse(hasattr(frappe.local, "ione_mcp_integration_user"))

	def test_required_actor_rejects_missing_token(self):
		frappe = self.frappe_module(required=True)
		with patch.dict(sys.modules, {"frappe": frappe}):
			with self.assertRaisesRegex(AuthenticationError, "identity is required"):
				with actor_context(""):
					pass

	def test_legacy_site_can_continue_as_integration_user(self):
		frappe = self.frappe_module(required=False)
		with patch.dict(sys.modules, {"frappe": frappe}):
			with actor_context("") as actor:
				self.assertEqual(actor, "integration@example.com")
				self.assertEqual(frappe.session.user, "integration@example.com")

	def test_actor_decorator_preserves_signature_and_applies_identity(self):
		frappe = self.frappe_module(required=True)

		@as_verified_actor
		def example(value: str, actor_token: str = ""):
			return value, frappe.session.user

		with (
			patch.dict(sys.modules, {"frappe": frappe}),
			patch("ione_core.mcp.identity.resolve_actor_user", return_value="operator@example.com"),
		):
			self.assertEqual(example("ok", actor_token="signed-token"), ("ok", "operator@example.com"))
		self.assertEqual(frappe.session.user, "integration@example.com")

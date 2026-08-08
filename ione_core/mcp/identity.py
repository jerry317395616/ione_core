from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


TOKEN_PREFIX = "ione1"
MAX_TOKEN_LENGTH = 4096


def _decode_segment(value: str) -> bytes:
	padding = "=" * (-len(value) % 4)
	return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _shared_secret() -> str:
	import frappe

	secret = str(frappe.conf.get("ione_agent_identity_shared_secret") or "").strip()
	if len(secret) < 32:
		frappe.throw("I-ONE Agent identity verification is not configured")
	return secret


def verify_actor_token(token: str, *, now: int | None = None) -> dict[str, Any]:
	"""Verify a short-lived identity assertion issued by the trusted Agent bridge."""
	import frappe

	value = str(token or "").strip()
	if not value or len(value) > MAX_TOKEN_LENGTH:
		frappe.throw("A valid Manager login identity is required", frappe.AuthenticationError)
	parts = value.split(".")
	if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
		frappe.throw("Manager login identity is invalid", frappe.AuthenticationError)

	signed = f"{parts[0]}.{parts[1]}".encode("ascii")
	expected = hmac.new(_shared_secret().encode("utf-8"), signed, hashlib.sha256).digest()
	try:
		provided = _decode_segment(parts[2])
	except (ValueError, UnicodeError):
		frappe.throw("Manager login identity is invalid", frappe.AuthenticationError)
	if not hmac.compare_digest(provided, expected):
		frappe.throw("Manager login identity is invalid", frappe.AuthenticationError)

	try:
		payload = json.loads(_decode_segment(parts[1]).decode("utf-8"))
	except (ValueError, UnicodeError, json.JSONDecodeError):
		frappe.throw("Manager login identity is invalid", frappe.AuthenticationError)
	if not isinstance(payload, dict) or payload.get("v") != 1 or payload.get("iss") != "ione-agent":
		frappe.throw("Manager login identity is invalid", frappe.AuthenticationError)

	current = int(time.time() if now is None else now)
	issued_at = int(payload.get("iat") or 0)
	expires_at = int(payload.get("exp") or 0)
	if issued_at > current + 60 or expires_at < current or expires_at - issued_at > 900:
		frappe.throw("Manager login identity has expired", frappe.AuthenticationError)

	current_site = str(getattr(frappe.local, "site", "") or "").strip().lower()
	audience = str(payload.get("aud") or "").strip().lower()
	if not current_site or not audience or not hmac.compare_digest(audience, current_site):
		frappe.throw("Manager login identity is for a different site", frappe.AuthenticationError)

	email = str(payload.get("email") or "").strip()
	if not email or len(email) > 254:
		frappe.throw("Manager login identity does not contain an account", frappe.AuthenticationError)
	return payload


def resolve_actor_user(token: str) -> str:
	"""Resolve a signed login email to one enabled Manager System User."""
	import frappe

	payload = verify_actor_token(token)
	email = str(payload["email"]).strip()
	user = email if frappe.db.exists("User", email) else frappe.db.get_value("User", {"email": email}, "name")
	if not user:
		frappe.throw("The logged-in Manager account no longer exists", frappe.AuthenticationError)
	user_doc = frappe.get_doc("User", user)
	if not user_doc.enabled or user_doc.user_type != "System User":
		frappe.throw("The logged-in Manager account is disabled or is not a system user", frappe.PermissionError)
	for doctype in ("CRM Lead", "CRM Task"):
		if not frappe.has_permission(doctype, ptype="read", user=user):
			frappe.throw(
				f"The logged-in Manager account has no read permission for {doctype}",
				frappe.PermissionError,
			)
	return str(user)

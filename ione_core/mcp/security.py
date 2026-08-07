from __future__ import annotations

import json
import re
from typing import Any

DENIED_DOCTYPES = {
	"Access Log",
	"Activity Log",
	"API Request Log",
	"Auth Token",
	"Communication",
	"Connected App",
	"Custom Field",
	"DocField",
	"DocPerm",
	"DocType",
	"Email Account",
	"Error Log",
	"Event Streaming",
	"Integration Request",
	"OAuth Authorization Code",
	"OAuth Bearer Token",
	"OAuth Client",
	"Package",
	"Package Import",
	"Password",
	"Property Setter",
	"RQ Job",
	"Scheduled Job Log",
	"Server Script",
	"Session Default Settings",
	"Social Login Key",
	"System Settings",
	"User",
	"User Permission",
	"Webhook",
}

PROTECTED_FIELDS = {
	"creation",
	"docstatus",
	"idx",
	"modified",
	"modified_by",
	"owner",
	"parent",
	"parentfield",
	"parenttype",
}

ORDER_BY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\s+(?:asc|desc))?$", re.IGNORECASE)
SAFE_FILE_EXTENSIONS = {".csv", ".json", ".md", ".txt"}
SENSITIVE_KEYS = {"api_key", "api_secret", "authorization", "password", "secret", "token"}


def require_login() -> str:
	import frappe

	user = getattr(frappe.session, "user", "Guest")
	if not user or user == "Guest":
		frappe.throw("MCP requires an authenticated Frappe user", frappe.AuthenticationError)
	return user


def ensure_doctype_permission(doctype: str, permission_type: str):
	import frappe

	require_login()
	doctype = (doctype or "").strip()
	if not doctype or doctype in DENIED_DOCTYPES:
		frappe.throw(f"DocType {doctype or '<empty>'} is not available through MCP", frappe.PermissionError)
	if not frappe.db.exists("DocType", doctype):
		frappe.throw(f"DocType {doctype} does not exist")
	meta = frappe.get_meta(doctype)
	if meta.istable:
		frappe.throw("Child tables must be accessed through their parent document")
	if not frappe.has_permission(doctype, ptype=permission_type):
		frappe.throw(f"No {permission_type} permission for {doctype}", frappe.PermissionError)
	return meta


def validate_order_by(meta, order_by: str | None, permitted: set[str]) -> str:
	value = (order_by or "modified desc").strip()
	if not ORDER_BY_PATTERN.fullmatch(value):
		raise ValueError("order_by must contain one field and an optional asc/desc direction")
	fieldname = value.split()[0]
	if fieldname not in {"name", "creation", "modified", "owner"} and not meta.has_field(fieldname):
		raise ValueError(f"Unknown order_by field: {fieldname}")
	if fieldname not in {"name", "creation", "modified", "owner"} and fieldname not in permitted:
		raise ValueError(f"order_by field is not available through MCP: {fieldname}")
	return value


def permitted_fields(doctype: str, permission_type: str, parenttype: str | None = None) -> set[str]:
	import frappe
	from frappe.model import get_permitted_fields

	return set(
		get_permitted_fields(
			doctype,
			parenttype=parenttype,
			user=frappe.session.user,
			permission_type=permission_type,
		)
	)


def safe_fields(meta, fields: list[str] | None, permitted: set[str]) -> list[str]:
	requested = fields or ["name", "modified", "owner"]
	allowed_standard = {"name", "creation", "modified", "modified_by", "owner", "docstatus"}
	result = []
	for fieldname in requested:
		if fieldname in allowed_standard:
			result.append(fieldname)
			continue
		field = meta.get_field(fieldname)
		if not field:
			raise ValueError(f"Unknown field: {fieldname}")
		if field.fieldtype == "Password" or fieldname not in permitted:
			raise ValueError(f"Field is not available through MCP: {fieldname}")
		result.append(fieldname)
	return list(dict.fromkeys(result))


def safe_filters(meta, filters: dict[str, Any] | None, permitted: set[str]) -> dict[str, Any]:
	if filters is None:
		return {}
	if not isinstance(filters, dict):
		raise ValueError("filters must be an object")
	allowed_standard = {"name", "creation", "modified", "modified_by", "owner", "docstatus"}
	for fieldname in filters:
		if fieldname in allowed_standard:
			continue
		if not meta.has_field(fieldname) or fieldname not in permitted:
			raise ValueError(f"Filter field is not available through MCP: {fieldname}")
	return filters


def safe_write_data(
	meta,
	data: dict[str, Any],
	permitted: set[str],
	*,
	parenttype: str | None = None,
) -> dict[str, Any]:
	if not isinstance(data, dict) or not data:
		raise ValueError("data must be a non-empty object")
	result = {}
	for fieldname, value in data.items():
		if fieldname in PROTECTED_FIELDS or fieldname == "doctype":
			continue
		if fieldname == "name":
			result[fieldname] = value
			continue
		field = meta.get_field(fieldname)
		if not field:
			raise ValueError(f"Unknown field: {fieldname}")
		if field.fieldtype == "Password" or field.read_only or fieldname not in permitted:
			raise ValueError(f"Field is not writable through MCP: {fieldname}")
		if field.fieldtype in {"Table", "Table MultiSelect"}:
			if not isinstance(value, list):
				raise ValueError(f"Child table field must be a list: {fieldname}")
			import frappe

			child_meta = frappe.get_meta(field.options)
			child_permitted = permitted_fields(field.options, "write", parenttype=parenttype or meta.name)
			result[fieldname] = [
				safe_write_data(
					child_meta,
					row,
					child_permitted,
					parenttype=parenttype or meta.name,
				)
				for row in value
			]
		else:
			result[fieldname] = value
	if not result:
		raise ValueError("data contains no writable fields")
	return result


def safe_document(doc, meta) -> dict[str, Any]:
	import frappe

	readable = permitted_fields(meta.name, "read")
	result = {
		key: doc.get(key)
		for key in ("name", "creation", "modified", "modified_by", "owner", "docstatus")
		if doc.get(key) is not None
	}
	for field in meta.fields:
		if field.fieldname not in readable or field.fieldtype == "Password":
			continue
		value = doc.get(field.fieldname)
		if field.fieldtype in {"Table", "Table MultiSelect"}:
			child_meta = frappe.get_meta(field.options)
			child_readable = permitted_fields(field.options, "read", parenttype=meta.name)
			result[field.fieldname] = [
				{
					key: row.get(key)
					for key in ("name", "idx", *child_readable)
					if row.get(key) is not None
					and (not child_meta.get_field(key) or child_meta.get_field(key).fieldtype != "Password")
				}
				for row in (value or [])
			]
		else:
			result[field.fieldname] = value
	return serializable(result)


def serializable(value: Any) -> Any:
	import frappe

	return json.loads(frappe.as_json(value))


def sanitize_for_audit(value: Any, *, max_length: int = 2000) -> str:
	def mask(item: Any) -> Any:
		if isinstance(item, dict):
			return {
				key: "***" if key.lower() in SENSITIVE_KEYS else mask(child)
				for key, child in item.items()
			}
		if isinstance(item, list):
			return [mask(child) for child in item[:50]]
		return item

	try:
		text = json.dumps(mask(value), ensure_ascii=False, default=str)
	except Exception:
		text = str(value)
	return text[:max_length]


def validate_text_file(file_name: str, content: str) -> tuple[str, bytes]:
	from pathlib import PurePath

	name = PurePath(file_name or "").name
	if not name or PurePath(name).suffix.lower() not in SAFE_FILE_EXTENSIONS:
		raise ValueError("Only .txt, .md, .csv and .json attachments are allowed")
	payload = (content or "").encode("utf-8")
	if not payload:
		raise ValueError("Attachment content cannot be empty")
	if len(payload) > 1024 * 1024:
		raise ValueError("Attachment content exceeds the 1 MB limit")
	return name, payload

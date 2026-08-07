from __future__ import annotations

from typing import Any

import frappe

from ione_core.mcp.audit import audited_tool
from ione_core.mcp.runtime import ToolAnnotations
from ione_core.mcp.security import (
	DENIED_DOCTYPES,
	ensure_doctype_permission,
	extract_docx_text,
	permitted_fields,
	require_login,
	safe_document,
	safe_fields,
	safe_filters,
	safe_write_data,
	serializable,
	validate_docx_file,
	validate_order_by,
	validate_text_file,
)
from ione_core.mcp.server import mcp

READ_ONLY = ToolAnnotations(
	readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
DRAFT_WRITE = ToolAnnotations(
	readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
)
UPSERT_WRITE = ToolAnnotations(
	readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


@mcp.tool(annotations=READ_ONLY)
@audited_tool("frappe_get_context", "读取")
def frappe_get_context() -> dict[str, Any]:
	"""Return the authenticated user, roles, site and installed Frappe applications."""
	user = require_login()
	return {
		"user": user,
		"roles": frappe.get_roles(user),
		"site": getattr(frappe.local, "site", ""),
		"installed_apps": frappe.get_installed_apps(),
	}


@mcp.tool(annotations=READ_ONLY)
@audited_tool("frappe_search_doctypes", "读取")
def frappe_search_doctypes(query: str, limit: int = 20) -> dict[str, Any]:
	"""Find non-child DocTypes that the authenticated user can read.

	Args:
		query: A DocType name fragment, such as Lead, Purchase or Wiki.
		limit: Maximum number of results from 1 to 50.
	"""
	require_login()
	limit = max(1, min(int(limit), 50))
	names = frappe.get_all(
		"DocType",
		filters={"name": ["like", f"%{(query or '').strip()}%"], "istable": 0},
		pluck="name",
		limit_page_length=limit * 4,
		order_by="name asc",
	)
	visible = [
		name for name in names if name not in DENIED_DOCTYPES and frappe.has_permission(name, ptype="read")
	][:limit]
	return {"query": query, "doctypes": visible, "count": len(visible)}


@mcp.tool(annotations=READ_ONLY)
@audited_tool("frappe_get_doctype_meta", "读取")
def frappe_get_doctype_meta(doctype: str) -> dict[str, Any]:
	"""Return safe field metadata for one readable business DocType.

	Args:
		doctype: Exact DocType name.
	"""
	meta = ensure_doctype_permission(doctype, "read")
	readable = permitted_fields(doctype, "read")
	writable = permitted_fields(doctype, "write") if frappe.has_permission(doctype, ptype="write") else set()
	fields = []
	for field in meta.fields:
		if field.fieldtype in {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Password"}:
			continue
		if field.fieldname not in readable and field.fieldname not in writable:
			continue
		fields.append(
			{
				"fieldname": field.fieldname,
				"label": field.label,
				"fieldtype": field.fieldtype,
				"options": field.options
				if field.fieldtype in {"Link", "Select", "Table", "Table MultiSelect"}
				else None,
				"required": bool(field.reqd),
				"read_only": bool(field.read_only),
				"readable": field.fieldname in readable,
				"writable": field.fieldname in writable and not field.read_only,
			}
		)
	return {
		"doctype": doctype,
		"title_field": meta.title_field,
		"search_fields": meta.search_fields,
		"is_submittable": bool(meta.is_submittable),
		"fields": fields,
	}


@mcp.tool(annotations=READ_ONLY)
@audited_tool("frappe_list_documents", "读取")
def frappe_list_documents(
	doctype: str,
	filters: dict[str, Any] | None = None,
	fields: list[str] | None = None,
	order_by: str = "modified desc",
	limit: int = 20,
	start: int = 0,
) -> dict[str, Any]:
	"""List business documents using the current user's Frappe permissions.

	Args:
		doctype: Exact business DocType name.
		filters: Frappe filter object using field names and values.
		fields: Fields to return. Password fields are never available.
		order_by: One field and optional asc or desc direction.
		limit: Maximum number of records from 1 to 100.
		start: Zero-based record offset for permission-aware pagination.
	"""
	meta = ensure_doctype_permission(doctype, "read")
	readable = permitted_fields(doctype, "read")
	limit = max(1, min(int(limit), 100))
	start = max(0, min(int(start), 100000))
	rows = frappe.get_list(
		doctype,
		filters=safe_filters(meta, filters, readable),
		fields=safe_fields(meta, fields, readable),
		order_by=validate_order_by(meta, order_by, readable),
		limit_start=start,
		limit_page_length=limit + 1,
	)
	has_more = len(rows) > limit
	rows = rows[:limit]
	return {
		"doctype": doctype,
		"records": serializable(rows),
		"count": len(rows),
		"start": start,
		"has_more": has_more,
		"next_start": start + len(rows) if has_more else None,
	}


@mcp.tool(annotations=READ_ONLY)
@audited_tool("frappe_get_document", "读取")
def frappe_get_document(doctype: str, name: str) -> dict[str, Any]:
	"""Get one business document after checking document-level read permission.

	Args:
		doctype: Exact business DocType name.
		name: Document name.
	"""
	ensure_doctype_permission(doctype, "read")
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	meta = frappe.get_meta(doctype)
	return {"doctype": doctype, "document": safe_document(doc, meta)}


@mcp.tool(annotations=READ_ONLY)
@audited_tool("frappe_list_attachments", "读取")
def frappe_list_attachments(
	doctype: str,
	document_name: str,
	include_text_content: bool = True,
) -> dict[str, Any]:
	"""List a document's attachments and optionally read small UTF-8 text attachments.

	Args:
		doctype: Parent business DocType.
		document_name: Parent document name.
		include_text_content: Include content for .txt, .md, .csv and .json files up to 1 MB total.
	"""
	ensure_doctype_permission(doctype, "read")
	doc = frappe.get_doc(doctype, document_name)
	doc.check_permission("read")
	rows = frappe.get_all(
		"File",
		filters={"attached_to_doctype": doctype, "attached_to_name": document_name},
		fields=[
			"name",
			"file_name",
			"file_url",
			"is_private",
			"file_size",
			"creation",
			"modified",
		],
		order_by="creation asc",
		limit_page_length=50,
	)
	attachments = []
	remaining_text_bytes = 1024 * 1024
	for row in rows:
		item = serializable(row)
		file_name = str(row.get("file_name") or "")
		if (
			include_text_content
			and not str(row.get("file_url") or "").startswith(("http://", "https://"))
			and file_name.lower().endswith((".txt", ".md", ".csv", ".json"))
		):
			file_size = int(row.get("file_size") or 0)
			if 0 < file_size <= remaining_text_bytes:
				content = frappe.get_doc("File", row.name).get_content()
				if isinstance(content, bytes):
					for encoding in ("utf-8-sig", "utf-8", "gb18030"):
						try:
							content = content.decode(encoding)
							break
						except UnicodeDecodeError:
							continue
				if isinstance(content, str):
					encoded_size = len(content.encode("utf-8"))
					if encoded_size <= remaining_text_bytes:
						item["content"] = content
						remaining_text_bytes -= encoded_size
		attachments.append(item)
	return {"doctype": doctype, "name": document_name, "attachments": attachments, "count": len(attachments)}


@mcp.tool(annotations=READ_ONLY)
@audited_tool("frappe_read_word_attachment", "读取")
def frappe_read_word_attachment(doctype: str, document_name: str, file_name: str) -> dict[str, Any]:
	"""Read text from one small DOCX attachment after checking parent document permission.

	Args:
		doctype: Parent business DocType.
		document_name: Parent document name.
		file_name: Exact attached .docx file name returned by frappe_list_attachments.
	"""
	ensure_doctype_permission(doctype, "read")
	doc = frappe.get_doc(doctype, document_name)
	doc.check_permission("read")
	name = str(file_name or "").strip()
	if not name.lower().endswith(".docx"):
		raise ValueError("Only .docx Word attachments can be read")
	file_row = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": doctype,
			"attached_to_name": document_name,
			"file_name": name,
		},
		fields=["name", "file_name", "file_url", "file_size", "modified"],
		order_by="modified desc",
		limit_page_length=1,
	)
	if not file_row:
		frappe.throw(f"Word attachment {name} was not found on {doctype} {document_name}")
	row = file_row[0]
	if str(row.file_url or "").startswith(("http://", "https://")):
		frappe.throw("Remote Word attachments cannot be read through MCP")
	payload = frappe.get_doc("File", row.name).get_content()
	if isinstance(payload, str):
		payload = payload.encode("utf-8")
	text = extract_docx_text(bytes(payload))
	return {
		"doctype": doctype,
		"name": document_name,
		"file_name": row.file_name,
		"file_url": row.file_url,
		"characters": len(text),
		"content": text,
	}


@mcp.tool(annotations=DRAFT_WRITE)
@audited_tool("frappe_create_document", "写入")
def frappe_create_document(doctype: str, data: dict[str, Any]) -> dict[str, Any]:
	"""Create one draft business document with normal Frappe validations and permissions.

	Args:
		doctype: Exact business DocType name.
		data: Field values. Submission and protected system fields are not accepted.
	"""
	meta = ensure_doctype_permission(doctype, "create")
	payload = safe_write_data(meta, data, permitted_fields(doctype, "write"))
	payload["doctype"] = doctype
	savepoint = "ione_mcp_create"
	frappe.db.savepoint(savepoint)
	try:
		doc = frappe.get_doc(payload).insert()
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise
	return {"doctype": doctype, "name": doc.name, "docstatus": doc.docstatus}


@mcp.tool(annotations=DRAFT_WRITE)
@audited_tool("frappe_update_document", "写入")
def frappe_update_document(doctype: str, name: str, data: dict[str, Any]) -> dict[str, Any]:
	"""Update one draft business document with normal Frappe validations and permissions.

	Args:
		doctype: Exact business DocType name.
		name: Existing document name.
		data: Writable field values. Submitted documents cannot be changed.
	"""
	meta = ensure_doctype_permission(doctype, "write")
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw("MCP can update draft documents only")
	payload = safe_write_data(meta, data, permitted_fields(doctype, "write"))
	payload.pop("name", None)
	savepoint = "ione_mcp_update"
	frappe.db.savepoint(savepoint)
	try:
		doc.update(payload)
		doc.save()
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise
	return {"doctype": doctype, "name": doc.name, "modified": serializable(doc.modified)}


@mcp.tool(annotations=DRAFT_WRITE)
@audited_tool("frappe_attach_text_file", "写入")
def frappe_attach_text_file(
	doctype: str,
	document_name: str,
	file_name: str,
	content: str,
) -> dict[str, Any]:
	"""Attach a private UTF-8 text, Markdown, CSV or JSON file to a writable document.

	Args:
		doctype: Parent business DocType.
		document_name: Parent document name.
		file_name: Safe file name ending in .txt, .md, .csv or .json.
		content: UTF-8 text content, limited to 1 MB.
	"""
	ensure_doctype_permission(doctype, "write")
	doc = frappe.get_doc(doctype, document_name)
	doc.check_permission("write")
	name, payload = validate_text_file(file_name, content)
	from frappe.utils.file_manager import save_file

	file_doc = save_file(name, payload, doctype, document_name, is_private=1)
	return {"doctype": doctype, "name": document_name, "file": file_doc.file_url}


@mcp.tool(annotations=DRAFT_WRITE)
@audited_tool("frappe_attach_word_file", "写入")
def frappe_attach_word_file(
	doctype: str,
	document_name: str,
	file_name: str,
	content_base64: str,
) -> dict[str, Any]:
	"""Attach a private, validated Word .docx file to a writable business document.

	Args:
		doctype: Parent business DocType.
		document_name: Parent document name.
		file_name: Safe file name ending in .docx.
		content_base64: Base64-encoded DOCX package, limited to 5 MB.
	"""
	ensure_doctype_permission(doctype, "write")
	doc = frappe.get_doc(doctype, document_name)
	doc.check_permission("write")
	name, payload = validate_docx_file(file_name, content_base64)
	from frappe.utils.file_manager import save_file

	file_doc = save_file(name, payload, doctype, document_name, is_private=1)
	return {"doctype": doctype, "name": document_name, "file": file_doc.file_url}


@mcp.tool(annotations=DRAFT_WRITE)
@audited_tool("frappe_convert_lead_to_deal", "转换")
def frappe_convert_lead_to_deal(
	lead: str,
	deal_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
	"""Convert one CRM Lead to a CRM Deal through CRM's official conversion service.

	The operation is idempotent: when a Deal already references the Lead, that Deal is returned.

	Args:
		lead: Exact CRM Lead document name.
		deal_data: Optional writable CRM Deal values such as next_step or expected_closure_date.
	"""
	ensure_doctype_permission("CRM Lead", "write")
	ensure_doctype_permission("CRM Deal", "create")
	lead_doc = frappe.get_doc("CRM Lead", lead)
	lead_doc.check_permission("write")
	existing_deal = frappe.db.get_value("CRM Deal", {"lead": lead}, "name")
	if existing_deal:
		frappe.get_doc("CRM Deal", existing_deal).check_permission("read")
		return {"lead": lead, "deal": existing_deal, "created": False}
	if lead_doc.get("converted"):
		frappe.throw("Lead is marked as converted but no linked CRM Deal was found")

	payload = None
	if deal_data:
		deal_meta = frappe.get_meta("CRM Deal")
		payload = safe_write_data(deal_meta, deal_data, permitted_fields("CRM Deal", "write"))
		for protected_field in ("name", "lead", "contacts", "contact", "organization", "naming_series"):
			payload.pop(protected_field, None)
		if not payload:
			payload = None

	savepoint = "ione_mcp_convert_lead"
	frappe.db.savepoint(savepoint)
	try:
		from crm.fcrm.doctype.crm_lead.crm_lead import convert_to_deal

		deal = convert_to_deal(lead=lead, deal=payload)
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise
	frappe.get_doc("CRM Deal", deal).check_permission("read")
	return {"lead": lead, "deal": deal, "created": True}


@mcp.tool(annotations=UPSERT_WRITE)
@audited_tool("frappe_upsert_deal_presentation", "生成演示")
def frappe_upsert_deal_presentation(
	deal: str,
	title: str,
	slides: list[dict[str, Any]],
	make_public: bool | None = None,
) -> dict[str, Any]:
	"""Create or update a Frappe Slides presentation linked to one CRM Deal.

	The slide input is a bounded business-content schema. The server renders it into editable
	Frappe Slides elements and reuses the Deal's linked presentation on repeated calls.

	Args:
		deal: Exact CRM Deal document name.
		title: Customer-facing presentation title.
		slides: Four to twenty slide objects using cover, section, content, metrics, timeline or closing layouts.
		make_public: Set public link access only when explicitly requested; omit to preserve the current setting.
	"""
	if "slides" not in frappe.get_installed_apps() or not frappe.db.exists("DocType", "Presentation"):
		frappe.throw("Frappe Slides is not installed on this site")

	from ione_core.mcp.slides import build_presentation_slides
	from ione_core.setup.slides_integration import ensure_deal_presentation_field

	ensure_deal_presentation_field()
	ensure_doctype_permission("CRM Deal", "write")
	deal_doc = frappe.get_doc("CRM Deal", deal)
	deal_doc.check_permission("write")
	presentation_title = " ".join(str(title or "").split())
	if not presentation_title or len(presentation_title) > 140:
		raise ValueError("title is required and must not exceed 140 characters")
	rendered_slides = build_presentation_slides(slides)

	linked_name = deal_doc.get("custom_customer_presentation")
	created = not bool(linked_name and frappe.db.exists("Presentation", linked_name))
	if created:
		ensure_doctype_permission("Presentation", "create")
		presentation = frappe.new_doc("Presentation")
		presentation.title = presentation_title
		presentation.theme = "Light"
		presentation.thumbnail = "/assets/slides/frontend/images/layouts/light/thumbnail-3.webp"
	else:
		ensure_doctype_permission("Presentation", "write")
		presentation = frappe.get_doc("Presentation", linked_name)
		presentation.check_permission("write")
		presentation.title = presentation_title

	if make_public is not None:
		presentation.is_public = int(bool(make_public))
	presentation.set("slides", [])
	for slide in rendered_slides:
		presentation.append("slides", slide)

	savepoint = "ione_mcp_deal_presentation"
	frappe.db.savepoint(savepoint)
	try:
		if created:
			presentation.insert()
		else:
			presentation.save()
		if deal_doc.get("custom_customer_presentation") != presentation.name:
			deal_doc.db_set("custom_customer_presentation", presentation.name)
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise

	editor_path = f"/slides/presentation/{presentation.name}"
	slideshow_path = f"/slides/slideshow/{presentation.name}"
	return {
		"deal": deal_doc.name,
		"presentation": presentation.name,
		"title": presentation.title,
		"slide_count": len(rendered_slides),
		"created": created,
		"is_public": bool(presentation.is_public),
		"editor_url": frappe.utils.get_url(editor_path),
		"slideshow_url": frappe.utils.get_url(slideshow_path),
	}

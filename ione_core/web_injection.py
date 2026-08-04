from __future__ import annotations

CRM_I18N_ASSET = "/assets/ione_core/js/crm_i18n_20260804.js?v=20260804-3"
CRM_I18N_MARKER = 'data-ione-crm-i18n="20260804-3"'


def is_crm_html_response(
	*,
	path: str,
	method: str,
	status_code: int,
	content_type: str,
	language: str,
) -> bool:
	"""Return whether a response needs the CRM-only localization asset."""
	normalized_path = (path or "").split("?", 1)[0].rstrip("/") or "/"
	normalized_language = (language or "").lower().replace("-", "_")
	return (
		method.upper() == "GET"
		and status_code == 200
		and (normalized_path == "/crm" or normalized_path.startswith("/crm/"))
		and "text/html" in (content_type or "").lower()
		and normalized_language.split("_", 1)[0] == "zh"
	)


def inject_crm_i18n_asset(html: str) -> str:
	"""Insert the localization script once, immediately before the closing body tag."""
	if not html or CRM_I18N_MARKER in html or "</body>" not in html:
		return html
	tag = (
		f'<script defer charset="utf-8" src="{CRM_I18N_ASSET}" '
		f'{CRM_I18N_MARKER}></script>'
	)
	return html.replace("</body>", f"{tag}\n</body>", 1)


def inject_crm_i18n(response, request) -> None:
	"""Inject I-ONE CRM localization without changing the upstream CRM application."""
	try:
		import frappe

		language = str(getattr(frappe.local, "lang", "") or "")
		content_type = response.headers.get("Content-Type", "")
		if not is_crm_html_response(
			path=request.path,
			method=request.method,
			status_code=response.status_code,
			content_type=content_type,
			language=language,
		):
			return

		html = response.get_data(as_text=True)
		localized_html = inject_crm_i18n_asset(html)
		if localized_html != html:
			response.set_data(localized_html)
	except (AttributeError, RuntimeError, TypeError, UnicodeDecodeError):
		# Response hooks must never make CRM unavailable if a non-HTML response differs.
		return

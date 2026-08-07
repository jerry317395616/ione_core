from __future__ import annotations


def ensure_deal_presentation_field() -> bool:
	import frappe

	if "slides" not in frappe.get_installed_apps():
		return False
	if not frappe.db.exists("DocType", "CRM Deal") or not frappe.db.exists("DocType", "Presentation"):
		return False

	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"CRM Deal": [
				{
					"fieldname": "custom_customer_presentation",
					"label": "客户演示",
					"fieldtype": "Link",
					"options": "Presentation",
					"read_only": 1,
					"no_copy": 1,
					"description": "由 I-ONE Agent 根据商机方案生成的 Frappe Slides 客户演示",
				}
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="CRM Deal")
	return True

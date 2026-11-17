"""Apply a versioned app menu default through Frappe's site customization layer."""

import frappe


def install(module, sections, version, *, label=None):
	marker = "ione_core.sidebar_defaults:" + version
	if frappe.db.exists("Patch Log", {"patch": marker}):
		return False
	from frappe.desk.doctype.custom_sidebar.custom_sidebar import get_customization, save_site_sidebar
	from frappe.desk.doctype.sidebar.sidebar import get_module_base, item_key

	base = [dict(row) for row in get_module_base(module).rows]
	current = get_customization(module, None)
	old = frappe.get_doc("Custom Sidebar", current.name).sidebar_items if current else []
	rows = arrange(base, [row.as_dict() for row in old], sections, item_key)
	save_site_sidebar(module, items=rows, label=label)
	frappe.get_doc({"doctype": "Patch Log", "patch": marker}).insert(ignore_permissions=True)
	return True


def arrange(base, previous, sections, item_key):
	identity = ("link_type", "link_to", "url", "route", "filters", "route_options", "navigate_to_tab")
	body = (
		"type",
		"label",
		"icon",
		"child",
		"indent",
		"collapsible",
		"show_arrow",
		"keep_closed",
		"open_in_new_tab",
		*identity,
	)
	result = []
	for section in sections:
		result.append(
			dict(
				type="Section Break",
				label=section["label"],
				icon=section.get("icon"),
				added=1,
				hidden=0,
				child=0,
				indent=1,
				collapsible=1,
				show_arrow=1,
			)
		)
		for entry in section["items"]:
			source = next(
				(
					row
					for row in base
					if row.get("link_type") == entry["link_type"]
					and row.get("link_to") == entry["link_to"]
					and not row.get("route")
					and not row.get("filters")
					and not row.get("route_options")
				),
				None,
			)
			row = {key: source.get(key) for key in identity} if source else dict(entry)
			result.append(
				{**row, **entry, "type": "Link", "child": 1, "hidden": 0, "added": int(source is None)}
			)
	used = {item_key(row) for row in result}
	# Hidden references retain every old entry for the native editor and recovery.
	# Site-added entries keep their body, while app rows remain native references.
	for source in [*base, *previous]:
		key = item_key(source)
		if key in used:
			continue
		used.add(key)
		row = {field: source.get(field) for field in body if field in source}
		row.update(key=key, added=int(bool(source.get("added"))), hidden=1)
		result.append(row)
	return result

from __future__ import annotations

import frappe

APP_TITLES = {
	"frappe": "框架",
}


def ensure_desktop_app_labels() -> dict[str, int]:
	"""Persist localized labels for sites using the Desktop Icons page."""
	if not frappe.db.exists("DocType", "Desktop Icon"):
		return {"updated": 0}

	icons = frappe.get_all(
		"Desktop Icon",
		filters={"icon_type": "App", "app": ("in", tuple(APP_TITLES))},
		fields=["name", "label", "app"],
		limit_page_length=0,
	)
	updated = 0
	for icon in icons:
		label = APP_TITLES.get(icon.app)
		if not label or icon.label == label:
			continue
		frappe.db.set_value(
			"Desktop Icon",
			icon.name,
			"label",
			label,
			update_modified=False,
		)
		updated += 1

	if updated:
		# These are hashes keyed by user. Removing the complete hashes ensures
		# existing sessions also receive the new label on their next reload.
		frappe.cache.delete_key("desktop_icons")
		frappe.cache.delete_key("bootinfo")

	return {"updated": updated}


def localize_app_titles(bootinfo) -> None:
	"""Localize titles for the hook-driven Apps desktop page."""
	for app in getattr(bootinfo, "app_data", None) or []:
		app_name = app.get("app_name")
		if app_name in APP_TITLES:
			app["app_title"] = APP_TITLES[app_name]

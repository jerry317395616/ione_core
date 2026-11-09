"""Project effective business access into desk and console navigation.

This is a visibility policy, never an authorization grant. Native sidebar resolution,
document permissions, domains, disabled apps and module/customization rules still apply.
Automatic roles provide account conveniences, not business application membership.
"""

from functools import cached_property
from hashlib import sha256

import frappe


def require_staff():
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(frappe._("Please log in."), frappe.AuthenticationError)
	staff = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
	if not staff or not staff.enabled or staff.user_type != "System User":
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)


class NavigationPolicy:
	def __init__(self):
		from frappe.permissions import AUTOMATIC_ROLES, get_valid_perms

		self.administrator = frappe.session.user == "Administrator"
		roles = set(frappe.get_roles()) - set(AUTOMATIC_ROLES)
		if roles:
			roles -= set(
				frappe.get_all("Role", filters={"name": ["in", list(roles)], "disabled": 1}, pluck="name")
			)
		self.roles = roles
		# Custom DocPerm replaces standard DocPerm for the entire DocType, exactly as in Frappe.
		self.readable = {p.parent for p in get_valid_perms(roles=list(roles)) if p.read} if roles else set()
		self._allowed = {}
		self._owners = {}

	@cached_property
	def views(self):
		from frappe.desk.desk_views import DeskViews

		return DeskViews()

	def owner(self, kind, name):
		key = (kind, name)
		if key not in self._owners:
			from frappe.utils.modules import get_module_placement

			module = frappe.db.get_value(kind, name, "module", cache=True)
			self._owners[key] = get_module_placement(module) if module else None
		return self._owners[key]

	def allows(self, kind, name, app=None):
		"""An entry needs an explicit grant and the native permission check.

		When app is given, only that app's own targets can establish membership.
		A curated User link in ERPNext must not turn User access into ERPNext access.
		"""
		key = (kind, name, app)
		if key in self._allowed:
			return self._allowed[key]
		self._allowed[key] = False  # workspace cycles fail closed
		if not name or kind not in ("DocType", "Page", "Report", "Workspace", "Dashboard"):
			return False
		from frappe.desk.utils import is_item_allowed

		if not is_item_allowed(name, kind, self.views):
			return False
		if kind == "Workspace":
			doc = frappe.get_cached_doc(kind, name)
			rows = [*doc.get("links"), *doc.get("shortcuts")]
			allowed = any(
				self.allows(row.get("link_type") or row.get("type"), row.get("link_to"), app)
				for row in rows
				if (row.get("link_type") or row.get("type"))
				in ("DocType", "Page", "Report", "Workspace", "Dashboard")
			)
			allowed = allowed or any(
				self.allows("DocType", row.document_type, app) for row in doc.get("quick_lists")
			)
			allowed = allowed or any(
				self.card_allows("Dashboard Chart", row.chart_name, app) for row in doc.get("charts")
			)
			allowed = allowed or any(
				self.card_allows("Number Card", row.number_card_name, app) for row in doc.get("number_cards")
			)
		elif kind == "DocType":
			allowed = name in self.readable and bool(frappe.has_permission(name, "read"))
		elif kind in ("Page", "Report"):
			doc = frappe.get_cached_doc(kind, name)
			custom = frappe.db.get_value("Custom Role", {kind.lower(): name}, "name")
			role_doc = frappe.get_cached_doc("Custom Role", custom) if custom else doc
			explicit = bool(self.roles.intersection(row.role for row in role_doc.get("roles")))
			ref = role_doc.get("ref_doctype") or doc.get("ref_doctype")
			# A report needs its reference DocType; an explicit Page role is itself a grant.
			allowed = self.allows("DocType", ref) if kind == "Report" else explicit
		elif kind == "Dashboard":
			doc = frappe.get_cached_doc(kind, name)
			allowed = any(self.card_allows("Dashboard Chart", row.chart, app) for row in doc.get("charts"))
			allowed = allowed or any(
				self.card_allows("Number Card", row.card, app) for row in doc.get("cards")
			)
			allowed = allowed or "Dashboard" in self.readable
		else:
			allowed = False  # URL/help and account basics cannot establish business access.
		if allowed and app and kind != "Workspace":
			allowed = self.owner(kind, name) == app
		self._allowed[key] = bool(allowed)
		return bool(allowed)

	def card_allows(self, kind, name, app):
		if not name:
			return False
		card = frappe.get_cached_doc(kind, name)
		return self.allows("DocType", card.get("document_type"), app) or self.allows(
			"Report", card.get("report_name"), app
		)

	def filter_sidebars(self, sidebars):
		if self.administrator:
			return sidebars
		candidates = {}
		apps = set()
		for shell, sidebar in sidebars.items():
			app = sidebar.get("app")
			rows = sidebar.get("items") or []
			kept = [
				row
				for row in rows
				if row.get("type") in ("Section Break", "Spacer")
				or row.get("link_type") in ("URL", "Help")
				or self.allows(row.get("link_type"), row.get("link_to"))
			]
			if any(
				self.allows(row.get("link_type"), row.get("link_to"), app)
				for row in kept
				if row.get("link_to")
			):
				apps.add(app)
			candidates[shell] = {**sidebar, "items": prune_sections(kept)}
		return {
			shell: sidebar
			for shell, sidebar in candidates.items()
			if sidebar.get("app") in apps
			and any(self.allows(row.get("link_type"), row.get("link_to")) for row in sidebar["items"])
		}


def prune_sections(rows):
	"""Keep the native section/child relationship, including intervening root rows."""
	section = None
	populated = set()
	for index, row in enumerate(rows):
		if row.get("type") == "Section Break":
			section = index
		elif section is not None and row.get("child") and row.get("type") != "Spacer":
			populated.add(section)
	return [row for index, row in enumerate(rows) if row.get("type") != "Section Break" or index in populated]


def projection(sidebars=None):
	from frappe.boot import get_module_sidebars

	policy = NavigationPolicy()
	return policy, policy.filter_sidebars(get_module_sidebars() if sidebars is None else sidebars)


def registered_apps(policy, sidebars):
	from frappe.apps import get_docked_apps
	from frappe.boot import get_app_rail_host_map
	from frappe.core.doctype.installed_applications.installed_applications import (
		get_setup_wizard_completed_apps,
		get_setup_wizard_not_required_apps,
	)

	from ione_core.desktop_i18n import get_hidden_apps

	accessible = {s.get("app") for s in sidebars.values()}
	hosts = get_app_rail_host_map()
	accessible.update(host for companion, host in hosts.items() if companion in accessible)
	hidden = set() if policy.administrator else get_hidden_apps()
	docked = get_docked_apps()
	ready = set(get_setup_wizard_completed_apps()) | set(get_setup_wizard_not_required_apps())
	result = []
	for app in frappe.get_active_apps():
		if app in docked or app in hidden or (not policy.administrator and app not in accessible):
			continue
		if app not in ready and not policy.administrator and "System Manager" not in policy.roles:
			continue
		for detail in frappe.get_hooks("add_to_apps_screen", app_name=app):
			# Desk membership is derived from native-permitted business entries. Its old
			# coarse role-name hook must not veto a custom role with real DocPerm grants.
			# Non-desk applications keep their application-specific access gate as well.
			route = detail.get("route") or ""
			permission = detail.get("has_permission")
			if (
				not policy.administrator
				and not route.startswith(("/desk", "/app/"))
				and permission
				and not frappe.get_attr(permission)()
			):
				continue
			if not policy.administrator and route.startswith("/desk"):
				from frappe.desk.doctype.sidebar.sidebar import shell_slug

				# The registered landing may be a setup module this user cannot open.
				shell = next(
					(
						name
						for name, sidebar in sidebars.items()
						if hosts.get(sidebar.get("app"), sidebar.get("app")) == app
					),
					None,
				)
				if shell:
					route = "/desk/" + shell_slug(shell)
			result.append(
				{
					"name": app,
					"title": frappe._(detail.get("title")),
					"logo": detail.get("logo"),
					"route": route,
					"setup_wizard_text": frappe._(detail["setup_wizard_text"])
					if detail.get("setup_wizard_text")
					else None,
				}
			)
	return result


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def get_apps():
	require_staff()
	policy, sidebars = projection()
	return registered_apps(policy, sidebars)


def sidebar_navigation(rows, shell):
	# Same section state machine as Frappe Sidebar.nest_section_items.
	roots = []
	section = None
	for row in rows:
		key = sha256((shell + "\0" + row["key"]).encode()).hexdigest()
		if row.get("type") == "Section Break":
			section = {
				"type": "section",
				"key": key,
				"title": row.get("label") or "",
				"icon": row.get("icon") or None,
				**{
					field: bool(row.get(field))
					for field in ("indent", "collapsible", "show_arrow", "keep_closed")
				},
				"children": [],
			}
			roots.append(section)
			continue
		if row.get("type") == "Spacer":
			node = {"type": "divider", "key": key}
		elif row.get("link_to") or row.get("url"):
			node = {
				"type": "item",
				"key": key,
				"id": sha256(row["key"].encode()).hexdigest(),
				"title": row.get("label") or row.get("link_to") or frappe._("Link"),
				"icon": row.get("icon") or None,
			}
		else:
			continue
		(section["children"] if section is not None and row.get("child") else roots).append(node)
	return [
		node
		for node in roots
		if node["type"] != "section" or any(child["type"] == "item" for child in node["children"])
	]


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_application(app_name):
	require_staff()
	policy, sidebars = projection()
	app = next((app for app in registered_apps(policy, sidebars) if app["name"] == app_name), None)
	if not app:
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
	modules = {}
	# Business application contents remain outside the current console implementation.
	if app_name == "frappe":
		for shell, sidebar in sidebars.items():
			if sidebar.get("app") != app_name:
				continue
			name = sidebar["module"]
			module = modules.setdefault(
				name, {"name": name, "title": frappe._(name), "items": [], "navigation": []}
			)
			module["navigation"].extend(sidebar_navigation(sidebar["items"], shell))
			seen = {item["id"] for item in module["items"]}
			for row in sidebar["items"]:
				if row.get("type") in ("Section Break", "Spacer") or not (
					row.get("link_to") or row.get("url")
				):
					continue
				item_id = sha256(row["key"].encode()).hexdigest()
				if item_id not in seen:
					module["items"].append(
						{"id": item_id, "title": row.get("label") or row.get("link_to") or frappe._("Link")}
					)
					seen.add(item_id)
	return {
		"app": {key: app.get(key) for key in ("name", "title", "logo")},
		"supported": app_name == "frappe",
		"modules": list(modules.values()),
	}


def filter_boot(bootinfo):
	"""Apply the same policy to native Desk, including its dock and route maps."""
	if frappe.session.user in ("Guest", "Administrator"):
		return
	from frappe.boot import build_entity_module_map, get_app_data, get_app_rail_host_map
	from frappe.desk.doctype.dock.dock import get_app_entry_set
	from frappe.desk.doctype.sidebar.sidebar import build_canonical_shells

	policy, sidebars = projection(bootinfo.get("module_sidebars"))
	apps = {app["name"]: app for app in registered_apps(policy, sidebars)}
	hosts = get_app_rail_host_map()
	visible = set(apps) | {companion for companion, host in hosts.items() if host in apps}
	sidebars = {shell: sidebar for shell, sidebar in sidebars.items() if sidebar.get("app") in visible}
	bootinfo["module_sidebars"] = sidebars
	bootinfo["entity_module"] = build_entity_module_map(sidebars)
	bootinfo["canonical_shell"], bootinfo["home_shell"] = build_canonical_shells(
		sidebars, bootinfo["entity_module"], policy.views
	)

	def dock_rows(rows):
		return [
			row
			for row in rows
			if (row.get("link_type") == "Sidebar" and row.get("link_to") in sidebars)
			or (row.get("link_type") == "Workspace" and policy.allows("Workspace", row.get("link_to")))
			or row.get("link_type") == "URL"
		]

	app_data = []
	for entry in bootinfo["app_data"] if "app_data" in bootinfo else get_app_data():
		app = entry.get("app_name")
		if app not in visible:
			continue
		metadata = apps.get(app)
		app_data.append(
			{
				**entry,
				"on_apps_screen": bool(metadata),
				"app_route": metadata["route"] if metadata else entry.get("app_route", ""),
				"dock": dock_rows(get_app_entry_set(app)),
			}
		)
	bootinfo["app_data"] = app_data
	if "dock" in bootinfo:
		bootinfo["dock"] = {app: dock_rows(rows) for app, rows in bootinfo["dock"].items() if app in apps}
	if "desktop_icons" in bootinfo:
		bootinfo["desktop_icons"] = [
			icon
			for icon in bootinfo["desktop_icons"]
			if (icon.get("icon_type") == "App" and icon.get("app") in apps)
			or (
				icon.get("icon_type") != "App"
				and (
					icon.get("link_to") in sidebars
					or policy.allows(icon.get("link_type"), icon.get("link_to"))
				)
			)
		]


def filter_navigation_response(response, request=None):
	"""Workspace/sidebar writes can send fresh navigation without another boot."""
	if response.mimetype != "application/json":
		return
	data = response.get_json(silent=True)
	payload = data.get("message") if isinstance(data, dict) else None
	if isinstance(payload, dict) and "module_sidebars" in payload:
		filter_boot(payload)
		response.set_data(frappe.as_json(data))

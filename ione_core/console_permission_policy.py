"""Explicit, module-scoped permission administration, separate from Role CRUD."""

import frappe

from ione_core.console_roles import get_readable_role, present, require_reader
from ione_core.navigation import NavigationPolicy

GRANT = "I-ONE Permission Administration"
MODULE = "I-ONE Permission Module"
PROTECTED = {GRANT, MODULE, "DocType", "Patch Log", "Module Def"}


def require_supervisor():
	policy = NavigationPolicy()
	if not policy.administrator and "System Manager" not in policy.roles:
		frappe.throw("只有系统权限管理员可以变更权限配置授权。", frappe.PermissionError)


def business_modules():
	installed = set(frappe.get_installed_apps()) - {"frappe"}
	return {
		row.name
		for row in frappe.get_all("Module Def", fields=["name", "app_name"])
		if row.app_name in installed
	}


def authority():
	require_reader()
	policy = NavigationPolicy()
	if policy.administrator or "System Manager" in policy.roles:
		return {"supervisor": True, "view_modules": None, "edit_modules": None}
	view, edit = set(), set()
	if frappe.db.exists("DocType", GRANT):
		for row in frappe.get_all(
			GRANT,
			filters={"enabled": 1, "manager_role": ["in", list(policy.roles)]},
			fields=["name", "can_edit"],
		):
			modules = set(
				frappe.get_all(MODULE, filters={"parent": row.name, "parenttype": GRANT}, pluck="module")
			)
			view.update(modules)
			if row.can_edit:
				edit.update(modules)
	allowed = business_modules()
	return {"supervisor": False, "view_modules": view & allowed, "edit_modules": edit & allowed}


def capabilities():
	scope = authority()
	return {"can_view": scope["supervisor"] or bool(scope["view_modules"])}


def role_scope(role):
	scope = authority()
	if not scope["supervisor"] and not scope["view_modules"]:
		frappe.throw("当前账号没有业务权限配置授权。", frappe.PermissionError)
	doc = get_readable_role(role)
	protected = present({"name": role})["is_reserved"] or frappe.db.exists(
		"User Type", {"role": role, "is_standard": 0}
	)
	return scope, doc, not (protected or doc.disabled)


def allowed_doctypes(scope):
	filters = {"istable": 0}
	if not scope["supervisor"]:
		filters["module"] = ["in", sorted(scope["view_modules"])]
	domains = set(frappe.get_active_domains())
	return [
		row
		for row in frappe.get_all(
			"DocType",
			filters=filters,
			fields=["name", "module", "restrict_to_domain", "issingle", "is_submittable", "allow_import"],
			order_by="name",
		)
		if row.name not in PROTECTED and (not row.restrict_to_domain or row.restrict_to_domain in domains)
	]


def can_edit(scope, editable_role, module):
	return bool(editable_role and (scope["supervisor"] or module in scope["edit_modules"]))


def provision_business_manager(role, modules=None, can_edit=True):
	"""Explicit operator provisioning; never called by install/migrate or exposed as an API."""
	require_supervisor()
	if present({"name": role})["is_reserved"] or not frappe.db.exists("Role", role):
		frappe.throw("请选择普通管理角色。")
	allowed = business_modules()
	selected = set(modules) if modules is not None else allowed
	if not selected or selected - allowed:
		frappe.throw("授权范围必须是有效业务模块。")
	doc = frappe.get_doc(GRANT, role) if frappe.db.exists(GRANT, role) else frappe.new_doc(GRANT)
	doc.manager_role = role
	doc.enabled = 1
	doc.can_edit = int(bool(can_edit))
	doc.set("modules", [{"module": name} for name in sorted(selected)])
	doc.save()
	return doc.name

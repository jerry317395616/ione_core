"""Role assignment adapters with native document and field permissions."""
# ruff: noqa: RUF001

import frappe

from ione_core.console_user_creation import assignable_roles, field_error
from ione_core.navigation import NavigationPolicy, require_staff

STANDARD_USERS = {"Administrator", "Guest"}


def access():
	require_staff()
	policy = NavigationPolicy()
	meta = frappe.get_meta("User")

	def allowed(field, right):
		return policy.administrator or any(
			p.role in policy.roles and p.permlevel == meta.get_field(field).permlevel and p.get(right)
			for p in meta.permissions
		)

	can_view = allowed("roles", "read") and bool(frappe.has_permission("User", "read"))
	return {
		"can_view": can_view,
		"can_edit": can_view
		and allowed("roles", "write")
		and (
			policy.administrator
			or any(p.role in policy.roles and p.permlevel == 0 and p.write for p in meta.permissions)
		),
		"profile_read": allowed("role_profiles", "read"),
		"profile_write": allowed("role_profiles", "write"),
		"is_administrator": policy.administrator,
	}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_role_access():
	permissions = access()
	frappe.local.response_headers["Cache-Control"] = "private, no-store"
	return {key: permissions[key] for key in ("can_view", "can_edit", "is_administrator")}


def target_user(user, permissions):
	if not permissions["can_view"]:
		frappe.throw("当前账号没有查看用户角色的权限。", frappe.PermissionError)
	if not isinstance(user, str) or not user or len(user) > 140:
		frappe.throw("请选择有效的用户。", frappe.ValidationError)
	doc = frappe.get_doc("User", user)
	doc.check_permission("read")
	return doc


def profiles_of(doc):
	return list(
		dict.fromkeys(
			[row.role_profile for row in doc.role_profiles]
			+ ([doc.role_profile_name] if doc.role_profile_name else [])
		)
	)


def editable(doc, permissions):
	return bool(
		permissions["can_edit"]
		and doc.name not in STANDARD_USERS
		and doc.user_type in ("System User", "Website User")
		and doc.has_permission("write")
		and (not profiles_of(doc) or permissions["profile_write"])
	)


def profile_options(allowed_roles):
	if not (frappe.has_permission("Role Profile", "read") or frappe.has_permission("Role Profile", "select")):
		return []
	names = frappe.get_list(
		"Role Profile", fields=["name"], order_by="name", limit_page_length=0, ignore_permissions=False
	)
	result = []
	for row in names:
		profile = frappe.get_cached_doc("Role Profile", row.name)
		roles = list(dict.fromkeys(role.role for role in profile.roles))
		result.append({"name": row.name, "roles": roles, "available": not bool(set(roles) - allowed_roles)})
	return result


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_user_roles(user):
	permissions = access()
	doc = target_user(user, permissions)
	can_edit = editable(doc, permissions)
	choices = (
		[
			{"name": row.name, "label": frappe._(row.name), "desk_access": bool(row.desk_access)}
			for row in assignable_roles()
		]
		if can_edit
		else []
	)
	profiles = (
		profile_options({role["name"] for role in choices})
		if can_edit and permissions["profile_write"]
		else []
	)
	from frappe.permissions import AUTOMATIC_ROLES

	frappe.local.response_headers["Cache-Control"] = "private, no-store"
	return {
		"user": {
			"name": doc.name,
			"full_name": doc.full_name,
			"email": doc.email,
			"enabled": bool(doc.enabled),
			"user_type": doc.user_type,
			"modified": doc.modified,
		},
		"can_edit": can_edit,
		"can_use_profiles": can_edit and permissions["profile_write"],
		"protected": doc.name in STANDARD_USERS,
		"roles": [row.role for row in doc.roles if row.role not in AUTOMATIC_ROLES],
		"role_profiles": profiles_of(doc) if permissions["profile_read"] else [],
		"mode": "profiles" if profiles_of(doc) else "direct",
		"automatic_roles": [role for role in AUTOMATIC_ROLES if role in frappe.get_roles(doc.name)],
		"role_options": choices,
		"profile_options": profiles,
	}


def names_value(data, field):
	values = data.get(field, [])
	if (
		not isinstance(values, list)
		or len(values) > 500
		or any(not isinstance(value, str) or not value or len(value) > 140 for value in values)
	):
		field_error(field, "请选择有效的角色或角色配置。")
	return list(dict.fromkeys(values))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def save_user_roles(data):
	permissions = access()
	if isinstance(data, str):
		data = frappe.parse_json(data)
	if not isinstance(data, dict) or set(data) - {
		"user",
		"modified",
		"mode",
		"roles",
		"role_profiles",
		"confirm_loss_of_desk_access",
	}:
		frappe.throw("提交内容包含不支持的字段。", frappe.ValidationError)
	doc = target_user(data.get("user"), permissions)
	if not editable(doc, permissions):
		frappe.throw("当前账号没有修改该用户角色的权限。", frappe.PermissionError)
	doc.check_permission("write")
	from frappe.utils import get_datetime

	if not isinstance(data.get("modified"), str) or get_datetime(data["modified"]) != get_datetime(
		doc.modified
	):
		frappe.throw("该用户已被其他管理员修改，请重新加载后再保存。", frappe.TimestampMismatchError)
	mode = data.get("mode")
	roles = names_value(data, "roles")
	profiles = names_value(data, "role_profiles")
	choices = {row.name: bool(row.desk_access) for row in assignable_roles()}
	if mode == "direct":
		if profiles or set(roles) - set(choices):
			field_error("roles", "部分角色已停用或不可分配，请重新选择。")
		resolved = roles
	elif mode == "profiles":
		if not permissions["profile_write"]:
			frappe.throw("当前账号没有修改角色配置的权限。", frappe.PermissionError)
		if roles or not profiles:
			field_error("role_profiles", "请选择角色配置，配置模式下不能手工提交角色。")
		available = {
			profile["name"]: profile for profile in profile_options(set(choices)) if profile["available"]
		}
		if set(profiles) - set(available):
			field_error("role_profiles", "部分角色配置不可用，请重新选择。")
		resolved = list(dict.fromkeys(role for name in profiles for role in available[name]["roles"]))
	else:
		field_error("mode", "请选择角色来源。")
	loses_desk = doc.user_type == "System User" and not any(choices.get(role) for role in resolved)
	if loses_desk and data.get("confirm_loss_of_desk_access") is not True:
		frappe.throw("移除全部桌面角色后，该用户将无法登录工作台。请确认后再保存。", frappe.ValidationError)
	if mode == "profiles":
		doc.role_profile_name = None
		doc.set("role_profiles", [{"role_profile": name} for name in profiles])
		doc.set("roles", [])
	else:
		if profiles_of(doc):
			if not permissions["profile_write"]:
				frappe.throw("当前账号没有解除角色配置的权限。", frappe.PermissionError)
			doc.role_profile_name = None
			doc.set("role_profiles", [])
		doc.set("roles", [{"role": role} for role in roles])
	doc.save()
	frappe.clear_cache(user=doc.name)
	frappe.local.response_headers["Cache-Control"] = "private, no-store"
	return {
		"name": doc.name,
		"modified": doc.modified,
		"can_login_console": bool(doc.enabled and doc.user_type == "System User"),
	}

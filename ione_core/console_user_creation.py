"""Create users through the native document lifecycle without elevating the caller."""
# ruff: noqa: RUF001

import frappe

from ione_core.navigation import NavigationPolicy, require_staff

INPUT_FIELDS = {
	"email",
	"first_name",
	"last_name",
	"username",
	"enabled",
	"roles",
	"credential_mode",
	"password",
	"password_confirm",
}


def field_error(field, message):
	frappe.local.response["field_errors"] = {field: message}
	frappe.throw(message, frappe.ValidationError)


def creation_access():
	require_staff()
	policy = NavigationPolicy()
	meta = frappe.get_meta("User")
	can_create = bool(frappe.has_permission("User", "create")) and (
		policy.administrator
		or any(p.role in policy.roles and p.permlevel == 0 and p.create for p in meta.permissions)
	)
	write_levels = {p.permlevel for p in meta.permissions if p.role in policy.roles and p.write}
	can_assign = can_create and (policy.administrator or meta.get_field("roles").permlevel in write_levels)
	return can_create, can_assign, meta, write_levels, policy.administrator


def assignable_roles():
	from frappe.core.doctype.user.user import get_all_roles

	names = get_all_roles()
	return (
		frappe.get_all(
			"Role", filters={"name": ["in", names]}, fields=["name", "desk_access"], order_by="name"
		)
		if names
		else []
	)


def invitation_available():
	return not frappe.conf.get("mute_emails") and bool(
		frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1})
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_creation_options():
	can_create, can_assign, _, _, _ = creation_access()
	frappe.local.response_headers["Cache-Control"] = "private, no-store"
	return {
		"can_create": can_create,
		"can_assign_roles": can_assign,
		"email_invitation_available": can_create and invitation_available(),
		"roles": [
			{"name": row.name, "label": frappe._(row.name), "desk_access": bool(row.desk_access)}
			for row in assignable_roles()
		]
		if can_assign
		else [],
	}


def text_value(data, field, required=False):
	value = data.get(field) or ""
	if not isinstance(value, str) or len(value) > 140:
		field_error(field, "请输入有效内容，长度不超过 140 个字符。")
	value = value.strip()
	if required and not value:
		field_error(field, "此项为必填项。")
	return value


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_user(data):
	can_create, can_assign, meta, write_levels, administrator = creation_access()
	if not can_create:
		frappe.throw("当前账号没有添加用户的权限。", frappe.PermissionError)
	if isinstance(data, str):
		data = frappe.parse_json(data)
	if not isinstance(data, dict) or set(data) - INPUT_FIELDS:
		frappe.throw("提交内容包含不支持的字段。", frappe.ValidationError)
	for field in (
		"email",
		"first_name",
		"last_name",
		"username",
		"enabled",
		"new_password",
		"send_welcome_email",
	):
		if not administrator and meta.get_field(field).permlevel not in {0, *write_levels}:
			frappe.throw("当前账号无权设置此用户字段。", frappe.PermissionError)
	email = text_value(data, "email", required=True).lower()
	from frappe.utils import validate_email_address

	if validate_email_address(email) != email:
		field_error("email", "请输入有效的邮箱地址。")
	first_name = text_value(data, "first_name", required=True)
	last_name = text_value(data, "last_name")
	username = text_value(data, "username").strip(" @")
	if data.get("username") and not username:
		field_error("username", "请输入有效的用户名。")
	if frappe.db.exists("User", email):
		field_error("email", "该邮箱已存在。")
	if username and frappe.db.exists("User", {"username": username}):
		field_error("username", "该用户名已存在。")
	enabled = data.get("enabled", True)
	if type(enabled) not in (bool, int) or enabled not in (0, 1):
		field_error("enabled", "请选择有效的启用状态。")
	roles = data.get("roles") or []
	if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
		field_error("roles", "请选择有效的角色。")
	if roles and not can_assign:
		frappe.throw("当前账号没有分配角色的权限。", frappe.PermissionError)
	if roles and set(roles) - {row.name for row in assignable_roles()}:
		field_error("roles", "部分角色已停用或不可分配，请重新选择。")
	mode = data.get("credential_mode", "password")
	password = data.get("password")
	if mode == "password":
		if not isinstance(password, str) or not password or len(password) > 512:
			field_error("password", "请输入有效的初始密码。")
		if password != data.get("password_confirm"):
			field_error("password_confirm", "两次输入的密码不一致。")
	elif mode == "invitation":
		if not enabled:
			field_error("enabled", "发送邀请邮件需要启用账号。")
		if not invitation_available():
			field_error("credential_mode", "当前无法发送邀请邮件，请使用初始密码。")
		if password or data.get("password_confirm"):
			field_error("credential_mode", "邀请邮件方式无需提交密码。")
	else:
		field_error("credential_mode", "请选择有效的登录方式。")
	doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"username": username or None,
			"enabled": int(enabled),
			"send_welcome_email": int(mode == "invitation"),
			"new_password": password if mode == "password" else None,
			"roles": [{"role": role} for role in dict.fromkeys(roles)],
		}
	)
	try:
		doc.insert()
	except frappe.DuplicateEntryError:
		field_error("email", "该邮箱已存在。")
	if username and doc.username != username:
		field_error("username", "该用户名已存在，请重新填写。")
	# Native welcome-mail failures may be caught by User. Fail the request instead
	# of returning a usable-looking account whose invitation was never queued.
	if mode == "invitation" and not doc.flags.email_sent:
		field_error("credential_mode", "邀请邮件未能加入发送队列，请稍后重试或使用初始密码。")
	frappe.local.response_headers["Cache-Control"] = "private, no-store"
	return {
		"name": doc.name,
		"enabled": bool(doc.enabled),
		"can_login_console": bool(doc.enabled and doc.user_type == "System User"),
		"credential_mode": mode,
	}

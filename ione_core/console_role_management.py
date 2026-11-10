"""Role management for the console using native document authorization/lifecycle."""
# ruff: noqa: RUF001

import hashlib
import json
import secrets
from urllib.parse import urlsplit

import frappe

from ione_core.console_roles import RoleReadQuery, get_readable_role, get_role, present, require_reader
from ione_core.console_roles import get_roles as read_roles
from ione_core.navigation import NavigationPolicy

FIELDS = ("role_name", "disabled", "desk_access", "home_page", "restrict_to_domain", "two_factor_auth")
MUTABLE = set(FIELDS) - {"role_name"}


def fail(message, kind=None):
	frappe.throw(message, kind or frappe.ValidationError)


def no_store(value):
	frappe.local.response_headers["Cache-Control"] = "private, no-store"
	return value


def access():
	require_reader()
	policy = NavigationPolicy()
	meta = frappe.get_meta("Role")

	def allowed(right):
		return policy.administrator or any(
			p.role in policy.roles and p.permlevel == 0 and p.get(right) for p in meta.permissions
		)

	write_levels = {p.permlevel for p in meta.permissions if p.role in policy.roles and p.write}
	return {
		"can_create": allowed("create") and bool(frappe.has_permission("Role", "create")),
		"can_edit": allowed("write"),
		"can_delete": allowed("delete"),
		"write_fields": [
			field
			for field in FIELDS
			if not meta.get_field(field).read_only
			and (policy.administrator or meta.get_field(field).permlevel in write_levels)
		],
		"create_fields": [
			field
			for field in FIELDS
			if not meta.get_field(field).read_only
			and (policy.administrator or meta.get_field(field).permlevel in {0, *write_levels})
		],
	}


def role_doc(role, lock=False):
	return get_readable_role(role, for_update=lock)


def actions(doc, permissions):
	reserved = present({"name": doc.name})["is_reserved"]
	self_protected = current_role(doc.name)
	can_edit = not reserved and permissions["can_edit"] and doc.has_permission("write")
	return {
		"can_edit": bool(can_edit),
		"can_delete": bool(
			not reserved and not self_protected and permissions["can_delete"] and doc.has_permission("delete")
		),
		"can_rename": bool(can_edit and not self_protected and "role_name" in permissions["write_fields"]),
		"self_protected": self_protected,
	}


def current_role(name):
	# Administrator derives every role automatically; it does not depend on each
	# ordinary role to retain its native superuser access.
	return frappe.session.user != "Administrator" and name in frappe.get_roles()


def domains():
	if not (frappe.has_permission("Domain", "read") or frappe.has_permission("Domain", "select")):
		return []
	return frappe.get_list("Domain", pluck="name", order_by="name", limit_page_length=0)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_options():
	permissions = access()
	return no_store({**permissions, "domains": domains()})


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_roles(
	current=1,
	page_size=20,
	keyword="",
	disabled=None,
	desk_access=None,
	sort_field="role_name",
	sort_order="ascend",
):
	permissions = access()
	result = read_roles(current, page_size, keyword, disabled, desk_access, sort_field, sort_order)
	for row in result["data"]:
		row.update(actions(role_doc(row["name"]), permissions))
	return result


def has_references(doc):
	# Explicit checks also cover permission/child rows that hooks might otherwise
	# exclude from generic link checks. Never force-delete or silently unlink.
	if any(
		frappe.db.exists(table, {"role": doc.name}) for table in ("Has Role", "DocPerm", "Custom DocPerm")
	):
		return True
	from frappe.model.delete_doc import LinkedDocumentsOverflow, get_dynamic_linked_docs, get_linked_docs

	try:
		return bool(get_linked_docs(doc, limit=1) or get_dynamic_linked_docs(doc, limit=1))
	except LinkedDocumentsOverflow:
		return True


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_context(role):
	permissions = access()
	doc = role_doc(role)
	flags = actions(doc, permissions)
	return no_store(
		{
			"role": get_role(role),
			**flags,
			"write_fields": permissions["write_fields"] if flags["can_edit"] else [],
			"domains": domains() if flags["can_edit"] else [],
			"delete_blocked": has_references(doc) if flags["can_delete"] else False,
		}
	)


def payload(data, fields):
	if isinstance(data, str):
		data = frappe.parse_json(data)
	if not isinstance(data, dict) or set(data) - set(fields):
		fail("提交内容包含不支持的字段。")
	return data


def name_value(value):
	if (
		not isinstance(value, str)
		or not value.strip()
		or len(value.strip()) > 140
		or any(ord(c) < 32 for c in value)
	):
		fail("角色名称不能为空，且不能超过 140 个字符或包含控制字符。")
	return value.strip()


def values_of(values, permissions, doc=None):
	if not isinstance(values, dict) or set(values) - (MUTABLE if doc else set(FIELDS)):
		fail("角色字段无效；已有角色请使用重命名操作修改名称。")
	allowed = permissions["write_fields" if doc else "create_fields"]
	if set(values) - set(allowed):
		fail("当前账号无权修改提交的角色字段。", frappe.PermissionError)
	result = dict(values)
	for field in ("disabled", "desk_access", "two_factor_auth"):
		if field in result:
			if type(result[field]) not in (bool, int) or result[field] not in (0, 1):
				fail("角色开关必须为有效的布尔值。")
			result[field] = int(result[field])
	for field in ("home_page", "restrict_to_domain"):
		if field in result:
			value = result[field]
			if value is not None and (not isinstance(value, str) or len(value) > 140):
				fail("首页或限制领域格式无效。")
			result[field] = value.strip() or None if value is not None else None
	home = result.get("home_page")
	if home:
		url = urlsplit(home)
		if (
			not home.startswith("/")
			or home.startswith("//")
			or url.scheme
			or url.netloc
			or "\\" in home
			or any(ord(c) < 32 for c in home)
		):
			fail("默认首页必须是安全的站内路径。")
	domain = result.get("restrict_to_domain")
	if domain and domain != (doc.restrict_to_domain if doc else None) and domain not in domains():
		fail("当前账号不能选择此限制领域。", frappe.PermissionError)
	if not doc:
		result["role_name"] = name_value(result.get("role_name"))
		if frappe.db.exists("Role", result["role_name"]):
			fail("该角色名称已存在。")
	return result


def checked_target(data, permissions, action="can_edit"):
	doc = role_doc(data.get("role"), lock=True)
	if not actions(doc, permissions)[action]:
		fail("当前账号不能对此角色执行该操作。", frappe.PermissionError)
	doc.check_permission("delete" if action == "can_delete" else "write")
	from frappe.utils import get_datetime

	try:
		matches = isinstance(data.get("modified"), str) and get_datetime(data["modified"]) == get_datetime(
			doc.modified
		)
	except ValueError, TypeError:
		matches = False
	if not matches:
		fail("该角色已被其他人修改，请重新加载后再操作。", frappe.TimestampMismatchError)
	return doc


def check_self(doc, values):
	if current_role(doc.name) and (
		(values.get("disabled") and not doc.disabled)
		or (doc.desk_access and "desk_access" in values and not values["desk_access"])
		or values.get("restrict_to_domain", doc.restrict_to_domain) != doc.restrict_to_domain
	):
		fail("当前账号正在使用此角色，不能停用、取消桌面访问或改变其限制领域。", frappe.PermissionError)


def reasons_for(doc, values):
	reasons = []
	if values.get("disabled", doc.disabled):
		reasons.append("停用会清除该角色在用户、角色配置及其他记录中的关联，重新启用不会自动恢复。")
	if values.get("desk_access", doc.desk_access) != doc.desk_access:
		reasons.append("修改桌面访问会重新评估关联用户的账号类型。")
	if values.get("restrict_to_domain", doc.restrict_to_domain) != doc.restrict_to_domain:
		reasons.append("修改限制领域可能改变角色的可用范围。")
	if values.get("two_factor_auth", doc.two_factor_auth) != doc.two_factor_auth:
		reasons.append("修改两步验证要求可能影响关联用户后续登录，最终按站点设置生效。")
	return reasons


def associations(doc):
	return frappe.get_all(
		"Has Role",
		filters={"role": doc.name},
		fields=["name", "parent", "parenttype", "modified"],
		order_by="name",
	)


def intent(doc, values, refs):
	parents = sorted({(row.parenttype, row.parent) for row in refs})
	state = {
		"user": frappe.session.user,
		"sid": frappe.session.sid,
		"role": doc.name,
		"modified": doc.modified,
		"values": values,
		"refs": refs,
		"parents": [(dt, name, frappe.db.get_value(dt, name, "modified")) for dt, name in parents],
		"permissions": {
			table: frappe.get_all(
				table, filters={"role": doc.name}, fields=["name", "modified"], order_by="name"
			)
			for table in ("DocPerm", "Custom DocPerm")
		},
	}
	return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()


def visible_count(doctype, names):
	if not names or not frappe.has_permission(doctype, "read"):
		return 0
	policy = NavigationPolicy()
	meta = frappe.get_meta(doctype)
	if not policy.administrator and not any(
		p.role in policy.roles and p.read and p.permlevel == meta.get_field("roles").permlevel
		for p in meta.permissions
	):
		return 0
	return len(
		RoleReadQuery()
		.get_query(
			table=doctype,
			fields=["name"],
			filters={"name": ["in", list(names)]},
			ignore_permissions=False,
			db_query_compat=True,
			limit=None,
		)
		.run()
	)


def preview_summary(refs):
	users = {row.parent for row in refs if row.parenttype == "User"}
	profiles = {row.parent for row in refs if row.parenttype == "Role Profile"}
	user_count = visible_count("User", users)
	profile_count = visible_count("Role Profile", profiles)
	return {
		"visible_users": user_count,
		"visible_profiles": profile_count,
		"restricted": user_count < len(users) or profile_count < len(profiles),
		"other_associations": any(row.parenttype not in ("User", "Role Profile") for row in refs),
	}


def token_key(token):
	return f"ione-console-role-confirmation:{frappe.session.user}:{token}"


@frappe.whitelist(allow_guest=True, methods=["POST"])
def preview_change(data):
	permissions = access()
	data = payload(data, ("role", "modified", "values"))
	doc = checked_target(data, permissions)
	values = values_of(data.get("values"), permissions, doc)
	check_self(doc, values)
	reasons = reasons_for(doc, values)
	if not reasons:
		return no_store({"reasons": [], "token": None})
	refs = associations(doc)
	token = secrets.token_urlsafe(24)
	frappe.cache.set_value(token_key(token), intent(doc, values, refs), expires_in_sec=300)
	return no_store({"reasons": reasons, "token": token, **preview_summary(refs)})


def clear_permissions():
	frappe.clear_cache()
	frappe.db.after_commit.add(frappe.clear_cache)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_role(data):
	permissions = access()
	if not permissions["can_create"]:
		fail("当前账号没有新增角色的权限。", frappe.PermissionError)
	data = payload(data, ("values",))
	values = values_of(data.get("values"), permissions)
	doc = frappe.get_doc({"doctype": "Role", **values}).insert()
	clear_permissions()
	return no_store({"name": doc.name, "modified": doc.modified})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def save_role(data):
	permissions = access()
	data = payload(data, ("role", "modified", "values", "confirmation_token"))
	doc = checked_target(data, permissions)
	values = values_of(data.get("values"), permissions, doc)
	check_self(doc, values)
	token = data.get("confirmation_token")
	if token is not None and (not isinstance(token, str) or len(token) > 100):
		fail("确认信息格式无效，请重新预览。")
	if reasons_for(doc, values):
		if (
			not isinstance(token, str)
			or not token
			or len(token) > 100
			or frappe.cache.get_value(token_key(token), use_local_cache=False)
			!= intent(doc, values, associations(doc))
		):
			fail("请重新预览并确认本次修改；角色或关联状态可能已变化。")
	doc.update(values)
	doc.save()
	clear_permissions()
	if token:
		frappe.cache.delete_value(token_key(token))
	return no_store({"name": doc.name, "modified": doc.modified})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def rename_role(data):
	permissions = access()
	data = payload(data, ("role", "modified", "new_name", "confirm_name"))
	doc = checked_target(data, permissions, "can_rename")
	new_name = name_value(data.get("new_name"))
	if data.get("confirm_name") != doc.name or new_name == doc.name:
		fail("请确认当前角色标识并填写不同的新名称。")
	from frappe.model.rename_doc import rename_doc

	new_name = rename_doc(
		"Role", doc.name, new_name, force=False, merge=False, ignore_permissions=False, show_alert=False
	)
	# Native rename changes identifiers/links without advancing the edit stamp.
	# Do not rerun Role.validate here: disabled roles would clear their links.
	from frappe.utils import now

	renamed = frappe.get_doc("Role", new_name)
	renamed.db_set("modified", now())
	clear_permissions()
	return no_store({"name": new_name, "modified": renamed.modified})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def delete_role(data):
	permissions = access()
	data = payload(data, ("role", "modified", "confirm_name"))
	doc = checked_target(data, permissions, "can_delete")
	if data.get("confirm_name") != doc.name:
		fail("请输入完整角色标识以确认删除。")
	if has_references(doc):
		fail("该角色仍被用户、角色配置、权限规则或其他记录引用，请先解除关联。")
	frappe.delete_doc("Role", doc.name, force=False, ignore_permissions=False, ignore_missing=False)
	clear_permissions()
	return no_store({"name": doc.name, "deleted": True})

"""Native business permission editing with scoped delegation and confirmed writes."""
# ruff: noqa: RUF001

import hashlib
import json
import secrets

import frappe
from frappe.app_state import is_disabled_app_filtering_active, is_module_disabled
from frappe.permissions import get_rights, setup_custom_perms

from ione_core.console_permission_policy import allowed_doctypes, can_edit, role_scope
from ione_core.console_role_management import no_store, payload, preview_summary

RULE_KEYS = {"permlevel", "if_owner", "rights"}
HIGHER_RIGHTS = {"read", "write", "mask"}


def digest(value):
	return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def fail(message, kind=None):
	frappe.throw(message, kind or frappe.ValidationError)


def all_rights(doctype):
	meta = frappe.get_meta("Custom DocPerm")
	return [right for right in dict.fromkeys([*get_rights(doctype), "mask"]) if meta.has_field(right)]


def rule_value(row, rights):
	return {
		"permlevel": int(row.get("permlevel") or 0),
		"if_owner": int(bool(row.get("if_owner"))),
		"rights": {right: int(bool(row.get(right))) for right in rights},
	}


def rule_key(rule):
	return rule["permlevel"], rule["if_owner"]


def rows_for(doctype, lock=False):
	rows = {
		table: frappe.qb.get_query(
			table, filters={"parent": doctype}, fields="*", order_by="name", for_update=True
		).run(as_dict=True)
		if lock
		else frappe.get_all(table, filters={"parent": doctype}, fields="*", order_by="name")
		for table in ("DocPerm", "Custom DocPerm")
	}
	# Legacy child-table reads prepend idx ordering; the locking query orders by
	# name. Fingerprints must compare rules independently of transport ordering.
	return {table: sorted(values, key=lambda row: row.name) for table, values in rows.items()}


def effective(rows):
	custom = rows["Custom DocPerm"]
	if is_disabled_app_filtering_active():
		custom = [row for row in custom if not row.get("is_app_disabled")]
	return custom or rows["DocPerm"]


def rules_for(rows, role, rights):
	return sorted([rule_value(row, rights) for row in effective(rows) if row.role == role], key=rule_key)


def supported_rights(meta, level=0, owner=0):
	rights = all_rights(meta.name)
	if level:
		return [right for right in rights if right in HIGHER_RIGHTS]
	if not meta.is_submittable:
		rights = [right for right in rights if right not in {"submit", "cancel", "amend"}]
	if not meta.allow_import:
		rights = [right for right in rights if right != "import"]
	if meta.issingle:
		rights = [
			right for right in rights if right not in {"create", "delete", "report", "import", "export"}
		]
	if owner:
		rights = [right for right in rights if right != "report"]
	return rights


def context_for(doctype, role, scope, editable, lock=False):
	if lock:
		frappe.db.get_value("DocType", doctype, "name", for_update=True)
	meta = frappe.get_meta(doctype, cached=False)
	rows = rows_for(doctype, lock)
	rights = all_rights(doctype)
	rules = rules_for(rows, role, rights)
	fields = [
		{
			"name": field.fieldname,
			"label": frappe._(field.label or field.fieldname),
			"permlevel": int(field.permlevel or 0),
			"read_only": bool(field.read_only),
		}
		for field in meta.fields
		if field.fieldtype not in {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading"}
	]
	levels = sorted({0, *(field["permlevel"] for field in fields), *(rule["permlevel"] for rule in rules)})
	return {
		"doctype": doctype,
		"label": frappe._(doctype),
		"module": meta.module,
		"can_edit": can_edit(scope, editable, meta.module),
		"source": "custom" if effective(rows) is not rows["DocPerm"] else "standard",
		"rules": rules,
		"rights": rights,
		"levels": [
			{
				"level": level,
				"rights": supported_rights(meta, level),
				"owner_rights": supported_rights(meta, level, 1),
			}
			for level in levels
		],
		"fields": fields,
		"version": digest({"rows": rows, "fields": fields, "modified": meta.modified, "rights": rights}),
	}


def target_scope(role, doctype):
	scope, doc, editable = role_scope(role)
	allowed = {row.name for row in allowed_doctypes(scope) if not is_module_disabled(row.module)}
	if not isinstance(doctype, str) or doctype not in allowed:
		fail("当前账号无权配置此业务对象。", frappe.PermissionError)
	return scope, doc, editable


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_catalog(role):
	scope, doc, editable = role_scope(role)
	objects = [row for row in allowed_doctypes(scope) if not is_module_disabled(row.module)]
	app_map = {row.name: row.app_name for row in frappe.get_all("Module Def", fields=["name", "app_name"])}
	names = [row.name for row in objects]
	custom = frappe.get_all("Custom DocPerm", filters={"parent": ["in", names]}, fields="*") if names else []
	standard = frappe.get_all("DocPerm", filters={"parent": ["in", names]}, fields="*") if names else []
	by_name = {name: {"DocPerm": [], "Custom DocPerm": []} for name in names}
	for table, rows in (("DocPerm", standard), ("Custom DocPerm", custom)):
		for row in rows:
			by_name[row.parent][table].append(row)
	return no_store(
		{
			"role": doc.name,
			"label": frappe._(doc.name),
			"editable_role": editable,
			"supervisor": scope["supervisor"],
			"objects": [
				{
					"doctype": row.name,
					"label": frappe._(row.name),
					"module": row.module,
					"module_label": frappe._(row.module),
					"app": app_map.get(row.module) or "custom",
					"can_edit": can_edit(scope, editable, row.module),
					"basic_rights": ["read", "write"]
					if row.issingle
					else ["read", "create", "write", "delete", "export"],
					"source": "custom"
					if effective(by_name[row.name]) is not by_name[row.name]["DocPerm"]
					else "standard",
					"rules": rules_for(by_name[row.name], role, all_rights(row.name)),
				}
				for row in objects
			],
		}
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_context(role, doctype):
	scope, doc, editable = target_scope(role, doctype)
	return no_store(context_for(doctype, doc.name, scope, editable))


def normalized_rules(values, context):
	if not isinstance(values, list) or len(values) > 60:
		fail("权限规则格式无效或数量过多。")
	known = set(context["rights"])
	levels = {row["level"]: row for row in context["levels"]}
	old = {rule_key(row): row for row in context["rules"]}
	normalized, keys = [], set()
	for value in values:
		if not isinstance(value, dict) or set(value) != RULE_KEYS:
			fail("权限规则包含不支持的字段。")
		level, owner, rights = value["permlevel"], value["if_owner"], value["rights"]
		if type(level) is not int or level not in levels or type(owner) is not int or owner not in (0, 1):
			fail("权限级别或创建者范围无效。")
		if level and owner:
			fail("仅本人创建只适用于权限级别 0。")
		if not isinstance(rights, dict) or set(rights) != known:
			fail("请提交完整且受支持的权限项。")
		if any(type(v) is not int or v not in (0, 1) for v in rights.values()):
			fail("权限项必须为 0 或 1。")
		key = (level, owner)
		if key in keys:
			fail("同一权限级别和创建者范围只能有一条规则。")
		keys.add(key)
		allowed = set(levels[level]["owner_rights" if owner else "rights"])
		for right, value_on in rights.items():
			if right not in allowed and value_on and not old.get(key, {}).get("rights", {}).get(right):
				fail("该业务对象或字段级别不支持所选操作。")
		if not any(rights.get(right) for right in ("select", "read", "write", "create", "submit", "cancel")):
			fail("权限规则至少需要一项基础权限；撤销全部权限请移除此规则。")
		if owner and rights.get("report"):
			fail("仅本人创建的规则不能授予报表权限。")
		normalized.append({"permlevel": level, "if_owner": owner, "rights": dict(rights)})
	if any(row["permlevel"] for row in normalized) and not any(row["permlevel"] == 0 for row in normalized):
		fail("配置字段级别权限前，必须保留级别 0 的权限。")
	return sorted(normalized, key=rule_key)


def validate_native(doctype, role, rules):
	from frappe.core.doctype.doctype.doctype import validate_permissions

	# Validate only the target role in an unsaved native schema document. Native
	# validation may normalize rows; other roles are never rewritten as a side effect.
	doc = frappe.get_doc("DocType", doctype)
	doc.set(
		"permissions",
		[
			{"role": role, **row["rights"], "permlevel": row["permlevel"], "if_owner": row["if_owner"]}
			for row in rules
		],
	)
	validate_permissions(doc)
	if [rule_value(row, all_rights(doctype)) for row in doc.permissions] != rules:
		fail("所选权限需要调整才能符合原生规则，请检查权限级别和操作依赖。")


def prepare(data, lock=False):
	data = payload(data, {"role", "changes", "token"})
	if set(data) - {"token"} != {"role", "changes"}:
		fail("请选择角色并提交变更。")
	scope, role, editable = role_scope(data["role"])
	if not editable:
		fail("系统保留角色和已停用角色的权限在此只读。", frappe.PermissionError)
	if lock:
		frappe.db.get_value("Role", role.name, "name", for_update=True)
		scope, role, editable = role_scope(data["role"])
		if not editable:
			fail("角色状态已改变，请重新加载。", frappe.TimestampMismatchError)
	changes = data["changes"]
	if not isinstance(changes, list) or not 1 <= len(changes) <= 100:
		fail("请一次提交 1 到 100 个业务对象的变更。")
	allowed = {row.name: row for row in allowed_doctypes(scope) if not is_module_disabled(row.module)}
	seen, result = set(), []
	for change in changes:
		if not isinstance(change, dict) or set(change) != {"doctype", "version", "rules"}:
			fail("业务权限变更格式无效。")
		name = change["doctype"]
		if (
			not isinstance(name, str)
			or name not in allowed
			or not can_edit(scope, editable, allowed[name].module)
		):
			fail("当前账号无权配置此业务对象。", frappe.PermissionError)
		if name in seen:
			fail("业务对象不能重复。")
		seen.add(name)
	for change in sorted(changes, key=lambda row: row["doctype"]):
		context = context_for(change["doctype"], role.name, scope, editable, lock)
		if change["version"] != context["version"]:
			fail("权限规则已被其他操作修改，请重新加载后再配置。", frappe.TimestampMismatchError)
		rules = normalized_rules(change["rules"], context)
		validate_native(change["doctype"], role.name, rules)
		if rules != context["rules"]:
			result.append(
				{
					"doctype": change["doctype"],
					"version": context["version"],
					"before": context["rules"],
					"after": rules,
				}
			)
	if not result:
		fail("没有需要保存的权限变更。")
	return data, role, result


def confirmation_key(token):
	if not isinstance(token, str) or len(token) != 64:
		fail("请先预览并确认本次权限变更。")
	return "ione-permission-preview:" + token


def intent(role, changes):
	return digest(
		{
			"user": frappe.session.user,
			"sid": frappe.session.sid,
			"role": role.name,
			"modified": role.modified,
			"changes": changes,
		}
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def preview_change(data):
	_, role, changes = prepare(data)
	token = secrets.token_hex(32)
	frappe.cache.set_value(confirmation_key(token), intent(role, changes), expires_in_sec=300)
	refs = frappe.get_all("Has Role", filters={"role": role.name}, fields=["parent", "parenttype"])
	return no_store({"token": token, "changes": changes, **preview_summary(refs)})


def persist(doctype, role, rules):
	# The native copier preserves the complete default matrix before the first
	# override. Scoped authority was already checked; callers never choose bypasses.
	setup_custom_perms(doctype)
	rows = frappe.get_all("Custom DocPerm", filters={"parent": doctype}, fields="*")
	if any(row.role == role and row.get("is_app_disabled") for row in rows):
		fail("该角色包含已停用应用的权限规则，请由系统权限管理员核实。")
	existing = {(int(row.permlevel or 0), int(bool(row.if_owner))): row for row in rows if row.role == role}
	if len(existing) != sum(row.role == role for row in rows):
		fail("存在重复权限规则，请先由系统权限管理员处理。")
	if not rules and not any(row.role != role for row in rows):
		fail("业务对象必须至少保留一条权限规则，无法删除最后一条规则。")
	retained = set()
	for rule in rules:
		key = rule_key(rule)
		retained.add(key)
		previous = existing.get(key)
		values = {
			"role": role,
			"permlevel": rule["permlevel"],
			"if_owner": rule["if_owner"],
			**rule["rights"],
		}
		if previous:
			if rule_value(previous, all_rights(doctype)) == rule:
				continue
			doc = frappe.get_doc("Custom DocPerm", previous.name)
		else:
			doc = frappe.new_doc("Custom DocPerm")
			doc.update({"parent": doctype, "parenttype": "DocType", "parentfield": "permissions"})
		doc.update(values)
		doc.save(ignore_permissions=True)
	for key, row in existing.items():
		if key not in retained:
			frappe.delete_doc("Custom DocPerm", row.name, ignore_permissions=True, force=True)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def save_permissions(data):
	data, role, changes = prepare(data, lock=True)
	key = confirmation_key(data.get("token"))
	if frappe.cache.get_value(key) != intent(role, changes):
		fail("确认已过期或权限发生变化，请重新预览。", frappe.TimestampMismatchError)
	for change in changes:
		persist(change["doctype"], role.name, change["after"])
	from frappe.core.doctype.doctype.doctype import clear_permissions_cache

	def clear():
		for change in changes:
			clear_permissions_cache(change["doctype"])

	clear()
	frappe.db.after_commit.add(clear)
	frappe.cache.delete_value(key)
	return no_store({"saved": len(changes), "role": role.name})

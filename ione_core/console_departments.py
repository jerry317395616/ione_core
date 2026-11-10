"""Native Department tree, scoped lists and guarded organization maintenance."""
# ruff: noqa: RUF001

import hashlib
import json
import secrets

import frappe

from ione_core.console_role_management import no_store, payload
from ione_core.console_roles import RoleReadQuery as ScopedReadQuery
from ione_core.console_roles import integer
from ione_core.navigation import NavigationPolicy, require_staff

FIELDS = ("department_name", "company", "parent_department", "is_group", "disabled")
EDITABLE = {"parent_department", "is_group", "disabled"}


def fail(message, kind=None):
	frappe.throw(message, kind or frappe.ValidationError)


def query(**kwargs):
	return (
		ScopedReadQuery()
		.get_query(table="Department", ignore_permissions=False, db_query_compat=True, **kwargs)
		.run(as_dict=True)
	)


def root_name():
	from frappe.utils.nestedset import get_root_of

	return get_root_of("Department")


def lock_tree():
	root = root_name()
	if not root:
		fail("部门根节点尚未初始化，请由系统管理员核实。")
	frappe.db.get_value("Department", root, "name", for_update=True)


def access(require_read=False):
	require_staff()
	policy, meta = NavigationPolicy(), frappe.get_meta("Department")

	def explicit(right):
		return policy.administrator or any(
			p.role in policy.roles and not p.permlevel and p.get(right) for p in meta.permissions
		)

	permissions = {
		"can_read": explicit("read") and bool(frappe.has_permission("Department", "read")),
		"can_create": explicit("create") and bool(frappe.has_permission("Department", "create")),
		"can_edit": explicit("write"),
		"can_delete": explicit("delete"),
	}
	if require_read and not permissions["can_read"]:
		fail("当前账号没有查看部门的权限。", frappe.PermissionError)
	read_levels, write_levels = (
		set(meta.get_permlevel_access("read")),
		set(meta.get_permlevel_access("write")),
	)
	masked = {field.fieldname for field in meta.get_masked_fields()}
	permissions["read_fields"] = [
		field
		for field in FIELDS
		if field not in masked and (policy.administrator or meta.get_field(field).permlevel in read_levels)
	]
	permissions["create_fields"] = (
		[
			field
			for field in FIELDS
			if not meta.get_field(field).read_only
			and (policy.administrator or meta.get_field(field).permlevel in {0, *write_levels})
		]
		if permissions["can_create"]
		else []
	)
	permissions["write_fields"] = (
		[
			field
			for field in FIELDS
			if field not in masked
			and not meta.get_field(field).read_only
			and not meta.get_field(field).set_only_once
			and (policy.administrator or meta.get_field(field).permlevel in write_levels)
		]
		if permissions["can_edit"]
		else []
	)
	return permissions, meta


def checked(name, lock=False):
	if not isinstance(name, str) or not name or len(name) > 140:
		fail("部门编号无效。")
	if not query(fields=["name"], filters={"name": name}, limit=1):
		fail("当前账号无权访问此部门。", frappe.PermissionError)
	doc = frappe.get_doc("Department", name, for_update=lock)
	doc.check_permission("read")
	return doc


def flags(doc, permissions):
	protected = not doc.parent_department or doc.name == root_name()
	can_edit = not protected and permissions["can_edit"] and bool(doc.has_permission("write"))
	return {
		"is_root": protected,
		"can_edit": can_edit,
		"can_delete": not protected and permissions["can_delete"] and bool(doc.has_permission("delete")),
		"can_rename": can_edit and "department_name" in permissions["write_fields"],
	}


def has_links(doc):
	from frappe.model.delete_doc import LinkedDocumentsOverflow, get_dynamic_linked_docs, get_linked_docs

	try:
		return bool(get_linked_docs(doc, limit=1) or get_dynamic_linked_docs(doc, limit=1))
	except LinkedDocumentsOverflow:
		return True


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_options():
	permissions, _ = access()
	return no_store(permissions)


def filter_company(company, permissions):
	if company in (None, ""):
		return {}
	if not isinstance(company, str) or len(company) > 140:
		fail("公司筛选无效。")
	if "company" not in permissions["read_fields"]:
		fail("当前账号无权按公司筛选。", frappe.PermissionError)
	return {"company": company}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_tree(company=""):
	permissions, _ = access(require_read=True)
	rows = query(
		fields=["name", *permissions["read_fields"]],
		filters=filter_company(company, permissions),
		order_by="name asc",
		limit=None,
	)
	return no_store({"nodes": rows})


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_departments(
	current=1,
	page_size=20,
	keyword="",
	company="",
	department="",
	disabled=None,
	is_group=None,
	sort_field="modified",
	sort_order="descend",
):
	permissions, _ = access(require_read=True)
	current, page_size = integer(current, 1, 1_000_000), integer(page_size, 1, 100)
	fields = ["name", "modified", *permissions["read_fields"]]
	if (
		sort_field not in fields
		or sort_order not in ("ascend", "descend")
		or not isinstance(keyword, str)
		or len(keyword) > 120
	):
		fail("部门列表查询条件无效。")
	filters = filter_company(company, permissions)
	for field, value in (("disabled", disabled), ("is_group", is_group)):
		if value not in (None, "", 0, 1, "0", "1"):
			fail("部门筛选条件无效。")
		if value not in (None, ""):
			if field not in permissions["read_fields"]:
				fail("无权按此字段筛选。", frappe.PermissionError)
			filters[field] = int(value)
	if department:
		doc = checked(department)
		filters.update(lft=[">=", doc.lft], rgt=["<=", doc.rgt])
	text = keyword.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
	or_filters = (
		{field: ["like", "%" + text + "%"] for field in ("name", "department_name") if field in fields}
		if text
		else {}
	)
	conditions = {"filters": filters, "or_filters": or_filters}
	direction = "asc" if sort_order == "ascend" else "desc"
	rows = query(
		fields=fields,
		order_by=f"{sort_field} {direction}, name asc",
		offset=(current - 1) * page_size,
		limit=page_size,
		**conditions,
	)
	for row in rows:
		row.update(flags(frappe.get_lazy_doc("Department", row.name), permissions))
	counts = query(fields=[{"COUNT": "name", "as": "total"}], order_by=None, limit=1, **conditions)
	return no_store({"data": rows, "total": int(counts[0].total) if counts else 0, "success": True})


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_department(department):
	permissions, _ = access(require_read=True)
	doc = checked(department)
	capabilities = flags(doc, permissions)
	blocked = capabilities["can_delete"] and (
		bool(frappe.db.exists("Department", {"parent_department": doc.name})) or has_links(doc)
	)
	doc.apply_fieldlevel_read_permissions()
	return no_store(
		{
			"department": {
				field: doc.get(field) for field in ("name", "modified", *permissions["read_fields"])
			},
			**capabilities,
			"delete_blocked": blocked,
			"read_fields": permissions["read_fields"],
			"write_fields": [field for field in permissions["write_fields"] if field in EDITABLE]
			if capabilities["can_edit"]
			else [],
		}
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def search_companies(keyword=""):
	permissions, _ = access()
	if not (permissions["can_read"] or permissions["can_create"]) or "company" not in {
		*permissions["read_fields"],
		*permissions["create_fields"],
	}:
		fail("当前账号无权查询部门公司选项。", frappe.PermissionError)
	if not isinstance(keyword, str) or len(keyword) > 120:
		fail("公司查询无效。")
	from frappe.desk.search import search_link

	return no_store(
		search_link(
			"Company",
			keyword.strip(),
			reference_doctype="Department",
			link_fieldname="company",
			page_length=20,
		)
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def search_parents(company, keyword="", department=None):
	permissions, _ = access(require_read=True)
	if not {"company", "parent_department", "is_group", "disabled"}.issubset(permissions["read_fields"]):
		return no_store([])
	if (
		not isinstance(company, str)
		or not company
		or len(company) > 140
		or not isinstance(keyword, str)
		or len(keyword) > 120
	):
		fail("上级部门查询无效。")
	root = root_name()
	conditions = [["company", "=", company], ["name", "=", root]]
	text = keyword.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
	filters = {"is_group": 1, "disabled": 0}
	if text:
		filters["name"] = ["like", "%" + text + "%"]
	rows = query(
		fields=["name", "department_name", "company"],
		filters=filters,
		or_filters=conditions,
		order_by="name asc",
		limit=None,
	)
	if department:
		doc = checked(department)
		# Only readable IDs are collected. Invisible descendants are not disclosed.
		excluded = {
			row.name
			for row in query(
				fields=["name"], filters={"lft": [">=", doc.lft], "rgt": ["<=", doc.rgt]}, limit=None
			)
		}
		rows = [row for row in rows if row.name not in excluded]
	return no_store([{"value": row.name, "label": row.department_name or row.name} for row in rows[:30]])


def text(value):
	if (
		not isinstance(value, str)
		or not value.strip()
		or len(value.strip()) > 140
		or any(ord(char) < 32 for char in value)
	):
		fail("名称不能为空，且不能超过 140 个字符或包含控制字符。")
	return value.strip()


def values_of(values, permissions, doc=None):
	allowed = set(permissions["write_fields"]) & EDITABLE if doc else set(permissions["create_fields"])
	if not isinstance(values, dict) or not values or set(values) - allowed:
		fail("提交包含不可修改的部门字段。", frappe.PermissionError)
	result = dict(values)
	for field in ("is_group", "disabled"):
		if field in result:
			if type(result[field]) not in (bool, int) or result[field] not in (0, 1):
				fail("部门类型和状态必须是有效开关。")
			result[field] = int(result[field])
	for field in ("department_name", "company"):
		if field in result:
			result[field] = text(result[field])
	if not doc and not all(result.get(field) for field in ("department_name", "company")):
		fail("请填写部门名称和所属公司。")
	if not doc:
		from frappe.desk.search import search_link

		choices = search_link(
			"Company",
			"",
			filters={"name": result["company"]},
			reference_doctype="Department",
			link_fieldname="company",
			page_length=1,
		)
		if not any(row["value"] == result["company"] for row in choices):
			fail("所选公司不在当前账号的可选范围内。", frappe.PermissionError)
	if "parent_department" in result:
		value = result["parent_department"]
		if value not in (None, ""):
			value = text(value)
		result["parent_department"] = value or None
		if not doc or value != doc.parent_department:
			parent = frappe.get_doc("Department", root_name()) if not value else checked(value)
			company = doc.company if doc else result["company"]
			if (
				not parent.is_group
				or parent.disabled
				or (parent.name != root_name() and parent.company != company)
			):
				fail("上级必须是同一公司的启用分组部门，或系统公共根节点。")
			if doc and doc.lft <= parent.lft <= doc.rgt:
				fail("上级不能选择自身或自己的下级部门。")
	if (
		doc
		and result.get("is_group") == 0
		and frappe.db.exists("Department", {"parent_department": doc.name})
	):
		fail("存在下级部门，不能改为普通部门。")
	if doc and result.get("is_group") == 1 and not doc.is_group and has_links(doc):
		fail("部门仍被其他记录引用，暂不能改为分组部门。")
	return result


def target(data, action="can_edit"):
	permissions, _ = access(require_read=True)
	lock_tree()
	doc = checked(data.get("department"), lock=True)
	if not flags(doc, permissions)[action]:
		fail("当前账号不能对此部门执行此操作。", frappe.PermissionError)
	if data.get("modified") != str(doc.modified):
		fail("部门资料已变化，请重新加载后再操作。", frappe.TimestampMismatchError)
	doc.check_permission("delete" if action == "can_delete" else "write")
	return permissions, doc


def preview_data(data):
	permissions, doc = target(data)
	values = values_of(data.get("values"), permissions, doc)
	reasons = []
	if (
		"parent_department" in values
		and (values["parent_department"] or root_name()) != doc.parent_department
	):
		if frappe.db.exists(
			"Department", {"lft": [">", doc.lft], "rgt": ["<", doc.rgt], "company": ["!=", doc.company]}
		):
			fail("下级层级存在跨公司部门，请先由组织管理员核实。")
		reasons.append("调整上级部门会移动该部门及其下级的组织位置，并可能改变按部门层级设置的数据范围。")
	if "is_group" in values and values["is_group"] != doc.is_group:
		reasons.append("修改部门的分组类型。")
	if "disabled" in values and values["disabled"] != doc.disabled:
		reasons.append("停用当前部门；下级部门的状态分别管理。" if values["disabled"] else "启用当前部门。")
	return doc, values, reasons


def intent(doc, values):
	# NSM changes do not advance every ancestor's modified stamp. Include the
	# full subtree's versions so additions/moves invalidate an old confirmation.
	rows = frappe.get_all(
		"Department",
		filters={"lft": [">=", doc.lft], "rgt": ["<=", doc.rgt]},
		fields=["name", "modified", "parent_department", "company", "disabled", "is_group"],
		order_by="name",
	)
	parent = values.get("parent_department") or root_name()
	parent_state = frappe.db.get_value(
		"Department", parent, ["name", "modified", "company", "disabled", "is_group"], as_dict=True
	)
	return hashlib.sha256(
		json.dumps(
			{
				"user": frappe.session.user,
				"sid": frappe.session.sid,
				"name": doc.name,
				"modified": doc.modified,
				"values": values,
				"subtree": rows,
				"parent": parent_state,
			},
			sort_keys=True,
			default=str,
		).encode()
	).hexdigest()


def token_key(token):
	if not isinstance(token, str) or len(token) != 64:
		fail("请重新预览并确认部门变更。")
	return "ione-department-confirmation:" + token


@frappe.whitelist(allow_guest=True, methods=["POST"])
def preview_change(data):
	data = payload(data, {"department", "modified", "values"})
	doc, values, reasons = preview_data(data)
	token = secrets.token_hex(32) if reasons else None
	if token:
		frappe.cache.set_value(token_key(token), intent(doc, values), expires_in_sec=300)
	return no_store({"reasons": reasons, "token": token})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_department(data):
	permissions, _ = access()
	if not permissions["can_create"]:
		fail("当前账号没有新增部门的权限。", frappe.PermissionError)
	data = payload(data, {"values"})
	lock_tree()
	values = values_of(data.get("values"), permissions)
	doc = frappe.new_doc("Department")
	doc.update(values)
	doc.insert()
	return no_store({"name": doc.name, "modified": str(doc.modified)})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def save_department(data):
	data = payload(data, {"department", "modified", "values", "token"})
	doc, values, reasons = preview_data(data)
	if reasons and frappe.cache.get_value(token_key(data.get("token")), use_local_cache=False) != intent(
		doc, values
	):
		fail("确认已失效或层级已变化，请重新预览。", frappe.TimestampMismatchError)
	doc.update(values)
	doc.save()
	if reasons:
		frappe.cache.delete_value(token_key(data["token"]))
	return no_store({"name": doc.name, "modified": str(doc.modified)})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def rename_department(data):
	data = payload(data, {"department", "modified", "new_name", "confirm_name"})
	_, doc = target(data, "can_rename")
	label = text(data.get("new_name"))
	if data.get("confirm_name") != doc.name or label == doc.department_name:
		fail("请输入原部门完整编号及不同的新名称。")
	from erpnext.setup.doctype.department.department import get_abbreviated_name
	from frappe.model.rename_doc import rename_doc

	new_name = rename_doc(
		"Department",
		doc.name,
		get_abbreviated_name(label, doc.company),
		force=False,
		merge=False,
		ignore_permissions=False,
		show_alert=False,
	)
	frappe.clear_cache(user=frappe.session.user)
	renamed = frappe.get_doc("Department", new_name)
	renamed.department_name = label
	renamed.save()
	return no_store({"name": renamed.name, "modified": str(renamed.modified)})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def delete_department(data):
	data = payload(data, {"department", "modified", "confirm_name"})
	_, doc = target(data, "can_delete")
	if data.get("confirm_name") != doc.name:
		fail("请输入完整部门编号以确认删除。")
	if frappe.db.exists("Department", {"parent_department": doc.name}) or has_links(doc):
		fail("部门存在下级或仍被其他记录引用，请先处理关联。")
	frappe.delete_doc("Department", doc.name, force=False, ignore_permissions=False, ignore_missing=False)
	return no_store({"name": doc.name, "deleted": True})


def tree_changed(doc=None, method=None, *args, **kwargs):
	if frappe.flags.get("ione_department_refresh_pending"):
		return
	frappe.flags.ione_department_refresh_pending = True
	frappe.db.after_commit.add(refresh_tree_cache)
	frappe.db.after_rollback.add(lambda: frappe.flags.pop("ione_department_refresh_pending", None))


def refresh_tree_cache():
	from frappe.utils.nestedset import clear_descendant_user_permissions

	from ione_core.permission_cache import publish_revision

	frappe.clear_document_cache("Department")
	clear_descendant_user_permissions("Department")
	frappe.flags.ione_department_refresh_pending = False
	publish_revision()

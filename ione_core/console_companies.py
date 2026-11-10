"""Company list and basic-data forms, using ERPNext's native lifecycle and scope."""
# ruff: noqa: RUF001

import frappe

from ione_core.console_role_management import no_store, payload
from ione_core.console_roles import RoleReadQuery as ScopedReadQuery
from ione_core.console_roles import integer
from ione_core.navigation import NavigationPolicy, require_staff

FIELDS = (
	"company_name",
	"abbr",
	"country",
	"default_currency",
	"is_group",
	"parent_company",
	"tax_id",
	"phone_no",
	"email",
	"website",
	"valuation_method",
)
IMMUTABLE = {"company_name", "abbr", "is_group"}
LIST_FIELDS = (
	"name",
	"company_name",
	"abbr",
	"country",
	"default_currency",
	"is_group",
	"parent_company",
	"modified",
)
LINK_FIELDS = {"country": "Country", "default_currency": "Currency", "parent_company": "Company"}


def fail(message, kind=None):
	frappe.throw(message, kind or frappe.ValidationError)


def access(require_read=False):
	require_staff()
	policy = NavigationPolicy()
	meta = frappe.get_meta("Company")

	def allowed(right):
		return bool(frappe.has_permission("Company", right)) and (
			policy.administrator
			or any(p.role in policy.roles and not p.permlevel and p.get(right) for p in meta.permissions)
		)

	permissions = {"can_read": allowed("read"), "can_create": allowed("create"), "can_edit": allowed("write")}
	# Native write without a document is false for owner-only grants. Preserve
	# that capability here and check ownership/controller rules on each record.
	permissions["can_edit"] = policy.administrator or any(
		p.role in policy.roles and not p.permlevel and p.write for p in meta.permissions
	)
	if require_read and not permissions["can_read"]:
		fail("当前账号没有查看公司的权限。", frappe.PermissionError)
	read_levels = set(meta.get_permlevel_access("read"))
	write_levels = set(meta.get_permlevel_access("write"))
	masked = {field.fieldname for field in meta.get_masked_fields()}
	permissions["read_fields"] = [
		field for field in FIELDS if policy.administrator or meta.get_field(field).permlevel in read_levels
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
			if field not in IMMUTABLE
			and field not in masked
			and not meta.get_field(field).read_only
			and not meta.get_field(field).set_only_once
			and (policy.administrator or meta.get_field(field).permlevel in write_levels)
		]
		if permissions["can_edit"]
		else []
	)
	return permissions, meta


def query(**kwargs):
	return (
		ScopedReadQuery()
		.get_query(table="Company", ignore_permissions=False, db_query_compat=True, **kwargs)
		.run(as_dict=True)
	)


def checked_company(name, lock=False):
	if not isinstance(name, str) or not name or len(name) > 140:
		fail("公司标识无效。")
	if not query(fields=["name"], filters={"name": name}, limit=1):
		fail("当前账号无权访问此公司。", frappe.PermissionError)
	doc = frappe.get_doc("Company", name, for_update=lock)
	doc.check_permission("read")
	return doc


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_options():
	permissions, meta = access()
	defaults = {}
	if permissions["can_create"]:
		doc = frappe.new_doc("Company")
		defaults = {
			field: doc.get(field) for field in permissions["create_fields"] if doc.get(field) is not None
		}
	return no_store(
		{
			**permissions,
			"defaults": defaults,
			"valuation_methods": (meta.get_field("valuation_method").options or "").splitlines(),
		}
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_companies(
	current=1, page_size=20, keyword="", is_group=None, sort_field="modified", sort_order="descend"
):
	permissions, _ = access(require_read=True)
	current, page_size = integer(current, 1, 1_000_000), integer(page_size, 1, 100)
	fields = [field for field in LIST_FIELDS if field in {"name", "modified", *permissions["read_fields"]}]
	if (
		sort_field not in fields
		or sort_order not in ("ascend", "descend")
		or not isinstance(keyword, str)
		or len(keyword) > 120
		or is_group not in (None, "", 0, 1, "0", "1")
	):
		fail("公司列表查询条件无效。")
	filters = {}
	if is_group not in (None, ""):
		if "is_group" not in fields:
			fail("无权按此字段筛选。", frappe.PermissionError)
		filters["is_group"] = int(is_group)
	text = keyword.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
	or_filters = (
		{field: ["like", "%" + text + "%"] for field in ("name", "company_name", "abbr") if field in fields}
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
		row.can_edit = permissions["can_edit"] and bool(
			frappe.get_lazy_doc("Company", row.name).has_permission("write")
		)
	counts = query(fields=[{"COUNT": "name", "as": "total"}], order_by=None, limit=1, **conditions)
	return no_store({"data": rows, "total": int(counts[0].total) if counts else 0, "success": True})


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_company(company):
	permissions, meta = access(require_read=True)
	doc = checked_company(company)
	can_edit = permissions["can_edit"] and bool(doc.has_permission("write"))
	doc.apply_fieldlevel_read_permissions()
	doc.mask_fields()
	return no_store(
		{
			"company": {field: doc.get(field) for field in ("name", "modified", *permissions["read_fields"])},
			"can_edit": can_edit,
			"write_fields": permissions["write_fields"] if can_edit else [],
			"read_fields": permissions["read_fields"],
			"valuation_methods": (meta.get_field("valuation_method").options or "").splitlines(),
		}
	)


def link_options(field, keyword, company=None, exact=False):
	if field == "parent_company":
		filters = {"is_group": 1}
		if exact:
			filters["name"] = keyword
		elif company:
			filters["name"] = ["!=", company]
		pattern = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
		rows = query(
			fields=["name"],
			filters=filters,
			or_filters={"name": ["like", "%" + pattern + "%"]} if keyword and not exact else {},
			order_by="name asc",
			limit=20,
		)
		return [{"value": row.name, "label": row.name} for row in rows]
	from frappe.desk.search import search_link

	filters = {"enabled": 1} if field == "default_currency" else {}
	if exact:
		filters["name"] = keyword
	rows = search_link(
		LINK_FIELDS[field],
		"" if exact else keyword,
		filters=filters,
		reference_doctype="Company",
		page_length=20,
	)
	# Translated masters search their translated labels. Raw saved IDs (e.g.
	# United States in a Chinese session) must still be selectable/validatable.
	if not exact and keyword and frappe.get_meta(LINK_FIELDS[field]).translated_doctype:
		pattern = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
		by_id = search_link(
			LINK_FIELDS[field],
			"",
			filters={**filters, "name": ["like", "%" + pattern + "%"]},
			reference_doctype="Company",
			page_length=20,
		)
		rows = list({row["value"]: row for row in [*rows, *by_id]}.values())[:20]
	return [{"value": row["value"], "label": row.get("label") or frappe._(row["value"])} for row in rows]


@frappe.whitelist(allow_guest=True, methods=["GET"])
def search_options(field, keyword="", company=None):
	permissions, _ = access()
	if field not in LINK_FIELDS or not isinstance(keyword, str) or len(keyword) > 120:
		fail("关联字段查询无效。")
	if not (permissions["can_create"] or permissions["can_read"]):
		fail("当前账号无权查询公司选项。", frappe.PermissionError)
	if field not in set(permissions["read_fields"]) | set(permissions["create_fields"]):
		fail("无权读取此字段。", frappe.PermissionError)
	if company:
		checked_company(company)
	return no_store(link_options(field, keyword.strip(), company))


def values_of(data, permissions, meta, doc=None):
	values = data.get("values")
	allowed = permissions["write_fields" if doc else "create_fields"]
	if not isinstance(values, dict) or not values or set(values) - set(allowed):
		fail("提交包含不可修改的公司字段。", frappe.PermissionError)
	result = {}
	for field, value in values.items():
		if field == "is_group":
			if type(value) not in (int, bool) or value not in (0, 1):
				fail("公司类型无效。")
			result[field] = int(value)
			continue
		if value is not None and not isinstance(value, str):
			fail("公司字段格式无效。")
		value = value.strip() if isinstance(value, str) else None
		if value and len(value) > (meta.get_field(field).length or 140):
			fail("公司字段内容过长。")
		if value and any(ord(char) < 32 for char in value):
			fail("公司字段包含无效字符。")
		if meta.get_field(field).reqd and not value:
			fail("请填写所有必填资料。")
		if field == "valuation_method" and value not in (meta.get_field(field).options or "").splitlines():
			fail("库存计价方式无效。")
		if field in LINK_FIELDS and value and (not doc or value != doc.get(field)):
			if not any(
				row["value"] == value
				for row in link_options(field, value, doc.name if doc else None, exact=True)
			):
				fail("所选关联值不存在或不在当前账号的可选范围内。", frappe.PermissionError)
		result[field] = value or None
	return result


@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_company(data):
	permissions, meta = access()
	if not permissions["can_create"]:
		fail("当前账号没有新增公司的权限。", frappe.PermissionError)
	data = payload(data, {"values"})
	values = values_of(data, permissions, meta)
	doc = frappe.new_doc("Company")
	doc.update(values)
	doc.insert()
	return no_store({"name": doc.name, "modified": str(doc.modified)})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def save_company(data):
	permissions, meta = access(require_read=True)
	if not permissions["can_edit"]:
		fail("当前账号没有修改公司的权限。", frappe.PermissionError)
	data = payload(data, {"company", "modified", "values"})
	doc = checked_company(data.get("company"), lock=True)
	doc.check_permission("write")
	if data.get("modified") != str(doc.modified):
		fail("公司资料已被其他操作修改，请重新加载后再编辑。", frappe.TimestampMismatchError)
	doc.update(values_of(data, permissions, meta, doc))
	doc.save()
	return no_store({"name": doc.name, "modified": str(doc.modified)})

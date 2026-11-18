"""Operate on native Employee, with a limited, independently granted directory."""
# ruff: noqa: RUF001

from contextvars import ContextVar
from datetime import date

import frappe

from ione_core.console_role_management import no_store, payload
from ione_core.console_roles import RoleReadQuery, integer
from ione_core.navigation import NavigationPolicy, require_staff

TYPE = "Employee"
ACCESS = "I-ONE Employee Directory"
EDIT = (
	"first_name",
	"middle_name",
	"last_name",
	"employee_number",
	"company",
	"department",
	"designation",
	"reports_to",
	"gender",
	"date_of_birth",
	"date_of_joining",
)
SUMMARY = (
	"employee_name",
	"employee_number",
	"company",
	"department",
	"designation",
	"status",
	"date_of_joining",
)
DETAIL = (*dict.fromkeys((*EDIT, *SUMMARY)), "relieving_date", "user_id")
STATES = ("Active", "Inactive", "Suspended", "Left")
LINKS = {"company": "Company", "department": "Department", "designation": "Designation", "gender": "Gender"}
WRITING = ContextVar("ione_employee_directory_write", default=None)


class DirectoryQuery(RoleReadQuery):
	def requires_owner_constraint(self, role_permissions):
		right = "read" if role_permissions.get("read") else "select"
		return bool(role_permissions.get(right) and right in (role_permissions.get("if_owner") or {}))


def fail(message, kind=frappe.ValidationError):
	frappe.throw(message, kind)


def text(value, maximum=140, required=False):
	if not isinstance(value, str) or len(value.strip()) > maximum or any(ord(c) < 32 for c in value):
		fail("输入内容无效或超长。")
	if required and not value.strip():
		fail("请填写必填项。")
	return value.strip()


def like(value):
	return "%" + text(value, 120).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def can(doctype, right="read", doc=None):
	policy = NavigationPolicy()
	return (
		policy.administrator
		or any(
			r.role in policy.roles and r.permlevel == 0 and r.get(right)
			for r in frappe.get_meta(doctype).permissions
		)
	) and bool(frappe.has_permission(doctype, right, doc=doc))


def require(doctype, right="read", doc=None):
	if not can(doctype, right, doc):
		fail("当前账号无权执行此员工操作。", frappe.PermissionError)


def access(right="read"):
	require_staff()
	require(ACCESS)
	if right != "read":
		require(ACCESS, right)
	if not (can(TYPE, "read") or can(TYPE, "select")):
		fail("缺少员工档案选择权限。", frappe.PermissionError)


def query(doctype, **kwargs):
	return DirectoryQuery().get_query(table=doctype, ignore_permissions=False, db_query_compat=True, **kwargs)


def fields(names, write=False):
	meta = frappe.get_meta(TYPE)
	masked = {field.fieldname for field in meta.get_masked_fields()}
	levels = set(meta.get_permlevel_access("write" if write else "read"))
	native_read = can(TYPE)
	return [
		name
		for name in names
		if (field := meta.get_field(name))
		and name not in masked
		and (
			frappe.session.user == "Administrator"
			or field.permlevel in levels
			or (not native_read and not field.permlevel)
		)
		and (not write or not field.read_only)
	]


def _allowed_source(doctype, name, *, lock=False, select=False):
	name = text(name, required=True)
	right = "select" if select and not can(doctype) else "read"
	require(doctype, right)
	if not query(doctype, fields=["name"], filters={"name": name}, limit=1).run():
		fail("关联资料不在当前账号的可用范围。", frappe.PermissionError)
	doc = frappe.get_doc(doctype, name, for_update=lock)
	require(doctype, right, doc)
	return doc


def scope():
	require("Company")
	emp = frappe.qb.DocType(TYPE)
	company = query("Company", fields=["name"], limit=None)
	dept = query("Department", fields=["name"], limit=None) if can("Department") else None
	department = emp.department.isin(dept) if dept is not None else emp.name.isnull()
	if not _department_limited():
		department |= emp.department.isnull() | (emp.department == "")
	return emp.company.isin(company) & department


def _department_limited():
	from frappe.core.doctype.user_permission.user_permission import get_user_permissions

	return frappe.session.user != "Administrator" and any(
		not row.applicable_for or row.applicable_for in (TYPE, "Department")
		for row in get_user_permissions().get("Department", [])
	)


def _checked(name, lock=False):
	name = text(name, required=True)
	emp = frappe.qb.DocType(TYPE)
	if not query(TYPE, fields=["name"], filters=scope() & (emp.name == name), limit=1).run():
		fail("当前账号无权访问该员工档案。", frappe.PermissionError)
	doc = frappe.get_doc(TYPE, name, for_update=lock)
	right = "read" if can(TYPE) else "select"
	require(TYPE, right, doc)
	_allowed_source("Company", doc.company)
	if doc.department:
		_allowed_source("Department", doc.department)
	return doc


def _caps(doc=None):
	return dict(
		can_create=can(ACCESS, "create"),
		can_edit=can(ACCESS, "write"),
		write_fields=fields(EDIT, write=True),
		read_fields=fields(DETAIL),
		can_status=bool(
			can(ACCESS, "write")
			and "status" in fields(["status"], write=True)
			and (
				not doc or not doc.user_id or (can(TYPE, "write", doc) and can("User", "write", doc.user_id))
			)
		),
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def listing(
	current=1,
	page_size=20,
	keyword="",
	employee_number="",
	company="",
	department="",
	designation="",
	status="",
):
	access()
	visible = fields(SUMMARY)
	emp = frappe.qb.DocType(TYPE)
	filters = scope()
	if keyword:
		matching = emp.name.like(like(keyword))
		if "employee_name" in visible:
			matching |= emp.employee_name.like(like(keyword))
		filters &= matching
	for field, value in (
		("employee_number", employee_number),
		("company", company),
		("department", department),
		("designation", designation),
		("status", status),
	):
		if not value:
			continue
		if field not in visible:
			fail("无权按此字段筛选员工。", frappe.PermissionError)
		filters &= emp[field].like(like(value)) if field == "employee_number" else emp[field] == text(value)
	size = integer(page_size, 1, 100)
	rows = query(
		TYPE,
		filters=filters,
		fields=["name", "modified", *visible],
		order_by="modified desc,name",
		limit=size,
		offset=(integer(current, 1, 1000000) - 1) * size,
	).run(as_dict=True)
	count = query(
		TYPE, filters=filters, fields=[{"COUNT": "name", "as": "total"}], order_by=None, limit=1
	).run(as_dict=True)
	return no_store(dict(data=rows, total=int(count[0].total) if count else 0, success=True, **_caps()))


def _account(doc):
	if not doc.user_id or "user_id" not in fields(["user_id"]) or not can("User"):
		return None
	meta = frappe.get_meta("User")
	if frappe.session.user != "Administrator" and (
		meta.get_field("enabled").permlevel not in meta.get_permlevel_access("read")
		or any(field.fieldname == "enabled" for field in meta.get_masked_fields())
	):
		return None
	rows = query("User", fields=["name", "enabled", "modified"], filters={"name": doc.user_id}, limit=1).run(
		as_dict=True
	)
	return rows[0] if rows and can("User", doc=doc.user_id) else None


def _impact(doc):
	return {
		key: value
		for hook in frappe.get_hooks("ione_employee_directory_impact")
		for key, value in frappe.get_attr(hook)(doc).items()
	}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def detail(name):
	access()
	doc = _checked(name)
	rights = _caps(doc)
	value = {key: doc.get(key) for key in ("name", "modified", *rights["read_fields"]) if key != "user_id"}
	return no_store(dict(doc=value, account=_account(doc), **_impact(doc), **rights))


@frappe.whitelist(allow_guest=True, methods=["GET"])
def options(field, keyword="", company="", current=""):
	access()
	if field not in (*LINKS, "reports_to") or field not in fields([field]):
		fail("人员关联字段不可用。", frappe.PermissionError)
	dt = LINKS.get(field, TYPE)
	if not (can(dt) or can(dt, "select")):
		return no_store([])
	if field == "reports_to" and not company:
		return no_store([])
	label = (
		"employee_name" if field == "reports_to" and "employee_name" in fields(["employee_name"]) else "name"
	)
	table = frappe.qb.DocType(dt)
	filters = table.name.like(like(keyword))
	if company and field in ("department", "reports_to"):
		_allowed_source("Company", company)
		filters &= table.company == company
	if field == "department":
		filters &= table.disabled == 0
	if field == "reports_to":
		if label == "employee_name":
			filters |= table.employee_name.like(like(keyword))
		filters &= scope() & (table.status == "Active")
		if current:
			filters &= table.name != text(current)
	rows = query(
		dt, fields=list(dict.fromkeys(("name", label))), filters=filters, order_by="name", limit=50
	).run(as_dict=True)
	return no_store([dict(value=row.name, label=row.get(label) or row.name) for row in rows])


def _version(doc, modified):
	if str(doc.modified) != modified:
		fail("档案已更新，请重新打开后操作。", frappe.TimestampMismatchError)


def _save(doc, mode):
	token = WRITING.set(mode)
	try:
		# The API has already checked the separate directory grant, source scope,
		# permitted fields and expected version. Retain the native validators.
		doc.save(ignore_permissions=True)
	finally:
		WRITING.reset(token)


class EmployeeDirectoryMixin:
	def update_user(self):
		if not WRITING.get():
			return super().update_user()

	def update_user_permissions(self):
		if not WRITING.get():
			return super().update_user_permissions()

	def update_user_status(self):
		if WRITING.get() != "profile":
			return super().update_user_status()


def _date(value):
	try:
		parsed = date.fromisoformat(value)
	except ValueError:
		fail("请填写有效日期。")
	if parsed.isoformat() != value:
		fail("请使用 YYYY-MM-DD 日期格式。")
	return value


@frappe.whitelist(allow_guest=True, methods=["POST"])
def save(data):
	data = payload(data, {"name", "modified", "values"})
	access("write" if data.get("name") else "create")
	if data.get("name"):
		doc = _checked(data["name"], lock=True)
		_version(doc, data.get("modified"))
	else:
		doc = frappe.new_doc(TYPE)
		doc.create_user_automatically = 0
		doc.create_user_permission = 0
		doc.status = "Active"
	prior = {field: doc.get(field) for field in EDIT}
	values = payload(data.get("values"), EDIT)
	if not set(values).issubset(fields(EDIT, write=True)):
		fail("缺少所提交字段的维护权限。", frappe.PermissionError)
	for field, value in values.items():
		value = text(value)
		doc.set(field, _date(value) if value and field.startswith("date_") else (value or None))
	if not doc.is_new() and doc.company != prior["company"]:
		fail("调换任职公司请走人事调动核验流程。")
	if not all(
		doc.get(key) for key in ("company", "first_name", "gender", "date_of_birth", "date_of_joining")
	):
		fail("请填写姓名、公司、性别、出生日期和入职日期。")
	_allowed_source("Company", doc.company, lock=True)
	for field, dt in LINKS.items():
		if field == "company" or doc.get(field) == prior[field] or not doc.get(field):
			continue
		source = _allowed_source(dt, doc.get(field), select=True)
		if field == "department" and (source.company != doc.company or source.disabled):
			fail("请选择本公司的启用组织部门。")
	if doc.department:
		_allowed_source("Department", doc.department)
	elif _department_limited():
		fail("请为员工选择当前账号可维护的组织部门。", frappe.PermissionError)
	from frappe.permissions import has_user_permission

	if frappe.session.user != "Administrator" and not has_user_permission(
		doc, frappe.session.user, ptype="create" if doc.is_new() else "write"
	):
		fail("员工资料超出允许的机构或部门范围。", frappe.PermissionError)
	if doc.has_value_changed("reports_to") and doc.reports_to:
		manager = _checked(doc.reports_to)
		if manager.company != doc.company or manager.status != "Active":
			fail("请选择本公司的在职直属上级。")
	if (
		doc.employee_number
		and doc.employee_number != prior["employee_number"]
		and frappe.db.get_value(
			TYPE,
			{"company": doc.company, "employee_number": doc.employee_number, "name": ["!=", doc.name or ""]},
			"name",
			for_update=True,
		)
	):
		fail("该公司已存在此工号，请核对原档案。")
	_save(doc, "profile")
	doc.add_comment("Edit", "通过新前端维护员工基础档案")
	return no_store(dict(name=doc.name, modified=str(doc.modified)))


@frappe.whitelist(allow_guest=True, methods=["GET"])
def preview_status(name):
	access("write")
	doc = _checked(name)
	account = _account(doc)
	return no_store(
		dict(
			name=doc.name,
			modified=str(doc.modified),
			status=doc.status,
			account=account,
			has_account=bool(doc.user_id),
			can_status=_caps(doc)["can_status"] and (not doc.user_id or bool(account)),
			has_active_reports=bool(frappe.db.exists(TYPE, {"reports_to": doc.name, "status": "Active"})),
			**_impact(doc),
		)
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def set_status(data):
	data = payload(data, {"name", "modified", "status", "relieving_date", "account_modified", "confirmed"})
	access("write")
	doc = _checked(data.get("name"), lock=True)
	_version(doc, data.get("modified"))
	if not _caps(doc)["can_status"]:
		fail("变更该员工状态需要关联账号的维护权限。", frappe.PermissionError)
	status = data.get("status")
	if data.get("confirmed") is not True or status not in STATES or status == doc.status:
		fail("请选择新的员工状态并确认。")
	if status == "Left":
		if "relieving_date" not in fields(["relieving_date"], write=True):
			fail("缺少离职日期维护权限。", frappe.PermissionError)
		if frappe.db.get_value(TYPE, {"reports_to": doc.name, "status": "Active"}, "name", for_update=True):
			fail("请先为仍在职的直属下属调整上级。")
		value = _date(text(data.get("relieving_date"), 10, required=True))
		from frappe.utils import nowdate

		if value > nowdate():
			fail("离职状态即时生效，离职日期不能晚于今天。")
		doc.relieving_date = value
	elif doc.status == "Left":
		if "relieving_date" not in fields(["relieving_date"], write=True):
			fail("缺少离职日期维护权限。", frappe.PermissionError)
		doc.relieving_date = None
	if doc.user_id:
		if not _account(doc):
			fail("缺少关联账号状态查看权限。", frappe.PermissionError)
		account = _allowed_source("User", doc.user_id, lock=True)
		_version(account, data.get("account_modified"))
		require("User", "write", account)
	prior = doc.status
	doc.status = status
	_save(doc, "status")
	doc.add_comment("Edit", f"新前端员工状态变更：{prior} → {status}")
	return no_store(dict(name=doc.name, modified=str(doc.modified)))

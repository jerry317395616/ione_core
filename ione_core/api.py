from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, getdate, nowdate


def _require_login():
	if frappe.session.user == "Guest":
		frappe.throw(_("请先登录"), frappe.AuthenticationError)


def _call_permission(method_path):
	if not method_path:
		return True
	try:
		return bool(frappe.get_attr(method_path)())
	except Exception:
		return False


def _app_category(app_name):
	return {
		"erpnext": "经营管理",
		"crm": "经营管理",
		"lending": "经营管理",
		"hrms": "组织发展",
		"lms": "组织发展",
		"helpdesk": "服务协作",
		"gameplan": "服务协作",
		"drive": "服务协作",
		"insights": "数据分析",
		"builder": "建设工具",
		"site_manager": "系统管理",
		"frappe": "系统管理",
		"ione_core": "I-ONE",
	}.get(app_name, "其他")


@frappe.whitelist()
def has_app_permission():
	return frappe.session.user != "Guest" and bool(
		{"System Manager", "I-ONE User", "I-ONE Manager", "I-ONE AI Operator"}.intersection(
			frappe.get_roles()
		)
	)


@frappe.whitelist()
def get_app_registry():
	_require_login()
	installed = set(frappe.get_installed_apps())
	result = []
	for item in frappe.get_hooks("add_to_apps_screen", default=[]):
		app_name = item.get("name")
		if not app_name or app_name not in installed or not _call_permission(item.get("has_permission")):
			continue
		result.append(
			{
				"name": app_name,
				"title": item.get("title") or app_name,
				"route": item.get("route") or "/app",
				"logo": item.get("logo"),
				"category": _app_category(app_name),
				"sequence": item.get("sequence_id", 999),
			}
		)
	return sorted(result, key=lambda app: (app["category"], app["sequence"], app["title"]))


def _safe_count(doctype, filters=None):
	if not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):
		return None
	try:
		rows = frappe.get_list(
			doctype,
			filters=filters or {},
			fields=[{"COUNT": "*", "as": "value"}],
			limit_page_length=1,
		)
		return int(rows[0].value or 0) if rows else 0
	except Exception:
		return None


def _metric(key, label, value, source, route):
	return {"key": key, "label": label, "value": value, "source": source, "route": route}


def _overview_metric(key, label, value, source, route, value_format="number", tone="primary", available=True):
	return {
		"key": key,
		"label": label,
		"value": value if available else None,
		"source": source,
		"route": route,
		"format": value_format,
		"tone": tone,
		"available": available,
	}


def _default_company():
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if not company and frappe.db.exists("DocType", "Company"):
		company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
	return company


def _can_view_finance():
	if not frappe.db.exists("DocType", "GL Entry") or not frappe.db.exists("DocType", "Account"):
		return False
	roles = set(frappe.get_roles())
	return frappe.has_permission("GL Entry", "read") or bool(
		{"System Manager", "Accounts User", "Accounts Manager", "I-ONE Manager"}.intersection(roles)
	)


def _sum_gl(root_type, company, from_date, to_date, use_permissions):
	accounts = frappe.get_all(
		"Account",
		filters={"root_type": root_type, "is_group": 0, "company": company},
		pluck="name",
	)
	if not accounts:
		return 0
	getter = frappe.get_list if use_permissions else frappe.get_all
	rows = getter(
		"GL Entry",
		filters={
			"company": company,
			"posting_date": ["between", [str(from_date), str(to_date)]],
			"is_cancelled": 0,
			"account": ["in", accounts],
		},
		fields=[{"SUM": "debit", "as": "debit"}, {"SUM": "credit", "as": "credit"}],
		limit_page_length=1,
	)
	row = rows[0] if rows else {}
	debit = flt(row.get("debit"))
	credit = flt(row.get("credit"))
	return credit - debit if root_type == "Income" else debit - credit


def _finance_summary(from_date, to_date, company):
	if not company or not _can_view_finance():
		return {"available": False, "income": None, "expense": None, "profit": None}
	use_permissions = frappe.has_permission("GL Entry", "read")
	try:
		income = _sum_gl("Income", company, from_date, to_date, use_permissions)
		expense = _sum_gl("Expense", company, from_date, to_date, use_permissions)
		return {
			"available": True,
			"income": income,
			"expense": expense,
			"profit": income - expense,
		}
	except Exception:
		frappe.log_error(title="I-ONE Dashboard Finance", message=frappe.get_traceback())
		return {"available": False, "income": None, "expense": None, "profit": None}


def _operating_target(company, month_start):
	if not company or not frappe.db.exists("DocType", "I-ONE Operating Target"):
		return None
	if not frappe.has_permission("I-ONE Operating Target", "read"):
		return None
	rows = frappe.get_list(
		"I-ONE Operating Target",
		filters={"company": company, "target_month": month_start, "enabled": 1},
		fields=["name", "currency", "revenue_target", "profit_target", "customer_target"],
		order_by="modified desc",
		limit_page_length=1,
	)
	return dict(rows[0]) if rows else None


@frappe.whitelist()
def get_unified_todos(limit=20):
	_require_login()
	limit = max(1, min(int(limit or 20), 50))
	items = []

	if frappe.db.exists("DocType", "ToDo") and frappe.has_permission("ToDo", "read"):
		for row in frappe.get_list(
			"ToDo",
			filters={"status": "Open", "allocated_to": frappe.session.user},
			fields=["name", "description", "priority", "date", "reference_type", "reference_name"],
			order_by="priority desc, date asc, modified desc",
			limit_page_length=limit,
		):
			items.append(
				{
					"id": f"todo:{row.name}",
					"title": row.description or row.reference_name or _("待办事项"),
					"source": "Frappe ToDo",
					"status": "待处理",
					"priority": row.priority or "Medium",
					"due_date": row.date,
					"route": f"/app/todo/{quote(row.name)}",
				}
			)

	if frappe.db.exists("DocType", "I-ONE AI Task") and frappe.has_permission("I-ONE AI Task", "read"):
		for row in frappe.get_list(
			"I-ONE AI Task",
			filters={"status": ["in", ["待审批", "已排队", "执行中"]]},
			fields=["name", "title", "priority", "status", "modified"],
			order_by="modified desc",
			limit_page_length=limit,
		):
			items.append(
				{
					"id": f"ione:{row.name}",
					"title": row.title,
					"source": "I-ONE AI",
					"status": row.status,
					"priority": row.priority,
					"due_date": None,
					"route": f"/app/i-one-ai-task/{quote(row.name)}",
				}
			)

	return items[:limit]


@frappe.whitelist()
def get_dashboard():
	_require_login()
	metrics = []

	leads_doctype = "CRM Lead" if frappe.db.exists("DocType", "CRM Lead") else "Lead"
	leads = _safe_count(leads_doctype)
	if leads is not None:
		metrics.append(_metric("leads", "销售线索", leads, "CRM", f"/app/{frappe.scrub(leads_doctype).replace('_', '-')}"))

	employees = _safe_count("Employee", {"status": "Active"})
	if employees is not None:
		metrics.append(_metric("employees", "在职员工", employees, "Frappe HR", "/app/employee"))

	tickets = _safe_count("HD Ticket", {"status": ["not in", ["Resolved", "Closed"]]})
	if tickets is not None:
		metrics.append(_metric("tickets", "未关闭工单", tickets, "Helpdesk", "/helpdesk"))

	today = getdate(nowdate())
	month_start = get_first_day(today)
	company = _default_company()
	currency = frappe.db.get_value("Company", company, "default_currency") if company else None
	currency = currency or frappe.db.get_single_value("Global Defaults", "default_currency") or "CNY"

	today_todos = _safe_count(
		"ToDo",
		{"status": "Open", "allocated_to": frappe.session.user, "date": ["<=", today]},
	)
	customers = _safe_count("Customer")
	pending_ai = _safe_count("I-ONE AI Task", {"status": ["in", ["待审批", "已排队", "执行中"]]})
	today_finance = _finance_summary(today, today, company)
	month_finance = _finance_summary(month_start, today, company)

	ledger_route = f"/app/query-report/General%20Ledger?from_date={today}&to_date={today}"
	profit_route = f"/app/query-report/Profit%20and%20Loss%20Statement?from_date={today}&to_date={today}"
	overview = [
		_overview_metric("today_todos", "今日待办", today_todos or 0, "Frappe ToDo", "/app/todo"),
		_overview_metric(
			"today_income", "今日收入", today_finance["income"], "ERPNext 总账", ledger_route,
			value_format="currency", tone="positive", available=today_finance["available"],
		),
		_overview_metric(
			"today_expense", "今日支出", today_finance["expense"], "ERPNext 总账", ledger_route,
			value_format="currency", tone="negative", available=today_finance["available"],
		),
		_overview_metric(
			"today_profit", "今日利润", today_finance["profit"], "ERPNext 总账", profit_route,
			value_format="currency", tone="positive", available=today_finance["available"],
		),
		_overview_metric(
			"customers", "客户数量", customers or 0, "ERPNext", "/app/customer",
			available=customers is not None,
		),
		_overview_metric(
			"ai_tasks", "AI 处理中", pending_ai or 0, "I-ONE AI", "/app/i-one-ai-task",
			available=pending_ai is not None,
		),
	]

	target = _operating_target(company, month_start)
	target_profit = flt(target.get("profit_target")) if target else None
	profit_progress = {
		"actual": month_finance["profit"] if month_finance["available"] else None,
		"target": target_profit,
		"percent": (
			(month_finance["profit"] / target_profit * 100)
			if month_finance["available"] and target_profit and target_profit > 0
			else None
		),
		"currency": currency,
		"route": f"/app/i-one-operating-target/{quote(target['name'])}" if target else "/app/i-one-operating-target",
	}

	return {
		"metrics": metrics,
		"overview": overview,
		"currency": currency,
		"company": company,
		"as_of_date": str(today),
		"profit_progress": profit_progress,
		"todos": get_unified_todos(8),
		"apps": get_app_registry(),
	}


@frappe.whitelist()
def get_bootstrap():
	_require_login()
	user = frappe.session.user
	user_info = frappe.db.get_value(
		"User",
		user,
		["full_name", "user_image", "language", "time_zone"],
		as_dict=True,
	) or {}
	return {
		"user": {
			"username": user,
			"full_name": user_info.get("full_name") or user,
			"user_image": user_info.get("user_image"),
			"language": user_info.get("language"),
			"time_zone": user_info.get("time_zone"),
			"roles": frappe.get_roles(user),
		},
		"site": frappe.local.site,
		"apps": get_app_registry(),
		"features": {
			"ai_tasks": bool(frappe.db.exists("DocType", "I-ONE AI Task")),
			"approvals": bool(frappe.db.exists("DocType", "I-ONE Approval Request")),
			"background_jobs": True,
		},
	}

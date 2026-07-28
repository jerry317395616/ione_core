from __future__ import annotations

# ruff: noqa: RUF001
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import frappe
from frappe.utils import add_days, add_months, get_first_day, get_last_day, now_datetime, today

SEED_PREFIX = "I-ONE 业务样例"

CORE_COVERAGE = {
	"通用协作": ("ToDo", "Event", "Note"),
	"销售管理": ("Lead", "Opportunity", "Quotation", "Sales Order", "Sales Invoice", "Payment Entry"),
	"采购管理": ("Material Request", "Purchase Order", "Purchase Receipt", "Purchase Invoice"),
	"库存管理": ("Stock Entry",),
	"生产制造": ("BOM", "Work Order"),
	"项目管理": ("Project", "Task", "Timesheet"),
	"资产管理": ("Asset",),
	"质量与支持": ("Quality Inspection", "Issue", "Contract"),
	"人力资源": (
		"Employee",
		"Shift Assignment",
		"Attendance",
		"Leave Allocation",
		"Leave Application",
		"Expense Claim",
		"Job Opening",
		"Job Applicant",
		"Job Offer",
		"Salary Structure",
		"Salary Structure Assignment",
		"Salary Slip",
	),
	"CRM": ("CRM Organization", "CRM Lead", "CRM Deal", "CRM Task", "FCRM Note"),
	"服务台": ("HD Customer", "HD Ticket", "HD Article"),
	"学习": ("LMS Course", "Course Chapter", "Course Lesson", "LMS Quiz", "LMS Enrollment"),
	"借贷": ("Loan Product", "Loan Application"),
	"Gameplan": ("GP Team", "GP Project", "GP Task", "GP Discussion", "GP Page"),
	"内容协作": ("Writer Document", "Wiki Space", "Wiki Document"),
	"数据分析": ("Insights Data Source", "Insights Workbook", "Insights Dashboard"),
	"网站建设": ("Builder Page",),
	"智能执行": ("Flow Agent", "Flow Session", "I-ONE Agent", "I-ONE AI Task"),
	"I-ONE 经营": ("I-ONE Growth Plan", "I-ONE Experience", "I-ONE Achievement"),
}


@dataclass
class SeedReport:
	created: list[str] = field(default_factory=list)
	existing: list[str] = field(default_factory=list)
	skipped: list[str] = field(default_factory=list)
	errors: dict[str, str] = field(default_factory=dict)

	def as_dict(self) -> dict[str, Any]:
		return {
			"created": self.created,
			"existing": self.existing,
			"skipped": self.skipped,
			"errors": self.errors,
			"coverage": get_business_data_coverage(),
		}


@dataclass
class SeedContext:
	report: SeedReport
	company: str
	abbr: str
	currency: str
	customer: str
	supplier: str
	service_item: str
	stock_item: str
	warehouse: str
	user: str


def _doctype_exists(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype))


def _first(doctype: str, filters: dict[str, Any] | None = None, field: str = "name") -> Any:
	return frappe.db.get_value(doctype, filters or {}, field, order_by="creation asc")


def _record_label(doctype: str, name: str) -> str:
	return f"{doctype}: {name}"


def _ensure_doc(
	ctx: SeedContext,
	doctype: str,
	filters: dict[str, Any],
	values: dict[str, Any],
	*,
	submit: bool = False,
	name: str | None = None,
) -> Any:
	if not _doctype_exists(doctype):
		ctx.report.skipped.append(f"{doctype}: DocType 未安装")
		return None

	existing = frappe.db.exists(doctype, filters)
	if existing:
		ctx.report.existing.append(_record_label(doctype, existing))
		return frappe.get_doc(doctype, existing)

	doc = frappe.get_doc({"doctype": doctype, **values})
	if name:
		doc.name = name
	doc.insert(ignore_permissions=True)
	if submit and doc.docstatus == 0:
		doc.submit()
	ctx.report.created.append(_record_label(doctype, doc.name))
	return doc


def _find_account(company: str, *, account_type: str | None = None, root_type: str | None = None) -> str | None:
	filters: dict[str, Any] = {"company": company, "is_group": 0, "disabled": 0}
	if account_type:
		filters["account_type"] = account_type
	if root_type:
		filters["root_type"] = root_type
	return _first("Account", filters)


def _make_context(report: SeedReport) -> SeedContext:
	company = frappe.defaults.get_user_default("Company") or _first("Company")
	if not company:
		frappe.throw("请先创建公司后再生成业务数据。")
	company_doc = frappe.get_cached_doc("Company", company)

	return SeedContext(
		report=report,
		company=company,
		abbr=company_doc.abbr,
		currency=company_doc.default_currency,
		customer=_first("Customer"),
		supplier=_first("Supplier"),
		service_item=_first("Item", {"disabled": 0, "is_sales_item": 1, "is_stock_item": 0}),
		stock_item=_first("Item", {"disabled": 0, "is_stock_item": 1}),
		warehouse=_first("Warehouse", {"company": company, "is_group": 0, "disabled": 0}),
		user=frappe.session.user if frappe.session.user != "Guest" else "Administrator",
	)


def _run_domain(ctx: SeedContext, domain: str, callback: Callable[[SeedContext], None]) -> None:
	savepoint = f"ione_seed_{len(ctx.report.errors)}_{len(ctx.report.created)}"
	created_count = len(ctx.report.created)
	existing_count = len(ctx.report.existing)
	skipped_count = len(ctx.report.skipped)
	frappe.db.savepoint(savepoint)
	try:
		callback(ctx)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		del ctx.report.created[created_count:]
		del ctx.report.existing[existing_count:]
		del ctx.report.skipped[skipped_count:]
		ctx.report.errors[domain] = frappe.get_traceback()


def _seed_framework(ctx: SeedContext) -> None:
	for index, (description, priority) in enumerate(
		(
			("确认本周销售报价与客户回访计划", "High"),
			("审核采购到货和库存补货需求", "Medium"),
			("完成月度经营数据复盘", "Low"),
		),
		1,
	):
		_ensure_doc(
			ctx,
			"ToDo",
			{"description": f"{SEED_PREFIX}：{description}"},
			{
				"description": f"{SEED_PREFIX}：{description}",
				"priority": priority,
				"status": "Closed" if index == 3 else "Open",
				"allocated_to": ctx.user,
				"date": add_days(today(), index),
			},
		)

	_ensure_doc(
		ctx,
		"Event",
		{"subject": f"{SEED_PREFIX}：月度经营例会"},
		{
			"subject": f"{SEED_PREFIX}：月度经营例会",
			"event_type": "Public",
			"event_category": "Meeting",
			"starts_on": add_days(now_datetime(), 2),
			"ends_on": add_days(now_datetime(), 2),
			"description": "复盘销售、采购、库存、人事和客户服务数据。",
		},
	)
	_ensure_doc(
		ctx,
		"Note",
		{"title": f"{SEED_PREFIX}：经营数据说明"},
		{
			"title": f"{SEED_PREFIX}：经营数据说明",
			"content": "<p>本记录用于说明 I-ONE 跨应用业务样例数据及其关联关系。</p>",
			"public": 1,
		},
	)


def _sales_item(item_code: str, qty: float, rate: float, delivery_date: str | None = None) -> dict[str, Any]:
	row = {"item_code": item_code, "qty": qty, "rate": rate}
	if delivery_date:
		row["delivery_date"] = delivery_date
	return row


def _seed_sales(ctx: SeedContext) -> None:
	lead = _ensure_doc(
		ctx,
		"Lead",
		{"company_name": f"{SEED_PREFIX}客户"},
		{
			"company_name": f"{SEED_PREFIX}客户",
			"first_name": "张",
			"last_name": "经理",
			"email_id": "demo.customer@myyr.top",
			"mobile_no": "13800000001",
			"status": "Lead",
			"request_type": "Product Enquiry",
		},
	)
	_ensure_doc(
		ctx,
		"Opportunity",
		{"opportunity_from": "Customer", "party_name": ctx.customer, "company": ctx.company},
		{
			"naming_series": "CRM-OPP-.YYYY.-",
			"opportunity_from": "Customer",
			"party_name": ctx.customer,
			"company": ctx.company,
			"transaction_date": today(),
			"expected_closing": add_days(today(), 20),
			"opportunity_amount": 68000,
			"source": "Website",
			"items": [_sales_item(ctx.service_item, 10, 6800)],
		},
	)
	_ensure_doc(
		ctx,
		"Quotation",
		{
			"party_name": ctx.customer,
			"order_type": "Sales",
			"company": ctx.company,
			"transaction_date": today(),
		},
		{
			"naming_series": "SAL-QTN-.YYYY.-",
			"quotation_to": "Customer",
			"party_name": ctx.customer,
			"company": ctx.company,
			"transaction_date": today(),
			"valid_till": add_days(today(), 30),
			"order_type": "Sales",
			"currency": ctx.currency,
			"conversion_rate": 1,
			"selling_price_list": "Standard Selling",
			"price_list_currency": ctx.currency,
			"plc_conversion_rate": 1,
			"remarks": SEED_PREFIX,
			"items": [_sales_item(ctx.service_item, 10, 6800)],
		},
		submit=True,
	)
	order = _ensure_doc(
		ctx,
		"Sales Order",
		{"customer": ctx.customer, "po_no": f"IONE-DEMO-SO-{today()}"},
		{
			"naming_series": "SAL-ORD-.YYYY.-",
			"company": ctx.company,
			"customer": ctx.customer,
			"po_no": f"IONE-DEMO-SO-{today()}",
			"transaction_date": today(),
			"delivery_date": add_days(today(), 14),
			"order_type": "Sales",
			"currency": ctx.currency,
			"conversion_rate": 1,
			"selling_price_list": "Standard Selling",
			"price_list_currency": ctx.currency,
			"plc_conversion_rate": 1,
			"items": [_sales_item(ctx.service_item, 5, 6800, add_days(today(), 14))],
		},
		submit=True,
	)
	if order:
		invoice = _ensure_doc(
			ctx,
			"Sales Invoice",
			{"customer": ctx.customer, "remarks": SEED_PREFIX},
			{
				"naming_series": "ACC-SINV-.YYYY.-",
				"company": ctx.company,
				"customer": ctx.customer,
				"posting_date": today(),
				"due_date": add_days(today(), 15),
				"currency": ctx.currency,
				"conversion_rate": 1,
				"selling_price_list": "Standard Selling",
				"price_list_currency": ctx.currency,
				"plc_conversion_rate": 1,
				"remarks": SEED_PREFIX,
				"items": [
					{
						"item_code": ctx.service_item,
						"qty": 2,
						"rate": 6800,
						"sales_order": order.name,
						"so_detail": order.items[0].name,
					}
				],
			},
			submit=True,
		)
		if invoice and invoice.docstatus == 1 and invoice.outstanding_amount:
			from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

			existing_payment = frappe.db.exists(
				"Payment Entry Reference",
				{"reference_doctype": "Sales Invoice", "reference_name": invoice.name},
			)
			if not existing_payment:
				payment = get_payment_entry("Sales Invoice", invoice.name)
				payment.reference_no = f"IONE-DEMO-{invoice.name}"
				payment.reference_date = today()
				payment.insert(ignore_permissions=True)
				payment.submit()
				ctx.report.created.append(_record_label("Payment Entry", payment.name))

	if lead and not lead.company:
		lead.db_set("company", ctx.company, update_modified=False)


def _seed_buying_and_stock(ctx: SeedContext) -> None:
	request = _ensure_doc(
		ctx,
		"Material Request",
		{"title": SEED_PREFIX, "material_request_type": "Purchase"},
		{
			"naming_series": "MAT-MR-.YYYY.-",
			"title": SEED_PREFIX,
			"material_request_type": "Purchase",
			"company": ctx.company,
			"transaction_date": today(),
			"schedule_date": add_days(today(), 7),
			"items": [
				{
					"item_code": ctx.stock_item,
					"qty": 30,
					"schedule_date": add_days(today(), 7),
					"warehouse": ctx.warehouse,
				}
			],
		},
		submit=True,
	)
	order = _ensure_doc(
		ctx,
		"Purchase Order",
		{
			"supplier": ctx.supplier,
			"company": ctx.company,
			"transaction_date": today(),
			"schedule_date": add_days(today(), 7),
		},
		{
			"naming_series": "PUR-ORD-.YYYY.-",
			"company": ctx.company,
			"supplier": ctx.supplier,
			"transaction_date": today(),
			"schedule_date": add_days(today(), 7),
			"currency": ctx.currency,
			"conversion_rate": 1,
			"buying_price_list": "Standard Buying",
			"price_list_currency": ctx.currency,
			"plc_conversion_rate": 1,
			"remarks": SEED_PREFIX,
			"items": [
				{
					"item_code": ctx.stock_item,
					"qty": 20,
					"rate": 50,
					"schedule_date": add_days(today(), 7),
					"warehouse": ctx.warehouse,
					"material_request": request.name if request else None,
					"material_request_item": request.items[0].name if request else None,
				}
			],
		},
		submit=True,
	)
	if order:
		from erpnext.buying.doctype.purchase_order.mapper import (
			make_purchase_invoice,
			make_purchase_receipt,
		)

		receipt = frappe.db.exists("Purchase Receipt Item", {"purchase_order": order.name})
		if not receipt:
			receipt_doc = make_purchase_receipt(order.name)
			receipt_doc.posting_date = today()
			receipt_doc.set_warehouse = ctx.warehouse
			receipt_doc.insert(ignore_permissions=True)
			receipt_doc.submit()
			ctx.report.created.append(_record_label("Purchase Receipt", receipt_doc.name))

		invoice_name = frappe.db.get_value(
			"Purchase Invoice Item", {"purchase_order": order.name}, "parent"
		)
		if not invoice_name:
			invoice = make_purchase_invoice(order.name)
			invoice.posting_date = today()
			invoice.bill_date = today()
			invoice.bill_no = f"IONE-DEMO-PI-{today()}"
			invoice.remarks = SEED_PREFIX
			invoice.insert(ignore_permissions=True)
			invoice.submit()
			ctx.report.created.append(_record_label("Purchase Invoice", invoice.name))

	_ensure_doc(
		ctx,
		"Stock Entry",
		{"stock_entry_type": "Material Receipt", "remarks": SEED_PREFIX},
		{
			"stock_entry_type": "Material Receipt",
			"company": ctx.company,
			"posting_date": today(),
			"remarks": SEED_PREFIX,
			"items": [
				{
					"item_code": ctx.stock_item,
					"qty": 50,
					"t_warehouse": ctx.warehouse,
					"basic_rate": 45,
				}
			],
		},
		submit=True,
	)


def _seed_projects(ctx: SeedContext) -> None:
	project = _ensure_doc(
		ctx,
		"Project",
		{"project_name": f"{SEED_PREFIX}：医院智能化交付"},
		{
			"project_name": f"{SEED_PREFIX}：医院智能化交付",
			"company": ctx.company,
			"status": "Open",
			"expected_start_date": today(),
			"expected_end_date": add_months(today(), 3),
			"percent_complete_method": "Manual",
			"percent_complete": 25,
			"notes": "覆盖售前、实施、培训和验收全过程。",
		},
	)
	task = _ensure_doc(
		ctx,
		"Task",
		{"subject": f"{SEED_PREFIX}：完成需求调研"},
		{
			"subject": f"{SEED_PREFIX}：完成需求调研",
			"project": project.name,
			"status": "Working",
			"priority": "High",
			"exp_start_date": today(),
			"exp_end_date": add_days(today(), 7),
			"description": "访谈业务部门并形成需求确认清单。",
		},
	)
	activity = _ensure_doc(
		ctx,
		"Activity Type",
		{"activity_type": f"{SEED_PREFIX}实施"},
		{"activity_type": f"{SEED_PREFIX}实施"},
	)
	_ensure_doc(
		ctx,
		"Timesheet",
		{"title": f"{SEED_PREFIX}项目工时"},
		{
			"title": f"{SEED_PREFIX}项目工时",
			"company": ctx.company,
			"time_logs": [
				{
					"activity_type": activity.name,
					"project": project.name,
					"task": task.name,
					"from_time": now_datetime(),
					"hours": 2,
					"description": "项目需求调研和方案确认。",
				}
			],
		},
	)


def _ensure_item_group(ctx: SeedContext) -> str:
	group = _ensure_doc(
		ctx,
		"Item Group",
		{"item_group_name": f"{SEED_PREFIX}产品"},
		{
			"item_group_name": f"{SEED_PREFIX}产品",
			"parent_item_group": "All Item Groups",
			"is_group": 0,
		},
	)
	return group.name


def _ensure_item(
	ctx: SeedContext,
	code: str,
	name: str,
	*,
	stock: bool = True,
	fixed_asset: bool = False,
	asset_category: str | None = None,
) -> Any:
	values = {
		"item_code": code,
		"item_name": name,
		"item_group": _ensure_item_group(ctx),
		"stock_uom": "Nos",
		"is_stock_item": int(stock),
		"is_sales_item": 1,
		"is_purchase_item": 1,
	}
	if fixed_asset:
		values.update(
			{
				"is_fixed_asset": 1,
				"auto_create_assets": 0,
				"asset_category": asset_category,
			}
		)
	return _ensure_doc(ctx, "Item", {"item_code": code}, values)


def _seed_manufacturing(ctx: SeedContext) -> None:
	raw = _ensure_item(ctx, "IONE-DEMO-RM-001", "I-ONE 智能终端核心板")
	finished = _ensure_item(ctx, "IONE-DEMO-FG-001", "I-ONE AI 智能终端")
	_ensure_doc(
		ctx,
		"Stock Entry",
		{"stock_entry_type": "Material Receipt", "remarks": f"{SEED_PREFIX}生产备料"},
		{
			"stock_entry_type": "Material Receipt",
			"company": ctx.company,
			"posting_date": today(),
			"remarks": f"{SEED_PREFIX}生产备料",
			"items": [
				{
					"item_code": raw.name,
					"qty": 100,
					"t_warehouse": ctx.warehouse,
					"basic_rate": 120,
				}
			],
		},
		submit=True,
	)
	bom = _ensure_doc(
		ctx,
		"BOM",
		{"item": finished.name, "is_active": 1, "is_default": 1},
		{
			"item": finished.name,
			"company": ctx.company,
			"quantity": 1,
			"is_active": 1,
			"is_default": 1,
			"with_operations": 0,
			"items": [{"item_code": raw.name, "qty": 2, "rate": 120, "source_warehouse": ctx.warehouse}],
		},
		submit=True,
	)
	_ensure_doc(
		ctx,
		"Work Order",
		{"production_item": finished.name, "bom_no": bom.name},
		{
			"company": ctx.company,
			"production_item": finished.name,
			"bom_no": bom.name,
			"qty": 10,
			"source_warehouse": ctx.warehouse,
			"fg_warehouse": ctx.warehouse,
			"planned_start_date": now_datetime(),
			"expected_delivery_date": add_days(now_datetime(), 10),
			"use_multi_level_bom": 1,
		},
	)


def _seed_assets(ctx: SeedContext) -> None:
	fixed_account = _find_account(ctx.company, account_type="Fixed Asset")
	accumulated = _find_account(ctx.company, account_type="Accumulated Depreciation")
	depreciation = _find_account(ctx.company, account_type="Depreciation")
	category = _ensure_doc(
		ctx,
		"Asset Category",
		{"asset_category_name": f"{SEED_PREFIX}设备"},
		{
			"asset_category_name": f"{SEED_PREFIX}设备",
			"enable_cwip_accounting": 0,
			"accounts": [
				{
					"company_name": ctx.company,
					"fixed_asset_account": fixed_account,
					"accumulated_depreciation_account": accumulated,
					"depreciation_expense_account": depreciation,
				}
			],
		},
	)
	asset_item = _ensure_item(
		ctx,
		"IONE-DEMO-ASSET-001",
		"I-ONE AI 推理服务器",
		stock=False,
		fixed_asset=True,
		asset_category=category.name,
	)
	location = _ensure_doc(
		ctx,
		"Location",
		{"location_name": f"{SEED_PREFIX}办公室"},
		{
			"location_name": f"{SEED_PREFIX}办公室",
			"is_group": 0,
		},
	)
	_ensure_doc(
		ctx,
		"Asset",
		{"asset_name": f"{SEED_PREFIX}：AI 推理服务器"},
		{
			"asset_name": f"{SEED_PREFIX}：AI 推理服务器",
			"item_code": asset_item.name,
			"asset_category": category.name,
			"company": ctx.company,
			"purchase_date": today(),
			"available_for_use_date": today(),
			"gross_purchase_amount": 68000,
			"net_purchase_amount": 68000,
			"location": location.name,
			"calculate_depreciation": 0,
			"is_existing_asset": 1,
			"opening_accumulated_depreciation": 0,
		},
	)


def _seed_quality(ctx: SeedContext) -> None:
	parameter = _ensure_doc(
		ctx,
		"Quality Inspection Parameter",
		{"parameter": f"{SEED_PREFIX}外观与包装"},
		{
			"parameter": f"{SEED_PREFIX}外观与包装",
			"description": "检查外观完整性和包装状态。",
		},
	)
	stock_entry = _first(
		"Stock Entry Detail",
		{"item_code": ctx.stock_item, "docstatus": 1},
		field="parent",
	)
	if not stock_entry:
		frappe.throw("请先生成并提交 I-ONE 业务样例库存入库单，再生成质检数据。")
	_ensure_doc(
		ctx,
		"Quality Inspection",
		{
			"inspection_type": "Incoming",
			"reference_type": "Stock Entry",
			"reference_name": stock_entry,
			"item_code": ctx.stock_item,
		},
		{
			"inspection_type": "Incoming",
			"reference_type": "Stock Entry",
			"reference_name": stock_entry,
			"item_code": ctx.stock_item,
			"sample_size": 5,
			"report_date": today(),
			"inspected_by": ctx.user,
			"status": "Accepted",
			"remarks": SEED_PREFIX,
			"readings": [
				{
					"specification": parameter.name,
					"value": "符合要求",
					"status": "Accepted",
				}
			],
		},
	)


def _seed_support(ctx: SeedContext) -> None:
	_ensure_doc(
		ctx,
		"Issue",
		{"subject": f"{SEED_PREFIX}：设备联网异常"},
		{
			"subject": f"{SEED_PREFIX}：设备联网异常",
			"customer": ctx.customer,
			"status": "Open",
			"priority": "Medium",
			"description": "现场设备偶发无法连接服务，需要检查网络和证书配置。",
			"raised_by": "demo.customer@myyr.top",
		},
	)
	_ensure_doc(
		ctx,
		"Contract",
		{
			"party_type": "Customer",
			"party_name": ctx.customer,
			"start_date": today(),
			"end_date": add_months(today(), 12),
		},
		{
			"party_type": "Customer",
			"party_name": ctx.customer,
			"start_date": today(),
			"end_date": add_months(today(), 12),
			"contract_terms": f"{SEED_PREFIX}：软件订阅、实施服务和年度运维。",
			"status": "Active",
		},
	)


def _ensure_expense_claim_account(ctx: SeedContext, expense_type: str) -> None:
	expense_account = _find_account(ctx.company, root_type="Expense")
	if not expense_account:
		frappe.throw(f"{ctx.company} 没有可用的费用科目。")
	doc = frappe.get_doc("Expense Claim Type", expense_type)
	if any(row.company == ctx.company and row.default_account for row in doc.accounts):
		return
	doc.append(
		"accounts",
		{
			"company": ctx.company,
			"default_account": expense_account,
		},
	)
	doc.save(ignore_permissions=True)


def _seed_hr_people(ctx: SeedContext) -> None:
	department = _first("Department", {"company": ctx.company, "is_group": 0})
	designation = _first("Designation")
	gender = "Female" if frappe.db.exists("Gender", "Female") else _first("Gender")
	employees = []
	for index, employee_name in enumerate(("张敏", "李强", "王芳"), 1):
		company_email = f"demo.employee{index}@myyr.top"
		employee = _ensure_doc(
			ctx,
			"Employee",
			{"company_email": company_email, "company": ctx.company},
			{
				"first_name": employee_name,
				"employee_name": f"{SEED_PREFIX}-{employee_name}",
				"company": ctx.company,
				"date_of_birth": f"199{index}-0{index + 2}-15",
				"date_of_joining": add_months(today(), -12 - index),
				"gender": gender,
				"status": "Active",
				"department": department,
				"designation": designation,
				"employment_type": "Full-time",
				"cell_number": f"1380000000{index + 1}",
				"company_email": company_email,
			},
		)
		employees.append(employee)

	holiday_list = _ensure_doc(
		ctx,
		"Holiday List",
		{"holiday_list_name": f"{SEED_PREFIX}-{today()[:4]}"},
		{
			"holiday_list_name": f"{SEED_PREFIX}-{today()[:4]}",
			"from_date": f"{today()[:4]}-01-01",
			"to_date": f"{today()[:4]}-12-31",
			"weekly_off": "Sunday",
			"holidays": [
				{"holiday_date": f"{today()[:4]}-01-01", "description": "元旦"},
				{"holiday_date": f"{today()[:4]}-05-01", "description": "劳动节"},
				{"holiday_date": f"{today()[:4]}-10-01", "description": "国庆节"},
			],
		},
	)
	shift = _ensure_doc(
		ctx,
		"Shift Type",
		{"name": f"{SEED_PREFIX}标准班次"},
		{
			"start_time": "09:00:00",
			"end_time": "18:00:00",
			"holiday_list": holiday_list.name,
			"enable_auto_attendance": 0,
		},
		name=f"{SEED_PREFIX}标准班次",
	)
	for employee in employees:
		_ensure_doc(
			ctx,
			"Holiday List Assignment",
			{
				"applicable_for": "Employee",
				"assigned_to": employee.name,
				"from_date": f"{today()[:4]}-01-01",
			},
			{
				"applicable_for": "Employee",
				"assigned_to": employee.name,
				"holiday_list": holiday_list.name,
				"from_date": f"{today()[:4]}-01-01",
			},
			submit=True,
		)
		_ensure_doc(
			ctx,
			"Shift Assignment",
			{"employee": employee.name, "shift_type": shift.name, "start_date": get_first_day(today())},
			{
				"employee": employee.name,
				"shift_type": shift.name,
				"start_date": get_first_day(today()),
				"company": ctx.company,
				"status": "Active",
			},
			submit=True,
		)
		_ensure_doc(
			ctx,
			"Attendance",
			{"employee": employee.name, "attendance_date": add_days(today(), -1)},
			{
				"employee": employee.name,
				"attendance_date": add_days(today(), -1),
				"status": "Present",
				"company": ctx.company,
				"shift": shift.name,
			},
			submit=True,
		)
		allocation = _ensure_doc(
			ctx,
			"Leave Allocation",
			{
				"employee": employee.name,
				"leave_type": "Casual Leave",
				"from_date": f"{today()[:4]}-01-01",
			},
			{
				"employee": employee.name,
				"leave_type": "Casual Leave",
				"from_date": f"{today()[:4]}-01-01",
				"to_date": f"{today()[:4]}-12-31",
				"new_leaves_allocated": 8,
				"company": ctx.company,
			},
			submit=True,
		)
		if allocation and employee == employees[0]:
			_ensure_doc(
				ctx,
				"Leave Application",
				{
					"employee": employee.name,
					"leave_type": "Casual Leave",
					"from_date": add_days(today(), 20),
				},
				{
					"employee": employee.name,
					"leave_type": "Casual Leave",
					"from_date": add_days(today(), 20),
					"to_date": add_days(today(), 20),
					"company": ctx.company,
					"description": f"{SEED_PREFIX}：个人事务请假",
					"status": "Open",
				},
			)

	employee = employees[0]
	_ensure_expense_claim_account(ctx, "Travel")
	_ensure_doc(
		ctx,
		"Expense Claim",
		{"employee": employee.name, "remark": SEED_PREFIX},
		{
			"employee": employee.name,
			"company": ctx.company,
			"posting_date": today(),
			"currency": ctx.currency,
			"exchange_rate": 1,
			"remark": SEED_PREFIX,
			"expenses": [
				{
					"expense_date": today(),
					"expense_type": "Travel",
					"description": "客户现场调研交通费",
					"amount": 680,
					"sanctioned_amount": 680,
				}
			],
		},
	)


def _seed_hr_recruiting(ctx: SeedContext) -> None:
	designation = _first("Designation")
	opening = _ensure_doc(
		ctx,
		"Job Opening",
		{"job_title": f"{SEED_PREFIX}：AI 产品经理", "company": ctx.company},
		{
			"job_title": f"{SEED_PREFIX}：AI 产品经理",
			"designation": designation,
			"company": ctx.company,
			"status": "Open",
			"posted_on": today(),
			"closes_on": add_days(today(), 30),
			"description": "负责 I-ONE AI 产品规划、需求分析与交付。",
		},
	)
	applicant_source = _ensure_doc(
		ctx,
		"Job Applicant Source",
		{"source_name": f"{SEED_PREFIX}网站"},
		{
			"source_name": f"{SEED_PREFIX}网站",
			"details": "I-ONE 官网与人才推荐渠道。",
		},
	)
	applicant = _ensure_doc(
		ctx,
		"Job Applicant",
		{"email_id": "demo.applicant@myyr.top"},
		{
			"applicant_name": f"{SEED_PREFIX}-赵晨",
			"email_id": "demo.applicant@myyr.top",
			"phone_number": "13800000008",
			"job_title": opening.name,
			"status": "Open",
			"source": applicant_source.name,
		},
	)
	_ensure_doc(
		ctx,
		"Job Offer",
		{"job_applicant": applicant.name},
		{
			"job_applicant": applicant.name,
			"applicant_name": applicant.applicant_name,
			"offer_date": today(),
			"designation": designation,
			"company": ctx.company,
			"status": "Awaiting Response",
		},
	)


def _seed_hr_payroll(ctx: SeedContext) -> None:
	employee_name = frappe.db.exists(
		"Employee",
		{"company_email": "demo.employee1@myyr.top", "company": ctx.company},
	)
	if not employee_name:
		frappe.throw("请先生成 I-ONE 业务样例员工，再生成薪酬数据。")
	employee = frappe.get_doc("Employee", employee_name)
	basic = _ensure_doc(
		ctx,
		"Salary Component",
		{"salary_component": f"{SEED_PREFIX}基本工资"},
		{
			"salary_component": f"{SEED_PREFIX}基本工资",
			"salary_component_abbr": "IONE-BASIC",
			"type": "Earning",
		},
	)
	allowance = _ensure_doc(
		ctx,
		"Salary Component",
		{"salary_component": f"{SEED_PREFIX}岗位津贴"},
		{
			"salary_component": f"{SEED_PREFIX}岗位津贴",
			"salary_component_abbr": "IONE-ALLOW",
			"type": "Earning",
		},
	)
	structure = _ensure_doc(
		ctx,
		"Salary Structure",
		{"name": f"{SEED_PREFIX}月薪结构"},
		{
			"company": ctx.company,
			"is_active": "Yes",
			"is_default": "No",
			"currency": ctx.currency,
			"payroll_frequency": "Monthly",
			"earnings": [
				{"salary_component": basic.name, "amount": 8000},
				{"salary_component": allowance.name, "amount": 2000},
			],
		},
		name=f"{SEED_PREFIX}月薪结构",
		submit=True,
	)
	_ensure_doc(
		ctx,
		"Salary Structure Assignment",
		{"employee": employee.name, "salary_structure": structure.name},
		{
			"employee": employee.name,
			"salary_structure": structure.name,
			"from_date": get_first_day(today()),
			"company": ctx.company,
			"currency": ctx.currency,
			"base": 10000,
		},
		submit=True,
	)


def _seed_hr_salary_slip(ctx: SeedContext) -> None:
	employee_name = frappe.db.exists(
		"Employee",
		{"company_email": "demo.employee1@myyr.top", "company": ctx.company},
	)
	structure_name = frappe.db.exists("Salary Structure", f"{SEED_PREFIX}月薪结构")
	if not employee_name or not structure_name:
		frappe.throw("请先生成 I-ONE 业务样例员工和薪酬结构，再生成工资单。")
	_ensure_doc(
		ctx,
		"Salary Slip",
		{
			"employee": employee_name,
			"start_date": get_first_day(today()),
			"end_date": get_last_day(today()),
		},
		{
			"employee": employee_name,
			"company": ctx.company,
			"posting_date": today(),
			"start_date": get_first_day(today()),
			"end_date": get_last_day(today()),
			"salary_structure": structure_name,
			"payroll_frequency": "Monthly",
			"currency": ctx.currency,
			"exchange_rate": 1,
		},
	)


def _seed_crm(ctx: SeedContext) -> None:
	organization = _ensure_doc(
		ctx,
		"CRM Organization",
		{"organization_name": f"{SEED_PREFIX}客户集团"},
		{
			"organization_name": f"{SEED_PREFIX}客户集团",
			"no_of_employees": "201-500",
			"currency": ctx.currency,
			"annual_revenue": 50000000,
			"website": "https://myyr.top",
			"company_description": "医疗健康行业数字化客户。",
			"industry": "Healthcare",
		},
	)
	lead = _ensure_doc(
		ctx,
		"CRM Lead",
		{"email": "crm.demo@myyr.top"},
		{
			"first_name": "陈",
			"last_name": "经理",
			"email": "crm.demo@myyr.top",
			"mobile_no": "13800000009",
			"organization": organization.name,
			"status": "New",
			"source": "Website",
			"industry": "Healthcare",
			"lead_owner": ctx.user,
			"no_of_employees": "201-500",
			"annual_revenue": 50000000,
		},
	)
	deal = _ensure_doc(
		ctx,
		"CRM Deal",
		{"lead": lead.name, "organization": organization.name},
		{
			"lead": lead.name,
			"organization": organization.name,
			"organization_name": organization.name,
			"status": "Qualification",
			"deal_owner": ctx.user,
			"probability": 35,
			"expected_deal_value": 180000,
			"expected_closure_date": add_days(today(), 45),
			"next_step": "安排产品方案演示",
			"currency": ctx.currency,
		},
	)
	_ensure_doc(
		ctx,
		"CRM Task",
		{"title": f"{SEED_PREFIX}：安排客户方案演示"},
		{
			"title": f"{SEED_PREFIX}：安排客户方案演示",
			"priority": "High",
			"start_date": today(),
			"due_date": add_days(now_datetime(), 3),
			"reference_doctype": "CRM Deal",
			"reference_docname": deal.name,
			"assigned_to": ctx.user,
			"status": "Todo",
			"description": "准备行业方案、产品演示和报价范围。",
		},
	)
	_ensure_doc(
		ctx,
		"FCRM Note",
		{"title": f"{SEED_PREFIX}：客户沟通纪要"},
		{
			"title": f"{SEED_PREFIX}：客户沟通纪要",
			"content": "客户关注数据安全、国产模型部署与业务自动化能力。",
			"reference_doctype": "CRM Deal",
			"reference_docname": deal.name,
		},
	)


def _seed_helpdesk(ctx: SeedContext) -> None:
	_ensure_doc(
		ctx,
		"HD Agent",
		{"user": ctx.user},
		{
			"user": ctx.user,
			"agent_name": frappe.db.get_value("User", ctx.user, "full_name") or ctx.user,
			"is_active": 1,
			"availability": _first("HD Agent Status"),
		},
	)
	team_name = _first("HD Team", {"disabled": 0})
	team = frappe.get_doc("HD Team", team_name)
	if not any(row.user == ctx.user for row in team.users):
		team.append("users", {"user": ctx.user})
		team.save(ignore_permissions=True)
	if team.assignment_rule:
		rule = frappe.get_doc("Assignment Rule", team.assignment_rule)
		if not any(row.user == ctx.user for row in rule.users):
			rule.append("users", {"user": ctx.user})
			rule.save(ignore_permissions=True)

	customer = _ensure_doc(
		ctx,
		"HD Customer",
		{"customer_name": f"{SEED_PREFIX}客户"},
		{
			"customer_name": f"{SEED_PREFIX}客户",
			"customer_type": "Company",
			"email_id": "support.demo@myyr.top",
			"mobile_no": "13800000010",
			"country": "China",
			"erpnext_customer": ctx.customer,
		},
	)
	for subject, priority, status in (
		("账号登录后页面加载缓慢", "High", "Open"),
		("需要增加经营日报模板", "Medium", "Replied"),
		("移动端消息提醒未收到", "Low", "Resolved"),
	):
		_ensure_doc(
			ctx,
			"HD Ticket",
			{"subject": f"{SEED_PREFIX}：{subject}"},
			{
				"subject": f"{SEED_PREFIX}：{subject}",
				"raised_by": "support.demo@myyr.top",
				"customer": customer.name,
				"status": status,
				"priority": priority,
				"ticket_type": "Question",
				"agent_group": team.name,
				"description": f"<p>{subject}，请协助排查并反馈处理进展。</p>",
			},
		)
	category = _ensure_doc(
		ctx,
		"HD Article Category",
		{"category_name": f"{SEED_PREFIX}使用指南"},
		{
			"category_name": f"{SEED_PREFIX}使用指南",
			"description": "I-ONE 产品使用和常见问题。",
			"icon": "book-open",
		},
	)
	_ensure_doc(
		ctx,
		"HD Article",
		{"title": f"{SEED_PREFIX}：如何创建今日待办"},
		{
			"title": f"{SEED_PREFIX}：如何创建今日待办",
			"status": "Published",
			"published_on": now_datetime(),
			"category": category.name,
			"author": ctx.user,
			"content": "<h2>创建待办</h2><p>在工作台进入今日待办，填写任务、负责人和截止时间。</p>",
		},
	)


def _seed_learning(ctx: SeedContext) -> None:
	category = _ensure_doc(
		ctx,
		"LMS Category",
		{"category": f"{SEED_PREFIX}课程"},
		{"category": f"{SEED_PREFIX}课程"},
	)
	course = _ensure_doc(
		ctx,
		"LMS Course",
		{"title": f"{SEED_PREFIX}：AI 业务应用入门"},
		{
			"title": f"{SEED_PREFIX}：AI 业务应用入门",
			"category": category.name,
			"status": "Approved",
			"published": 1,
			"published_on": today(),
			"card_gradient": "Blue",
			"short_introduction": "学习如何在 I-ONE 中使用业务应用和 AI 员工。",
			"description": "<p>课程覆盖客户管理、销售采购、项目协作和 AI 自动化。</p>",
			"instructors": [{"instructor": ctx.user}],
		},
	)
	chapter = _ensure_doc(
		ctx,
		"Course Chapter",
		{"course": course.name, "title": "第一章：认识 I-ONE"},
		{
			"course": course.name,
			"title": "第一章：认识 I-ONE",
		},
	)
	question = _ensure_doc(
		ctx,
		"LMS Question",
		{"question": "I-ONE AI 的核心用途是什么？"},
		{
			"question": "I-ONE AI 的核心用途是什么？",
			"type": "Choices",
			"option_1": "连接业务数据并协助执行工作",
			"is_correct_1": 1,
			"option_2": "只用于修改页面颜色",
			"is_correct_2": 0,
		},
	)
	quiz = _ensure_doc(
		ctx,
		"LMS Quiz",
		{"title": f"{SEED_PREFIX}：入门测验"},
		{
			"title": f"{SEED_PREFIX}：入门测验",
			"course": course.name,
			"total_marks": 10,
			"passing_percentage": 60,
			"show_answers": 1,
			"questions": [{"question": question.name, "marks": 10}],
		},
	)
	lesson = _ensure_doc(
		ctx,
		"Course Lesson",
		{"chapter": chapter.name, "title": "I-ONE 业务工作台"},
		{
			"course": course.name,
			"chapter": chapter.name,
			"title": "I-ONE 业务工作台",
			"include_in_preview": 1,
			"body": "本节介绍首页、今日待办、快捷入口以及 AI 员工的基本使用方法。",
			"quiz_id": quiz.name,
		},
	)
	course.reload()
	if not any(row.chapter == chapter.name for row in course.chapters):
		course.append("chapters", {"chapter": chapter.name})
		course.save(ignore_permissions=True)
	chapter.reload()
	if not any(row.lesson == lesson.name for row in chapter.lessons):
		chapter.append("lessons", {"lesson": lesson.name})
		chapter.save(ignore_permissions=True)
	_ensure_doc(
		ctx,
		"LMS Enrollment",
		{"course": course.name, "member": ctx.user},
		{
			"course": course.name,
			"member": ctx.user,
			"member_type": "Student",
			"role": "Member",
			"current_lesson": lesson.name,
			"progress": 25,
		},
	)


def _seed_lending(ctx: SeedContext) -> None:
	cash = _find_account(ctx.company, account_type="Cash") or _find_account(ctx.company, root_type="Asset")
	receivable = _find_account(ctx.company, account_type="Receivable") or cash
	income = _find_account(ctx.company, root_type="Income")
	offset_order = _ensure_doc(
		ctx,
		"Loan Demand Offset Order",
		{"title": f"{SEED_PREFIX}回收顺序"},
		{
			"title": f"{SEED_PREFIX}回收顺序",
			"components": [
				{"demand_type": "Penalty"},
				{"demand_type": "Charges"},
				{"demand_type": "Additional Interest"},
				{"demand_type": "Interest"},
				{"demand_type": "Principal"},
			],
		},
	)
	product = _ensure_doc(
		ctx,
		"Loan Product",
		{"product_code": "IONE-DEMO-LOAN"},
		{
			"product_code": "IONE-DEMO-LOAN",
			"product_name": f"{SEED_PREFIX}员工发展借款",
			"company": ctx.company,
			"rate_of_interest": 4.8,
			"maximum_loan_amount": 100000,
			"is_term_loan": 1,
			"repayment_schedule_type": "Monthly as per repayment start date",
			"repayment_date_on": "Start of the next month",
			"collection_offset_sequence_for_standard_asset": offset_order.name,
			"collection_offset_sequence_for_sub_standard_asset": offset_order.name,
			"collection_offset_sequence_for_written_off_asset": offset_order.name,
			"collection_offset_sequence_for_settlement_collection": offset_order.name,
			"disbursement_account": cash,
			"payment_account": cash,
			"loan_account": receivable,
			"interest_income_account": income,
			"interest_accrued_account": receivable,
			"interest_receivable_account": receivable,
		},
	)
	_ensure_doc(
		ctx,
		"Loan Application",
		{"applicant_type": "Customer", "applicant": ctx.customer, "loan_product": product.name},
		{
			"applicant_type": "Customer",
			"applicant": ctx.customer,
			"applicant_name": ctx.customer,
			"company": ctx.company,
			"posting_date": today(),
			"status": "Open",
			"loan_product": product.name,
			"loan_amount": 50000,
			"rate_of_interest": 4.8,
			"is_term_loan": 1,
			"repayment_method": "Repay Over Number of Periods",
			"repayment_periods": 12,
		},
	)


def _seed_gameplan(ctx: SeedContext) -> None:
	team = _ensure_doc(
		ctx,
		"GP Team",
		{"title": f"{SEED_PREFIX}经营团队"},
		{
			"title": f"{SEED_PREFIX}经营团队",
			"icon": "target",
			"is_private": 0,
			"readme": "<p>负责产品、销售、交付和客户成功协同。</p>",
			"members": [{"user": ctx.user}],
		},
		name=f"{SEED_PREFIX}经营团队",
	)
	project = _ensure_doc(
		ctx,
		"GP Project",
		{"title": f"{SEED_PREFIX}：I-ONE 产品发布"},
		{
			"title": f"{SEED_PREFIX}：I-ONE 产品发布",
			"team": team.name,
			"icon": "rocket",
			"description": "统一跟踪发布准备、市场物料、客户试点和复盘。",
			"members": [{"user": ctx.user}],
		},
	)
	for title, status, priority in (
		("完成版本发布清单", "Done", "High"),
		("准备客户演示环境", "In Progress", "Urgent"),
		("整理产品培训材料", "Todo", "Medium"),
	):
		_ensure_doc(
			ctx,
			"GP Task",
			{"title": f"{SEED_PREFIX}：{title}", "project": project.name},
			{
				"title": f"{SEED_PREFIX}：{title}",
				"description": title,
				"project": project.name,
				"team": team.name,
				"assigned_to": ctx.user,
				"status": status,
				"priority": priority,
				"start_date": today(),
				"due_date": add_days(today(), 7),
			},
		)
	_ensure_doc(
		ctx,
		"GP Discussion",
		{"project": project.name, "title": f"{SEED_PREFIX}：试点客户反馈"},
		{
			"project": project.name,
			"team": team.name,
			"title": f"{SEED_PREFIX}：试点客户反馈",
			"content": "<p>集中讨论试点客户反馈、优先级和版本计划。</p>",
			"status": "Open",
		},
	)
	_ensure_doc(
		ctx,
		"GP Page",
		{"project": project.name, "title": f"{SEED_PREFIX}：项目说明"},
		{
			"project": project.name,
			"team": team.name,
			"title": f"{SEED_PREFIX}：项目说明",
			"slug": "ione-demo-project-readme",
			"content": "<h1>I-ONE 产品发布</h1><p>目标、范围、里程碑与职责说明。</p>",
		},
	)


def _seed_writer(ctx: SeedContext) -> None:
	_ensure_doc(
		ctx,
		"Writer Document",
		{"html": ["like", f"%{SEED_PREFIX}%"]},
		{
			"html": f"<h1>{SEED_PREFIX}经营月报</h1><p>本月销售、交付与客户成功工作稳步推进。</p>",
			"settings": json.dumps({"title": f"{SEED_PREFIX}经营月报"}, ensure_ascii=False),
			"collab": 1,
		},
	)


def _seed_wiki(ctx: SeedContext) -> None:
	root = _ensure_doc(
		ctx,
		"Wiki Document",
		{"title": f"{SEED_PREFIX}业务手册", "is_group": 1},
		{
			"title": f"{SEED_PREFIX}业务手册",
			"slug": "ione-business-handbook",
			"is_group": 1,
			"is_published": 1,
		},
	)
	space = _ensure_doc(
		ctx,
		"Wiki Space",
		{"route": "ione-business-handbook"},
		{
			"space_name": f"{SEED_PREFIX}业务手册",
			"route": "ione-business-handbook",
			"is_published": 1,
			"show_in_switcher": 1,
			"allow_contributions": 1,
			"root_group": root.name,
		},
	)
	_ensure_doc(
		ctx,
		"Wiki Document",
		{"title": f"{SEED_PREFIX}：业务快速开始", "parent_wiki_document": root.name},
		{
			"title": f"{SEED_PREFIX}：业务快速开始",
			"slug": "quick-start",
			"is_published": 1,
			"is_group": 0,
			"parent_wiki_document": root.name,
			"wiki_space": space.name,
			"content": "# I-ONE 业务快速开始\n\n本页介绍销售、采购、人事、服务和 AI 员工的协作流程。",
			"meta_description": "I-ONE 业务系统快速开始指南",
		},
	)


def _seed_insights(ctx: SeedContext) -> None:
	_ensure_doc(
		ctx,
		"Insights Dashboard",
		{"title": f"{SEED_PREFIX}经营驾驶舱"},
		{"title": f"{SEED_PREFIX}经营驾驶舱"},
	)
	_ensure_doc(
		ctx,
		"Insights Workbook",
		{"title": f"{SEED_PREFIX}经营分析"},
		{"title": f"{SEED_PREFIX}经营分析"},
	)


def _seed_ione(ctx: SeedContext) -> None:
	agent = _ensure_doc(
		ctx,
		"I-ONE Agent",
		{"agent_code": "ione-demo-sales"},
		{
			"agent_code": "ione-demo-sales",
			"agent_name": "I-ONE 销售助理",
			"agent_type": "销售助理",
			"status": "在职",
			"operating_mode": "半自动",
			"description": "负责线索整理、客户跟进、报价准备和销售复盘。",
			"responsibilities": "CRM 线索与商机管理；销售待办；客户沟通摘要。",
			"allowed_modules": "CRM\nERPNext\nGameplan\nInsights",
		},
	)
	_ensure_doc(
		ctx,
		"I-ONE AI Task",
		{"title": f"{SEED_PREFIX}：生成本周销售跟进计划"},
		{
			"title": f"{SEED_PREFIX}：生成本周销售跟进计划",
			"task_type": "查询分析",
			"priority": "高",
			"status": "已完成",
			"requested_by": ctx.user,
			"assigned_agent": agent.name,
			"risk_level": "低",
			"prompt": "汇总本周需要跟进的 CRM 线索与商机，并按优先级生成行动计划。",
			"result_summary": "已生成客户演示、方案确认和报价跟进计划。",
		},
	)
	_ensure_doc(
		ctx,
		"I-ONE Growth Plan",
		{"title": f"{SEED_PREFIX}：年度智能化增长计划"},
		{
			"title": f"{SEED_PREFIX}：年度智能化增长计划",
			"category": "公司战略",
			"owner_user": ctx.user,
			"status": "进行中",
			"description": "通过 AI 员工、流程自动化和数据分析提升经营效率。",
		},
	)
	_ensure_doc(
		ctx,
		"I-ONE Experience",
		{"title": f"{SEED_PREFIX}：客户需求调研方法"},
		{
			"title": f"{SEED_PREFIX}：客户需求调研方法",
			"author_user": ctx.user,
			"status": "已发布",
			"content": "<p>先明确业务目标，再梳理角色、流程、数据和验收指标。</p>",
		},
	)
	_ensure_doc(
		ctx,
		"I-ONE Achievement",
		{"user": ctx.user, "achievement_code": "IONE-DEMO-FIRST-WORKFLOW"},
		{
			"user": ctx.user,
			"achievement_code": "IONE-DEMO-FIRST-WORKFLOW",
			"title": "完成首个跨应用业务流程",
			"achievement_type": "智能化",
			"description": "完成从客户线索到销售、交付和服务的跨应用数据链。",
		},
	)


DOMAIN_SEEDERS: tuple[tuple[str, Callable[[SeedContext], None]], ...] = (
	("通用协作", _seed_framework),
	("销售管理", _seed_sales),
	("采购与库存", _seed_buying_and_stock),
	("项目管理", _seed_projects),
	("生产制造", _seed_manufacturing),
	("资产管理", _seed_assets),
	("质量管理", _seed_quality),
	("客户支持", _seed_support),
	("人力资源基础", _seed_hr_people),
	("招聘管理", _seed_hr_recruiting),
	("薪酬管理", _seed_hr_payroll),
	("工资单", _seed_hr_salary_slip),
	("CRM", _seed_crm),
	("服务台", _seed_helpdesk),
	("学习", _seed_learning),
	("借贷", _seed_lending),
	("Gameplan", _seed_gameplan),
	("Writer", _seed_writer),
	("Wiki", _seed_wiki),
	("Insights", _seed_insights),
	("I-ONE AI", _seed_ione),
)


@frappe.whitelist()
def seed_manager_business_data() -> dict[str, Any]:
	"""Create an idempotent, cross-application business dataset for the manager site."""
	frappe.only_for("System Manager")
	report = SeedReport()
	ctx = _make_context(report)
	for domain, seeder in DOMAIN_SEEDERS:
		_run_domain(ctx, domain, seeder)
	return report.as_dict()


@frappe.whitelist()
def get_business_data_coverage() -> dict[str, Any]:
	coverage: dict[str, Any] = {}
	for domain, doctypes in CORE_COVERAGE.items():
		rows = {}
		for doctype in doctypes:
			if not _doctype_exists(doctype):
				rows[doctype] = None
				continue
			try:
				rows[doctype] = frappe.db.count(doctype)
			except Exception:
				rows[doctype] = None
		coverage[domain] = {
			"covered": bool(rows)
			and all(isinstance(count, int) and count > 0 for count in rows.values()),
			"records": rows,
		}
	return coverage

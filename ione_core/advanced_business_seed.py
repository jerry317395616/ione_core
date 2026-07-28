from __future__ import annotations

# ruff: noqa: RUF001
from typing import Any

import frappe
from frappe.utils import add_days, add_months, now_datetime, today

POS_MARKER = "I-ONE 业务样例：POS 销售出库样例"
SUBCONTRACTING_MARKER = "IONE-SCIO-DEMO-001"
ASSET_SHIFT_MARKER = "I-ONE AI 推理服务器（班次折旧样例）"


def _doctype_exists(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype))


def _label(doctype: str, name: str) -> str:
	return f"{doctype}: {name}"


def _record(ctx: Any, doctype: str, name: str, *, created: bool) -> None:
	target = ctx.report.created if created else ctx.report.existing
	target.append(_label(doctype, name))


def _ensure(
	ctx: Any,
	doctype: str,
	filters: dict[str, Any],
	values: dict[str, Any],
	*,
	submit: bool = False,
) -> Any:
	if not _doctype_exists(doctype):
		ctx.report.skipped.append(f"{doctype}: DocType 未安装")
		return None

	existing = frappe.db.exists(doctype, filters)
	if existing:
		doc = frappe.get_doc(doctype, existing)
		if submit and doc.docstatus == 0:
			doc.submit()
		_record(ctx, doctype, doc.name, created=False)
		return doc

	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.insert(ignore_permissions=True)
	if submit and doc.docstatus == 0:
		doc.submit()
	_record(ctx, doctype, doc.name, created=True)
	return doc


def _first(
	doctype: str,
	filters: dict[str, Any] | None = None,
	field: str = "name",
	order_by: str = "creation asc",
) -> Any:
	return frappe.db.get_value(doctype, filters or {}, field, order_by=order_by)


def _account(
	company: str,
	*,
	account_type: str | None = None,
	root_type: str | None = None,
) -> str | None:
	filters: dict[str, Any] = {"company": company, "is_group": 0, "disabled": 0}
	if account_type:
		filters["account_type"] = account_type
	if root_type:
		filters["root_type"] = root_type
	return _first("Account", filters)


def _cost_center(company: str) -> str | None:
	return _first("Cost Center", {"company": company, "is_group": 0, "disabled": 0})


def _ensure_mode_of_payment_account(ctx: Any, mode_of_payment: str, account: str) -> None:
	if frappe.db.exists(
		"Mode of Payment Account",
		{"parent": mode_of_payment, "company": ctx.company},
	):
		return
	mode = frappe.get_doc("Mode of Payment", mode_of_payment)
	mode.append("accounts", {"company": ctx.company, "default_account": account})
	mode.save(ignore_permissions=True)


def _pos_stock(ctx: Any) -> tuple[str, str, float] | None:
	bins = frappe.get_all(
		"Bin",
		filters={"actual_qty": [">", 5]},
		fields=["item_code", "warehouse", "actual_qty", "valuation_rate"],
		order_by="actual_qty desc",
		limit_page_length=50,
	)
	for row in bins:
		if frappe.db.get_value("Warehouse", row.warehouse, "company") != ctx.company:
			continue
		item = frappe.db.get_value(
			"Item",
			row.item_code,
			["disabled", "is_stock_item", "is_sales_item", "has_batch_no", "has_serial_no"],
			as_dict=True,
		)
		if not item or item.disabled or not item.is_stock_item or not item.is_sales_item:
			continue
		if item.has_batch_no or item.has_serial_no:
			continue
		rate = _first(
			"Item Price",
			{"item_code": row.item_code, "price_list": "Standard Selling", "selling": 1},
			"price_list_rate",
		)
		return row.item_code, row.warehouse, max(float(rate or row.valuation_rate or 1), 1)
	return None


def _ensure_pos_profile(ctx: Any, warehouse: str) -> Any:
	profile_name = "I-ONE 医疗产品零售"
	existing = frappe.db.exists("POS Profile", profile_name)
	if existing:
		_record(ctx, "POS Profile", existing, created=False)
		return frappe.get_doc("POS Profile", existing)

	cash_account = _account(ctx.company, account_type="Cash", root_type="Asset")
	income_account = _account(ctx.company, root_type="Income")
	expense_account = _account(ctx.company, account_type="Cost of Goods Sold", root_type="Expense")
	expense_account = expense_account or _account(ctx.company, root_type="Expense")
	write_off_account = _account(ctx.company, account_type="Round Off", root_type="Expense")
	write_off_account = write_off_account or expense_account
	cost_center = _cost_center(ctx.company)
	if not all((cash_account, income_account, expense_account, write_off_account, cost_center)):
		frappe.throw("POS 业务样例缺少现金、收入、成本、尾差账户或成本中心。")

	mode_of_payment = "Cash"
	if not frappe.db.exists("Mode of Payment", mode_of_payment):
		mode = frappe.get_doc(
			{
				"doctype": "Mode of Payment",
				"mode_of_payment": mode_of_payment,
				"type": "Cash",
			}
		).insert(ignore_permissions=True)
		_record(ctx, "Mode of Payment", mode.name, created=True)
	_ensure_mode_of_payment_account(ctx, mode_of_payment, cash_account)

	profile = frappe.get_doc(
		{
			"doctype": "POS Profile",
			"name": profile_name,
			"company": ctx.company,
			"customer": ctx.customer,
			"warehouse": warehouse,
			"currency": ctx.currency,
			"selling_price_list": "Standard Selling",
			"write_off_account": write_off_account,
			"write_off_cost_center": cost_center,
			"income_account": income_account,
			"expense_account": expense_account,
			"cost_center": cost_center,
			"update_stock": 1,
			"set_grand_total_to_default_mop": 1,
			"payments": [{"mode_of_payment": mode_of_payment, "default": 1}],
			"applicable_for_users": [{"user": ctx.user, "default": 1}],
		}
	)
	profile.insert(ignore_permissions=True)
	_record(ctx, "POS Profile", profile.name, created=True)
	return profile


def _open_pos(ctx: Any, profile: Any) -> Any:
	opening_name = frappe.db.get_value(
		"POS Opening Entry",
		{"pos_profile": profile.name, "status": "Open"},
		"name",
	)
	if opening_name:
		_record(ctx, "POS Opening Entry", opening_name, created=False)
		return frappe.get_doc("POS Opening Entry", opening_name)

	other_opening = frappe.db.get_value(
		"POS Opening Entry",
		{"user": ctx.user, "status": "Open"},
		["name", "pos_profile"],
		as_dict=True,
	)
	if other_opening:
		ctx.report.skipped.append(
			f"POS Opening Entry: 用户 {ctx.user} 已在 {other_opening.pos_profile} 开班"
		)
		return None

	opening = frappe.get_doc(
		{
			"doctype": "POS Opening Entry",
			"period_start_date": now_datetime(),
			"posting_date": today(),
			"company": ctx.company,
			"pos_profile": profile.name,
			"user": ctx.user,
			"balance_details": [
				{"mode_of_payment": row.mode_of_payment, "opening_amount": 0}
				for row in profile.payments
			],
		}
	)
	opening.insert(ignore_permissions=True)
	opening.submit()
	_record(ctx, "POS Opening Entry", opening.name, created=True)
	return opening


def _ensure_pos_workflow(ctx: Any) -> None:
	required = (
		"POS Profile",
		"POS Opening Entry",
		"POS Invoice",
		"POS Closing Entry",
		"POS Invoice Merge Log",
	)
	if not all(_doctype_exists(doctype) for doctype in required):
		ctx.report.skipped.append("POS：当前 ERPNext 版本未安装完整 POS DocType")
		return

	stock = _pos_stock(ctx)
	if not stock:
		ctx.report.skipped.append("POS：没有数量充足且不使用批次/序列号的销售库存")
		return
	item_code, warehouse, rate = stock
	profile = _ensure_pos_profile(ctx, warehouse)
	frappe.db.set_single_value("POS Settings", "invoice_type", "POS Invoice")

	existing_invoice = frappe.db.get_value(
		"POS Invoice",
		{"company": ctx.company, "remarks": POS_MARKER, "docstatus": 1},
		"name",
	)
	if existing_invoice:
		_record(ctx, "POS Invoice", existing_invoice, created=False)
		merge_log = frappe.db.get_value(
			"POS Invoice Reference",
			{"pos_invoice": existing_invoice, "parenttype": "POS Invoice Merge Log"},
			"parent",
		)
		if merge_log:
			_record(ctx, "POS Invoice Merge Log", merge_log, created=False)
		_open_pos(ctx, profile)
		return

	opening = _open_pos(ctx, profile)
	if not opening:
		return
	payment = profile.payments[0]
	payment_account = frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": payment.mode_of_payment, "company": ctx.company},
		"default_account",
	)
	invoice = frappe.get_doc(
		{
			"doctype": "POS Invoice",
			"customer": profile.customer or ctx.customer,
			"company": ctx.company,
			"posting_date": today(),
			"due_date": today(),
			"is_pos": 1,
			"pos_profile": profile.name,
			"update_stock": 1,
			"set_warehouse": warehouse,
			"currency": ctx.currency,
			"selling_price_list": profile.selling_price_list,
			"remarks": POS_MARKER,
			"items": [{"item_code": item_code, "qty": 2, "rate": rate, "warehouse": warehouse}],
			"payments": [
				{
					"mode_of_payment": payment.mode_of_payment,
					"account": payment_account,
					"amount": 2 * rate,
					"default": 1,
				}
			],
		}
	)
	invoice.insert(ignore_permissions=True)
	invoice.submit()
	_record(ctx, "POS Invoice", invoice.name, created=True)

	from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import (
		make_closing_entry_from_opening,
	)

	closing = make_closing_entry_from_opening(opening)
	for row in closing.payment_reconciliation:
		row.closing_amount = row.expected_amount
	closing.insert(ignore_permissions=True)
	closing.submit()
	_record(ctx, "POS Closing Entry", closing.name, created=True)
	merge_log = frappe.db.get_value(
		"POS Invoice Merge Log",
		{"pos_closing_entry": closing.name},
		"name",
	)
	if merge_log:
		_record(ctx, "POS Invoice Merge Log", merge_log, created=True)
	_open_pos(ctx, profile)


def _ensure_sample_item(
	ctx: Any,
	item_code: str,
	item_name: str,
	*,
	stock: bool,
	customer_provided: bool = False,
	subcontracted: bool = False,
) -> Any:
	existing = frappe.db.exists("Item", item_code)
	if existing:
		_record(ctx, "Item", existing, created=False)
		return frappe.get_doc("Item", existing)
	group = _first("Item Group", {"is_group": 0})
	uom = "Nos" if stock else (_first("UOM", {"enabled": 1}, "name") or "Nos")
	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_name,
			"item_group": group,
			"stock_uom": uom,
			"is_stock_item": int(stock),
			"is_sales_item": 1,
			"is_purchase_item": 1,
			"is_customer_provided_item": int(customer_provided),
			"is_sub_contracted_item": int(subcontracted),
			"default_material_request_type": "Customer Provided" if customer_provided else "Purchase",
		}
	)
	doc.insert(ignore_permissions=True)
	_record(ctx, "Item", doc.name, created=True)
	return doc


def _ensure_subcontracting_inward(ctx: Any) -> Any:
	required = ("Subcontracting BOM", "Subcontracting Inward Order")
	if not all(_doctype_exists(doctype) for doctype in required):
		ctx.report.skipped.append("委外加工：当前 ERPNext 版本未安装委外加工 DocType")
		return None

	existing_order = frappe.db.get_value(
		"Sales Order",
		{"company": ctx.company, "po_no": SUBCONTRACTING_MARKER, "docstatus": 1},
		"name",
	)
	if existing_order:
		inward = frappe.db.get_value(
			"Subcontracting Inward Order",
			{"sales_order": existing_order, "docstatus": 1},
			"name",
		)
		if inward:
			_record(ctx, "Subcontracting Inward Order", inward, created=False)
			return frappe.get_doc("Sales Order", existing_order)

	finished = _ensure_sample_item(
		ctx,
		"IONE-SUB-FG-001",
		"I-ONE 委外加工终端外壳",
		stock=True,
		subcontracted=True,
	)
	raw = _ensure_sample_item(
		ctx,
		"IONE-CUST-RM-001",
		"客户提供医疗设备核心材料",
		stock=True,
		customer_provided=True,
	)
	service = _ensure_sample_item(
		ctx,
		"IONE-SUB-SVC-001",
		"I-ONE 委外精密加工服务",
		stock=False,
	)
	customer_warehouse = _ensure(
		ctx,
		"Warehouse",
		{"company": ctx.company, "customer": ctx.customer, "disabled": 0},
		{
			"warehouse_name": f"{ctx.customer}客户物料仓",
			"company": ctx.company,
			"parent_warehouse": f"All Warehouses - {ctx.abbr}",
			"customer": ctx.customer,
			"is_group": 0,
		},
	)
	bom = _ensure(
		ctx,
		"BOM",
		{"item": finished.name, "is_active": 1, "is_default": 1, "docstatus": 1},
		{
			"item": finished.name,
			"company": ctx.company,
			"quantity": 1,
			"is_active": 1,
			"is_default": 1,
			"items": [{"item_code": raw.name, "qty": 1, "source_warehouse": ctx.warehouse}],
		},
		submit=True,
	)
	if finished.default_bom != bom.name:
		finished.default_bom = bom.name
		finished.save(ignore_permissions=True)
	_ensure(
		ctx,
		"Subcontracting BOM",
		{
			"finished_good": finished.name,
			"service_item": service.name,
			"is_active": 1,
		},
		{
			"finished_good": finished.name,
			"finished_good_qty": 1,
			"finished_good_bom": bom.name,
			"service_item": service.name,
			"service_item_qty": 1,
			"is_active": 1,
		},
	)
	order = _ensure(
		ctx,
		"Sales Order",
		{"company": ctx.company, "po_no": SUBCONTRACTING_MARKER, "docstatus": 1},
		{
			"company": ctx.company,
			"customer": ctx.customer,
			"transaction_date": today(),
			"delivery_date": add_days(today(), 7),
			"order_type": "Sales",
			"is_subcontracted": 1,
			"po_no": SUBCONTRACTING_MARKER,
			"po_date": today(),
			"currency": ctx.currency,
			"selling_price_list": "Standard Selling",
			"items": [
				{
					"item_code": service.name,
					"fg_item": finished.name,
					"fg_item_qty": 2,
					"qty": 2,
					"rate": 8000,
					"delivery_date": add_days(today(), 7),
				}
			],
		},
		submit=True,
	)
	inward_name = frappe.db.get_value(
		"Subcontracting Inward Order",
		{"sales_order": order.name, "docstatus": ["!=", 2]},
		"name",
	)
	if not inward_name:
		from erpnext.selling.doctype.sales_order.mapper import make_subcontracting_inward_order

		inward = make_subcontracting_inward_order(order.name)
		inward.customer_warehouse = customer_warehouse.name
		inward.insert(ignore_permissions=True)
		inward.submit()
		_record(ctx, "Subcontracting Inward Order", inward.name, created=True)
	else:
		_record(ctx, "Subcontracting Inward Order", inward_name, created=False)
	return order


def _ensure_advance_payment(ctx: Any, order: Any) -> None:
	if not order or not _doctype_exists("Advance Payment Ledger Entry"):
		return
	existing = frappe.db.get_value(
		"Payment Entry Reference",
		{
			"reference_doctype": "Sales Order",
			"reference_name": order.name,
			"docstatus": 1,
		},
		"parent",
	)
	if existing:
		_record(ctx, "Payment Entry", existing, created=False)
		ledger = frappe.db.get_value(
			"Advance Payment Ledger Entry",
			{"voucher_type": "Payment Entry", "voucher_no": existing},
			"name",
		)
		if ledger:
			_record(ctx, "Advance Payment Ledger Entry", ledger, created=False)
		return

	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	amount = min(float(order.grand_total or 0) * 0.25, 4000)
	payment = get_payment_entry("Sales Order", order.name, party_amount=amount)
	cash_account = _account(ctx.company, account_type="Cash", root_type="Asset")
	if cash_account:
		payment.paid_to = cash_account
	payment.reference_no = "IONE-ADV-SCIO-001"
	payment.reference_date = today()
	payment.insert(ignore_permissions=True)
	payment.submit()
	_record(ctx, "Payment Entry", payment.name, created=True)
	ledger = frappe.db.get_value(
		"Advance Payment Ledger Entry",
		{"voucher_type": "Payment Entry", "voucher_no": payment.name},
		"name",
	)
	if ledger:
		_record(ctx, "Advance Payment Ledger Entry", ledger, created=True)


def seed_inventory_completion(ctx: Any) -> None:
	"""Create the remaining submitted inventory-related workflows."""
	_ensure_pos_workflow(ctx)
	order = _ensure_subcontracting_inward(ctx)
	_ensure_advance_payment(ctx, order)


def seed_asset_shift_allocation(ctx: Any) -> None:
	"""Create a submitted shift-based depreciation asset and allocation."""
	required = ("Asset Shift Factor", "Asset Shift Allocation", "Finance Book")
	if not all(_doctype_exists(doctype) for doctype in required):
		ctx.report.skipped.append("班次折旧：当前 ERPNext 版本未安装完整资产 DocType")
		return
	existing_asset = frappe.db.get_value(
		"Asset",
		{"asset_name": ASSET_SHIFT_MARKER, "docstatus": 1},
		"name",
	)
	existing_allocation = frappe.db.get_value(
		"Asset Shift Allocation",
		{"asset": existing_asset, "docstatus": 1},
		"name",
	) if existing_asset else None
	if existing_allocation:
		_record(ctx, "Asset Shift Allocation", existing_allocation, created=False)
		return

	default_shift = _first("Asset Shift Factor", {"default": 1})
	if not default_shift:
		shift = _ensure(
			ctx,
			"Asset Shift Factor",
			{"shift_name": "标准班次"},
			{"shift_name": "标准班次", "shift_factor": 1, "default": 1},
		)
		if not shift.default:
			shift.default = 1
			shift.save(ignore_permissions=True)
		default_shift = shift.name
	finance_book = _ensure(
		ctx,
		"Finance Book",
		{"finance_book_name": "I-ONE 管理财务账簿"},
		{"finance_book_name": "I-ONE 管理财务账簿"},
	)
	asset_item = frappe.db.get_value("Item", {"item_code": "IONE-DEMO-ASSET-001"}, "name")
	category = _first("Asset Category", {"asset_category_name": "I-ONE 业务样例设备"})
	category = category or _first("Asset Category")
	location = _ensure(
		ctx,
		"Location",
		{"location_name": "I-ONE 设备机房"},
		{"location_name": "I-ONE 设备机房", "is_group": 0},
	)
	asset = _ensure(
		ctx,
		"Asset",
		{"asset_name": ASSET_SHIFT_MARKER},
		{
			"asset_name": ASSET_SHIFT_MARKER,
			"item_code": asset_item,
			"asset_category": category,
			"company": ctx.company,
			"purchase_date": today(),
			"available_for_use_date": today(),
			"gross_purchase_amount": 120000,
			"net_purchase_amount": 120000,
			"location": location.name,
			"calculate_depreciation": 1,
			"is_existing_asset": 1,
			"finance_books": [
				{
					"finance_book": finance_book.name,
					"depreciation_method": "Straight Line",
					"frequency_of_depreciation": 1,
					"total_number_of_depreciations": 12,
					"depreciation_start_date": add_months(today(), 1),
					"shift_based": 1,
				}
			],
		},
		submit=True,
	)
	allocation = frappe.get_doc(
		{
			"doctype": "Asset Shift Allocation",
			"asset": asset.name,
			"finance_book": finance_book.name,
		}
	)
	allocation.insert(ignore_permissions=True)
	for row in allocation.depreciation_schedule:
		if not row.shift:
			row.shift = default_shift
	allocation.save(ignore_permissions=True)
	allocation.submit()
	_record(ctx, "Asset Shift Allocation", allocation.name, created=True)

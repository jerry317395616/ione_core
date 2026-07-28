from __future__ import annotations

# ruff: noqa: RUF001
from typing import Any

import frappe
from frappe.utils import add_days, add_months, now_datetime, nowtime, today

COMPANY = "美妍伊人医疗科技有限公司"
PR_MARKER = "IONE-STOCK-PR-001"


def _doctype_exists(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype))


def _label(doctype: str, name: str) -> str:
	return f"{doctype}: {name}"


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
		ctx.report.existing.append(_label(doctype, doc.name))
		return doc

	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.insert(ignore_permissions=True)
	if submit and doc.docstatus == 0:
		doc.submit()
	ctx.report.created.append(_label(doctype, doc.name))
	return doc


def _account(
	company: str,
	account_type: str | None = None,
	root_type: str = "Expense",
) -> str | None:
	filters: dict[str, Any] = {
		"company": company,
		"is_group": 0,
		"disabled": 0,
		"root_type": root_type,
	}
	if account_type:
		filters["account_type"] = account_type
	return frappe.db.get_value("Account", filters, "name", order_by="creation asc")


def _warehouse(ctx: Any, warehouse_name: str) -> str:
	name = frappe.db.get_value(
		"Warehouse",
		{"company": ctx.company, "warehouse_name": warehouse_name},
		"name",
	)
	if name:
		return name
	doc = _ensure(
		ctx,
		"Warehouse",
		{"company": ctx.company, "warehouse_name": warehouse_name},
		{
			"warehouse_name": warehouse_name,
			"company": ctx.company,
			"is_group": 0,
			"parent_warehouse": f"All Warehouses - {ctx.abbr}",
		},
	)
	return doc.name


def _ensure_item(
	ctx: Any,
	code: str,
	name: str,
	*,
	is_stock_item: int = 1,
	has_batch_no: int = 0,
	has_serial_no: int = 0,
	valuation_method: str = "",
) -> Any:
	base_item = frappe.get_cached_doc("Item", ctx.stock_item)
	values = {
		"item_code": code,
		"item_name": name,
		"item_group": base_item.item_group,
		"stock_uom": base_item.stock_uom,
		"is_stock_item": is_stock_item,
		"is_sales_item": 1,
		"is_purchase_item": is_stock_item,
		"has_batch_no": has_batch_no,
		"create_new_batch": has_batch_no,
		"has_serial_no": has_serial_no,
		"valuation_method": valuation_method,
	}
	if has_batch_no:
		values["batch_number_series"] = "IONE-BATCH-.YYYY.-.####"
	if has_serial_no:
		values["serial_no_series"] = "IONE-SN-.YYYY.-.####"
	return _ensure(ctx, "Item", {"item_code": code}, values)


def _ensure_item_price(ctx: Any, item: Any, price_list: str, rate: float) -> None:
	if not frappe.db.exists("Price List", price_list):
		return
	price_list_doc = frappe.get_cached_doc("Price List", price_list)
	_ensure(
		ctx,
		"Item Price",
		{"item_code": item.name, "price_list": price_list, "uom": item.stock_uom},
		{
			"item_code": item.name,
			"item_name": item.item_name,
			"uom": item.stock_uom,
			"price_list": price_list,
			"buying": price_list_doc.buying,
			"selling": price_list_doc.selling,
			"currency": ctx.currency,
			"price_list_rate": rate,
			"valid_from": today(),
		},
	)


def _ensure_inventory_masters(ctx: Any) -> dict[str, Any]:
	settings = frappe.get_single("Stock Settings")
	if settings.meta.has_field("enable_serial_and_batch_no_for_item"):
		settings.enable_serial_and_batch_no_for_item = 1
	if settings.meta.has_field("use_serial_batch_fields"):
		settings.use_serial_batch_fields = 1
	settings.save(ignore_permissions=True)

	parameter = _ensure(
		ctx,
		"Quality Inspection Parameter",
		{"parameter": "I-ONE 医疗物资包装完整性"},
		{
			"parameter": "I-ONE 医疗物资包装完整性",
			"description": "检查外包装、标签和封口是否完整。",
		},
	)
	template = _ensure(
		ctx,
		"Quality Inspection Template",
		{"quality_inspection_template_name": "I-ONE 医疗物资入库质检"},
		{
			"quality_inspection_template_name": "I-ONE 医疗物资入库质检",
			"item_quality_inspection_parameter": [
				{
					"specification": parameter.name,
					"value": "包装完整、标签清晰",
					"numeric": 0,
				}
			],
		},
	)
	batch_item = _ensure_item(
		ctx,
		"IONE-STOCK-BATCH-001",
		"I-ONE 批次检验试剂",
		has_batch_no=1,
	)
	if (
		not batch_item.inspection_required_before_purchase
		or batch_item.quality_inspection_template != template.name
	):
		batch_item.inspection_required_before_purchase = 1
		batch_item.quality_inspection_template = template.name
		batch_item.save(ignore_permissions=True)
	serial_item = _ensure_item(
		ctx,
		"IONE-STOCK-SERIAL-001",
		"I-ONE 医疗监护终端",
		has_serial_no=1,
	)
	repack_item = _ensure_item(
		ctx,
		"IONE-STOCK-REPACK-001",
		"I-ONE 防护物资组合箱",
		valuation_method="Standard Cost",
	)
	bundle_item = _ensure_item(
		ctx,
		"IONE-STOCK-KIT-001",
		"I-ONE 应急诊疗组合包",
		is_stock_item=0,
	)

	for item, buying_rate, selling_rate in (
		(batch_item, 120, 168),
		(serial_item, 6800, 9200),
		(repack_item, 35, 58),
	):
		_ensure_item_price(ctx, item, "Standard Buying", buying_rate)
		_ensure_item_price(ctx, item, "Standard Selling", selling_rate)
	_ensure_item_price(ctx, bundle_item, "Standard Selling", 88)

	_ensure(
		ctx,
		"Product Bundle",
		{"new_item_code": bundle_item.name, "disabled": 0},
		{
			"new_item_code": bundle_item.name,
			"description": "由常用库存物资组成的应急诊疗组合包。",
			"is_active": 1,
			"disabled": 0,
			"items": [
				{"item_code": ctx.stock_item, "qty": 2},
				{"item_code": batch_item.name, "qty": 1},
			],
		},
		submit=True,
	)
	manufacturer = _ensure(
		ctx,
		"Manufacturer",
		{"short_name": "I-ONE Medical"},
		{
			"short_name": "I-ONE Medical",
			"full_name": ctx.company,
			"country": "China",
		},
	)
	_ensure(
		ctx,
		"Item Manufacturer",
		{"item_code": serial_item.name, "manufacturer": manufacturer.name},
		{
			"item_code": serial_item.name,
			"manufacturer": manufacturer.name,
			"manufacturer_part_no": "IONE-MONITOR-001",
			"is_default": 1,
		},
	)

	existing_alternative = frappe.db.get_value(
		"Item Alternative",
		{"two_way": 1},
		"name",
		order_by="creation asc",
	)
	if existing_alternative:
		ctx.report.existing.append(_label("Item Alternative", existing_alternative))
	else:
		alternative = frappe.db.get_value(
			"Item",
			{"name": ["!=", ctx.stock_item], "disabled": 0, "is_stock_item": 1},
			"name",
			order_by="creation asc",
		)
	if not existing_alternative and alternative:
		for item_code in (ctx.stock_item, alternative):
			item = frappe.get_doc("Item", item_code)
			if not item.allow_alternative_item:
				item.allow_alternative_item = 1
				item.save(ignore_permissions=True)
		_ensure(
			ctx,
			"Item Alternative",
			{"item_code": ctx.stock_item, "alternative_item_code": alternative},
			{
				"item_code": ctx.stock_item,
				"alternative_item_code": alternative,
				"two_way": 1,
			},
		)

	_ensure(
		ctx,
		"Customs Tariff Number",
		{"tariff_number": "90183900"},
		{
			"tariff_number": "90183900",
			"description": "医用耗材及器械相关海关编码",
		},
	)
	expense_account = _account(ctx.company, root_type="Expense")
	cost_center = frappe.db.get_value(
		"Cost Center",
		{"company": ctx.company, "is_group": 0, "disabled": 0},
		"name",
		order_by="creation asc",
	)
	if expense_account and cost_center:
		_ensure(
			ctx,
			"Shipping Rule",
			{"label": "I-ONE 医疗物资配送规则", "company": ctx.company},
			{
				"label": "I-ONE 医疗物资配送规则",
				"shipping_rule_type": "Selling",
				"company": ctx.company,
				"account": expense_account,
				"cost_center": cost_center,
				"calculate_based_on": "Net Total",
				"conditions": [
					{"from_value": 0, "to_value": 1000, "shipping_amount": 80},
					{"from_value": 1000.01, "to_value": 5000, "shipping_amount": 150},
					{"from_value": 5000.01, "to_value": 99999999, "shipping_amount": 0},
				],
			},
		)
	_ensure(
		ctx,
		"Pricing Rule",
		{"title": "I-ONE 医用外科口罩批量折扣", "company": ctx.company},
		{
			"title": "I-ONE 医用外科口罩批量折扣",
			"apply_on": "Item Code",
			"price_or_product_discount": "Price",
			"selling": 1,
			"min_qty": 10,
			"valid_from": today(),
			"valid_upto": add_months(today(), 12),
			"company": ctx.company,
			"currency": ctx.currency,
			"rate_or_discount": "Discount Percentage",
			"discount_percentage": 5,
			"items": [{"item_code": ctx.stock_item}],
		},
	)
	_ensure(
		ctx,
		"Item Standard Cost",
		{"item_code": repack_item.name, "company": ctx.company},
		{
			"item_code": repack_item.name,
			"company": ctx.company,
			"standard_rate": 35,
			"effective_date": today(),
		},
	)
	variance_account = _account(ctx.company, "Stock Adjustment") or expense_account
	repack_item.reload()
	default = next((row for row in repack_item.item_defaults if row.company == ctx.company), None)
	if not default:
		default = repack_item.append("item_defaults", {"company": ctx.company})
	if variance_account and default.manufacturing_variance_account != variance_account:
		default.manufacturing_variance_account = variance_account
	if not repack_item.reorder_levels:
		repack_item.append(
			"reorder_levels",
			{
				"warehouse": ctx.warehouse,
				"warehouse_group": ctx.warehouse,
				"warehouse_reorder_level": 10,
				"warehouse_reorder_qty": 50,
				"material_request_type": "Purchase",
			},
		)
	repack_item.save(ignore_permissions=True)

	return {
		"batch_item": batch_item,
		"serial_item": serial_item,
		"repack_item": repack_item,
		"inspection_template": template,
		"expense_account": variance_account,
		"cost_center": cost_center,
	}


def _ensure_quality_inspection(ctx: Any, receipt: Any, batch_item: Any, template: Any) -> Any:
	row = next(item for item in receipt.items if item.item_code == batch_item.name)
	inspection = _ensure(
		ctx,
		"Quality Inspection",
		{
			"reference_type": "Purchase Receipt",
			"reference_name": receipt.name,
			"item_code": batch_item.name,
		},
		{
			"company": ctx.company,
			"report_date": receipt.posting_date,
			"inspection_type": "Incoming",
			"reference_type": "Purchase Receipt",
			"reference_name": receipt.name,
			"child_row_reference": row.name,
			"item_code": batch_item.name,
			"sample_size": 5,
			"quality_inspection_template": template.name,
			"manual_inspection": 1,
			"inspected_by": ctx.user,
			"remarks": "I-ONE 库存完整业务样例：批次入库质检合格",
			"readings": [
				{
					"specification": "I-ONE 医疗物资包装完整性",
					"numeric": 0,
					"manual_inspection": 1,
					"value": "包装完整、标签清晰",
					"reading_value": "包装完整、标签清晰",
					"status": "Accepted",
				}
			],
		},
		submit=True,
	)
	return inspection


def _ensure_purchase_flow(ctx: Any, masters: dict[str, Any]) -> Any:
	batch_item = masters["batch_item"]
	serial_item = masters["serial_item"]
	template = masters["inspection_template"]
	receipt_name = frappe.db.get_value(
		"Purchase Receipt",
		{"supplier_delivery_note": PR_MARKER, "docstatus": ["!=", 2]},
		"name",
	)
	if receipt_name:
		receipt = frappe.get_doc("Purchase Receipt", receipt_name)
		ctx.report.existing.append(_label("Purchase Receipt", receipt.name))
	else:
		receipt = frappe.get_doc(
			{
				"doctype": "Purchase Receipt",
				"company": ctx.company,
				"supplier": ctx.supplier,
				"posting_date": today(),
				"set_posting_time": 1,
				"set_warehouse": ctx.warehouse,
				"supplier_delivery_note": PR_MARKER,
				"remarks": "I-ONE 库存完整业务样例：批次与序列号入库",
				"items": [
					{
						"item_code": batch_item.name,
						"qty": 20,
						"rate": 120,
						"warehouse": ctx.warehouse,
					},
					{
						"item_code": serial_item.name,
						"qty": 3,
						"rate": 6800,
						"warehouse": ctx.warehouse,
					},
				],
			}
		)
		receipt.insert(ignore_permissions=True)
		inspection = _ensure_quality_inspection(ctx, receipt, batch_item, template)
		batch_row = next(item for item in receipt.items if item.item_code == batch_item.name)
		batch_row.quality_inspection = inspection.name
		receipt.save(ignore_permissions=True)
		receipt.submit()
		ctx.report.created.append(_label("Purchase Receipt", receipt.name))

	if not frappe.db.exists(
		"Quality Inspection",
		{
			"reference_type": "Purchase Receipt",
			"reference_name": receipt.name,
			"item_code": batch_item.name,
		},
	):
		_ensure_quality_inspection(ctx, receipt, batch_item, template)

	lcv_name = frappe.db.get_value(
		"Landed Cost Purchase Receipt",
		{"receipt_document": receipt.name},
		"parent",
	)
	if lcv_name:
		ctx.report.existing.append(_label("Landed Cost Voucher", lcv_name))
	else:
		valuation_account = _account(ctx.company, "Expenses Included In Valuation")
		if valuation_account:
			lcv = frappe.get_doc(
				{
					"doctype": "Landed Cost Voucher",
					"company": ctx.company,
					"posting_date": receipt.posting_date,
					"distribute_charges_based_on": "Amount",
					"purchase_receipts": [
						{
							"receipt_document_type": "Purchase Receipt",
							"receipt_document": receipt.name,
							"supplier": receipt.supplier,
							"posting_date": receipt.posting_date,
							"grand_total": receipt.base_grand_total,
						}
					],
					"taxes": [
						{
							"expense_account": valuation_account,
							"description": "I-ONE 冷链运输及保险费",
							"amount": 180,
						}
					],
				}
			)
			lcv.get_items_from_purchase_receipts()
			lcv.insert(ignore_permissions=True)
			lcv.submit()
			ctx.report.created.append(_label("Landed Cost Voucher", lcv.name))
	return receipt


def _ensure_stock_entry(
	ctx: Any,
	marker: str,
	purpose: str,
	items: list[dict[str, Any]],
	*,
	from_warehouse: str | None = None,
	to_warehouse: str | None = None,
	expense_account: str | None = None,
	cost_center: str | None = None,
) -> Any:
	values: dict[str, Any] = {
		"stock_entry_type": purpose,
		"purpose": purpose,
		"company": ctx.company,
		"posting_date": today(),
		"set_posting_time": 1,
		"remarks": marker,
		"items": items,
	}
	if from_warehouse:
		values["from_warehouse"] = from_warehouse
	if to_warehouse:
		values["to_warehouse"] = to_warehouse
	if expense_account:
		values["expense_account"] = expense_account
	if cost_center:
		values["cost_center"] = cost_center
	return _ensure(
		ctx,
		"Stock Entry",
		{"remarks": marker, "docstatus": ["!=", 2]},
		values,
		submit=True,
	)


def _ensure_warehouse_operations(ctx: Any, masters: dict[str, Any]) -> None:
	east = _warehouse(ctx, "华东分仓")
	north = _warehouse(ctx, "华北分仓")
	south = _warehouse(ctx, "华南分仓")
	expense_account = masters["expense_account"]
	cost_center = masters["cost_center"]

	_ensure_stock_entry(
		ctx,
		"I-ONE 库存完整业务样例：调拨至华东分仓",
		"Material Transfer",
		[
			{
				"item_code": ctx.stock_item,
				"qty": 5,
				"s_warehouse": ctx.warehouse,
				"t_warehouse": east,
			}
		],
		from_warehouse=ctx.warehouse,
		to_warehouse=east,
	)
	_ensure_stock_entry(
		ctx,
		"I-ONE 库存完整业务样例：调拨至华北分仓",
		"Material Transfer",
		[
			{
				"item_code": ctx.stock_item,
				"qty": 4,
				"s_warehouse": ctx.warehouse,
				"t_warehouse": north,
			}
		],
		from_warehouse=ctx.warehouse,
		to_warehouse=north,
	)
	_ensure_stock_entry(
		ctx,
		"I-ONE 库存完整业务样例：院感防护物资领用",
		"Material Issue",
		[
			{
				"item_code": ctx.stock_item,
				"qty": 2,
				"s_warehouse": ctx.warehouse,
				"expense_account": expense_account,
				"cost_center": cost_center,
			}
		],
		from_warehouse=ctx.warehouse,
		expense_account=expense_account,
		cost_center=cost_center,
	)
	_ensure_stock_entry(
		ctx,
		"I-ONE 库存完整业务样例：防护物资组合装箱",
		"Repack",
		[
			{"item_code": ctx.stock_item, "qty": 1, "s_warehouse": ctx.warehouse},
			{
				"item_code": masters["batch_item"].name,
				"qty": 1,
				"s_warehouse": ctx.warehouse,
			},
			{
				"item_code": masters["repack_item"].name,
				"qty": 1,
				"t_warehouse": ctx.warehouse,
				"basic_rate": 35,
				"valuation_rate": 35,
				"set_basic_rate_manually": 1,
			},
		],
	)
	for title, request_type, item_values in (
		(
			"I-ONE 华南分仓补货申请",
			"Material Transfer",
			{
				"item_code": ctx.stock_item,
				"qty": 5,
				"from_warehouse": ctx.warehouse,
				"warehouse": south,
			},
		),
		(
			"I-ONE 院感物资领用申请",
			"Material Issue",
			{
				"item_code": ctx.stock_item,
				"qty": 3,
				"warehouse": ctx.warehouse,
				"expense_account": expense_account,
				"cost_center": cost_center,
			},
		),
	):
		item_values["schedule_date"] = add_days(today(), 3)
		_ensure(
			ctx,
			"Material Request",
			{"title": title, "docstatus": ["!=", 2]},
			{
				"title": title,
				"company": ctx.company,
				"transaction_date": today(),
				"schedule_date": add_days(today(), 3),
				"material_request_type": request_type,
				"items": [item_values],
			},
			submit=True,
		)


def _ensure_sales_order(ctx: Any, marker: str, qty: float) -> Any:
	return _ensure(
		ctx,
		"Sales Order",
		{"po_no": marker, "docstatus": ["!=", 2]},
		{
			"company": ctx.company,
			"customer": ctx.customer,
			"transaction_date": today(),
			"delivery_date": add_days(today(), 3),
			"po_no": marker,
			"set_warehouse": ctx.warehouse,
			"items": [
				{
					"item_code": ctx.stock_item,
					"qty": qty,
					"rate": 50,
					"warehouse": ctx.warehouse,
					"delivery_date": add_days(today(), 3),
				}
			],
		},
		submit=True,
	)


def _ensure_sales_fulfilment(ctx: Any) -> None:
	from erpnext.selling.doctype.sales_order.mapper import create_pick_list, make_delivery_note
	from erpnext.stock.doctype.delivery_note.mapper import make_installation_note, make_packing_slip

	pick_order = _ensure_sales_order(ctx, "IONE-STOCK-PICK-001", 2)
	pick_name = frappe.db.get_value(
		"Pick List Item",
		{"sales_order": pick_order.name},
		"parent",
	)
	if pick_name:
		ctx.report.existing.append(_label("Pick List", pick_name))
	else:
		pick = create_pick_list(pick_order.name)
		pick.insert(ignore_permissions=True)
		pick.submit()
		ctx.report.created.append(_label("Pick List", pick.name))

	pack_order = _ensure_sales_order(ctx, "IONE-STOCK-PACK-001", 1)
	delivery_name = frappe.db.get_value(
		"Delivery Note Item",
		{"against_sales_order": pack_order.name, "docstatus": 0},
		"parent",
	)
	if delivery_name:
		delivery = frappe.get_doc("Delivery Note", delivery_name)
		ctx.report.existing.append(_label("Delivery Note", delivery.name))
	else:
		delivery = make_delivery_note(
			pack_order.name,
			kwargs={"for_reserved_stock": False, "skip_item_mapping": False},
		)
		delivery.posting_date = today()
		delivery.set_posting_time = 1
		delivery.remarks = "I-ONE 库存完整业务样例：待装箱销售出库"
		delivery.insert(ignore_permissions=True)
		ctx.report.created.append(_label("Delivery Note", delivery.name))
	packing_slip = frappe.db.get_value(
		"Packing Slip",
		{"delivery_note": delivery.name, "docstatus": ["!=", 2]},
		"name",
	)
	if packing_slip:
		ctx.report.existing.append(_label("Packing Slip", packing_slip))
	else:
		slip = make_packing_slip(delivery.name)
		slip.insert(ignore_permissions=True)
		slip.submit()
		ctx.report.created.append(_label("Packing Slip", slip.name))

	existing_installation = frappe.db.get_value(
		"Installation Note",
		{"docstatus": ["!=", 2], "company": ctx.company},
		"name",
		order_by="creation asc",
	)
	if existing_installation:
		ctx.report.existing.append(_label("Installation Note", existing_installation))
		return
	submitted_delivery = frappe.db.get_value(
		"Delivery Note",
		{"docstatus": 1, "company": ctx.company},
		"name",
		order_by="posting_date desc, creation desc",
	)
	if submitted_delivery:
		note = make_installation_note(submitted_delivery)
		if note.items:
			note.inst_date = today()
			note.inst_time = nowtime()
			note.remarks = "I-ONE 库存完整业务样例：交付安装验收"
			note.insert(ignore_permissions=True)
			note.submit()
			ctx.report.created.append(_label("Installation Note", note.name))


def _ensure_address(ctx: Any, customer: str, city: str, address_line: str) -> Any:
	title = f"{customer}配送地址"
	return _ensure(
		ctx,
		"Address",
		{"address_title": title, "city": city, "disabled": 0},
		{
			"address_title": title,
			"address_type": "Shipping",
			"address_line1": address_line,
			"city": city,
			"country": "China",
			"is_shipping_address": 1,
			"links": [{"link_doctype": "Customer", "link_name": customer, "link_title": customer}],
		},
	)


def _ensure_delivery_trip(ctx: Any) -> None:
	existing_trip = frappe.db.get_value(
		"Delivery Trip",
		{"docstatus": ["!=", 2], "company": ctx.company},
		"name",
		order_by="creation asc",
	)
	if existing_trip:
		ctx.report.existing.append(_label("Delivery Trip", existing_trip))
		return
	deliveries = frappe.get_all(
		"Delivery Note",
		filters={"docstatus": 1, "company": ctx.company},
		fields=["name", "customer", "grand_total"],
		order_by="posting_date desc, creation desc",
		limit=2,
	)
	if len(deliveries) < 2:
		ctx.report.skipped.append("Delivery Trip: 至少需要两张已提交的销售出库单")
		return
	existing = frappe.db.get_value(
		"Delivery Stop",
		{"delivery_note": deliveries[0].name},
		"parent",
	)
	if existing:
		ctx.report.existing.append(_label("Delivery Trip", existing))
		return
	addresses = [
		_ensure_address(ctx, deliveries[0].customer, "北京", "北京市朝阳区 I-ONE 配送中心"),
		_ensure_address(ctx, deliveries[1].customer, "上海", "上海市浦东新区 I-ONE 配送中心"),
	]
	vehicle = _ensure(
		ctx,
		"Vehicle",
		{"license_plate": "陕AIONE01"},
		{
			"license_plate": "陕AIONE01",
			"make": "上汽大通",
			"model": "冷链配送车",
			"company": ctx.company,
			"last_odometer": 12000,
			"fuel_type": "Diesel",
			"uom": "Litre",
		},
	)
	driver = _ensure(
		ctx,
		"Driver",
		{"full_name": "王配送"},
		{
			"full_name": "王配送",
			"status": "Active",
			"cell_number": "13800000009",
			"license_number": "IONE-DRIVER-001",
		},
	)
	trip = frappe.get_doc(
		{
			"doctype": "Delivery Trip",
			"company": ctx.company,
			"vehicle": vehicle.name,
			"driver": driver.name,
			"departure_time": add_days(now_datetime(), 1),
			"uom": "Litre",
			"delivery_stops": [
				{
					"customer": delivery.customer,
					"address": address.name,
					"delivery_note": delivery.name,
					"grand_total": delivery.grand_total,
				}
				for delivery, address in zip(deliveries, addresses, strict=True)
			],
		}
	)
	trip.insert(ignore_permissions=True)
	trip.submit()
	ctx.report.created.append(_label("Delivery Trip", trip.name))


def seed_inventory_workspace(ctx: Any) -> None:
	"""Fill every inventory workspace surface with linked, repeatable business records."""
	if ctx.company != COMPANY:
		ctx.report.skipped.append(f"库存完整业务样例：当前公司为 {ctx.company}，将按当前公司动态生成数据。")
	masters = _ensure_inventory_masters(ctx)
	_ensure_purchase_flow(ctx, masters)
	_ensure_warehouse_operations(ctx, masters)
	_ensure_sales_fulfilment(ctx)
	_ensure_delivery_trip(ctx)

"""Explicit, narrowly scoped metadata setup; no recipes, users, stock or orders."""
# ruff: noqa: RUF001

import json
from pathlib import Path

import frappe


def install_meal_planning():
	if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
		frappe.throw("需要系统管理员配置食谱业务。", frappe.PermissionError)
	for role in ("食谱编排员", "食谱审核员"):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()
	for target in ("meal_plan_meal", "meal_planning_week"):
		frappe.reload_doc("i_one_ai", "doctype", target, force=True)
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from ione_core.meal_population import STUDENT_BATCH_CUSTOM_FIELD

	definitions = json.loads((Path(__file__).parent / "meal_planning_fields.json").read_text())
	definitions += [
		STUDENT_BATCH_CUSTOM_FIELD,
		{
			"dt": "Production Plan",
			"fieldname": "custom_meal_week",
			"label": "食谱周计划",
			"fieldtype": "Link",
			"options": "Meal Planning Week",
			"insert_after": "custom_meal_batch",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"dt": "Production Plan",
			"fieldname": "custom_meal_headcount",
			"label": "计划供餐人数",
			"fieldtype": "Int",
			"insert_after": "custom_meal_week",
			"read_only": 1,
		},
		{
			"dt": "Item",
			"fieldname": "custom_meal_procurement_policy",
			"label": "食谱采购方式",
			"fieldtype": "Select",
			"options": "\n采购\n厨房用水\n厨房自产待配方",
			"insert_after": "is_purchase_item",
			"description": "食谱备料须明确采购方式；厨房用水不生成采购申请，自产配料需先补完整配方。",
		},
	]
	missing = {}
	for definition in definitions:
		item = dict(definition)
		dt = item.pop("dt")
		if not frappe.get_meta(dt).has_field(item["fieldname"]):
			missing.setdefault(dt, []).append(item)
	if missing:
		create_custom_fields(missing, update=False)
	for target in ("meal_weekly_plan", "meal_ingredient_requirements"):
		frappe.reload_doc("i_one_ai", "report", target, force=True)
	for source, translated in {
		"Meal Planning Week": "周食谱编排",
		"Meal Plan Meal": "食谱餐次",
		"Meal Weekly Plan": "周带量食谱",
		"Meal Ingredient Requirements": "食材备料需求",
		"Stock is based on the ledger and has not been represented as a physical stock count.": "库存依据为账面记录，尚未声明完成实物盘点。",
		"Some ingredients have no valid buying price. The request specifies quantity only; obtain quotations before placing orders.": "部分食材尚无有效采购价格。申请仅核定数量，请完成询价后再下单。",
		"Overdue or undated purchase orders are shown as unconfirmed and do not reduce this request.": "逾期或未注明到货日期的采购订单视为待确认，不抵扣本次采购需求。",
		"Overdue or undated material requests need review and do not reduce this request.": "逾期或未注明需求日期的采购申请需要核对，不抵扣本次采购需求。",
		"Meal week {0} has an unreconciled stock commitment. Reconcile it before requesting procurement for another week.": "周计划 {0} 的库存占用尚未完成核销，请核销后再生成另一周的采购需求。",
		"Stock, incoming supply, recipe, or procurement settings changed after review. Revise and review the meal week.": "库存、到货、配方或采购设置已发生变化，请修订并重新审核周食谱。",
	}.items():
		if not frappe.db.exists("Translation", {"language": "zh", "source_text": source}):
			frappe.get_doc(
				{
					"doctype": "Translation",
					"language": "zh",
					"source_text": source,
					"translated_text": translated,
				}
			).insert()
	for dt in ("Student", "Item", "Production Plan", "Meal Planning Week"):
		frappe.clear_cache(doctype=dt)
	return {
		"doctype": "Meal Planning Week",
		"created_fields": sum(map(len, missing.values())),
		"reports": ["Meal Weekly Plan", "Meal Ingredient Requirements"],
	}

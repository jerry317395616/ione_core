(() => {
	const esc = (value) => frappe.utils.escape_html(String(value ?? ""));
	const canOperate = () => ["System Manager", "Stock Manager", "Stock User", "膳食业务经办员"].some((role) => frappe.user.has_role(role));
	const number = (value) => {
		if (value === null || value === undefined || value === "") return "—";
		const result = Number(value);
		return Number.isFinite(result) ? result.toLocaleString("zh-CN", { maximumFractionDigits: 6 }) : String(value);
	};

	function saved(frm) {
		if (frm.is_new() || frm.is_dirty()) frappe.throw(__("请先保存实际供餐记录，再执行库存操作。"));
	}

	async function call(frm, button, method, args, callback) {
		if (frm.__meal_kitchen_busy) return;
		try {
			saved(frm);
			frm.__meal_kitchen_busy = true;
			button?.prop("disabled", true);
			const response = await frappe.call({ method, args, freeze: true, freeze_message: __("正在核对厨房执行记录…") });
			if (response.exc) throw new Error(__("操作失败，请查看服务器提示。"));
			await callback?.(response.message);
		} catch (error) {
			if (!error?._server_messages && !error?.responseJSON?._server_messages) {
				frappe.msgprint({ title: __("操作未完成"), indicator: "red", message: esc(error?.message || "请求失败，请检查连接和权限后重试。") });
			}
		} finally {
			frm.__meal_kitchen_busy = false;
			button?.prop("disabled", false);
		}
	}

	function renderLedger(frm, ledger) {
		const wrapper = frm.fields_dict.ledger_html?.$wrapper;
		if (!wrapper) return;
		const rows = Array.isArray(ledger?.rows) ? ledger.rows : [];
		const entries = Array.isArray(ledger?.stock_entries) ? ledger.stock_entries : [];
		const blockers = Array.isArray(ledger?.blockers) ? ledger.blockers : [];
		const cells = rows.map((row) => `<tr><td>${esc(row.item_name || row.item_code)}</td><td>${esc(row.stock_uom)}</td>${[
			"planned_qty", "issued_qty", "returned_qty", "consumed_qty", "loss_qty", "balance_qty",
		].map((key) => `<td class="text-right">${esc(number(row[key]))}</td>`).join("")}</tr>`).join("");
		const links = entries.map((entry) => {
			const status = { 0: "草稿，未计入余额", 1: "已提交", 2: "已取消" }[Number(entry.docstatus)] || "待核对";
			return `<li><a href="/desk/stock-entry/${encodeURIComponent(entry.name)}">${esc(entry.name)}</a> · ${esc(entry.action)} · ${esc(entry.posting_date)} · ${esc(status)}</li>`;
		}).join("");
		wrapper.html(`<p class="text-muted">下列数量均为食材库存单位。余额＝已提交领用－已提交退料－已提交耗用－已提交损耗；草稿不会改变余额。</p>
			${blockers.length ? `<div class="alert alert-warning"><ul style="margin-bottom:0">${blockers.map((value) => `<li>${esc(value)}</li>`).join("")}</ul></div>` : ""}
			${ledger?.has_drafts ? '<p class="text-warning">存在未处理的库存单草稿，请先核对再日结。</p>' : ""}
			<div style="overflow-x:auto"><table class="table table-bordered table-condensed"><thead><tr><th>食材</th><th>单位</th><th>计划用量</th><th>已领用</th><th>已退料</th><th>已耗用</th><th>已损耗</th><th>待核销余额</th></tr></thead>
			<tbody>${cells || '<tr><td colspan="8">暂无计划食材。</td></tr>'}</tbody></table></div>
			<p>${ledger?.can_close ? "已满足库存余额核对条件，可继续审核实际人数并提交日结。" : "请完成实际人数、库存单和余额核对后提交日结。"}</p>
			<strong>关联原生库存单</strong><ul>${links || "<li>尚无关联库存单。</li>"}</ul>`);
		frm.__meal_kitchen_ledger = ledger;
	}

	function openAction(frm, action, ledger, button) {
		if (frm.__meal_kitchen_dialog_open) return;
		const rows = Array.isArray(ledger?.rows) ? ledger.rows : [];
		if (!rows.length) return frappe.msgprint(__("本日没有可操作食材。"));
		frm.__meal_kitchen_dialog_open = true;
		const data = rows.map((row) => ({ item_code: row.item_code, item_name: row.item_name,
			stock_uom: row.stock_uom, balance_qty: row.balance_qty, qty: 0 }));
		const dialog = new frappe.ui.Dialog({
			title: __(`创建${action}库存单草稿`), size: "extra-large",
			fields: [
				{ fieldname: "notice", fieldtype: "HTML", options: `<p>${esc("请填写本次实际操作量，未填写或零数量的食材不会加入单据。所有数量均为该食材库存单位；生成后须在原生库存单中审核提交。")} ${esc(action === "领用" ? "领用将从原料仓调拨到厨房仓。" : "服务端将按本日真实领用来源分配，不能重复退料或核销。")}</p>` },
				{ fieldname: "items", fieldtype: "Table", label: __("本次操作食材"), in_place_edit: true, cannot_add_rows: true, cannot_delete_rows: true, data,
					fields: [
						{ fieldname: "item_code", fieldtype: "Link", label: __("食材"), options: "Item", read_only: 1, in_list_view: 1 },
						{ fieldname: "item_name", fieldtype: "Data", label: __("名称"), read_only: 1, in_list_view: 1 },
						{ fieldname: "stock_uom", fieldtype: "Data", label: __("库存单位"), read_only: 1, in_list_view: 1 },
						{ fieldname: "balance_qty", fieldtype: "Float", label: __("本日待核销余额"), read_only: 1, in_list_view: 1, precision: 6 },
						{ fieldname: "qty", fieldtype: "Float", label: __("本次操作量"), in_list_view: 1, non_negative: 1, precision: 6 },
					] },
				{ fieldname: "reason", fieldtype: "Small Text", label: __("操作说明"), reqd: action === "损耗" ? 1 : 0 },
			],
			onhide() { frm.__meal_kitchen_dialog_open = false; },
			primary_action_label: __("生成库存单草稿"),
			primary_action(values) {
				if (frm.__meal_kitchen_busy) return;
				const items = (values.items || []).filter((row) => Number(row.qty) > 0).map((row) => ({ item_code: row.item_code, qty: row.qty }));
				if (!items.length) return frappe.msgprint(__("请至少填写一项正数操作量。"));
				dialog.get_primary_btn().prop("disabled", true);
				call(frm, button, "ione_core.meal_kitchen.create_kitchen_stock_entry", {
					day_name: frm.doc.name, action, items, reason: values.reason || "",
				}, async (result) => {
					if (!result?.stock_entry) throw new Error(__("未返回库存单编号，请刷新流水核对。"));
					dialog.hide();
					await frm.reload_doc();
					frappe.set_route("Form", "Stock Entry", result.stock_entry);
				}).finally(() => dialog.get_primary_btn().prop("disabled", false));
			},
		});
		dialog.show();
	}

	frappe.ui.form.on("Meal Kitchen Day", {
		setup(frm) {
			frm.set_query("kitchen_warehouse", () => ({ filters: { company: frm.doc.company, is_group: 0, name: ["!=", frm.doc.source_warehouse] } }));
		},
		refresh(frm) {
			for (const name of ["meals", "items"]) {
				const grid = frm.fields_dict[name]?.grid;
				if (grid) { grid.cannot_add_rows = true; grid.cannot_delete_rows = true; }
			}
			frm.set_intro(__("逐餐记录并确认实际供餐人数；库存操作先生成草稿，经原生库存单提交后计入核销。审核日结前须处理草稿并核清领用余额。"), "blue");
			frm.fields_dict.ledger_html?.$wrapper.html(`<p class="text-muted">${esc("点击“刷新库存流水”查看已提交的领用、退料、耗用、损耗及待核销余额。")}</p>`);
			if (frm.is_new()) return;
			frm.add_custom_button(__("周食谱计划"), () => frappe.set_route("Form", "Meal Planning Week", frm.doc.meal_week));
			const refresh = frm.add_custom_button(__("刷新库存流水"), () => call(frm, refresh, "ione_core.meal_kitchen.get_kitchen_ledger", { day_name: frm.doc.name }, (ledger) => renderLedger(frm, ledger)));
			if (frm.doc.docstatus !== 0 || !canOperate()) return;
			for (const action of ["领用", "退料", "耗用", "损耗"]) {
				const button = frm.add_custom_button(__(`${action}草稿`), () => call(frm, button, "ione_core.meal_kitchen.get_kitchen_ledger", { day_name: frm.doc.name }, (ledger) => {
					renderLedger(frm, ledger);
					openAction(frm, action, ledger, button);
				}), __("库存操作"));
			}
		},
		before_submit(frm) {
			if ((frm.doc.meals || []).length !== 5 || frm.doc.meals.some((row) => !row.actual_confirmed)) {
				frappe.throw(__("请逐一确认五个餐次的实际供餐人数，零人停供也须明确确认。"));
			}
			if (frm.doc.meals.some((row) => (Number(row.actual_headcount) === 0 || Number(row.actual_headcount) !== Number(row.planned_headcount)) && !String(row.reason || "").trim())) {
				frappe.throw(__("实际人数与计划不同，或实际停供时，请填写该餐原因。"));
			}
		},
	});

	frappe.ui.form.on("Meal Kitchen Meal", {
		actual_headcount(frm, cdt, cdn) {
			frappe.model.set_value(cdt, cdn, "actual_confirmed", 0);
		},
	});
})();

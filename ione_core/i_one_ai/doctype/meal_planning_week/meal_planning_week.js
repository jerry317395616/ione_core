(() => {
	const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
	const hasRole = (...roles) => roles.some((role) => frappe.user.has_role(role));
	const canReviewStock = () => hasRole("System Manager", "Purchase Manager", "Stock Manager");
	const canCreateRequest = () => hasRole("System Manager", "Purchase Manager");
	const editable = (frm) => frm.doc.docstatus === 0 && !!frm.perm?.[0]?.write;
	const reportName = "Meal Weekly Plan";
	const statuses = {
		purchase: "需采购",
		kitchen_water: "厨房用水，不采购",
		needs_recipe: "待补配方",
		needs_policy: "待确认采购分类",
		needs_conversion: "待确认单位换算",
	};
	const displayQty = (value) => {
		if (value === undefined || value === null || value === "") return "—";
		const number = Number(value);
		return Number.isFinite(number)
			? number.toLocaleString("zh-CN", { maximumFractionDigits: 6 })
			: String(value);
	};
	const field = (value) => `<td>${escape(value || "—")}</td>`;
	const quantity = (value) => `<td class="text-right">${escape(displayQty(value))}</td>`;

	function ensureSaved(frm) {
		if (frm.is_new() || frm.is_dirty()) {
			frappe.throw(__("请先保存本周编排，再执行此操作。"));
		}
	}

	async function runAction(frm, button, method, args, onSuccess) {
		if (frm.__meal_action_running) return;
		try {
			ensureSaved(frm);
			frm.__meal_action_running = true;
			button?.prop("disabled", true);
			const response = await frappe.call({
				method,
				args,
				freeze: true,
				freeze_message: __("正在处理周食谱…"),
			});
			if (response.exc) throw new Error(__("操作未完成，请查看服务器提示。"));
			await onSuccess?.(response.message);
		} catch (error) {
			// Frappe displays detailed server validation messages; this covers network failures too.
			if (!error?._server_messages && !error?.responseJSON?._server_messages) {
				frappe.msgprint({
					title: __("操作未完成"),
					indicator: "red",
					message: escape(error?.message || __("请求失败，请检查连接并重试。")),
				});
			}
		} finally {
			frm.__meal_action_running = false;
			button?.prop("disabled", false);
		}
	}

	function actionButton(frm, label, method, args, onSuccess) {
		const button = frm.add_custom_button(__(label), () =>
			runAction(frm, button, method, args(), onSuccess)
		);
		return button;
	}

	function renderPreview(frm, preview) {
		const wrapper = frm.fields_dict.procurement_html?.$wrapper;
		if (!wrapper) return;
		const rows = Array.isArray(preview?.rows) ? preview.rows : [];
		const totals = preview?.totals || {};
		const warnings = Array.isArray(preview?.warnings) ? preview.warnings : [];
		const blockers = Array.isArray(preview?.blockers) ? preview.blockers : [];
		const notes = (values, indicator) => values.length
			? `<div class="alert alert-${indicator}"><ul style="margin-bottom:0">${values
				.map((value) => `<li>${escape(value)}</li>`).join("")}</ul></div>`
			: "";
		const body = rows.map((row) => {
			const status = statuses[row.status] || row.status || "待确认";
			const price = row.status === "kitchen_water"
				? "不适用"
				: row.price_status === "available" ? "有参考价格" : "待询价";
			const plan = row.production_plan
				? `<a href="/desk/production-plan/${encodeURIComponent(row.production_plan)}">${escape(row.production_plan)}</a>`
				: "—";
			return `<tr>${field(row.meal_date)}${field(row.meal_type)}${field(row.item_name || row.item_code)}
				${quantity(row.required_qty)}${quantity(row.allocated_stock_qty)}${quantity(row.expected_receipt_qty)}
				${quantity(row.already_requested_qty)}${field(row.stock_uom)}${quantity(row.purchase_qty)}
				${field(row.purchase_uom)}${field(status)}${field(price)}<td>${plan}</td></tr>`;
		}).join("");
		wrapper.html(`<div class="meal-procurement-preview">
			<p><strong>本周采购需求预览</strong> · 食材 ${escape(totals.ingredient_count ?? "—")} 种，
			需采购 ${escape(totals.purchase_row_count ?? "—")} 行，待询价 ${escape(totals.need_quote_count ?? "—")} 项。</p>
			<p class="text-muted">需求、库存、待到货和已申请数量使用库存单位；本次申请量使用采购单位。
			厨房用水不采购，骨汤按采购食材处理。价格未确认时仅核算数量。</p>
			${notes(warnings, "warning")}${notes(blockers, "danger")}
			<div style="overflow-x:auto"><table class="table table-bordered table-condensed" style="min-width:1400px">
			<thead><tr><th>使用日期</th><th>餐次</th><th>食材</th><th>需求量</th><th>分配库存</th>
			<th>分配待到货</th><th>已申请量</th><th>库存单位</th><th>本次申请量</th><th>采购单位</th>
			<th>处理状态</th><th>价格</th><th>生产计划</th></tr></thead>
			<tbody>${body || '<tr><td colspan="13">暂无食材需求。请先完成本周餐次编排和人数核算。</td></tr>'}</tbody>
			</table></div>
			<p class="text-muted small">账面库存${preview?.stock_reviewed ? "已核对" : "尚未核对"}；
			此处预览不会提交采购、收货或库存单据。</p></div>`);
		frm.__meal_procurement_preview = preview;
	}

	function resetPreview(frm, message) {
		frm.__meal_procurement_preview = null;
		frm.fields_dict.procurement_html?.$wrapper.html(
			`<p class="text-muted">${escape(message || "点击“采购需求预览”核对食材、库存、到货和采购分类。")}</p>`
		);
	}

	function editMealDishes(frm, button) {
		try {
			ensureSaved(frm);
		} catch (error) {
			return;
		}
		const meals = (frm.doc.meals || []).filter((row) => row.production_plan);
		if (!meals.length || frm.__meal_action_running) return;
		const label = (row) => `${row.meal_date}｜${row.meal_type}`;
		let loading = false;
		const dialog = new frappe.ui.Dialog({
			title: __("调整本餐菜品"),
			size: "large",
			fields: [
				{ fieldname: "meal", fieldtype: "Select", label: __("选择餐次"), reqd: 1,
					options: meals.map(label).join("\n"), default: label(meals[0]),
					onchange() { loadCurrentDishes(); } },
				{ fieldname: "notice", fieldtype: "HTML", options: `<p class="text-muted">${escape(
					"下表为本餐完整菜品配方列表。调整后将替换本餐菜品；生产数量由计划人数确定。"
				)}</p>` },
				{ fieldname: "boms", fieldtype: "Table", label: __("菜品配方"), reqd: 1,
					in_place_edit: true, fields: [
						{ fieldname: "bom", fieldtype: "Link", label: __("菜品配方"), options: "BOM",
							reqd: 1, in_list_view: 1, get_query: () => ({
								filters: { docstatus: 1, is_active: 1, company: frm.doc.company },
							}) },
					] },
			],
			primary_action_label: __("保存本餐菜品"),
			primary_action(values) {
				if (loading || frm.__meal_action_running) return;
				const row = meals.find((meal) => label(meal) === values.meal);
				const boms = (values.boms || []).map((entry) => entry.bom).filter(Boolean);
				if (!row || !boms.length) return frappe.msgprint(__("请至少选择一个有效菜品配方。"));
				dialog.get_primary_btn().prop("disabled", true);
				runAction(frm, button, "ione_core.meal_planning.update_meal_dishes", {
					week_name: frm.doc.name, meal_date: row.meal_date, meal_type: row.meal_type, boms,
				}, async () => {
					dialog.hide();
					await frm.reload_doc();
				}).finally(() => dialog.get_primary_btn().prop("disabled", false));
			},
		});
		async function loadCurrentDishes() {
			const selectedMeal = dialog.get_value("meal");
			const row = meals.find((meal) => label(meal) === selectedMeal);
			if (!row) return;
			loading = true;
			dialog.get_primary_btn().prop("disabled", true);
			try {
				const plan = await frappe.db.get_doc("Production Plan", row.production_plan);
				if (dialog.get_value("meal") !== selectedMeal) return;
				dialog.fields_dict.boms.df.data = (plan.po_items || []).map((item) => ({ bom: item.bom_no }));
				dialog.fields_dict.boms.grid.refresh();
			} catch (error) {
				if (dialog.get_value("meal") !== selectedMeal) return;
				dialog.fields_dict.boms.df.data = [];
				dialog.fields_dict.boms.grid.refresh();
				frappe.msgprint({ title: __("读取菜品失败"), indicator: "red",
					message: escape(error?.message || "无法读取本餐生产计划，请核对读取权限后重试。") });
			} finally {
				if (dialog.get_value("meal") === selectedMeal) {
					loading = false;
					dialog.get_primary_btn().prop("disabled", false);
				}
			}
		}
		dialog.show();
		loadCurrentDishes();
	}

	frappe.ui.form.on("Meal Planning Week", {
		setup(frm) {
			frm.set_query("raw_material_warehouse", () => ({
				filters: { company: frm.doc.company, is_group: 0 },
			}));
		},
		refresh(frm) {
			const grid = frm.fields_dict.meals?.grid;
			if (grid) {
				grid.cannot_add_rows = true;
				grid.cannot_delete_rows = true;
			}
			resetPreview(frm);
			frm.set_intro(__("供餐人数来自教育管理的在园学生名册，属于计划人数。请核对各餐停餐调整，再预览采购需求并核对账面库存。"), "blue");
			if (frm.is_new()) return;
			if (editable(frm) && !(frm.doc.meals || []).length) {
				actionButton(frm, "从上一周编排", "ione_core.meal_planning.initialize_week",
					() => ({ name: frm.doc.name }), async () => { await frm.reload_doc(); });
			}
			if (editable(frm) && (frm.doc.meals || []).length) {
				actionButton(frm, "刷新教育人数", "ione_core.meal_planning.refresh_population",
					() => ({ name: frm.doc.name }), async () => { await frm.reload_doc(); });
				const button = frm.add_custom_button(__("调整本餐菜品"), () => editMealDishes(frm, button));
			}
			frm.add_custom_button(__("周食谱表"), () => {
				frappe.set_route("query-report", reportName, { week_name: frm.doc.name });
			});
			if (frm.doc.docstatus === 2) return;
			actionButton(frm, "采购需求预览", "ione_core.meal_procurement.get_procurement_preview",
				() => ({ week_name: frm.doc.name }), (preview) => renderPreview(frm, preview));
			if (canReviewStock() && frm.doc.docstatus === 0 && (frm.doc.meals || []).length) {
				const button = frm.add_custom_button(__("核对账面库存"), () => {
					if (frm.__meal_action_running) return;
					frappe.confirm(
						__("请确认已核对采购预览中的账面库存、待到货及采购分类。此操作只记录账面核对，不表示完成实物盘点。"),
						() => runAction(frm, button, "ione_core.meal_planning.confirm_stock_review",
							{ name: frm.doc.name }, async () => { await frm.reload_doc(); })
					);
				});
			}
			if (frm.doc.docstatus === 1) {
				if (!frm.doc.material_request && canCreateRequest()) {
					actionButton(frm, "生成采购申请草稿", "ione_core.meal_procurement.create_material_request",
						() => ({ week_name: frm.doc.name }), async (result) => {
							await frm.reload_doc();
							const name = result?.material_request || frm.doc.material_request;
							if (name) frappe.set_route("Form", "Material Request", name);
						});
				}
				if (hasRole("System Manager", "食谱编排员")) {
					const button = frm.add_custom_button(__("复制到下一周"), () => {
						if (frm.__meal_action_running) return;
						frappe.prompt([
							{ fieldname: "target_week_start", fieldtype: "Date", label: __("新一周开始日期"),
								reqd: 1, default: frappe.datetime.add_days(frm.doc.week_start, 7) },
						], (values) => runAction(frm, button, "ione_core.meal_planning.copy_next_week",
							{ name: frm.doc.name, target_week_start: values.target_week_start }, (result) => {
								const name = typeof result === "string" ? result : result?.name;
								if (!name) throw new Error(__("服务器未返回新一周的编号，请刷新列表核对。"));
								frappe.set_route("Form", "Meal Planning Week", name);
							}), __("复制周食谱"), __("创建新周草稿"));
					});
				}
			}
		},
		before_submit(frm) {
			if (!frm.doc.stock_reviewed) frappe.throw(__("请先预览采购需求，并由授权人员核对账面库存。"));
		},
		week_start(frm) {
			if (frm.doc.week_start) frm.set_value("week_end", frappe.datetime.add_days(frm.doc.week_start, 4));
			resetPreview(frm, "日期已调整，请保存后重新核对人数和采购需求。");
		},
	});

	frappe.ui.form.on("Meal Plan Meal", {
		excluded_count(frm) {
			resetPreview(frm, "停餐人数已调整，请保存后重新预览采购需求。人数由服务器重新核算。");
		},
		adjustment_reason(frm) {
			resetPreview(frm, "停餐调整说明已修改，请保存后重新预览采购需求。");
		},
	});
})();

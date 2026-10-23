(() => {
	const reportName = "Meal Ingredient Requirements";
	const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
	const selectedWeek = (report) => report.get_filter_value("week_name") || report.data?.[0]?.week_name;

	frappe.query_reports[reportName] = {
		filters: [{ fieldname: "week_name", label: __("周食谱"), fieldtype: "Link", options: "Meal Planning Week" }],
		async onload(report) {
			report.page.set_title(__("食材需求明细（计划供餐）"));
			report.page.add_inner_button(__("周计划"), () => {
				const week = selectedWeek(report);
				if (!week) return frappe.msgprint(__("请先选择可查看的周食谱。"));
				frappe.set_route("Form", "Meal Planning Week", week);
			});
			report.page.add_inner_button(__("周食谱表"), () => {
				const week = selectedWeek(report);
				if (!week) return frappe.msgprint(__("请先选择可查看的周食谱。"));
				frappe.set_route("query-report", "Meal Weekly Plan", { week_name: week });
			});
			if (report.get_filter_value("week_name")) return;
			try {
				const weeks = await frappe.db.get_list("Meal Planning Week", {
					fields: ["name"], filters: { docstatus: ["<", 2] },
					order_by: "week_start desc, modified desc", limit: 1,
				});
				if (weeks[0]?.name && !report.get_filter_value("week_name")) {
					await report.set_filter_value("week_name", weeks[0].name);
				}
			} catch (error) {
				frappe.msgprint({ title: __("读取周食谱失败"), indicator: "red",
					message: escape(error?.message || "无法读取可查看的周食谱，请检查权限后重试。") });
			}
		},
		get_datatable_options(options) {
			return { ...options, inlineFilters: false };
		},
		after_datatable_render(datatable) {
			const report = frappe.query_report;
			if (report.report_name !== reportName || report.datatable !== datatable) return;
			const wrapper = $(datatable.wrapper);
			wrapper.children(".meal-live-detail-note").remove();
			$("<div class=\"meal-live-detail-note text-muted\" style=\"padding:8px 0 16px\">")
				.text("备料总量＝每名幼儿带量×该餐已保存的计划供餐人数。人数来自周计划，属于计划供餐人数，不代表当天实际出勤、实际进餐或摄入。各食材保留配方单位，克与毫升不混算；该表为食材需求，采购量还需核对库存和待到货。")
				.prependTo(wrapper);
		},
		formatter(value, row, column, data, default_formatter) {
			if (["per_child_qty", "headcount", "total_qty"].includes(column.fieldname)) {
				if (value === null || value === undefined || value === "") return "—";
				if (Number.isFinite(Number(value))) {
					return `<span style="display:block;text-align:right">${Number(value).toLocaleString("zh-CN", {
						maximumFractionDigits: column.fieldname === "headcount" ? 0 : 6,
					})}</span>`;
				}
			}
			if (["dish_name", "ingredient_name", "uom", "meal_type"].includes(column.fieldname)) return escape(value);
			return default_formatter(value, row, column, data);
		},
	};
})();

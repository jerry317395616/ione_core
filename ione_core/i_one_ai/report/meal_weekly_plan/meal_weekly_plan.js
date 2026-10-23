(() => {
	const reportName = "Meal Weekly Plan";
	const detailReport = "Meal Ingredient Requirements";
	const slots = ["早餐", "早点", "午餐", "午点", "晚餐"];
	const colors = ["#996900", "#26764a", "#295ca4", "#7950a6", "#a24d26"];
	const escape = (value) => frappe.utils.escape_html(String(value ?? ""));
	const selectedWeek = (report) => report.get_filter_value("week_name") || report.data?.[0]?.week_name;
	const detailUrl = (week) => `/desk/query-report/${encodeURIComponent(detailReport)}?${new URLSearchParams({ week_name: week })}`;

	function openWeek(report) {
		const week = selectedWeek(report);
		if (!week) return frappe.msgprint(__("请先选择可查看的周食谱。"));
		frappe.set_route("Form", "Meal Planning Week", week);
	}

	function buildTable(report) {
		const data = report.data || [];
		const week = selectedWeek(report) || "";
		const dates = Array.from({ length: 5 }, (_, i) =>
			data.find((row) => row[`date_${i}`])?.[`date_${i}`] || "—"
		);
		const headers = dates.map((date, i) =>
			`<th scope="col">星期${"一二三四五"[i]}<br><span class="meal-live-day-date">${escape(date)}</span></th>`
		).join("");
		const rows = slots.map((meal, slot) => ["菜品", "带量"].map((kind, index) => {
			const row = data.find((value) => value.meal_type === meal && value.row_kind === kind) || {};
			const cells = dates.map((_date, day) => {
				const value = row[`day_${day}`];
				const suspended = Boolean(Number(row[`suspended_${day}`] || row[`service_suspended_${day}`] || 0)) || value === "整餐停供";
				if (suspended) {
					const reason = row[`suspension_reason_${day}`];
					return kind === "菜品"
						? `<td><strong>${escape("整餐停供")}</strong><span class="meal-live-headcount">${escape(reason || "本餐不供餐，计划 0 人")}</span></td>`
						: `<td>${escape("不计入食材需求")}</td>`;
				}
				if (!value) return "<td>—</td>";
				const plan = row[`plan_${day}`];
				const href = kind === "菜品" && plan
					? `/desk/production-plan/${encodeURIComponent(plan)}`
					: detailUrl(week);
				let content;
				if (kind === "菜品") {
					const number = Number(row[`headcount_${day}`]);
					const count = row[`headcount_${day}`] !== null && row[`headcount_${day}`] !== undefined
						&& Number.isInteger(number) && number >= 0
						? `计划 ${number.toLocaleString("zh-CN")} 人` : "计划人数待核对";
					content = `${escape(value).replace(/、/g, "<br>")}<span class="meal-live-headcount">${escape(count)}</span>`;
				} else {
					content = String(value).split("；").map((item) =>
						`<span class="meal-live-ingredient">${escape(item)}</span>`
					).join(" ");
				}
				return `<td><a href="${escape(href)}">${content}</a></td>`;
			}).join("");
			return `<tr class="meal-live-${index ? "amount" : "dish"}">${index === 0
				? `<th rowspan="2" scope="rowgroup" style="color:${colors[slot]}">${escape(meal)}</th>` : ""}
				<th scope="row">${escape(kind)}</th>${cells}</tr>`;
		}).join("")).join("");
		return `<div class="meal-live-week-heading"><strong>每名幼儿带量食谱</strong>
			<span>${escape(week)} · 带量为每人用量，同餐相同食材已合并；人数为保存的计划供餐人数，不代表实际出勤。</span></div>
			<div style="overflow-x:auto"><table class="meal-live-week-table">
			<colgroup><col style="width:65px"><col style="width:60px">${"<col>".repeat(5)}</colgroup>
			<thead><tr><th>餐次</th><th>内容</th>${headers}</tr></thead><tbody>${rows}</tbody></table></div>
			<p class="text-muted small">点击菜品打开本餐有效生产计划；点击带量查看本周食材需求明细。整餐停供不计入食材需求。各食材保留配方单位，克与毫升不混算。</p>`;
	}

	frappe.query_reports[reportName] = {
		filters: [{ fieldname: "week_name", label: __("周食谱"), fieldtype: "Link", options: "Meal Planning Week" }],
		async onload(report) {
			report.page.set_title(__("周食谱（每名幼儿带量）"));
			report.page.add_inner_button(__("周计划"), () => openWeek(report));
			report.page.add_inner_button(__("食材需求明细"), () => {
				const week = selectedWeek(report);
				if (!week) return frappe.msgprint(__("请先选择可查看的周食谱。"));
				frappe.set_route("query-report", detailReport, { week_name: week });
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
			return { ...options, inlineFilters: false, cellHeight: 38 };
		},
		after_datatable_render(datatable) {
			const report = frappe.query_report;
			if (report.report_name !== reportName || report.datatable !== datatable) return;
			const wrapper = $(datatable.wrapper);
			wrapper.children(".meal-live-week-preview").remove();
			if (!report.data?.length) {
				$(datatable.datatableWrapper).removeClass("meal-live-native-data").removeAttr("aria-hidden");
				return;
			}
			$("<div class=\"meal-live-week-preview\">").html(buildTable(report)).appendTo(wrapper);
			$(datatable.datatableWrapper).addClass("meal-live-native-data").attr("aria-hidden", "true");
			let style = document.getElementById("meal-live-week-style");
			if (!style) {
				style = document.createElement("style");
				style.id = "meal-live-week-style";
				document.head.appendChild(style);
			}
			style.textContent = ".report-wrapper:has(>.meal-live-week-preview){position:relative}"
				+ ".report-wrapper:has(>.meal-live-week-preview)>.meal-live-native-data{position:absolute;inset-inline-start:0;top:0;width:100%;visibility:hidden;pointer-events:none}"
				+ ".meal-live-week-preview .meal-live-week-heading{display:flex;gap:20px;align-items:center;padding:12px 0 18px}"
				+ ".meal-live-week-preview .meal-live-week-heading span{color:var(--text-muted);font-size:12px}"
				+ ".meal-live-week-preview .meal-live-week-table{width:100%;min-width:980px;table-layout:fixed;border-collapse:collapse}"
				+ ".meal-live-week-preview .meal-live-week-table th,.meal-live-week-preview .meal-live-week-table td{border:1px solid var(--border-color);padding:10px;vertical-align:middle;line-height:1.8}"
				+ ".meal-live-week-preview .meal-live-week-table thead th{background:var(--subtle-fg);text-align:center}"
				+ ".meal-live-week-preview .meal-live-week-table tbody th{text-align:center;background:var(--subtle-accent)}"
				+ ".meal-live-week-preview .meal-live-day-date{font-weight:normal;font-size:12px;color:var(--text-muted)}"
				+ ".meal-live-week-preview .meal-live-headcount{display:block;font-size:12px;color:var(--text-muted);margin-top:5px}"
				+ ".meal-live-week-preview .meal-live-week-table a{display:block;color:var(--text-color);text-decoration:none}"
				+ ".meal-live-week-preview .meal-live-week-table a:hover{text-decoration:underline}"
				+ ".meal-live-week-preview .meal-live-ingredient{display:inline-block;white-space:nowrap;margin-right:6px}"
				+ ".meal-live-week-preview .meal-live-amount td{font-size:13px;color:var(--text-muted)}";
		},
		after_refresh(report) {
			if (!report.data?.length) report.$report?.find(".meal-live-week-preview").remove();
		},
	};
})();

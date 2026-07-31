(() => {
	"use strict";

	const PATCH_FLAG = "__ione_workspace_dock_i18n";
	const FALLBACK_LABELS = {
		Home: "首页",
		Accounting: "会计",
		Selling: "销售",
		Buying: "采购",
		Stock: "库存",
		Assets: "资产",
		Manufacturing: "制造",
		Projects: "项目",
		Support: "支持",
		CRM: "客户关系",
		"Human Resources": "人力资源",
		Payroll: "薪资",
		Quality: "质量",
		Subcontracting: "委外",
		Tools: "工具",
		Settings: "设置",
		Integrations: "集成",
		Users: "用户",
		Website: "网站",
		Email: "邮件",
		Build: "构建",
		Automation: "自动化",
		Printing: "打印",
	};

	function translate_label(label) {
		if (!label) {
			return label;
		}

		const translated = typeof __ === "function" ? __(label) : label;
		return translated !== label ? translated : FALLBACK_LABELS[label] || label;
	}

	function set_item_label(item, label) {
		if (!item || !label) {
			return;
		}

		item.setAttribute("title", label);
		item.setAttribute("aria-label", label);
		item.setAttribute("data-original-title", label);
	}

	function translate_existing_items() {
		document
			.querySelectorAll(".workspace-dock-items .workspace-dock-item")
			.forEach((item) => {
				const label =
					item.getAttribute("data-original-title") ||
					item.getAttribute("title") ||
					item.getAttribute("aria-label");
				set_item_label(item, translate_label(label));
			});
	}

	function install_workspace_dock_patch() {
		const prototype = window.frappe?.ui?.WorkspaceDock?.prototype;
		if (!prototype?.make_workspace_item) {
			return false;
		}

		if (prototype[PATCH_FLAG]) {
			return true;
		}

		const make_workspace_item = prototype.make_workspace_item;
		prototype.make_workspace_item = function (workspace) {
			const item = make_workspace_item.call(this, workspace);
			const label = workspace?.title || workspace?.label || workspace?.name;
			const translated = translate_label(label);

			if (item?.attr && translated) {
				item.attr({
					title: translated,
					"aria-label": translated,
					"data-original-title": translated,
				});
			}

			return item;
		};
		prototype[PATCH_FLAG] = true;
		return true;
	}

	function initialize() {
		let attempts = 0;
		const timer = window.setInterval(() => {
			attempts += 1;
			const installed = install_workspace_dock_patch();
			translate_existing_items();

			if (installed || attempts >= 100) {
				window.clearInterval(timer);
			}
		}, 100);

		const observer = new MutationObserver(translate_existing_items);
		observer.observe(document.body, { childList: true, subtree: true });
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", initialize, { once: true });
	} else {
		initialize();
	}
})();

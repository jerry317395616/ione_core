(() => {
	"use strict";

	const PATCH_FLAG = "__ione_workspace_dock_i18n";
	const FALLBACK_LABELS = {
		Home: "首页",
		Invoicing: "发票",
		Payments: "收付款",
		Accounting: "会计",
		Selling: "销售",
		Buying: "采购",
		"Financial Reports": "财务报表",
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
		"ERPNext Settings": "ERPNext 设置",
		"Reports & Masters": "报表与基础资料",
		Vacant: "空闲",
		"Previous sessions": "历史会话",
		"New chat": "新建会话",
		"Full screen": "全屏",
		"Close (Ctrl+I)": "关闭 (Ctrl+I)",
		"Ask about your data, draft records, or run a task.":
			"询问数据、起草单据或执行任务。",
		"Ask Flow…": "询问 Flow…",
		"Attach file": "附加文件",
		"All Assessment Groups": "全部考核组",
		"Education Settings": "教育管理设置",
		Actions: "操作",
		"Assign To": "分配给",
		"Clear Assignment": "清除分配",
		Delete: "删除",
		Message: "消息",
		Docstatus: "文档状态",
		Assign: "分配",
		Attachments: "附件",
		Share: "分享",
		Comments: "评论",
		"New Email": "新建邮件",
		Attach: "上传",
	};
	const UI_TEXT_FALLBACK_CONTAINERS = [
		".form-sidebar",
		".list-row-container",
		".modal",
		".dropdown-menu",
		".awesomplete",
		".page-actions",
	].join(",");
	const UI_TEXT_FALLBACK_SKIP_TAGS = new Set([
		"INPUT",
		"TEXTAREA",
		"SCRIPT",
		"STYLE",
	]);

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

		for (const attribute of ["title", "aria-label", "data-original-title"]) {
			if (item.getAttribute(attribute) !== label) {
				item.setAttribute(attribute, label);
			}
		}
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

	function translate_flow_panel() {
		const root = document.querySelector("#flow-root");
		if (!root) {
			return;
		}

		root
			.querySelectorAll("[title], [aria-label], [data-original-title], [placeholder]")
			.forEach((item) => {
				for (const attribute of [
					"title",
					"aria-label",
					"data-original-title",
					"placeholder",
				]) {
					const value = item.getAttribute(attribute);
					const translated = translate_label(value);
					if (translated && translated !== value) {
						item.setAttribute(attribute, translated);
					}
				}
			});

		root.querySelectorAll("*").forEach((item) => {
			for (const node of item.childNodes) {
				if (node.nodeType !== Node.TEXT_NODE) {
					continue;
				}
				const value = node.nodeValue || "";
				const trimmed = value.trim();
				const translated = FALLBACK_LABELS[trimmed];
				if (translated) {
					node.nodeValue = value.replace(trimmed, translated);
				}
			}
		});
	}

	function translate_workspace_content() {
		document
			.querySelectorAll(".ce-header .h4, .widget-control .es-badge")
			.forEach((item) => {
				const value = item.textContent || "";
				const trimmed = value.trim();
				const vacant = trimmed.match(/^(\d+)\s+Vacant$/);
				const translated = vacant
					? `${vacant[1]} 空闲`
					: FALLBACK_LABELS[trimmed];
				if (translated && translated !== trimmed) {
					item.textContent = value.replace(trimmed, translated);
				}
			});
	}

	function translate_ui_text_fallback() {
		document.querySelectorAll(UI_TEXT_FALLBACK_CONTAINERS).forEach((container) => {
			const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
			let node = walker.nextNode();
			while (node) {
				const parent = node.parentElement;
				if (
					parent &&
					!UI_TEXT_FALLBACK_SKIP_TAGS.has(parent.tagName) &&
					!parent.isContentEditable
				) {
					const value = node.nodeValue || "";
					const trimmed = value.trim();
					const translated = FALLBACK_LABELS[trimmed];
					if (translated && translated !== trimmed) {
						node.nodeValue = value.replace(trimmed, translated);
					}
				}
				node = walker.nextNode();
			}
		});
	}

	let translation_scheduled = false;
	function schedule_translation() {
		if (translation_scheduled) {
			return;
		}
		translation_scheduled = true;
		window.requestAnimationFrame(() => {
			translation_scheduled = false;
			translate_existing_items();
			translate_flow_panel();
			translate_workspace_content();
			translate_ui_text_fallback();
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
			translate_flow_panel();
			translate_workspace_content();
			translate_ui_text_fallback();

			if (installed || attempts >= 100) {
				window.clearInterval(timer);
			}
		}, 100);

		const observer = new MutationObserver(schedule_translation);
		observer.observe(document.body, { childList: true, subtree: true });

		for (const delay of [1000, 3000, 8000]) {
			window.setTimeout(() => {
				translate_flow_panel();
				translate_workspace_content();
				translate_ui_text_fallback();
			}, delay);
		}
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", initialize, { once: true });
	} else {
		initialize();
	}
})();

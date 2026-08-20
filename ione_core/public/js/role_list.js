const format_role_name = (value) => frappe.utils.escape_html(__(value || ""));

const current_role_settings = frappe.listview_settings["Role"] || {};

frappe.listview_settings["Role"] = {
	...current_role_settings,
	formatters: {
		...(current_role_settings.formatters || {}),
		name: format_role_name,
		role_name: format_role_name,
	},
};

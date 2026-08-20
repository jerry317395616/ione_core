const localize_role_sidebar_title = (frm) => {
	if (!frm.doc?.name || !frm.sidebar?.sidebar) {
		return;
	}

	const translated_name = __(frm.doc.name);
	frm.sidebar.sidebar
		.find(".sidebar-meta-details .form-title-text .text-medium")
		.text(translated_name);
};

frappe.ui.form.on("Role", {
	refresh(frm) {
		localize_role_sidebar_title(frm);
	},
});

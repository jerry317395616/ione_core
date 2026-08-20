const localize_user_timezone = (frm) => {
	const control = frm.fields_dict.time_zone;
	if (
		!frm.doc.time_zone ||
		!control?._data?.length ||
		control.$input?.is(":focus") ||
		typeof control.set_formatted_input !== "function"
	) {
		return;
	}

	control.set_formatted_input(frm.doc.time_zone);
};

frappe.ui.form.on("User", {
	refresh(frm) {
		localize_user_timezone(frm);
		frappe.after_ajax(() => localize_user_timezone(frm));
	},
});

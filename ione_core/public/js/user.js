const schedule_user_timezone_localization = (frm) => {
	window.clearTimeout(frm.__ione_core_timezone_i18n_timer);

	const apply = (attempt = 0) => {
		const control = frm.fields_dict.time_zone;
		const ready =
			frm.doc.time_zone &&
			control?._data?.length &&
			!control.$input?.is(":focus") &&
			typeof control.set_formatted_input === "function";

		if (ready) {
			control.set_formatted_input(frm.doc.time_zone);
			return;
		}

		if (attempt < 20) {
			frm.__ione_core_timezone_i18n_timer = window.setTimeout(
				() => apply(attempt + 1),
				250
			);
		}
	};

	apply();
};

frappe.ui.form.on("User", {
	refresh(frm) {
		schedule_user_timezone_localization(frm);
	},
	time_zone(frm) {
		schedule_user_timezone_localization(frm);
	},
});

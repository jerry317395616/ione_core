const schedule_user_timezone_localization = (frm) => {
	window.clearTimeout(frm.__ione_core_timezone_i18n_timer);

	const apply = (attempt = 0) => {
		const control = frm.fields_dict.time_zone;
		const timezone = frm.doc.time_zone || control?.value || control?.$input?.val();
		const ready =
			timezone &&
			!control.$input?.is(":focus") &&
			typeof control.set_data === "function" &&
			typeof control.set_formatted_input === "function";

		if (ready) {
			const timezones = frappe.all_timezones?.length ? frappe.all_timezones : [timezone];
			control.set_data(
				timezones.map((value) => ({
					label: __(value),
					value,
				}))
			);
			control.set_formatted_input(timezone);
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

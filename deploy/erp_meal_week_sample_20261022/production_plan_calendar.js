(() => {
  const showSampleWeek = calendar => {
    calendar.setOption('firstDay', 1);
    calendar.setOption('weekends', false);
    calendar.setOption('editable', false);
    calendar.setOption('eventStartEditable', false);
    calendar.setOption('eventDurationEditable', false);
    calendar.setOption('dayMaxEvents', false);
    calendar.setOption('dayMaxEventRows', false);
    calendar.setOption('eventOrder', 'title');
    calendar.changeView('dayGridWeek', '2026-10-12');
  };
  frappe.provide('frappe.views.calendar');
  frappe.views.calendar['Production Plan'] = {
    ...(frappe.views.calendar['Production Plan'] || {}),
    apply_to_custom_calendar_views: true,
    fields: ['docstatus', 'custom_meal_type', 'custom_meal_color'],
    get_css_class: d => d.custom_meal_color || 'blue'
  };
  const settings = frappe.listview_settings['Production Plan'] || {};
  const previousOnload = settings.onload;
  const previousRefresh = settings.refresh;
  frappe.listview_settings['Production Plan'] = {
    ...settings,
    onload(listview) {
      if (previousOnload) previousOnload(listview);
      listview.page.add_inner_button('周食谱表', () => frappe.set_route('query-report', '周食谱样例'));
      listview.page.add_inner_button('查看样例周', async () => {
        await frappe.set_route('List', 'Production Plan', 'Calendar', 'Weekly Meal Plan');
        let attempts = 0;
        const show = () => {
          const current = window.cur_list;
          const calendar = current && current.calendar && current.calendar.fullCalendar;
          if (calendar && frappe.get_route().slice(-1)[0] === 'Weekly Meal Plan') {
            showSampleWeek(calendar);
            return;
          }
          if (++attempts < 30) setTimeout(show, 200);
        };
        show();
      });
    },
    refresh(listview) {
      if (previousRefresh) previousRefresh.call(this, listview);
      const active = () => {
        const route = frappe.get_route();
        return route[0] === 'List' && route[1] === 'Production Plan' && route[2] === 'Calendar'
          && route[3] === 'Weekly Meal Plan' && window.cur_list === listview;
      };
      if (!active()) return;
      clearTimeout(listview.__meal_button_timer);
      let attempts = 0;
      const decorate = () => {
        if (!active()) return;
        const calendar = listview.calendar?.fullCalendar;
        if (!calendar) {
          if (++attempts < 50) listview.__meal_button_timer = setTimeout(decorate, 200);
          return;
        }
        listview.page.add_inner_button('周食谱表', () => frappe.set_route('query-report', '周食谱样例'));
        listview.page.add_inner_button('查看样例周', () => showSampleWeek(calendar));
        calendar.el.classList.add('erp-meal-week-calendar');
        if (!document.getElementById('erp-meal-week-calendar-style')) {
          const style = document.createElement('style');
          style.id = 'erp-meal-week-calendar-style';
          style.textContent = '.erp-meal-week-calendar .fc-event {opacity:1 !important} .erp-meal-week-calendar .fc-daygrid-event {white-space:normal; margin-top:8px; padding:8px 6px; line-height:1.6} .erp-meal-week-calendar .fc-event-title {white-space:normal; overflow-wrap:anywhere}';
          document.head.appendChild(style);
        }
        if (listview.__meal_initialized_calendar !== calendar) {
          listview.__meal_initialized_calendar = calendar;
          showSampleWeek(calendar);
        }
      };
      decorate();
    }
  };
})();

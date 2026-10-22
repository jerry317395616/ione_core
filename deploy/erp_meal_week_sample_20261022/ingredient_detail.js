frappe.query_reports['食材带量明细'] = {
  filters: [
    {fieldname:'week_start',label:'周开始日期',fieldtype:'Date',default:'2026-10-12',reqd:1},
    {fieldname:'meal_plan',label:'供餐计划',fieldtype:'Data',default:'全部',on_change(report) {
      const value = String(report.get_filter_value('meal_plan') || '').trim();
      if (!value) return report.set_filter_value('meal_plan', '全部');
      report.refresh();
    }},
    {fieldname:'headcount',label:'就餐人数（备料计算）',fieldtype:'Data',default:'未填写',on_change(report) {
      const value = String(report.get_filter_value('headcount') || '').trim();
      if (!value) return report.set_filter_value('headcount', '未填写');
      if (value !== '未填写' && !/^[1-9][0-9]*$/.test(value)) {
        frappe.msgprint('请输入正整数人数，留空时仅显示人均用量。');
        return report.set_filter_value('headcount', '未填写');
      }
      report.refresh();
    }}
  ],
  onload(report) {
    report.page.set_title('食材带量明细（每名幼儿）');
    report.page.add_inner_button('周食谱表', () => frappe.set_route('query-report', '周食谱样例'));
    report.page.add_inner_button('食谱日历', () => frappe.set_route('List','Production Plan','Calendar','Weekly Meal Plan'));
  },
  get_datatable_options(options) { return {...options, inlineFilters:false}; },
  after_datatable_render(datatable) {
    const report=frappe.query_report;
    if(report.report_name!=='食材带量明细' || report.datatable!==datatable) return;
    const wrapper=$(datatable.wrapper),count=String(report.get_filter_value('headcount') || '未填写');
    wrapper.children('.meal-detail-note').remove();
    const message=/^[1-9][0-9]*$/.test(count)
      ? `就餐人数：${count}人。备料总量＝人均用量×就餐人数，计量单位与该行食材一致。`
      : '当前仅显示每名幼儿的食材用量。在上方“就餐人数”中填写人数后，计算备料总量。';
    $('<div class="meal-detail-note text-muted" style="padding:8px 0 16px">').text(message).prependTo(wrapper);
  },
  formatter(value,row,column,data,default_formatter) {
    if (['headcount','total_qty'].includes(column.fieldname) && (value===null || value===undefined || value==='')) return '—';
    if (['per_child_qty','total_qty'].includes(column.fieldname) && Number.isFinite(Number(value))) {
      return `<span style="display:block;text-align:right">${Number(value).toLocaleString('zh-CN',{maximumFractionDigits:6})}</span>`;
    }
    return default_formatter(value,row,column,data);
  }
};

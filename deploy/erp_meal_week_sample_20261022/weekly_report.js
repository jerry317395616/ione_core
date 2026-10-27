(() => {
  const slots = ['早餐','早点','午餐','午点','晚餐'];
  const colors = ['#996900','#26764a','#295ca4','#7950a6','#a24d26'];
  const escape = value => frappe.utils.escape_html(String(value ?? ''));
  const buildTable = report => {
    const start = report.get_filter_value('week_start');
    const dates = Array.from({length:5},(_,i)=>frappe.datetime.add_days(start,i));
    const headers = dates.map((date,i)=>`<th scope="col">星期${'一二三四五'[i]}<br><span class="meal-day-date">${escape(date)}</span></th>`).join('');
    const rows = slots.map((meal,slot)=>['菜品','带量'].map((kind,index)=>{
      const data = (report.data || []).find(row=>row.meal_type===meal && row.row_kind===kind) || {};
      const cells = dates.map((date,day)=>{
        const value = data[`day_${day}`];
        const plan = `MEAL-DEMO-${date.replace(/-/g,'')}-${String(slot+1).padStart(2,'0')}`;
        const query = new URLSearchParams({week_start:start,meal_plan:plan,headcount:'未填写'});
        const text = kind==='菜品'
          ? escape(value || '—').replace(/、/g,'<br>')
          : String(value || '—').split('；').map(item=>`<span class="meal-ingredient">${escape(item)}</span>`).join(' ');
        return `<td>${value ? `<a href="/desk/query-report/${encodeURIComponent('食材带量明细')}?${query}">${text}</a>` : '—'}</td>`;
      }).join('');
      return `<tr class="meal-${index ? 'amount' : 'dish'}">${index===0 ? `<th rowspan="2" scope="rowgroup" style="color:${colors[slot]}">${meal}</th>` : ''}<th scope="row">${kind}</th>${cells}</tr>`;
    }).join('')).join('');
    return `<div class="meal-week-heading"><strong>每名幼儿带量食谱</strong><span>带量为每人用量，同餐相同食材已合并；点击单元格查看明细。</span></div><div style="overflow-x:auto"><table class="meal-week-table"><colgroup><col style="width:65px"><col style="width:60px">${'<col>'.repeat(5)}</colgroup><thead><tr><th>餐次</th><th>内容</th>${headers}</tr></thead><tbody>${rows}</tbody></table></div>`;
  };
  frappe.query_reports['周食谱样例'] = {
    filters:[{fieldname:'week_start',label:'周开始日期',fieldtype:'Date',default:'2026-10-12',reqd:1}],
    onload(report) {
      report.page.set_title('周食谱样例（每名幼儿带量）');
      report.page.add_inner_button('食谱日历',()=>frappe.set_route('List','Production Plan','Calendar','Weekly Meal Plan'));
      report.page.add_inner_button('食材带量明细',()=>frappe.set_route('query-report','食材带量明细',{
        week_start:report.get_filter_value('week_start'),meal_plan:'全部',headcount:'未填写'
      }));
    },
    get_datatable_options(options) { return {...options,inlineFilters:false,cellHeight:38}; },
    after_datatable_render(datatable) {
      const report = frappe.query_report;
      if (report.report_name!=='周食谱样例' || report.datatable!==datatable) return;
      const wrapper = $(datatable.wrapper);
      wrapper.children('.erp-meal-preview').remove();
      $('<div class="erp-meal-preview">').html(buildTable(report)).appendTo(wrapper);
      $(datatable.datatableWrapper).addClass('erp-meal-native-data').attr('aria-hidden','true');
      let style = document.getElementById('erp-meal-ingredient-report-style');
      if (!style) {style=document.createElement('style');style.id='erp-meal-ingredient-report-style';document.head.appendChild(style);}
      style.textContent = '.report-wrapper:has(>.erp-meal-preview){position:relative}.report-wrapper:has(>.erp-meal-preview)>.erp-meal-native-data{position:absolute;inset-inline-start:0;top:0;width:100%;visibility:hidden;pointer-events:none}.erp-meal-preview .meal-week-heading{display:flex;gap:20px;align-items:center;padding:12px 0 18px}.erp-meal-preview .meal-week-heading span{color:var(--text-muted);font-size:12px}.erp-meal-preview .meal-week-table{width:100%;min-width:980px;table-layout:fixed;border-collapse:collapse}.erp-meal-preview .meal-week-table th,.erp-meal-preview .meal-week-table td{border:1px solid var(--border-color);padding:10px;vertical-align:middle;line-height:1.8}.erp-meal-preview .meal-week-table thead th{background:var(--subtle-fg);text-align:center}.erp-meal-preview .meal-week-table tbody th{text-align:center;background:var(--subtle-accent)}.erp-meal-preview .meal-day-date{font-weight:normal;font-size:12px;color:var(--text-muted)}.erp-meal-preview .meal-week-table a{display:block;color:var(--text-color);text-decoration:none}.erp-meal-preview .meal-week-table a:hover{text-decoration:underline}.erp-meal-preview .meal-ingredient{display:inline-block;white-space:nowrap;margin-right:6px}.erp-meal-preview .meal-amount td{font-size:13px;color:var(--text-muted)}';
    },
    after_refresh(report) {
      if (!report.data?.length) report.$report?.children('.erp-meal-preview').remove();
    }
  };
})();

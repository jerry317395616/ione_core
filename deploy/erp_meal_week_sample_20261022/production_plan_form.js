(() => {
  const mealOrder = {早餐:1,早点:2,午餐:3,午点:4,晚餐:5};
  const palette = {早餐:'#e9b949',早点:'#66b88a',午餐:'#5b8bd9',午点:'#a887d5',晚餐:'#e58b64'};
  const escape = value => frappe.utils.escape_html(String(value ?? ''));
  frappe.ui.form.on('Production Plan', {
    refresh(frm) {
      if (!frm.doc.custom_is_meal_plan || frm.doc.custom_meal_batch !== 'MEAL-DEMO-20261012') return;
      frm.set_intro('食谱按每名幼儿的食材用量展示；备料总量在明细中填写就餐人数后计算。', 'blue');
      frm.add_custom_button('周食谱表',()=>frappe.set_route('query-report','周食谱样例'));
      frm.add_custom_button('食谱日历',()=>frappe.set_route('List','Production Plan','Calendar','Weekly Meal Plan'));
      frm.add_custom_button('食材带量明细',()=>frappe.set_route('query-report','食材带量明细',{
        week_start:'2026-10-12',meal_plan:frm.doc.name,headcount:'未填写'
      }));
      const wrapper = frm.fields_dict.custom_meal_ingredients_html?.$wrapper;
      if (!wrapper) return;
      wrapper.html('<div class="text-muted">正在读取人均食材用量…</div>');
      const name = frm.doc.name;
      frappe.call({method:'frappe.desk.query_report.run',args:{report_name:'食材带量明细',
        filters:{week_start:'2026-10-12',meal_plan:name,headcount:'未填写'},ignore_prepared_report:true}
      }).then(response=>{
        if (frm.doc.name !== name) return;
        const rows = response.message?.result || [];
        const ingredients = new Map();
        for (const row of rows) {
          const key = JSON.stringify([row.ingredient_name,row.uom]);
          const entry = ingredients.get(key) || {name:row.ingredient_name,uom:row.uom,qty:0};
          entry.qty += Number(row.per_child_qty); ingredients.set(key,entry);
        }
        const items = [...ingredients.values()].map(row=>`<tr><td>${escape(row.name)}</td><td style="text-align:right">${Number(row.qty.toFixed(6)).toLocaleString('zh-CN',{maximumFractionDigits:6})}</td><td>${escape(row.uom)}/人</td></tr>`).join('');
        wrapper.html(`<div class="meal-ingredient-summary"><strong>本餐食材带量（每名幼儿）</strong><table class="table table-bordered" style="margin-top:10px"><thead><tr><th>食材</th><th style="text-align:right">人均用量</th><th>单位</th></tr></thead><tbody>${items || '<tr><td colspan="3">未找到配方食材</td></tr>'}</tbody></table><p class="text-muted small">备料参考：此草稿保留了最初的 100 人演示参数，不代表实际人数。上方带量读取人均配方，不使用该演示人数。</p></div>`);
      }).catch(()=>{
        if (frm.doc.name === name) wrapper.html('<div class="text-danger">食材用量读取失败，请刷新页面或打开“食材带量明细”。</div>');
      });
    },
    async validate(frm) {
      if (!frm.doc.custom_is_meal_plan) return;
      if (!frm.doc.custom_meal_date || !frm.doc.custom_meal_type) frappe.throw('请填写供餐日期和餐次。');
      const names = (frm.doc.po_items || []).map(row=>row.custom_dish_name || frappe.utils.strip_html(row.description || '') || row.item_code);
      await frm.set_value('custom_meal_end_date',frm.doc.custom_meal_date);
      await frm.set_value('custom_meal_menu',names.join('、'));
      await frm.set_value('custom_meal_title',`${String(mealOrder[frm.doc.custom_meal_type] || 0).padStart(2,'0')} ${frm.doc.custom_meal_type}｜${names.join('、')}`.slice(0,140));
      await frm.set_value('custom_meal_color',palette[frm.doc.custom_meal_type] || '#5b8bd9');
    }
  });
})();

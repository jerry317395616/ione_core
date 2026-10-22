SELECT pp.custom_meal_date AS meal_date,
       pp.custom_meal_type AS meal_type,
       dish.item_name AS dish_name,
       ingredient.item_name AS ingredient_name,
       bi.qty / NULLIF(b.quantity, 0) AS per_child_qty,
       bi.uom AS uom,
       parameters.headcount,
       CASE WHEN parameters.headcount IS NOT NULL
            THEN (bi.qty / NULLIF(b.quantity, 0)) * parameters.headcount
            ELSE NULL
       END AS total_qty,
       pp.name AS plan_name,
       b.name AS bom_no
FROM `tabProduction Plan` pp
JOIN `tabProduction Plan Item` pi
  ON pi.parent = pp.name AND pi.parenttype = 'Production Plan'
JOIN `tabItem` dish ON dish.name = pi.item_code
JOIN `tabBOM` b ON b.name = pi.bom_no
JOIN `tabBOM Item` bi ON bi.parent = b.name AND bi.parenttype = 'BOM'
JOIN `tabItem` ingredient ON ingredient.name = bi.item_code
CROSS JOIN (
    SELECT CASE
             WHEN TRIM(CAST(%(headcount)s AS CHAR)) REGEXP '^[1-9][0-9]*$'
             THEN CAST(%(headcount)s AS UNSIGNED)
             ELSE NULL
           END AS headcount
) AS parameters
WHERE pp.custom_meal_batch = 'MEAL-DEMO-20261012'
  AND pp.docstatus < 2
  AND pp.custom_meal_date BETWEEN %(week_start)s
                              AND DATE_ADD(%(week_start)s, INTERVAL 4 DAY)
  AND (COALESCE(%(meal_plan)s, '') IN ('', '全部') OR pp.name = %(meal_plan)s)
ORDER BY pp.custom_meal_date,
         FIELD(pp.custom_meal_type, '早餐', '早点', '午餐', '午点', '晚餐'),
         pp.name, pi.idx, bi.idx

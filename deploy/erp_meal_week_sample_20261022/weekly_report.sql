SELECT meal_type, row_kind, day_0, day_1, day_2, day_3, day_4
FROM (
WITH meal_slots AS (
    SELECT 1 AS slot_order, '早餐' AS meal_type
    UNION ALL SELECT 2, '早点'
    UNION ALL SELECT 3, '午餐'
    UNION ALL SELECT 4, '午点'
    UNION ALL SELECT 5, '晚餐'
), row_kinds AS (
    SELECT 1 AS row_order, '菜品' AS row_kind
    UNION ALL SELECT 2, '带量'
), plan_dishes AS (
    SELECT pp.name AS plan_name,
           pp.custom_meal_date AS meal_date,
           pp.custom_meal_type AS meal_type,
           pi.idx AS dish_order,
           it.item_name AS dish_name,
           pi.bom_no
    FROM `tabProduction Plan` pp
    JOIN `tabProduction Plan Item` pi
      ON pi.parent = pp.name AND pi.parenttype = 'Production Plan'
    JOIN `tabItem` it ON it.name = pi.item_code
    WHERE pp.custom_meal_batch = 'MEAL-DEMO-20261012'
      AND pp.docstatus < 2
      AND pp.custom_meal_date BETWEEN %(week_start)s
                                  AND DATE_ADD(%(week_start)s, INTERVAL 4 DAY)
), dish_cells AS (
    SELECT meal_type, meal_date, '菜品' AS row_kind,
           GROUP_CONCAT(dish_name ORDER BY plan_name, dish_order SEPARATOR '、') AS cell_text
    FROM plan_dishes
    GROUP BY meal_type, meal_date
), ingredient_quantities AS (
    SELECT pd.meal_type, pd.meal_date,
           ingredient.item_name AS ingredient_name,
           bi.uom,
           SUM(bi.qty / NULLIF(b.quantity, 0)) AS per_child_qty,
           MIN(pd.dish_order * 10000 + bi.idx) AS ingredient_order
    FROM plan_dishes pd
    JOIN `tabBOM` b ON b.name = pd.bom_no
    JOIN `tabBOM Item` bi ON bi.parent = b.name AND bi.parenttype = 'BOM'
    JOIN `tabItem` ingredient ON ingredient.name = bi.item_code
    GROUP BY pd.meal_type, pd.meal_date, ingredient.item_name, bi.uom
), ingredient_cells AS (
    SELECT meal_type, meal_date, '带量' AS row_kind,
           GROUP_CONCAT(
               CONCAT(
                   ingredient_name,
                   TRIM(TRAILING '.' FROM TRIM(TRAILING '0' FROM
                       CAST(CAST(per_child_qty AS DECIMAL(24, 9)) AS CHAR))),
                   uom
               )
               ORDER BY ingredient_order, ingredient_name, uom SEPARATOR '；'
           ) AS cell_text
    FROM ingredient_quantities
    GROUP BY meal_type, meal_date
), cells AS (
    SELECT * FROM dish_cells
    UNION ALL
    SELECT * FROM ingredient_cells
)
SELECT ms.meal_type, rk.row_kind,
       MAX(CASE WHEN DATEDIFF(c.meal_date, %(week_start)s) = 0 THEN c.cell_text END) AS day_0,
       MAX(CASE WHEN DATEDIFF(c.meal_date, %(week_start)s) = 1 THEN c.cell_text END) AS day_1,
       MAX(CASE WHEN DATEDIFF(c.meal_date, %(week_start)s) = 2 THEN c.cell_text END) AS day_2,
       MAX(CASE WHEN DATEDIFF(c.meal_date, %(week_start)s) = 3 THEN c.cell_text END) AS day_3,
       MAX(CASE WHEN DATEDIFF(c.meal_date, %(week_start)s) = 4 THEN c.cell_text END) AS day_4
FROM meal_slots ms
CROSS JOIN row_kinds rk
LEFT JOIN cells c ON c.meal_type = ms.meal_type AND c.row_kind = rk.row_kind
GROUP BY ms.slot_order, ms.meal_type, rk.row_order, rk.row_kind
) AS weekly_result
ORDER BY FIELD(meal_type, '早餐', '早点', '午餐', '午点', '晚餐'),
         FIELD(row_kind, '菜品', '带量')

# ERP 周食谱试点配置归档（2026-10-22）

本目录保存已部署试点的配置源码，用于审查和追溯。它不是完整食谱产品，也不是可自动恢复业务数据的安装包。没有安装程序、迁移补丁或自动执行钩子；将这些文件放入仓库不会修改任何站点。

试点复用 ERPNext 的 Item、BOM 和 Production Plan。每个供餐日期、餐次对应一张草稿生产计划；菜品是物料，配方是 BOM，周报和日历读取这些原生记录。页面展示每名幼儿的食材带量，填写正整数就餐人数后，明细报告计算备料参考总量。

## 归档内容

| 文件 | 站点中的配置对象 |
| --- | --- |
| `configuration.json` | 白名单内的 Custom Field、Calendar View、Report 和 Client Script 定义；SQL/JS 由下列独立文件保存 |
| `production_plan_form.js` | Client Script：`ERP Meal Plan Form`，Production Plan 的 Form 视图 |
| `production_plan_calendar.js` | Client Script：`ERP Meal Plan Calendar`，Production Plan 的 List 视图 |
| `weekly_report.sql`、`weekly_report.js` | Query Report：`周食谱样例` |
| `ingredient_detail.sql`、`ingredient_detail.js` | Query Report：`食材带量明细` |
| `permissions-policy.json` | 试点权限设计记录；没有账号绑定和业务记录授权清单，不是权限导入文件 |

SQL/JS 保留已部署实现，未将试点限制改成通用能力。配置定义排除用户、审计元数据及无关站点配置。若人工复核这些定义，须同时阅读对应的 SQL/JS；只导入元数据并不能恢复页面行为。

## 明确保留的试点限制

- 两份 SQL 固定筛选样例批次 `MEAL-DEMO-20261012`，默认显示 2026-10-12 至 2026-10-16；日历首次进入也定位该周。
- 周报固定五天、五个餐次：早餐、早点、午餐、午点、晚餐。周开始日期按星期一使用；界面没有强制校验星期一，也没有节假日排餐逻辑。
- 周报明细链接按 `MEAL-DEMO-YYYYMMDD-餐次序号` 拼接计划编号，不能直接用于其他命名规则。
- 配方计算读取当前计划关联 BOM 的直接食材明细，按 `BOM Item.qty / BOM.quantity` 得到人均用量并保留该行单位。同餐同名、同单位食材合并显示；没有多层 BOM 展开、单位换算、净料率、营养分析或过敏原规则。
- 原草稿计划保留最初每道菜 100 份的演示数量。人均带量和按人数计算的报告不使用这项演示数量；报告筛选器中的人数不会回写计划、BOM 或库存。
- `headcount` 和 `meal_plan` 使用 `未填写`、`全部` 作为非空筛选值，避免当前 Query Report 将空值省略。明细 SQL 只接受正整数人数，其他值不计算总量。直接调用报告接口仍需传入全部 SQL 参数。
- 表单标题、日期、颜色同步是 Client Script 行为，不是服务端数据约束。该试点没有通用的新增食谱、审核发布或人数回写流程。
- 命名日历使用原生 Calendar View，页面局部切换到 `dayGridWeek`；该展示禁用拖动和拉伸，未修改其他日历或官方源文件。
- Query Report 的 SQL 不会自动加入 Frappe 的逐记录 User Permission 条件。本试点依赖固定批次及受控报告角色；SQL 没有通用的公司、园所或用户隔离逻辑，不能据此扩展访问范围。

## 页面、打印与导出

`周食谱样例` 仍返回 **10 行原生报告数据**，每餐分别有“菜品”和“带量”两行。页面通过报告的 `after_datatable_render` 扩展点，在原生容器内增加 HTML 表格，实现餐次跨两行、菜品行自然高度、食材带量自动换行；原生 DataTable 保留数据并在视觉上隐藏。

原生打印、PDF 和导出继续读取这 10 行数据，而不是复制屏幕上的 HTML。当前归档没有额外的周食谱打印模板，也没有使下载文件自动复现餐次合并单元格和页面版式。不能将页面排版验证等同于打印或下载版式一致。

空结果及刷新由报告扩展点清理附加节点；其他报表仍使用原生渲染流程。未覆盖 QueryReport 或 DataTable 的原生方法。

## 依赖与配置核对顺序

依赖试点所使用的 Frappe/ERPNext 版本中的 Production Plan、Production Plan Item、Item、BOM、BOM Item、Custom Field、Calendar View、Client Script 和 Query Report。还使用该版本提供的 `after_datatable_render`、`after_refresh` 和 Calendar List 视图扩展点。它不要求运行童健云或 Suite Calendar。

如需人工比对站点配置，应按以下顺序核查，不能直接重放最初的一次性部署脚本：

1. 核对 ERPNext 已安装及目标版本字段；核对 Custom Field 白名单，包括 `custom_is_meal_plan`、新增的 `custom_meal_ingredients_html` 和子表的 `custom_dish_name`。
2. 核对供餐区位于原生 `reserve_stock` 字段之后；`custom_meal_servings`、`custom_meal_notice` 隐藏，`custom_meal_source` 位于带量 HTML 区之后。
3. 核对 Calendar View `Weekly Meal Plan`、两份 Client Script、两份 Query Report 的定义与对应源码。
4. 单独复核角色及逐记录授权。用户绑定、DocShare 和 User Permission 不在本归档中，不应按文件内容自动扩大权限。
5. 使用站点已有、已获授权的样例数据核对日历、原生计划、BOM、周报、带量明细与原生导出。无样例数据时本目录不能重建该周菜单。

试点上线时核验过：管理员和授权查看角色可打开页面；五天共 25 个餐次、周报 10 行、明细 122 行；人均带量和填写人数后的计算相符；原生打印取数仍为 10 行。没有因展示功能新增采购、领料、库存或财务单据，也没有修改 Frappe/ERPNext 官方源码。上述是当时的验收结果，不是未来版本兼容性保证。

## 不纳入 Git 的材料

本目录不包含原始食谱及参考工作簿、物料或 BOM 业务记录、生产计划、用户记录、账号绑定、DocShare、User Permission、数据库备份、浏览器会话材料、截图和未经筛选的站点导出。

原始 `install.py`、`refine.py`、`ingredient_measure/deploy.py` 混合了一次性业务数据创建、站点路径、仓库及人员授权操作，因此未作为可执行脚本归档。尤其不能重放其中恢复 Custom DocPerm 的步骤。配置恢复和业务数据恢复应由维护者依据独立备份与授权范围处理。

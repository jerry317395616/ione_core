# 周食谱采购申请

本模块只负责“已核对学生人数的周食谱 → 原生食材需求 → 一张采购类型物料需求单草稿”。
采购订单与采购收货使用 ERPNext 原生流程，由有权限人员核对供应商、价格、送货和验收后操作。
模块不会自动提交订单、虚构报价、登记收货、增加库存或生成会计凭证。

## 数据与调用契约

- `get_procurement_preview(week_name)`：只读，要求周记录读取权限；返回逐餐逐食材需求、账面库存分配、有效待收货订单、已申请待下单数量、净申请量、策略/单位问题和报价完整性。
- `prepare_procurement_rows(week_doc)`：周提交控制器内部调用，返回 `{plans: {production_plan: [native_mr_row, ...]}, snapshot, warnings, blockers}`，本函数不保存记录。调用方必须在原生生产计划仍是草稿时保存 `mr_items`，随后提交生产计划，并把 `snapshot` 保存到周的 `procurement_snapshot`。
- `create_material_request(week_name)`：POST，要求已提交周、账面库存复核确认、周读取权限、System Manager 或 Purchase Manager 角色、物料需求单创建权限及所有来源生产计划写入权限。核对冻结依据后，只创建物料需求单草稿，返回 `{material_request, name, created}`。采购经理可以保持周记录只读，由受控操作回写申请链接及“采购申请已生成”状态。

周数据使用 `Meal Planning Week`，含 `company/week_start/week_end/raw_material_warehouse/stock_reviewed/material_request/procurement_snapshot/meals`；每个餐次行含 `meal_date/meal_type/planned_headcount/production_plan`。
每道菜生产数量必须等于该餐确认的学生人数；生产计划 `for_warehouse` 必须与周原料仓一致，且 `reserve_stock=0`。

所有公开数量为十进制字符串。`required_qty/allocated_stock_qty/expected_receipt_qty/already_requested_qty/purchase_stock_qty` 使用库存单位；`purchase_qty` 使用 `purchase_uom`。
每个需求行保留 `meal_date/meal_type/production_plan/item_code/item_name/warehouse/policy/status/price_status`。
`price_status=unquoted` 只提示待询价，不妨碍数量申请。

## 数量和防重

1. 调用本部署原生 `get_items_for_material_requests`，令 `ignore_existing_ordered_qty=0`，获取 BOM 全量需求。该参数在当前 ERPNext 的 `1` 实际启用预计库存抵扣；不能把它误解为“排除已订货量”。
2. 按日期、餐次顺序，只分配一次同物料同仓库的账面可用库存，扣除销售、生产、分包和生产计划占用。
   原生生产计划即使 `reserve_stock=0`，提交后仍会把 `mr_items.required_bom_qty` 计入 Bin 的生产计划占用。计算精确扣除本周已提交、仍开放计划的自身贡献，保留其他计划占用，使提交前后净需求不因自身占用被重复计算。本阶段发现本周关联生产工单即阻断，避免错误处理工单接管库存占用。
3. 仅把尚未收货且到货日期不早于系统当天、且不晚于用餐日的已提交采购订单作为待收供应。过去的逾期单和未填写日期的单据提示人工核对，不自动当作已到货。
4. 已提交采购申请的未下单数量单列为 `already_requested_qty`。使用 `stock_qty - max(ordered_qty, received_qty)`，避免同一数量在采购申请与采购订单中重复抵扣。逾期申请不自动冲抵。
5. 用 `Decimal` 分配和转换。采购单位只使用物料确认的换算；不推断 g 与 ml 的密度。按采购数量精度向上取值，最小舍入余量可供本周后续餐次使用。
6. 原生来源行完整保留。每条 MR Item 关联原生 `production_plan` 和 `material_request_plan_item`，不把不同来源强行合成失去追溯的行。
7. 创建操作对周行加事务锁；草稿与周链接一起提交。重复点击返回已创建的同一张申请。冻结后计算结果变化会要求修订复核，不改写已提交生产计划。

## 采购策略

物料 `custom_meal_procurement_policy` 必须明确：

- `采购`：根据库存和已有申请/订单计算本次净需求。
- `厨房用水`：仍保留配方用量展示，采购量为零。
- `厨房自产待配方`：待确认自产配方后再采购，当前阻止自动生成申请。

没有策略、单位换算缺失、物料停用、采购属性不符，以及本阶段尚未实现的批次/序列库存和最小起订量分配，均在预览中明确列为待处理问题。
骨汤是否采购、饮用水是否厨房用水依赖物料元数据和业务确认，代码不按名称硬编码。

## 本阶段的跨周边界

账面库存复核不等于厨房实物盘点。生产计划未启用库存预留，因此另一张已提交且具有采购冻结快照的周记录，会作为未核销承诺阻止新一周自动采购，提示其来源周。
新周仍可编排草稿和查看预览；不能因为上周日期已经过去、申请已经下单或已经收货就假定食材已领用。
本阶段不提供自动领用/核销或关闭算法，必须先完成上一周承诺的业务核销方案，才可连续发布采购周。取消的周不会继续占用这一保护。

## 原生采购衔接

原生 `Material Request → Purchase Order` 映射要求来源申请 `docstatus=1`；`Purchase Order → Purchase Receipt` 要求来源订单 `docstatus=1`。
因此完整的提交和收货演练必须在隔离数据库进行；正式站只保存实际采购需求草稿，不通过假提交或假收货制造闭环。

离线验证：`python -m unittest ione_core.tests.test_meal_procurement -v`。

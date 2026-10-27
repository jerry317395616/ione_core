# 周食谱采购申请

本模块只负责“已核对学生人数的周食谱 → 原生食材需求 → 一张采购类型物料需求单草稿”。
采购订单与采购收货使用 ERPNext 原生流程，由有权限人员核对供应商、价格、送货和验收后操作。
模块不会自动提交订单、虚构报价、登记收货、增加库存或生成会计凭证。

## 数据与调用契约

- `get_procurement_preview(week_name)`：只读，要求周记录读取权限；返回逐餐逐食材需求、账面库存分配、有效待收货订单、已申请待下单数量、净申请量、策略/单位问题和报价完整性。
- `prepare_procurement_rows(week_doc)`：周提交控制器内部调用，返回 `{plans: {production_plan: [native_mr_row, ...]}, snapshot, warnings, blockers}`，本函数不保存记录。调用方必须在原生生产计划仍是草稿时保存 `mr_items`，随后提交生产计划，并把 `snapshot` 保存到周的 `procurement_snapshot`。
- `create_material_request(week_name)`：POST，要求已提交周、账面库存复核确认、周读取权限和物料需求单创建权限。System Manager／Purchase Manager 须有来源生产计划写入权限；窄角色“膳食业务经办员”只需来源读取权限。核对冻结依据后仅创建物料需求单草稿，返回 `{material_request, name, created}`。

周数据使用 `Meal Planning Week`，含 `company/week_start/week_end/raw_material_warehouse/stock_reviewed/material_request/procurement_snapshot/meals`；每个餐次行含 `meal_date/meal_type/planned_headcount/production_plan`。
每道菜生产数量必须等于该餐确认的学生人数；生产计划 `for_warehouse` 必须与周原料仓一致，且 `reserve_stock=0`。

所有公开数量为十进制字符串。`required_qty/allocated_stock_qty/expected_receipt_qty/already_requested_qty/purchase_stock_qty` 使用库存单位；`purchase_qty` 使用 `purchase_uom`。
每个需求行保留 `meal_date/meal_type/production_plan/item_code/item_name/warehouse/policy/status/price_status`。
`price_status=unquoted` 只提示待询价，不妨碍数量申请。

## 数量和防重

1. 调用本部署原生 `get_items_for_material_requests`，令 `ignore_existing_ordered_qty=0`，获取 BOM 全量需求。该参数在当前 ERPNext 的 `1` 实际启用预计库存抵扣；不能把它误解为“排除已订货量”。
2. 按日期、餐次顺序，只分配一次同物料同仓库的账面可用库存。v2 精确排除所有已验证食谱生产计划的原生毛需求占用，保留非食谱生产计划、销售、生产及分包占用，再按真实周归属保护实物。已关联工单或启用额外原生库存预留的食谱计划会阻断，不能猜测工单接管量。
3. 仅把 native MR→PP 原料源行经核实属于本周、尚未收货且到货日期不早于系统当天、且不晚于用餐日的已提交采购订单作为待收供应。其他周、销售专用或来源不明的订单不冲抵，列入 `excluded_supply`。入库后，经原生采购来源和库存流水核实的膳食到货归属对应周，仅该周可用；非膳食且无专属归属的到货才进入共享可用库存。过去的逾期单和未填写日期的单据提示人工核对，不自动当作已到货。
4. 本周已提交采购申请的未下单数量单列为 `already_requested_qty`。使用 `stock_qty - max(ordered_qty, received_qty)`，避免同一数量在采购申请与采购订单中重复抵扣。逾期申请不自动冲抵。`prepare_adjustment_procurement(week_proxy)` 专用于尚未日结餐次的单餐变更，额外接受本周经核实来源的未取消草稿申请作为防重复承诺，绝不表示实物可用；默认周预览不把草稿当到货。
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

## 跨周实物归属与提前采购

账面库存复核不等于实物盘点。v2 允许提前编排、申请及真实采购下一周，用“已认领现货＋真实专属到货－已领入厨房净量”保护每周原料实物，而不把所有周的毛需求重复扣减。其他周未来 MR／PO 不作为共享供应，已经实际收到的其他周食材也不供本周挪用。

采购日早于新周开始日、且同原料仓仍有更早未核销周时，启用保守提前模式：不使用尚未释放的公共余量，只使用本周已有归属实物及本周有效申请／订单防重。预览明确提示可能多备，需采购人员核对。独立原料仓不因其他仓库的旧周而禁用现货。

每行 `allocated_stock_qty` 仍是总库存分配；`allocated_owned_stock_qty` 表示复用本周归属量，`new_physical_claim_qty` 表示本次从未分配池新增认领量。只有后者写入 v2 的新增承诺。v1 冻结分配作为既有开仓认领，原快照、原申请保持；提交后 free→own 分类变化不允许改变任何业务数量、来源、单位或完整 BOM。

减量未用完的认领保守保留，只有重新核实真实日／周结、采购结清和原生流水后才释放。厨房跨日或跨周留存沿用厨房来源链，不自动当作原料仓公共库存。详见 [实物认领模型](meal-stock-claims.md)。

## 原生采购衔接

原生 `Material Request → Purchase Order` 映射要求来源申请 `docstatus=1`；`Purchase Order → Purchase Receipt` 要求来源订单 `docstatus=1`。
因此完整的提交和收货演练必须在隔离数据库进行；正式站只保存实际采购需求草稿，不通过假提交或假收货制造闭环。

受控下单、真实报价、双人审核与厨房周结采购证明，见 [meal-purchasing.md](meal-purchasing.md)。

离线验证：`python -m unittest ione_core.tests.test_meal_procurement ione_core.tests.test_meal_purchasing -v`。

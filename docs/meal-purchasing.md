# 食谱采购草稿与双人报价审核

这些扩展使用 ERPNext 原生 Material Request、Supplier Quotation、Purchase Order、Purchase Receipt，
不修改官方源码，不发明供应商报价，不自动提交采购订单或模拟正式收货，也不自行提交数据库事务。

## 来源与权限

食谱单据必须通过原生 MR Item → Production Plan 原料源行 → `custom_meal_week` 核实归属。
只有周标签、混合他周/销售用途、Item/仓库/原料源行不匹配，均不可进入受控食谱采购。
单餐变更来源还必须与其原生 PP 的 `custom_meal_adjustment` 一致。

`膳食业务经办员` 可在原生权限及周读取权限下操作食谱采购草稿；该窄角色不能借原生表单维护来源不明的其他采购单。
经办对来源 PP 仅需读取权限，受控接口不改写已提交 PP。
采购审核仅允许 Purchase Manager／System Manager；申请提交人必须不同于 MR 创建人，报价确认人必须不同于 PO 创建人，管理员同样不能自审。

## 接口

- `meal_purchasing.create_purchase_order_draft(week_name, supplier, material_request_items=None, material_request=None)`：默认本周主 MR，也可明确选择本周已审核差额 MR；使用官方 mapper 创建 PO 草稿。按原料源行检测已存在草稿及交叠，不重复生成供应商订单。
- `apply_supplier_quotation(po_name, quotation_name)`：只处理已保存草稿。读取真实已提交 SQ，为整单逐 Item＋UOM 唯一匹配报价行；要求供应商、公司、币种及有效期匹配。保存真实报价引用并清除旧确认。
- `confirm_purchase_order_quote(po_name)`：由不同于 PO 创建人的采购审核人确认，冻结数量、单位换算、价格、来源、供应商、币种、报价有效期和已核实采购重量口径。
- `reissue_material_request_draft(week_name)`：仅在旧 MR 为另一创建人的草稿、没有任何后续 PO／PR 时原样重制。新记录由当前实际经办创建，原记录及原创建人保留，双方替代链接和 Comment 留痕，周链接指向新草稿。旧草稿不可修改或提交。只有来源及数量一致、双向链接真实且无循环的替代链，才从未申请上限和待处理草稿中排除原记录。
- `verify_week_procurement_settled(week)`：内部只读核实本周所有 PP（含变更替换来源）的 MR／PO／PR 链。未下单残量、未到货数量、未处理草稿或来源异常会阻断厨房周结。原生 Stopped MR／Closed PO 可按人工关闭处理，但证明仍保留原数量和未执行余量。

## 原生事件保护

部署方将以下钩子注册到 `ione_core`，不覆盖官方函数：

| DocType | 事件 | 函数 |
|---|---|---|
| Material Request | validate／before_update_after_submit | `meal_purchasing.validate_material_request` |
| Material Request | before_submit | `meal_purchasing.before_submit_material_request` |
| Purchase Order | validate／before_update_after_submit | `meal_purchasing.validate_purchase_order` |
| Purchase Order | before_submit | `meal_purchasing.before_submit_purchase_order` |

MR 逐来源核对冻结 Item、仓、日期、UOM 和转换，所有未取消草稿及已提交申请的合计不得超过原生源行冻结净申请量。
PO 合计也不能超过已审核 MR 数量。手工通过原生表单建单同样校验；去掉周标签不能解除保护。
PO 提交必须有真实 SQ 正价及有效的第二人确认；Item Price 只是参考价格，不能代替确认报价。
供应商、数量、日期、单位或价格变化会使草稿旧确认失效；正式订单变更应使用原生修订并重新审核。

## 受控字段

PO：`custom_meal_week` Link 和 `custom_meal_quote_snapshot` Long Text，均只读、不可复制；后者含确认人、时间、引用 SQ 与冻结依据。
MR：`custom_meal_superseded_by` 与 `custom_meal_replaces` Link Material Request，只读、不可由普通表单或 API 伪造。
字段定义、权限与钩子由统一安装配置提供；缺少配置时不得用修改官方代码或跳过校验来运行。

重量口径由 `meal_planning.verify_purchase_weight_basis` 独立核实，本模块只读取证明，不重算或改写历史冻结周与主 MR。
厨房周结证明不包括财务发票／付款结算；应付结算仍走原生财务流程。

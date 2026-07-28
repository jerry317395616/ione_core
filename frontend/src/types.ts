export type Tab = 'home' | 'photos' | 'dispatch' | 'tasks' | 'profile'

export type ReminderLevel = 'urgent' | 'normal'

export type TaskStatus = 'pending' | 'accepted' | 'in_progress' | 'completed' | 'cancelled'

export type AutoStrategy = 'efficiency' | 'cost' | 'quality' | 'balanced'

export type AutoMode = 'off' | 'partial' | 'full' | 'sim'

// ==================== ERP 模块类型 ====================
export type ERPModule =
  | 'dashboard'    // 仪表盘
  | 'finance'      // 财务中心
  | 'crm'          // 客户关系
  | 'order'        // 订单中心
  | 'hr'           // 人力资源
  | 'ticket'       // 工单中心
  | 'asset'        // 资产管理
  | 'report'       // 报表中心
  | 'inventory'    // 库存管理
  | 'project'      // 项目管理
  | 'settings'     // 系统设置

// ==================== 公司档案 ====================
export interface Company {
  name: string
  creditCode: string
  legalPerson: string
  businessScope: string
  registeredCapital: string
  establishDate: string
  industry: string
}

// ==================== 票据/凭证 ====================
export interface PhotoRecord {
  id: string
  url: string
  category: 'invoice' | 'receipt' | 'contract' | 'business_license' | 'voucher' | 'other'
  amount?: number
  taxAmount?: number
  createdAt: string
  voucherId?: string
  accountId?: string
  status: 'pending' | 'verified' | 'posted'
}

// ==================== ERP 财务科目 ====================
export interface GLAccount {
  code: string
  name: string
  type: 'asset' | 'liability' | 'equity' | 'revenue' | 'expense'
  balance: number
  children?: GLAccount[]
}

// ==================== 客户/供应商 ====================
export interface BusinessPartner {
  id: string
  name: string
  type: 'customer' | 'supplier'
  contact: string
  phone: string
  totalTrade: number
  outstanding: number
  rating: number
  tags: string[]
}

// ==================== 提醒 ====================
export interface Reminder {
  id: string
  level: ReminderLevel
  title: string
  description: string
  createdAt: string
  action?: 'dispatch' | 'remind' | 'suggest'
  daysUntil?: number
  module?: ERPModule
  relatedId?: string
}

// ==================== 工单 ====================
export interface DispatchTask {
  id: string
  title: string
  description: string
  address: string
  budget: number
  deadline: string
  status: TaskStatus
  createdAt: string
  isVoice: boolean
  plan: 'free' | 'premium'
  recipientName?: string
  autoAssigned?: string
  progress?: number
  logs?: TaskLog[]
  completedIncome?: number
  source: 'manual' | 'auto' | 'sim'
  orderNo?: string
  category: 'finance' | 'sales' | 'ops' | 'design' | 'admin'
  priority: 'low' | 'normal' | 'high' | 'urgent'
  amount?: number
}

// ==================== 工单日志 ====================
export interface TaskLog {
  time: string
  message: string
  type: 'start' | 'progress' | 'update' | 'complete'
  operator?: string
}

// ==================== 任务 ====================
export interface Task {
  id: string
  type: 'daily' | 'weekly' | 'main'
  title: string
  description: string
  reward: string
  progress: number
  maxProgress: number
  isCompleted: boolean
  mainStage?: number
  module?: ERPModule
  assignee?: string
}

// ==================== 成就/里程碑 ====================
export interface Achievement {
  id: string
  title: string
  description: string
  icon: string
  category: string
  isUnlocked: boolean
  progress: number
  maxProgress: number
  erpBadge?: string
}

// ==================== 自动化规则 ====================
export interface AutoRule {
  id: string
  name: string
  icon: string
  trigger: string
  action: string
  assignedNPC: string
  enabled: boolean
  schedule?: string
  module: ERPModule
  workflowId?: string
}

// ==================== 模拟任务 ====================
export interface SimTask {
  id: string
  title: string
  income: number
  estimatedTime: string
  requiredSkill: string
  assignedNPC?: string
  progress: number
  status: 'pending' | 'running' | 'completed'
  category: 'finance' | 'sales' | 'ops' | 'design' | 'admin'
}

// ==================== 日报 ====================
export interface DailyReport {
  date: string
  income: { title: string; amount: number }[]
  totalIncome: number
  expense: { title: string; amount: number }[]
  totalExpense: number
  netProfit: number
  efficiency: number
  exp: number
  gold: number
  streak: number
  autoStats: { auto: number; manual: number; aiDone: number; npcDone: number; successRate: number }
  tomorrowPredict: { tasks: number; income: string; advice: string }
  balanceSheet: { totalAssets: number; totalLiabilities: number; equity: number }
  cashFlow: { operating: number; investing: number; financing: number }
  receivableAmount: number
  payableAmount: number
  arHistory: { month: string; amount: number; collected: number }[]
  apHistory: { month: string; amount: number; paid: number }[]
}

// ==================== 自动化套餐 ====================
export interface AutoPackage {
  id: string
  name: string
  icon: string
  command: string
  description: string
  income: string
  cost: string
  enabled: boolean
  module: ERPModule
}

// ==================== 员工 ====================
export interface TeamMember {
  id: string
  name: string
  icon: string
  role: string
  department: string
  status: 'idle' | 'working' | 'break'
  currentTask?: string
  taskProgress: number
  taskTitle?: string
  salary: number
  skill: string
  skillLevel: number
  loyalty: number
  hireDate: string
  performance: number
}

// ==================== ERP 仪表盘指标 ====================
export interface ERPDashboardMetrics {
  todayIncome: number
  todayExpense: number
  monthIncome: number
  monthExpense: number
  receivableTotal: number
  payableTotal: number
  activeProjects: number
  pendingTickets: number
  employeeCount: number
  autoTaskCount: number
  efficiency: number
}

// ==================== ERP 模块配置 ====================
export interface ERPModuleConfig {
  id: ERPModule
  name: string
  icon: string
  enabled: boolean
  description: string
  order: number
}

// ======================== App-level state types ========================
export type TabId = 0 | 1 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13

export interface AppState {
  onboardingComplete: boolean
  industry: string
  userName: string
  companyName: string
  xp: number
  gold: number
  streak: number
  layoutMode: 'standard' | 'minimal' | 'rich'
  autoMode: 'off' | 'partial' | 'full' | 'sim'
  nightMode: boolean
  nightModeEnabled: boolean
  nightStartTime: string
  nightEndTime: string
  // ERP 扩展
  receivable: Record<string, number>
  payable: Record<string, number>
  projectCount: number
  modules: ERPModule[]
  departmentCount: number
  phone?: string
  email?: string
}

// ==================== OPE 智能指令中心类型 ====================
export type TaskPriority = 'P0' | 'P1' | 'P2'
export type RunErrandCategory = '工商' | '税务' | '银行' | '邮局' | '凭证' | '其他'
export type TaskActionMode = '出门办理' | '线上确认' | '自动处理'

export interface RunErrandTask {
  id: string
  title: string
  location: string
  dueDate: string
  materials: string[]
  status: 'waiting' | 'departed' | 'completed' | 'delayed'
  createdAt: string
}

export interface AIBackendTask {
  id: string
  name: string
  status: 'running' | 'done' | 'waiting'
  progress: number
  estimatedTime: string
  result?: unknown
}

export interface PendingConfirmation {
  id: string
  title: string
  type: 'voucher' | 'report' | 'dispatch'
  count?: number
  action: '确认归档' | '查看详情'
}

// ==================== AI 智能录入类型 ====================
export type OCRCategory = 'invoice' | 'receipt' | 'contract' | 'business_license' | 'bank_statement' | 'transport_receipt' | 'other'

export interface OCRResult {
  id: string
  imageUrl: string
  category: OCRCategory
  confidence: number        // 0-1 识别置信度
  extractedData: Record<string, string | number>  // 提取的字段
  rawText: string           // OCR 原始文本
  suggestedAccount?: string // AI 建议的科目
  suggestedPartner?: string // AI 建议的往来单位
  amount?: number           // 识别出的金额
  date?: string             // 识别出的日期
  confirmed: boolean        // 是否已确认
  entered: boolean          // 是否已录入
  createdAt: string
}

export interface VoiceCommand {
  id: string
  transcript: string        // 语音识别文本
  intent: string            // 意图识别结果
  entities: Record<string, string>  // 提取的实体
  suggestedAction: string   // AI 建议的操作
  confidence: number
  confirmed: boolean
  createdAt: string
}

export interface IntelligentEntryItem {
  id: string
  type: 'ocr' | 'voice'
  data: OCRResult | VoiceCommand
  status: 'pending' | 'confirming' | 'confirmed' | 'entered' | 'rejected'
  entryAction: string       // 具体录入操作
  entryTarget: string       // 录入目标（哪个库/科目）
  timestamp: string
}

// ==================== 证据链（完整业务闭环）类型 ====================

// 业务类型 — 每个类型有固定的凭证要求和审批规则
export type BusinessType =
  | 'expense'        // 费用报销
  | 'revenue'        // 收入入账
  | 'payment'        // 付款
  | 'receipt'        // 收款
  | 'asset_purchase' // 资产购置
  | 'transfer'       // 转账
  | 'other'          // 其他

// 凭证类型 — 每种业务类型要求的凭证不同
export type EvidenceType =
  | 'invoice'           // 发票（增值税专用发票/普通发票）
  | 'receipt'           // 收据
  | 'bank_slip'         // 银行回单
  | 'transport_ticket'  // 交通票据
  | 'hotel_receipt'     // 住宿发票
  | 'contract'          // 合同
  | 'photo'             // 现场照片
  | 'internal_form'     // 内部表单（审批单等）
  | 'none'              // 无需凭证（小额/特殊场景）

// 审批级别
export type ApprovalLevel =
  | 'auto'        // 自动通过（金额小/规则明确）
  | 'self'        // 自己确认即可
  | 'manager'     // 需要上级审批
  | 'finance'     // 需要财务审核
  | 'multi'       // 多级审批

// 证据链步骤状态
export type EvidenceStepStatus = 'pending' | 'in_progress' | 'completed' | 'failed'

// 单条证据
export interface EvidenceItem {
  id: string
  type: EvidenceType
  imageUrl: string
  verified: boolean        // 是否已验证真伪
  verifyMethod: 'manual' | 'ocr' | 'api'  // 验证方式
  data: Record<string, string | number>    // 识别提取的数据
  status: EvidenceStepStatus
  uploadedAt: string
}

// 业务动作 — 一次用户指令产生的完整业务操作
export interface BusinessAction {
  id: string
  businessType: BusinessType
  description: string       // 用户原始指令，如"报销北京出差差旅费"
  amount: number
  accountCode: string       // 会计科目编码
  accountName: string       // 会计科目名称
  partnerId?: string        // 往来单位
  evidenceType: EvidenceType[]  // 要求的凭证类型列表
  approvalLevel: ApprovalLevel  // 审批级别
  status: ActionStatus
  createdAt: string
  completedAt?: string
}

// 证据链 — 绑定一个业务动作的完整证据流
export interface EvidenceChain {
  id: string
  actionId: string          // 关联的业务动作
  evidenceItems: EvidenceItem[]     // 已上传的证据
  requiredEvidence: EvidenceType[]  // 要求的凭证类型（去重后）
  missingEvidence: EvidenceType[]   // 缺失的凭证
  evidenceComplete: boolean   // 证据是否齐全
  approvalPassed: boolean     // 审批是否通过
  approvedBy?: string         // 审批人
  approvedAt?: string         // 审批时间
  posted: boolean             // 是否已记账（过账）
  postedAt?: string           // 过账时间
  createdAt: string
  updatedAt: string
}

// 业务动作状态
export type ActionStatus =
  | 'pending_evidence'  // 等待上传凭证
  | 'pending_approval'  // 等待审批
  | 'pending_post'      // 等待过账（审批通过后）
  | 'completed'         // 已完成
  | 'rejected'          // 已驳回
  | 'cancelled'         // 已取消

// 业务规则 — 每种业务类型的固定规则
export interface BusinessRule {
  businessType: BusinessType
  requiredEvidence: EvidenceType[]      // 必须提供的凭证
  optionalEvidence: EvidenceType[]      // 可选凭证
  approvalLevel: ApprovalLevel          // 审批级别
  amountThreshold?: number              // 金额阈值（超过后提升审批级别）
  description: string                   // 规则描述
  complianceNotice: string              // 合规提示语
}

// 证据链状态提示
export interface EvidenceChainNotice {
  id: string
  actionId: string
  type: 'warning' | 'info' | 'error' | 'success'
  title: string
  message: string
  action?: 'upload' | 'approve' | 'post' | 'cancel'
  createdAt: string
}

// ==================== 老板成长计划（互动成长空间） ====================

// 成长话题分类
export type GrowthTopic =
  | 'company_strategy'   // 公司战略
  | 'personal_growth'    // 个人成长
  | 'team_building'      // 团队建设
  | 'finance_plan'       // 财务规划
  | 'product_vision'     // 产品愿景
  | 'culture'            // 企业文化
  | 'goal_setting'       // 目标设定
  | 'reflection'         // 回顾反思

// 成长计划
export interface GrowthPlan {
  id: string
  title: string                        // 计划标题，如"季度营收目标"
  topic: GrowthTopic                   // 所属话题
  description: string                  // 计划描述
  milestones: MilestoneItem[]          // 里程碑
  status: 'active' | 'completed' | 'paused' | 'abandoned'
  createdAt: string
  updatedAt: string
  completedAt?: string
}

// 计划里程碑
export interface MilestoneItem {
  id: string
  title: string
  description: string
  completed: boolean
  completedAt?: string
  deadline?: string
  progress?: number   // 0-100
}

// 互动对话记录（老板 × AI 的成长对话）
export interface GrowthConversation {
  id: string
  planId?: string            // 关联的成长计划（可选）
  topic: GrowthTopic         // 话题
  messages: GrowthMessage[]  // 对话消息
  summary: string            // 对话摘要
  keyDecisions: string[]     // 关键决策/结论
  createdAt: string
  updatedAt: string
}

// 单条对话消息
export interface GrowthMessage {
  id: string
  role: 'boss' | 'ai' | 'system'
  content: string
  timestamp: string
  mood?: 'inspired' | 'concerned' | 'determined' | 'reflective' | 'excited'
}

// 成长事件（从业务动作中自动产生的成长洞察）
export interface GrowthEvent {
  id: string
  type: 'achievement' | 'lesson' | 'milestone' | 'reflection'
  title: string
  description: string
  relatedActionId?: string   // 关联的业务动作ID
  impact: 'low' | 'medium' | 'high'
  createdAt: string
}

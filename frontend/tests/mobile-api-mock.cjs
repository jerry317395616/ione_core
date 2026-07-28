const http = require('node:http')

const port = Number(process.env.PORT || 4199)

const apps = [
  { name: 'erpnext', title: 'ERPNext', route: '/app/accounting', category: '经营管理', sequence: 1 },
  { name: 'crm', title: '客户关系', route: '/crm', category: '经营管理', sequence: 2 },
  { name: 'ione_core', title: 'I-ONE AI', route: '/app/i-one-ai', category: 'I-ONE', sequence: 3 },
]

const responses = {
  'ione_core.api.get_bootstrap': {
    user: { username: 'mobile@example.com', full_name: '移动端测试用户', roles: ['I-ONE User'] },
    site: 'manager.myyr.top',
    csrf_token: 'visual-test',
    apps,
    features: { ai_employees: true, ai_tasks: true, approvals: true, background_jobs: true },
  },
  'ione_core.onboarding.get_mobile_onboarding': {
    flow: { code: 'mobile-default', name: '手机端默认引导', version: 1, welcome: {}, steps: [] },
    progress: {
      record: 'TEST',
      status: '已完成',
      completed: true,
      current_step: 'report',
      answers: {},
      profile: {
        company_name: '美妍伊人医疗科技有限公司',
        display_name: '移动端测试用户',
        user_role: '负责人',
        city: '西安',
        skipped_info: false,
      },
      report: null,
    },
  },
  'ione_core.api.get_dashboard': {
    metrics: [
      { key: 'leads', label: '销售线索', value: 18, source: 'CRM', route: '/crm/leads' },
      { key: 'employees', label: '在职员工', value: 12, source: 'Frappe HR', route: '/app/employee' },
    ],
    overview: [
      { key: 'today_todos', label: '今日待办', value: 3, source: 'Frappe ToDo', route: '/app/todo', format: 'number', tone: 'primary', available: true },
      { key: 'today_income', label: '今日收入', value: 28600, source: 'ERPNext 总账', route: '/app/accounting', format: 'currency', tone: 'positive', available: true },
      { key: 'today_expense', label: '今日支出', value: 8200, source: 'ERPNext 总账', route: '/app/accounting', format: 'currency', tone: 'negative', available: true },
      { key: 'today_profit', label: '今日利润', value: 20400, source: 'ERPNext 总账', route: '/app/accounting', format: 'currency', tone: 'positive', available: true },
    ],
    currency: 'CNY',
    company: '美妍伊人医疗科技有限公司',
    as_of_date: '2026-07-28',
    profit_progress: { actual: 204000, target: 300000, percent: 68, currency: 'CNY', route: '/app/i-one-operating-target' },
    todos: [
      { id: 'todo:1', title: '确认本周销售回款', source: 'Frappe ToDo', status: '待处理', priority: 'High', due_date: '2026-07-28', route: '/app/todo/1' },
      { id: 'ione:1', title: '生成经营日报', source: 'I-ONE AI', status: '执行中', priority: '普通', route: '/app/i-one-ai-task/1' },
    ],
    apps,
  },
  'ione_core.api.get_mobile_task_center': {
    todos: [
      { id: 'todo:1', title: '确认本周销售回款', source: 'Frappe ToDo', status: '待处理', priority: 'High', due_date: '2026-07-28', route: '/app/todo/1' },
    ],
    plans: [
      { name: 'IGP-1', title: '三季度客户增长计划', category: '公司战略', status: '进行中', progress: 45, end_date: '2026-09-30', route: '/app/i-one-growth-plan/IGP-1' },
    ],
    achievements: [
      { name: 'IAC-1', title: '首个自动化任务', achievement_type: '智能化', points: 50, gold: 10, description: '完成首个 AI 工作单' },
    ],
  },
  'ione_core.api.get_mobile_finance': {
    available: true,
    company: '美妍伊人医疗科技有限公司',
    currency: 'CNY',
    as_of_date: '2026-07-28',
    balance: { assets: 1260000, liabilities: 380000, equity: 880000 },
    month: { available: true, income: 428000, expense: 224000, profit: 204000 },
    receivable: { amount: 156000, count: 8 },
    payable: { amount: 72000, count: 5 },
    weekly_income: [
      { date: '2026-07-22', income: 18000 }, { date: '2026-07-23', income: 32000 },
      { date: '2026-07-24', income: 26000 }, { date: '2026-07-25', income: 41000 },
      { date: '2026-07-26', income: 12000 }, { date: '2026-07-27', income: 35000 },
      { date: '2026-07-28', income: 28600 },
    ],
    accounts: [
      { name: '银行存款', code: '1002', label: '银行存款', root_type: 'Asset', balance: 620000, route: '/app/account/银行存款' },
      { name: '应收账款', code: '1122', label: '应收账款', root_type: 'Asset', balance: 156000, route: '/app/account/应收账款' },
    ],
    routes: { accounting: '/app/accounting', receivable: '/app/query-report/Accounts Receivable', payable: '/app/query-report/Accounts Payable' },
  },
  'ione_core.api.get_mobile_activity': {
    stats: { total: 8, completed: 5, running: 2, failed: 1 },
    tasks: [
      { name: 'AIT-1', title: '生成经营日报', status: '执行中', priority: '普通', progress: 65, assigned_agent: '经营分析助手', modified: '2026-07-28 10:30:00', route: '/app/i-one-ai-task/AIT-1' },
      { name: 'AIT-2', title: '整理客户跟进记录', status: '已完成', priority: '高', progress: 100, assigned_agent: 'CRM 助手', modified: '2026-07-28 09:40:00', route: '/app/i-one-ai-task/AIT-2' },
    ],
    logs: [
      { name: 'LOG-1', task: 'AIT-1', agent: '经营分析助手', event_type: '模型分析', level: '信息', message: '已读取本月经营指标，正在生成摘要', creation: '2026-07-28 10:31:00' },
    ],
  },
  'ione_core.api.get_mobile_profile': {
    user: { username: 'mobile@example.com', full_name: '移动端测试用户', roles: ['I-ONE User'] },
    company: { name: '美妍伊人医疗科技有限公司', company_name: '美妍伊人医疗科技有限公司', country: '中国', default_currency: 'CNY', tax_id: '9161XXXXXXXXXXXX', date_of_establishment: '2023-06-18' },
    employee_count: 12,
    department_count: 4,
    apps,
    achievements: [{ name: 'IAC-1', title: '首个自动化任务', points: 50, gold: 10 }],
    totals: { points: 50, gold: 10 },
  },
  'ione_core.api.get_mobile_notifications': {
    notifications: [
      { id: 'todo:1', title: '确认本周销售回款', message: 'Sales Invoice 待办', priority: 'High', status: '待处理', due_date: '2026-07-28', source: 'Frappe ToDo', route: '/app/todo/1' },
      { id: 'approval:1', title: '审批客户批量更新', message: '关联任务：AIT-3', priority: '高', status: '待审批', source: 'I-ONE 审批', route: '/app/i-one-approval-request/1' },
    ],
  },
  'ione_core.api.get_mobile_channels': {
    channels: [
      { name: '公司官网', channel_name: '公司官网', channel_type: '网站', status: '启用', account_name: 'myyr.top' },
      { name: '企业公众号', channel_name: '企业公众号', channel_type: '微信公众号', status: '启用', account_name: 'I-ONE AI' },
    ],
    jobs: [{ name: 'IPJ-1', title: '七月产品更新', channel: '公司官网', status: '已发布' }],
  },
  'ione_core.api.get_mobile_evaluations': {
    evaluations: [
      { name: 'IEV-1', task: 'AIT-1', task_title: '经营日报', agent: 'AG-1', agent_name: '经营分析助手', score: 92, grade: 'A', evaluated_at: '2026-07-28 10:32:00', dimensions: [{ dimension: 'accuracy', score: 94 }, { dimension: 'completeness', score: 90 }, { dimension: 'speed', score: 91 }, { dimension: 'satisfaction', score: 93 }], comments: '数据完整，建议进一步压缩摘要篇幅。' },
      { name: 'IEV-2', task: 'AIT-2', task_title: '客户跟进整理', agent: 'AG-2', agent_name: 'CRM 助手', score: 86, grade: 'B', evaluated_at: '2026-07-27 17:20:00', dimensions: [] },
    ],
  },
  'ione_core.api.get_mobile_experiences': {
    experiences: [
      { name: 'IEX-1', title: '高意向客户三步跟进法', category: '销售', author_user: 'mobile@example.com', status: '已发布', useful_count: 18, content: '<p>先确认需求，再提供量化方案，最后约定明确的下一步。</p>', tags: '客户,跟进', modified: '2026-07-28 09:00:00', route: '/app/i-one-experience/IEX-1' },
    ],
  },
  'ione_core.api.get_mobile_settings': {
    can_write: true,
    provider: 'OpenAI Compatible',
    model_name: 'qwen',
    llm_base_url: 'http://172.18.112.42:8000/v1',
    api_key_configured: true,
    require_confirmation_for_writes: true,
  },
  'ione_core.api.get_ai_employees': [],
  'ione_core.smart_record.get_smart_record_capabilities': { provider: 'I-ONE', actions: [] },
  'ione_core.smart_record.list_smart_records': [],
  'ione_core.expert.list_expert_conversations': [],
  'ione_core.expert.get_expert_service_access': {
    provider: 'I-ONE 模型服务',
    canManage: false,
    loggedIn: true,
    requiresLogin: false,
    requiresMobileVerification: false,
    blocked: false,
    busy: false,
    queueDepth: 0,
  },
}

http.createServer((request, response) => {
  const url = new URL(request.url, `http://${request.headers.host}`)
  const prefix = '/api/method/'
  if (!url.pathname.startsWith(prefix)) {
    response.writeHead(404)
    response.end()
    return
  }
  const method = decodeURIComponent(url.pathname.slice(prefix.length))
  const message = Object.prototype.hasOwnProperty.call(responses, method) ? responses[method] : {}
  response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
  response.end(JSON.stringify({ message }))
}).listen(port, '127.0.0.1', () => {
  console.log(`I-ONE mobile visual API mock listening on ${port}`)
})

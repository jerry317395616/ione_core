// ==================== 11个行业配置系统 ====================

export interface IndustryConfig {
  id: string
  name: string
  icon: string
  color: string
  gradient: string
  // 首页指标
  topMetrics: { income: string; expense: string; profit: string; label: string }[]
  // 任务类型术语
  taskTypes: Record<string, string>
  // 建筑类型
  buildings: { id: string; name: string; icon: string; level: number; maxLevel: number; desc: string; unlockLevel: number; upgradeCost: number; effect: string; unlocked: boolean }[]
  // 推荐NPC组合
  recommendedNPCs: string[]
  // NPC职位定制
  npcTitles: Record<string, string>
  // 欢迎文案
  welcome: string
  // 标语
  slogan: string
  // Boss列表
  bosses: { id: string; name: string; icon: string; hp: number; maxHp: number; type: 'urgent' | 'important' | 'daily'; desc: string; reward: string; timer: number; defeated: boolean }[]
  // 默认场景
  defaultScenes: string[]
}

export const industryConfigs: Record<string, IndustryConfig> = {
  '广告传媒': {
    id: 'ad', name: '广告传媒', icon: '📢', color: '#8b5cf6',
    gradient: 'linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%)',
    topMetrics: [
      { income: '项目收入', expense: '人力成本', profit: '项目净利', label: '本月进账 ¥42,500' }
    ],
    taskTypes: { task: '项目', invoice: '项目发票', collection: '尾款催收', design: '创意设计', meeting: '客户会议', delivery: '交付物' },
    buildings: [
      { id: 'bl1', name: '创意中心', icon: '🎨', level: 1, maxLevel: 5, desc: '核心创意工作区', unlockLevel: 1, upgradeCost: 200, effect: '设计效率+20%/级', unlocked: true },
      { id: 'bl2', name: '会议室', icon: '🏛️', level: 1, maxLevel: 3, desc: '客户洽谈区', unlockLevel: 1, upgradeCost: 150, effect: '客户满意度+15%/级', unlocked: true },
      { id: 'bl3', name: '素材库', icon: '📦', level: 0, maxLevel: 5, desc: '设计素材管理', unlockLevel: 2, upgradeCost: 300, effect: '素材检索+30%/级', unlocked: false },
      { id: 'bl4', name: '直播工作室', icon: '🎥', level: 0, maxLevel: 3, desc: '短视频直播', unlockLevel: 3, upgradeCost: 500, effect: '直播收益+25%/级', unlocked: false },
    ],
    recommendedNPCs: ['小美(设计)', '小王(销售)', '小李(会计)'],
    npcTitles: { 小李: '项目会计', 小王: '客户总监', 小美: '创意总监', 老张: '交付专员', 阿花: '项目助理', 小刘: '内容运营' },
    welcome: '欢迎来到广告传媒公司！你的创意价值百万。',
    slogan: '用创意驱动价值，让每个项目都成为作品',
    bosses: [
      { id: 'b1', name: '客户大考', icon: '🤯', hp: 3, maxHp: 3, type: 'urgent', desc: '客户要3个方案同时出，今天必须交稿！', reward: '经验×3 + "创意大师"徽章', timer: 180, defeated: false },
      { id: 'b2', name: '方案修改王', icon: '🔄', hp: 5, maxHp: 5, type: 'important', desc: '客户又提修改意见了', reward: '经验+金币×50', timer: 1440, defeated: false },
    ],
    defaultScenes: ['项目策划', '创意设计', '客户提案', '尾款催收', '素材整理'],
  },
  '电商零售': {
    id: 'ecom', name: '电商零售', icon: '🛒', color: '#ff6b35',
    gradient: 'linear-gradient(135deg, #ff6b35 0%, #f59e0b 100%)',
    topMetrics: [
      { income: '订单收入', expense: '运营成本', profit: '订单净利', label: '本月GMV ¥58,200' }
    ],
    taskTypes: { task: '订单', invoice: '进货发票', collection: '货款结算', design: '主图设计', meeting: '供应商会议', delivery: '发货' },
    buildings: [
      { id: 'bl1', name: '仓库', icon: '📦', level: 1, maxLevel: 5, desc: '商品存储区', unlockLevel: 1, upgradeCost: 200, effect: '库存容量+30%/级', unlocked: true },
      { id: 'bl2', name: '客服室', icon: '🎧', level: 1, maxLevel: 3, desc: '客户咨询服务', unlockLevel: 1, upgradeCost: 150, effect: '好评率+10%/级', unlocked: true },
      { id: 'bl3', name: '直播间', icon: '📱', level: 0, maxLevel: 3, desc: '直播带货', unlockLevel: 3, upgradeCost: 600, effect: '直播销售额+40%/级', unlocked: false },
      { id: 'bl4', name: '打包台', icon: '📋', level: 0, maxLevel: 3, desc: '发货打包区', unlockLevel: 2, upgradeCost: 250, effect: '发货速度+25%/级', unlocked: false },
    ],
    recommendedNPCs: ['小王(销售)', '小刘(运营)', '阿花(行政)'],
    npcTitles: { 小李: '电商会计', 小王: '店铺运营', 小美: '视觉设计', 老张: '物流专员', 阿花: '客服主管', 小刘: '直播运营' },
    welcome: '欢迎来到电商世界！你的店铺正在 Growing！',
    slogan: '每一件商品都是信任，每一次服务都是口碑',
    bosses: [
      { id: 'b1', name: '差评危机', icon: '💣', hp: 2, maxHp: 2, type: 'urgent', desc: '有客户给了差评，急需处理！', reward: '经验×2 + 店铺信誉+10', timer: 240, defeated: false },
      { id: 'b2', name: '大促Boss', icon: '🎉', hp: 4, maxHp: 4, type: 'important', desc: '双11大促准备，订单量暴增', reward: '金币×100 + 大促勋章', timer: 10080, defeated: false },
    ],
    defaultScenes: ['上架商品', '处理订单', '客户售后', '活动策划', '库存盘点'],
  },
  '设计工作室': {
    id: 'design', name: '设计工作室', icon: '🎨', color: '#ec4899',
    gradient: 'linear-gradient(135deg, #ec4899 0%, #f472b6 100%)',
    topMetrics: [
      { income: '设计费收入', expense: '设计成本', profit: '设计净利', label: '本月设计收入 ¥35,000' }
    ],
    taskTypes: { task: '设计稿', invoice: '设备发票', collection: '设计费催款', design: '设计执行', meeting: '方案确认', delivery: '交付成品' },
    buildings: [
      { id: 'bl1', name: '画室', icon: '🖼️', level: 1, maxLevel: 5, desc: '核心创作区', unlockLevel: 1, upgradeCost: 200, effect: '创作效率+20%/级', unlocked: true },
      { id: 'bl2', name: '设备间', icon: '💻', level: 1, maxLevel: 3, desc: '高性能工作站', unlockLevel: 1, upgradeCost: 250, effect: '渲染速度+25%/级', unlocked: true },
      { id: 'bl3', name: '素材墙', icon: '🖌️', level: 0, maxLevel: 3, desc: '灵感素材库', unlockLevel: 2, upgradeCost: 200, effect: '创意灵感+20%/级', unlocked: false },
      { id: 'bl4', name: '大师工作室', icon: '👑', level: 0, maxLevel: 2, desc: '高级创作区', unlockLevel: 4, upgradeCost: 600, effect: '设计单价+50%/级', unlocked: false },
    ],
    recommendedNPCs: ['小美(设计)', '阿花(行政)', '小李(会计)'],
    npcTitles: { 小李: '项目财务', 小王: '商务对接', 小美: '主创设计师', 老张: '交付专员', 阿花: '项目助理', 小刘: '品牌运营' },
    welcome: '欢迎来到设计工作室！每个像素都有价值。',
    slogan: '设计不只是美，是解决问题的艺术',
    bosses: [
      { id: 'b1', name: '甲方大魔王', icon: '😈', hp: 4, maxHp: 4, type: 'urgent', desc: '甲方要求明天交稿，今晚通宵！', reward: '经验×3 + "甲方克星"徽章', timer: 720, defeated: false },
      { id: 'b2', name: '交付大考', icon: '📦', hp: 3, maxHp: 3, type: 'important', desc: '3个项目同时交付，质量不能降', reward: '金币×80 + 交付大师', timer: 4320, defeated: false },
    ],
    defaultScenes: ['Logo设计', '海报制作', '品牌VI', '包装设计的', '网站UI'],
  },
  '摄影摄像': {
    id: 'photo', name: '摄影摄像', icon: '📸', color: '#4a9eff',
    gradient: 'linear-gradient(135deg, #4a9eff 0%, #00f0ff 100%)',
    topMetrics: [
      { income: '拍摄收入', expense: '器材成本', profit: '拍摄净利', label: '本月拍摄收入 ¥45,000' }
    ],
    taskTypes: { task: '拍摄', invoice: '器材发票', collection: '拍摄费催款', design: '修图排版', meeting: '需求沟通', delivery: '交付成片' },
    buildings: [
      { id: 'bl1', name: '器材库', icon: '📷', level: 1, maxLevel: 5, desc: '相机灯光器材', unlockLevel: 1, upgradeCost: 300, effect: '器材效率+15%/级', unlocked: true },
      { id: 'bl2', name: '影棚', icon: '💡', level: 1, maxLevel: 3, desc: '室内拍摄区', unlockLevel: 1, upgradeCost: 400, effect: '拍摄单价+20%/级', unlocked: true },
      { id: 'bl3', name: '图库', icon: '🗄️', level: 0, maxLevel: 5, desc: '照片素材管理', unlockLevel: 2, upgradeCost: 200, effect: '库存容量+50%/级', unlocked: false },
      { id: 'bl4', name: '后期室', icon: '🖥️', level: 0, maxLevel: 3, desc: '修图调色区', unlockLevel: 2, upgradeCost: 350, effect: '后期速度+30%/级', unlocked: false },
    ],
    recommendedNPCs: ['阿花(行政)', '小王(销售)', '老张(司机)'],
    npcTitles: { 小李: '财务', 小王: '客户顾问', 小美: '修图师', 老张: '外勤专员', 阿花: '摄影助理', 小刘: '自媒体运营' },
    welcome: '欢迎来到摄影世界！每一帧都是故事。',
    slogan: '用镜头捕捉光影，用照片讲述故事',
    bosses: [
      { id: 'b1', name: '大型拍摄日', icon: '🎬', hp: 5, maxHp: 5, type: 'urgent', desc: '今天拍5个场景，从早忙到晚！', reward: '经验×3 + "拍摄达人"徽章', timer: 1440, defeated: false },
      { id: 'b2', name: '修图Boss', icon: '🖥️', hp: 3, maxHp: 3, type: 'important', desc: '客户要精修200张，deadline迫在眉睫', reward: '金币×60', timer: 2880, defeated: false },
    ],
    defaultScenes: ['商业拍摄', '人像写真', '产品摄影', '活动记录', '视频剪辑'],
  },
  '咨询服务': {
    id: 'consult', name: '咨询服务', icon: '💼', color: '#22d3ee',
    gradient: 'linear-gradient(135deg, #22d3ee 0%, #06b6d4 100%)',
    topMetrics: [
      { income: '咨询费收入', expense: '运营成本', profit: '咨询净利', label: '本月咨询收入 ¥68,000' }
    ],
    taskTypes: { task: '咨询案', invoice: '差旅发票', collection: '咨询费催款', design: '报告排版', meeting: '客户会议', delivery: '方案交付' },
    buildings: [
      { id: 'bl1', name: '图书馆', icon: '📚', level: 1, maxLevel: 3, desc: '知识库', unlockLevel: 1, upgradeCost: 150, effect: '方案质量+15%/级', unlocked: true },
      { id: 'bl2', name: '会议室', icon: '🏛️', level: 1, maxLevel: 3, desc: '客户洽谈区', unlockLevel: 1, upgradeCost: 200, effect: '客户满意度+10%/级', unlocked: true },
      { id: 'bl3', name: '分析室', icon: '📊', level: 0, maxLevel: 3, desc: '数据分析区', unlockLevel: 2, upgradeCost: 400, effect: '分析效率+25%/级', unlocked: false },
      { id: 'bl4', name: 'VIP室', icon: '👑', level: 0, maxLevel: 2, desc: '大客户专区', unlockLevel: 3, upgradeCost: 500, effect: 'VIP单价+40%/级', unlocked: false },
    ],
    recommendedNPCs: ['小王(销售)', '小李(会计)', '阿花(行政)'],
    npcTitles: { 小李: '项目财务', 小王: '客户关系', 小美: '报告设计师', 老张: '物料专员', 阿花: '行政助理', 小刘: '知识运营' },
    welcome: '欢迎来到咨询世界！专业知识就是价值。',
    slogan: '用专业洞察驱动商业决策',
    bosses: [
      { id: 'b1', name: '大客户关系', icon: '🤝', hp: 2, maxHp: 2, type: 'urgent', desc: '大客户投诉，需要紧急处理！', reward: '经验×2 + VIP客户', timer: 360, defeated: false },
      { id: 'b2', name: '季度报告', icon: '📊', hp: 4, maxHp: 4, type: 'important', desc: '季度分析报告，数据量巨大', reward: '经验×3 + 报告大师', timer: 4320, defeated: false },
    ],
    defaultScenes: ['市场分析', '财务咨询', '战略规划', '团队培训', '方案设计'],
  },
  '教育培训': {
    id: 'edu', name: '教育培训', icon: '📚', color: '#34d399',
    gradient: 'linear-gradient(135deg, #34d399 0%, #10b981 100%)',
    topMetrics: [
      { income: '学费收入', expense: '教学成本', profit: '教学净利', label: '本月学费收入 ¥52,000' }
    ],
    taskTypes: { task: '课程', invoice: '教材发票', collection: '学费催款', design: '课件制作', meeting: '家长会', delivery: '教学交付' },
    buildings: [
      { id: 'bl1', name: '教室', icon: '🏫', level: 1, maxLevel: 3, desc: '教学区', unlockLevel: 1, upgradeCost: 200, effect: '学生容量+20%/级', unlocked: true },
      { id: 'bl2', name: '题库', icon: '📝', level: 1, maxLevel: 5, desc: '试题题库', unlockLevel: 1, upgradeCost: 150, effect: '题库+50题/级', unlocked: true },
      { id: 'bl3', name: '在线平台', icon: '🌐', level: 0, maxLevel: 3, desc: '在线教学', unlockLevel: 2, upgradeCost: 500, effect: '网课收入+30%/级', unlocked: false },
      { id: 'bl4', name: '录播室', icon: '🎙️', level: 0, maxLevel: 2, desc: '录制课程', unlockLevel: 3, upgradeCost: 400, effect: '课程产量+40%/级', unlocked: false },
    ],
    recommendedNPCs: ['小刘(运营)', '阿花(行政)', '小李(会计)'],
    npcTitles: { 小李: '教务财务', 小王: '招生顾问', 小美: '课件设计', 老张: '物资配送', 阿花: '教务助理', 小刘: '招生运营' },
    welcome: '欢迎来到教育世界！每一个孩子都是希望。',
    slogan: '教育不是灌输，而是点燃火焰',
    bosses: [
      { id: 'b1', name: '考试周', icon: '📝', hp: 5, maxHp: 5, type: 'urgent', desc: '本周要考3门课，学生压力大', reward: '经验×3 + 名师徽章', timer: 10080, defeated: false },
      { id: 'b2', name: '退课潮', icon: '😰', hp: 3, maxHp: 3, type: 'important', desc: '5个学生要退课，需要紧急挽留', reward: '金币×50 + 口碑维护', timer: 2880, defeated: false },
    ],
    defaultScenes: ['备课', '上课', '批改作业', '家长会', '招生宣传'],
  },
  '餐饮美食': {
    id: 'food', name: '餐饮美食', icon: '🍜', color: '#ff4d4f',
    gradient: 'linear-gradient(135deg, #ff4d4f 0%, #ff7875 100%)',
    topMetrics: [
      { income: '营业额', expense: '食材成本', profit: '营业净利', label: '本月营业额 ¥128,000' }
    ],
    taskTypes: { task: '菜品', invoice: '食材发票', collection: '团购催款', design: '菜单设计', meeting: '供应商洽谈', delivery: '外卖配送' },
    buildings: [
      { id: 'bl1', name: '后厨', icon: '👨‍🍳', level: 1, maxLevel: 5, desc: '核心烹饪区', unlockLevel: 1, upgradeCost: 300, effect: '出餐速度+15%/级', unlocked: true },
      { id: 'bl2', name: '前厅', icon: '🍽️', level: 1, maxLevel: 3, desc: '顾客用餐区', unlockLevel: 1, upgradeCost: 250, effect: '座位数+4/级', unlocked: true },
      { id: 'bl3', name: '仓库', icon: '📦', level: 0, maxLevel: 3, desc: '食材存储', unlockLevel: 2, upgradeCost: 200, effect: '食材保鲜+25%/级', unlocked: false },
      { id: 'bl4', name: '外卖区', icon: '🛵', level: 0, maxLevel: 3, desc: '外卖打包配送', unlockLevel: 2, upgradeCost: 250, effect: '外卖订单+30%/级', unlocked: false },
    ],
    recommendedNPCs: ['老张(司机)', '阿花(行政)', '小王(销售)'],
    npcTitles: { 小李: '收银财务', 小王: '团购销售', 小美: '菜单设计', 老张: '配送员', 阿花: '前台主管', 小刘: '外卖运营' },
    welcome: '欢迎来到餐饮世界！用心做好每一道菜。',
    slogan: '味道是最好的营销，服务是最好的招牌',
    bosses: [
      { id: 'b1', name: '用餐高峰', icon: '🔥', hp: 5, maxHp: 5, type: 'urgent', desc: '中午高峰期来了，订单暴增！', reward: '经验×3 + 高峰之王', timer: 180, defeated: false },
      { id: 'b2', name: '食安检查', icon: '🔍', hp: 2, maxHp: 2, type: 'important', desc: '市场监管局来检查了！', reward: '经验×2 + 信誉+20', timer: 720, defeated: false },
    ],
    defaultScenes: ['菜品研发', '食材采购', '外卖接单', '客人服务', '卫生清洁'],
  },
  '美容美发': {
    id: 'beauty', name: '美容美发', icon: '💇', color: '#e879a8',
    gradient: 'linear-gradient(135deg, #e879a8 0%, #ec4899 100%)',
    topMetrics: [
      { income: '服务费收入', expense: '产品成本', profit: '服务净利', label: '本月服务收入 ¥38,000' }
    ],
    taskTypes: { task: '预约', invoice: '产品发票', collection: '会员卡催款', design: '宣传单设计', meeting: 'VIP沟通', delivery: '上门服务' },
    buildings: [
      { id: 'bl1', name: '理发区', icon: '💇', level: 1, maxLevel: 3, desc: '核心服务区', unlockLevel: 1, upgradeCost: 200, effect: '服务效率+15%/级', unlocked: true },
      { id: 'bl2', name: '美甲区', icon: '💅', level: 1, maxLevel: 3, desc: '美甲专区', unlockLevel: 1, upgradeCost: 180, effect: '美甲单价+10%/级', unlocked: true },
      { id: 'bl3', name: '护肤区', icon: '🧴', level: 0, maxLevel: 3, desc: '美容护理', unlockLevel: 2, upgradeCost: 300, effect: '护理单价+20%/级', unlocked: false },
      { id: 'bl4', name: 'VIP室', icon: '👑', level: 0, maxLevel: 2, desc: '高端定制', unlockLevel: 3, upgradeCost: 500, effect: 'VIP服务+50%/级', unlocked: false },
    ],
    recommendedNPCs: ['阿花(行政)', '小王(销售)', '小刘(运营)'],
    npcTitles: { 小李: '收银财务', 小王: '会员顾问', 小美: '造型师', 老张: '送货员', 阿花: '前台接待', 小刘: '自媒体运营' },
    welcome: '欢迎来到美容美发！让每个人变美。',
    slogan: '美丽是力量，自信是最好化妆品',
    bosses: [
      { id: 'b1', name: '预约高峰', icon: '📅', hp: 4, maxHp: 4, type: 'urgent', desc: '周末全满，客人要等位了！', reward: '经验×3 + 忙碌之星', timer: 1440, defeated: false },
      { id: 'b2', name: '投诉危机', icon: '😤', hp: 2, maxHp: 2, type: 'important', desc: '有客人对服务不满意，需要安抚', reward: '经验×2 + 口碑维护', timer: 360, defeated: false },
    ],
    defaultScenes: ['美发服务', '美甲服务', '皮肤管理', '会员管理', '产品销售'],
  },
  '物流运输': {
    id: 'logistics', name: '物流运输', icon: '🚚', color: '#1e40af',
    gradient: 'linear-gradient(135deg, #1e40af 0%, #3b82f6 100%)',
    topMetrics: [
      { income: '运费收入', expense: '车辆成本', profit: '运营净利', label: '本月运费收入 ¥85,000' }
    ],
    taskTypes: { task: '运单', invoice: '油费发票', collection: '运费催款', design: '运单设计', meeting: '客户洽谈', delivery: '货物配送' },
    buildings: [
      { id: 'bl1', name: '车队', icon: '🚚', level: 1, maxLevel: 5, desc: '运输车辆', unlockLevel: 1, upgradeCost: 300, effect: '运力+20%/级', unlocked: true },
      { id: 'bl2', name: '仓储中心', icon: '🏗️', level: 1, maxLevel: 3, desc: '货物存储', unlockLevel: 1, upgradeCost: 250, effect: '仓储容量+50%/级', unlocked: true },
      { id: 'bl3', name: '调度中心', icon: '📡', level: 0, maxLevel: 3, desc: '智能调度', unlockLevel: 2, upgradeCost: 400, effect: '调度效率+25%/级', unlocked: false },
      { id: 'bl4', name: '维修站', icon: '🔧', level: 0, maxLevel: 2, desc: '车辆维护', unlockLevel: 2, upgradeCost: 350, effect: '车辆故障率-30%/级', unlocked: false },
    ],
    recommendedNPCs: ['老张(司机)', '小王(销售)', '小李(会计)'],
    npcTitles: { 小李: '运费会计', 小王: '业务拓展', 小美: '运单设计', 老张: '首席司机', 阿花: '调度员', 小刘: '物流营销' },
    welcome: '欢迎来到物流运输！让每个包裹准时到达。',
    slogan: '速度是生命，安全是底线',
    bosses: [
      { id: 'b1', name: '配送高峰', icon: '📦', hp: 5, maxHp: 5, type: 'urgent', desc: '双十一来了，1000个包裹要送！', reward: '经验×3 + 配送之王', timer: 10080, defeated: false },
      { id: 'b2', name: '货物损毁', icon: '💥', hp: 2, maxHp: 2, type: 'important', desc: '一批货物在途中损毁了', reward: '经验×2 + 理赔大师', timer: 1440, defeated: false },
    ],
    defaultScenes: ['调度派车', '路线规划', '货物追踪', '客户签收', '车辆维护'],
  },
  'IT外包': {
    id: 'it', name: 'IT外包', icon: '💻', color: '#6366f1',
    gradient: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
    topMetrics: [
      { income: '项目收入', expense: '人力成本', profit: '项目净利', label: '本月项目收入 ¥95,000' }
    ],
    taskTypes: { task: '项目', invoice: '设备发票', collection: '项目款催款', design: 'UI设计', meeting: '需求评审', delivery: '上线交付' },
    buildings: [
      { id: 'bl1', name: '开发室', icon: '💻', level: 1, maxLevel: 5, desc: '代码开发区', unlockLevel: 1, upgradeCost: 250, effect: '开发效率+15%/级', unlocked: true },
      { id: 'bl2', name: '测试室', icon: '🧪', level: 1, maxLevel: 3, desc: '质量保证', unlockLevel: 1, upgradeCost: 200, effect: 'Bug率-20%/级', unlocked: true },
      { id: 'bl3', name: '服务器', icon: '🖥️', level: 0, maxLevel: 3, desc: '部署运维', unlockLevel: 2, upgradeCost: 500, effect: '部署速度+30%/级', unlocked: false },
      { id: 'bl4', name: '学习中心', icon: '📖', level: 0, maxLevel: 3, desc: '技术培训', unlockLevel: 3, upgradeCost: 300, effect: '团队技能+10%/级', unlocked: false },
    ],
    recommendedNPCs: ['小美(设计)', '阿花(行政)', '小李(会计)'],
    npcTitles: { 小李: '项目财务', 小王: '客户经理', 小美: 'UI设计师', 老张: 'IT支持', 阿花: '项目经理', 小刘: '技术文档' },
    welcome: '欢迎来到IT外包世界！代码改变世界。',
    slogan: '技术是工具，交付价值才是目的',
    bosses: [
      { id: 'b1', name: '上线日', icon: '🚀', hp: 4, maxHp: 4, type: 'urgent', desc: '明天系统上线，Bug还没修完！', reward: '经验×3 + "上线达人"徽章', timer: 720, defeated: false },
      { id: 'b2', name: '需求变更王', icon: '🔄', hp: 3, maxHp: 3, type: 'important', desc: '客户又改需求了！第三次了！', reward: '经验×2 + 变更管理大师', timer: 4320, defeated: false },
    ],
    defaultScenes: ['需求分析', '代码开发', '测试验收', '上线部署', '运维监控'],
  },
  '自媒体/博主': {
    id: 'media', name: '自媒体/博主', icon: '✍️', color: '#fbbf24',
    gradient: 'linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%)',
    topMetrics: [
      { income: '广告收入', expense: '创作成本', profit: '创作净利', label: '本月广告收入 ¥28,000' }
    ],
    taskTypes: { task: '内容', invoice: '设备发票', collection: '广告费催款', design: '封面设计', meeting: '商务洽谈', delivery: '内容发布' },
    buildings: [
      { id: 'bl1', name: '内容中心', icon: '✍️', level: 1, maxLevel: 5, desc: '内容创作区', unlockLevel: 1, upgradeCost: 150, effect: '创作效率+20%/级', unlocked: true },
      { id: 'bl2', name: '数据分析', icon: '📊', level: 1, maxLevel: 3, desc: '流量分析', unlockLevel: 1, upgradeCost: 200, effect: '数据分析+25%/级', unlocked: true },
      { id: 'bl3', name: '剪辑室', icon: '🎬', level: 0, maxLevel: 3, desc: '视频制作', unlockLevel: 2, upgradeCost: 350, effect: '视频产量+40%/级', unlocked: false },
      { id: 'bl4', name: '粉丝群', icon: '💬', level: 0, maxLevel: 2, desc: '粉丝运营', unlockLevel: 3, upgradeCost: 250, effect: '粉丝增长+30%/级', unlocked: false },
    ],
    recommendedNPCs: ['小刘(运营)', '小美(设计)', '小王(销售)'],
    npcTitles: { 小李: '商务财务', 小王: '商务合作', 小美: '封面设计师', 老张: '快递收发', 阿花: '数据助理', 小刘: '全平台运营' },
    welcome: '欢迎来到自媒体世界！用内容影响世界。',
    slogan: '每个内容创作者都是一座灯塔',
    bosses: [
      { id: 'b1', name: '流量危机', icon: '📉', hp: 2, maxHp: 2, type: 'urgent', desc: '数据突然下滑，急需爆款内容！', reward: '经验×2 + "流量密码"徽章', timer: 360, defeated: false },
      { id: 'b2', name: '爆款挑战', icon: '🔥', hp: 5, maxHp: 5, type: 'important', desc: '冲10万赞挑战！', reward: '金币×100 + 爆款制造者', timer: 10080, defeated: false },
    ],
    defaultScenes: ['选题策划', '内容创作', '视频剪辑', '粉丝互动', '商务对接'],
  },
}

// 默认行业配置（通用模板）
export const defaultIndustryConfig: IndustryConfig = {
  id: 'general', name: '通用', icon: '🏢', color: '#00f0ff',
  gradient: 'linear-gradient(135deg, #00f0ff 0%, #3b82f6 100%)',
  topMetrics: [
    { income: '收入', expense: '支出', profit: '净利', label: '本月进账 ¥42,500' }
  ],
  taskTypes: { task: '任务', invoice: '发票', collection: '催款', design: '设计', meeting: '会议', delivery: '交付' },
  buildings: [
    { id: 'bl1', name: '办公室', icon: '🏢', level: 1, maxLevel: 5, desc: '公司总部', unlockLevel: 1, upgradeCost: 200, effect: 'NPC槽位+2/级', unlocked: true },
    { id: 'bl2', name: '工作台', icon: '💻', level: 1, maxLevel: 5, desc: 'AI识别中心', unlockLevel: 1, upgradeCost: 150, effect: 'AI识别速度+20%/级', unlocked: true },
    { id: 'bl3', name: 'AI中心', icon: '🤖', level: 0, maxLevel: 5, desc: '高级AI功能', unlockLevel: 3, upgradeCost: 500, effect: '每日免费AI调用+1/级', unlocked: false },
    { id: 'bl4', name: '员工宿舍', icon: '🏠', level: 0, maxLevel: 3, desc: 'NPC休息区', unlockLevel: 3, upgradeCost: 300, effect: 'NPC容量+2/级', unlocked: false },
  ],
  recommendedNPCs: ['小李(会计)', '小王(销售)', '阿花(行政)'],
  npcTitles: { 小李: '会计', 小王: '销售', 小美: '设计', 老张: '司机', 阿花: '行政', 小刘: '运营' },
  welcome: '欢迎来到一人公司助手！',
  slogan: '每个人开公司，都有自己的优势',
  bosses: [
    { id: 'b1', name: '税务大魔王', icon: '👹', hp: 3, maxHp: 3, type: 'urgent', desc: '本月增值税申报今日截止！', reward: '经验×3 + "避税大师"徽章', timer: 360, defeated: false },
    { id: 'b2', name: '催款副本', icon: '💰', hp: 2, maxHp: 2, type: 'important', desc: '客户尾款逾期，需催收', reward: '金币×50', timer: 10080, defeated: false },
  ],
  defaultScenes: ['催款', '记账', '派单', '归档', '设计'],
}

// 获取行业配置
export function getIndustryConfig(industry: string): IndustryConfig {
  return industryConfigs[industry] || defaultIndustryConfig
}

// 所有可用行业列表
export const availableIndustries = [
  { id: 'ad', name: '广告传媒', icon: '📢', color: '#8b5cf6' },
  { id: 'ecom', name: '电商零售', icon: '🛒', color: '#ff6b35' },
  { id: 'design', name: '设计工作室', icon: '🎨', color: '#ec4899' },
  { id: 'photo', name: '摄影摄像', icon: '📸', color: '#4a9eff' },
  { id: 'consult', name: '咨询服务', icon: '💼', color: '#22d3ee' },
  { id: 'edu', name: '教育培训', icon: '📚', color: '#34d399' },
  { id: 'food', name: '餐饮美食', icon: '🍜', color: '#ff4d4f' },
  { id: 'beauty', name: '美容美发', icon: '💇', color: '#e879a8' },
  { id: 'logistics', name: '物流运输', icon: '🚚', color: '#1e40af' },
  { id: 'it', name: 'IT外包', icon: '💻', color: '#6366f1' },
  { id: 'media', name: '自媒体/博主', icon: '✍️', color: '#fbbf24' },
] as const

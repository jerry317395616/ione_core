// ==================== 高级感主题系统 ====================
// 设计理念：参照系决定价值感知
// 喷泉效应：同样的钱，放在生态位里就觉得值
// 所有版面展示的不是"花了多少钱"，而是"构建了多强的生态位"

export type LayoutMode = 'standard' | 'minimal' | 'rich'

export interface LayoutTheme {
  id: LayoutMode
  name: string
  bgStyle: 'gradient' | 'solid' | 'glass'
  bgColor: string
  bgGradient: string | null
  cardBg: string
  cardBorder: string
  cardShadow: string
  textColor1: string
  textColor2: string
  textColor3: string
  textColor4: string
  accent: string
  accentLight: string
  accentGradient: string
  success: string
  warning: string
  danger: string
  info: string
  showNoise: boolean
  showGrain: boolean
  borderRadius: number
  fontFamily: string
  glowColor: string
  navStyle: 'standard' | 'minimal' | 'dock'
  blurIntensity: number
}

const themes: Record<LayoutMode, LayoutTheme> = {
  standard: {
    id: 'standard', name: 'Ant 标准',
    bgStyle: 'solid', bgColor: '#f5f5f5', bgGradient: null,
    cardBg: '#ffffff', cardBorder: '#eeeeee',
    cardShadow: 'none',
    textColor1: '#333333', textColor2: '#666666', textColor3: '#999999', textColor4: '#cccccc',
    accent: '#1677ff', accentLight: '#4096ff',
    accentGradient: '#1677ff',
    success: '#00b578', warning: '#ff8f1f', danger: '#ff3141', info: '#1677ff',
    showNoise: false, showGrain: false,
    borderRadius: 8,
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Helvetica Neue', Helvetica, 'Segoe UI', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif",
    glowColor: 'rgba(22, 119, 255, 0.06)',
    navStyle: 'standard', blurIntensity: 0,
  },
  minimal: {
    id: 'minimal', name: 'Ant 简洁',
    bgStyle: 'solid', bgColor: '#ffffff', bgGradient: null,
    cardBg: '#ffffff', cardBorder: '#f0f0f0',
    cardShadow: 'none',
    textColor1: '#333333', textColor2: '#666666', textColor3: '#999999', textColor4: '#cccccc',
    accent: '#1677ff', accentLight: '#4096ff',
    accentGradient: '#1677ff',
    success: '#00b578', warning: '#ff8f1f', danger: '#ff3141', info: '#1677ff',
    showNoise: false, showGrain: false,
    borderRadius: 4,
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Helvetica Neue', Helvetica, 'Segoe UI', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif",
    glowColor: 'rgba(22, 119, 255, 0.03)',
    navStyle: 'minimal', blurIntensity: 0,
  },
  rich: {
    id: 'rich', name: 'Ant 醒目',
    bgStyle: 'solid', bgColor: '#f5f7fa', bgGradient: null,
    cardBg: '#ffffff', cardBorder: '#d9d9d9',
    cardShadow: '0 2px 8px rgba(0, 0, 0, 0.06)',
    textColor1: '#1f1f1f', textColor2: '#595959', textColor3: '#8c8c8c', textColor4: '#bfbfbf',
    accent: '#0958d9', accentLight: '#1677ff',
    accentGradient: '#0958d9',
    success: '#389e0d', warning: '#d46b08', danger: '#cf1322', info: '#0958d9',
    showNoise: false, showGrain: false,
    borderRadius: 12,
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Helvetica Neue', Helvetica, 'Segoe UI', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif",
    glowColor: 'rgba(9, 88, 217, 0.06)',
    navStyle: 'standard', blurIntensity: 0,
  },
}

export function getLayoutTheme(mode: LayoutMode): LayoutTheme {
  return themes[mode] || themes['standard']
}

// ==================== 价值参照系（喷泉效应）====================
// 核心洞察：同一笔钱，参照系不同，价值感知完全相反
// 喷泉效应：在家开水龙头觉得亏 → 小区喷泉觉得值
// 解法：把"支出"重新框定为"生态位构建"

export interface ValueFrame {
  id: string
  label: string
  icon: string
  referencePoint: string
  valueHighlight: string
  comparison: string
  ecosystemBenefit: string
}

export const valueFrames: ValueFrame[] = [
  {
    id: 'ecosystem', label: '生态位投入', icon: '🌊',
    referencePoint: '公司整体运营生态',
    valueHighlight: '不是支出，是构建运营护城河',
    comparison: '就像小区喷泉，你看了觉得值，因为它属于公共生态',
    ecosystemBenefit: '让每个NPC成为你的生态位节点',
  },
  {
    id: 'leverage', label: '杠杆效应', icon: '⚡',
    referencePoint: '你的时间价值',
    valueHighlight: '用金钱买时间，是最高效的杠杆',
    comparison: '花¥200雇人做事 = 省下3小时做¥1000/小时的事',
    ecosystemBenefit: '每雇一个NPC，你的时间杠杆+1',
  },
  {
    id: 'compound', label: '复利效应', icon: '📈',
    referencePoint: '长期资产积累',
    valueHighlight: '每天的NPC成长 = 你的数字资产增值',
    comparison: '小区喷泉每天都在喷水，你的资产每天都在增值',
    ecosystemBenefit: 'NPC经验值积累 = 你的无形资产',
  },
]

export const defaultFrame: ValueFrame = valueFrames[0]

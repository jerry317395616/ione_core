import { useEffect, useState, type ReactNode } from 'react'
import {
  Button,
  Card,
  Empty,
  Grid,
  List,
  NoticeBar,
  ProgressBar,
  Tag,
} from 'antd-mobile'
import {
  AddSquareOutline,
  MessageOutline,
  PayCircleOutline,
  RightOutline,
  UserContactOutline,
} from 'antd-mobile-icons'
import {
  getFrappeDashboard,
  getFrappeUrl,
  type FrappeDashboard,
} from '../lib/frappeCore'
import type { LayoutMode } from '../LayoutThemes'
import type { AppState, TabId } from '../types'

interface QuickEntry {
  icon: ReactNode
  title: string
  description: string
  tone: 'purple' | 'blue' | 'orange' | 'green'
  tab?: TabId
  route?: string
}

const QUICK_ENTRIES: QuickEntry[] = [
  {
    icon: <AddSquareOutline />,
    title: '记录',
    description: '语音/拍照/文本',
    tone: 'purple',
    tab: 1,
  },
  {
    icon: <MessageOutline />,
    title: '问AI',
    description: '政策/合规/指南',
    tone: 'blue',
    tab: 9,
  },
  {
    icon: <UserContactOutline />,
    title: '客户管理',
    description: 'CRM 跟进记录',
    tone: 'orange',
    route: '/crm/leads',
  },
  {
    icon: <PayCircleOutline />,
    title: '财务中心',
    description: '收支/利润',
    tone: 'green',
    tab: 5,
  },
]

export default function HomePage({
  state,
  setActiveTab,
}: {
  industry: string
  state: AppState
  setState: (state: Partial<AppState>) => void
  layoutMode: LayoutMode
  setActiveTab?: (tab: TabId) => void
}) {
  const [frappeDashboard, setFrappeDashboard] = useState<FrappeDashboard | null>(null)
  const [frappeError, setFrappeError] = useState('')
  const [frappeLoading, setFrappeLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    getFrappeDashboard()
      .then(data => {
        if (cancelled) return
        setFrappeDashboard(data)
        setFrappeError('')
      })
      .catch(error => {
        if (cancelled) return
        setFrappeError(error instanceof Error ? error.message : 'Frappe 服务暂时不可用')
      })
      .finally(() => {
        if (!cancelled) setFrappeLoading(false)
      })

    return () => { cancelled = true }
  }, [])

  const overviewMetrics = frappeDashboard?.overview || []
  const todayTodoCount = overviewMetrics.find(metric => metric.key === 'today_todos')?.value
  const profitProgress = frappeDashboard?.profit_progress

  const today = new Date()
  const weekDays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const greeting = today.getHours() < 12 ? '早上好' : today.getHours() < 18 ? '下午好' : '晚上好'

  const formatMoney = (value: number | null, currency = frappeDashboard?.currency || 'CNY') => {
    if (value === null) return '--'
    return new Intl.NumberFormat('zh-CN', {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
    }).format(value)
  }

  const formatOverviewValue = (value: number | null, format: 'number' | 'currency') => {
    if (value === null) return '--'
    return format === 'currency' ? formatMoney(value) : value.toLocaleString('zh-CN')
  }

  const formatTodoDescription = (source: string, dueDate?: string | null) => {
    if (!dueDate) return source
    return `${source} · 截止 ${dueDate}`
  }

  const openQuickEntry = (entry: QuickEntry) => {
    if (entry.tab !== undefined) {
      setActiveTab?.(entry.tab)
      return
    }
    if (entry.route) {
      window.open(getFrappeUrl(entry.route), '_blank', 'noopener,noreferrer')
    }
  }

  return (
    <div className="page adm-home-page">
      <section className="home-heading">
        <div>
          <h1>{greeting}，{state.userName}</h1>
          <p>
            {frappeDashboard?.company || 'manager.myyr.top'} · {today.getFullYear()}年{today.getMonth() + 1}月{today.getDate()}日 · {weekDays[today.getDay()]}
          </p>
        </div>
        <Tag color={frappeError ? 'danger' : 'success'} fill="outline">
          {frappeError ? '连接异常' : '实时'}
        </Tag>
      </section>

      {frappeError && <NoticeBar color="alert" content={frappeError} className="home-notice" />}

      <section className="home-section">
        <div className="home-section-header">
          <h2>今日待办</h2>
          <span>{frappeDashboard?.todos.length || 0} 项</span>
        </div>
        {frappeLoading && <div className="frappe-loading" role="status">正在读取今日待办...</div>}
        {!frappeLoading && frappeDashboard && frappeDashboard.todos.length === 0 && (
          <div className="home-empty"><Empty description="今日暂无待办" /></div>
        )}
        {frappeDashboard && frappeDashboard.todos.length > 0 && (
          <List className="home-list frappe-todo-list">
            {frappeDashboard.todos.map(item => (
              <List.Item
                key={item.id}
                clickable
                description={formatTodoDescription(item.source, item.due_date)}
                extra={
                  <Tag color={item.priority === 'High' ? 'danger' : 'primary'} fill="outline">
                    {item.status}
                  </Tag>
                }
                onClick={() => window.open(getFrappeUrl(item.route), '_blank', 'noopener,noreferrer')}
              >
                {item.title}
              </List.Item>
            ))}
          </List>
        )}
      </section>

      <section className="home-section">
        <div className="home-section-header">
          <h2>快捷入口</h2>
        </div>
        <Grid columns={2} gap={8} className="home-quick-entry-grid">
          {QUICK_ENTRIES.map(entry => (
            <Grid.Item key={entry.title}>
              <button
                type="button"
                className={`home-quick-entry home-quick-entry-${entry.tone}`}
                aria-label={`${entry.title}：${entry.description}`}
                onClick={() => openQuickEntry(entry)}
              >
                <span className="home-quick-entry-icon" aria-hidden="true">{entry.icon}</span>
                <strong>{entry.title}</strong>
                <small>{entry.description}</small>
                <span className="home-quick-entry-watermark" aria-hidden="true">{entry.icon}</span>
              </button>
            </Grid.Item>
          ))}
        </Grid>
      </section>

      <section className="home-section">
        <div className="home-section-header">
          <h2>今日概览</h2>
          {todayTodoCount !== null && todayTodoCount !== undefined && <span>{todayTodoCount} 项待办</span>}
        </div>
        {frappeLoading && <div className="frappe-loading" role="status">正在读取经营数据...</div>}
        {!frappeLoading && overviewMetrics.length > 0 && (
          <Grid columns={2} gap={8}>
            {overviewMetrics.map(metric => (
              <Grid.Item key={metric.key}>
                <button
                  type="button"
                  className="overview-metric-card"
                  disabled={!metric.available}
                  onClick={() => window.open(getFrappeUrl(metric.route), '_blank', 'noopener,noreferrer')}
                >
                  <span>{metric.label}</span>
                  <strong className={metric.tone}>{formatOverviewValue(metric.value, metric.format)}</strong>
                  <small>{metric.available ? metric.source : '暂无查看权限'}</small>
                </button>
              </Grid.Item>
            ))}
          </Grid>
        )}
      </section>

      {profitProgress && (
        <Card
          title="本月利润目标"
          extra={profitProgress.percent !== null ? <Tag color="success">{Math.round(profitProgress.percent)}%</Tag> : null}
          className="home-section profit-card"
        >
          {profitProgress.target !== null && profitProgress.actual !== null ? (
            <>
              <div className="profit-summary">
                <span>实际 {formatMoney(profitProgress.actual, profitProgress.currency)}</span>
                <span>目标 {formatMoney(profitProgress.target, profitProgress.currency)}</span>
              </div>
              <ProgressBar
                percent={Math.min(100, Math.max(0, profitProgress.percent || 0))}
                style={{ '--fill-color': '#20b26b' }}
              />
            </>
          ) : (
            <div className="profit-target-empty">
              <span>{profitProgress.actual === null ? '暂无财务查看权限' : '尚未设置本月利润目标'}</span>
              {profitProgress.actual !== null && (
                <Button
                  size="mini"
                  fill="none"
                  onClick={() => { window.open(getFrappeUrl(profitProgress.route), '_blank', 'noopener,noreferrer') }}
                >
                  设置目标 <RightOutline />
                </Button>
              )}
            </div>
          )}
        </Card>
      )}

      {frappeDashboard && frappeDashboard.metrics.length > 0 && (
        <section className="home-section">
          <div className="home-section-header">
            <h2>应用动态</h2>
            <span>实时汇总</span>
          </div>
          <Grid columns={2} gap={8}>
            {frappeDashboard.metrics.map(metric => (
              <Grid.Item key={metric.key}>
                <button
                  type="button"
                  className="frappe-metric"
                  onClick={() => window.open(getFrappeUrl(metric.route), '_blank', 'noopener,noreferrer')}
                >
                  <span>{metric.label}</span>
                  <strong>{metric.value.toLocaleString('zh-CN')}</strong>
                  <small>{metric.source}</small>
                </button>
              </Grid.Item>
            ))}
          </Grid>
        </section>
      )}

    </div>
  )
}

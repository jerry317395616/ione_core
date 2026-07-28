import React from 'react'
import { Button, DotLoading, ErrorBlock } from 'antd-mobile'
import { RightOutline } from 'antd-mobile-icons'
import { useRemoteData } from '../hooks/useRemoteData'
import { getMobileNotifications, openFrappeRoute } from '../lib/mobileData'
import { getLayoutTheme, type LayoutMode } from '../LayoutThemes'

const priorityTone: Record<string, string> = {
  Urgent: '#dc2626',
  High: '#ea580c',
  紧急: '#dc2626',
  关键: '#dc2626',
  高: '#ea580c',
  中: '#ca8a04',
}

export default function ProactiveCarePage({ layoutMode = 'standard' }: { layoutMode?: LayoutMode }) {
  const theme = getLayoutTheme(layoutMode)
  const { data, loading, error, refresh } = useRemoteData(getMobileNotifications)
  const items = data?.notifications ?? []

  if (loading && !data) {
    return <div className="page remote-page-state"><DotLoading color="primary" /> 正在读取提醒</div>
  }
  if (error && !data) {
    return <div className="page"><ErrorBlock title="提醒加载失败" description={error} /><Button block onClick={refresh}>重新加载</Button></div>
  }

  return (
    <div className="page" style={{ background: theme.bgColor }}>
      <div className="page-title">主动关怀</div>
      <div className="page-desc">来自 Frappe 待办和 I-ONE 审批的实时提醒</div>
      <div className="mobile-metric-grid">
        {[
          ['全部提醒', items.length],
          ['待审批', items.filter(item => item.source === 'I-ONE 审批').length],
          ['紧急', items.filter(item => ['Urgent', '紧急', '关键', '高'].includes(item.priority)).length],
          ['今日到期', items.filter(item => item.due_date?.slice(0, 10) === new Date().toISOString().slice(0, 10)).length],
        ].map(([label, value]) => (
          <div className="stat-card" key={String(label)}>
            <strong style={{ color: theme.accentLight }}>{String(value)}</strong>
            <small>{String(label)}</small>
          </div>
        ))}
      </div>

      <div className="section-header mobile-section-gap"><span className="section-title">需要关注</span></div>
      {items.map(item => (
        <button className="mobile-notification-card" key={item.id} onClick={() => openFrappeRoute(item.route)}>
          <i style={{ background: priorityTone[item.priority] || theme.info }} />
          <span>
            <strong>{item.title}</strong>
            <small>{item.message}</small>
            <em>{item.source}{item.due_date ? ` · ${item.due_date}` : ''}</em>
          </span>
          <RightOutline />
        </button>
      ))}
      {!items.length && <div className="mobile-empty">当前没有待办或待审批提醒</div>}
    </div>
  )
}

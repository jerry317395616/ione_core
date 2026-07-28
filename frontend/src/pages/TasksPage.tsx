import React from 'react'
import { Button, DotLoading, ErrorBlock, ProgressBar } from 'antd-mobile'
import { CheckCircleOutline, ClockCircleOutline, RightOutline } from 'antd-mobile-icons'
import { useRemoteData } from '../hooks/useRemoteData'
import { getMobileTaskCenter, openFrappeRoute } from '../lib/mobileData'
import { getLayoutTheme, type LayoutMode } from '../LayoutThemes'

const priorityColor: Record<string, string> = {
  Urgent: '#dc2626',
  High: '#ea580c',
  紧急: '#dc2626',
  高: '#ea580c',
  Medium: '#ca8a04',
  普通: '#ca8a04',
}

export default function TasksPage({ layoutMode }: { layoutMode: LayoutMode }) {
  const theme = getLayoutTheme(layoutMode)
  const { data, loading, error, refresh } = useRemoteData(getMobileTaskCenter)

  if (loading && !data) {
    return <div className="page remote-page-state"><DotLoading color="primary" /> 正在读取 Frappe 待办</div>
  }
  if (error && !data) {
    return <div className="page"><ErrorBlock status="default" title="任务中心加载失败" description={error} /><Button block onClick={refresh}>重新加载</Button></div>
  }

  const todos = data?.todos ?? []
  const plans = data?.plans ?? []
  const achievements = data?.achievements ?? []

  return (
    <div className="page" style={{ background: theme.bgColor }}>
      <div className="page-title">任务与成长</div>
      <div className="page-desc">Frappe 待办、AI 工作单和成长计划统一呈现</div>

      <div className="section-header"><span className="section-title">今日待办</span></div>
      {todos.map(item => (
        <button className="mobile-data-row" key={item.id} onClick={() => openFrappeRoute(item.route)}>
          <span className="mobile-data-icon"><ClockCircleOutline /></span>
          <span className="mobile-data-main">
            <strong>{item.title}</strong>
            <small>{item.source}{item.due_date ? ` · ${item.due_date}` : ''}</small>
          </span>
          <span style={{ color: priorityColor[item.priority || ''] || theme.textColor3 }}>{item.status}</span>
          <RightOutline />
        </button>
      ))}
      {!todos.length && <div className="mobile-empty">当前没有待处理事项</div>}

      <div className="section-header mobile-section-gap"><span className="section-title">成长计划</span></div>
      {plans.map(plan => (
        <button className="mobile-plan-card" key={plan.name} onClick={() => openFrappeRoute(plan.route)}>
          <span className="mobile-card-heading">
            <strong>{plan.title}</strong>
            <small>{plan.status}</small>
          </span>
          <span className="mobile-muted">{plan.category || '未分类'}{plan.end_date ? ` · 目标 ${plan.end_date}` : ''}</span>
          <ProgressBar percent={Number(plan.progress || 0)} style={{ '--fill-color': theme.accentLight }} />
          <span className="mobile-progress-label">{Number(plan.progress || 0).toFixed(0)}%</span>
        </button>
      ))}
      {!plans.length && <div className="mobile-empty">尚未创建成长计划，可在 I-ONE AI 中新建</div>}

      <div className="section-header mobile-section-gap"><span className="section-title">已获成就</span></div>
      <div className="mobile-achievement-grid">
        {achievements.map(item => (
          <div className="mobile-achievement" key={item.name}>
            <CheckCircleOutline fontSize={22} color={theme.success} />
            <strong>{item.title}</strong>
            <small>{item.description || item.achievement_type || '业务成就'}</small>
            <span>+{item.points || 0} 经验</span>
          </div>
        ))}
      </div>
      {!achievements.length && <div className="mobile-empty">完成真实业务任务后，成就会显示在这里</div>}
    </div>
  )
}

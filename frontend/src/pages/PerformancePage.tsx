import React from 'react'
import { Button, DotLoading, ErrorBlock, ProgressBar } from 'antd-mobile'
import { RightOutline } from 'antd-mobile-icons'
import { useRemoteData } from '../hooks/useRemoteData'
import { getMobileActivity, openFrappeRoute } from '../lib/mobileData'
import { getLayoutTheme, type LayoutMode } from '../LayoutThemes'

const statusColor: Record<string, string> = {
  已完成: '#16a34a',
  执行中: '#2563eb',
  已排队: '#7c3aed',
  等待确认: '#ca8a04',
  执行失败: '#dc2626',
}

export default function PerformancePage({ layoutMode = 'standard' }: { layoutMode?: LayoutMode }) {
  const theme = getLayoutTheme(layoutMode)
  const { data, loading, error, refresh } = useRemoteData(getMobileActivity)

  if (loading && !data) {
    return <div className="page remote-page-state"><DotLoading color="primary" /> 正在读取运行记录</div>
  }
  if (error && !data) {
    return <div className="page"><ErrorBlock title="运行记录加载失败" description={error} /><Button block onClick={refresh}>重新加载</Button></div>
  }

  const stats = data?.stats ?? { total: 0, completed: 0, running: 0, failed: 0 }
  return (
    <div className="page" style={{ background: theme.bgColor }}>
      <div className="page-title">AI 工单运行记录</div>
      <div className="page-desc">来自 I-ONE AI Task 与运行日志的真实状态</div>

      <div className="mobile-metric-grid">
        {[
          ['最近工单', stats.total, theme.info],
          ['已完成', stats.completed, theme.success],
          ['处理中', stats.running, theme.warning],
          ['失败', stats.failed, theme.danger],
        ].map(([label, value, color]) => (
          <div className="stat-card" key={String(label)}>
            <strong style={{ color: String(color) }}>{String(value)}</strong>
            <small>{String(label)}</small>
          </div>
        ))}
      </div>

      <div className="section-header mobile-section-gap"><span className="section-title">工作单</span></div>
      {(data?.tasks ?? []).map(task => (
        <button className="mobile-plan-card" key={task.name} onClick={() => openFrappeRoute(task.route)}>
          <span className="mobile-card-heading">
            <strong>{task.title}</strong>
            <small style={{ color: statusColor[task.status] || theme.textColor3 }}>{task.status}</small>
          </span>
          <span className="mobile-muted">{task.assigned_agent || '未分配 AI 员工'} · {new Date(task.modified).toLocaleString('zh-CN')}</span>
          <ProgressBar percent={Number(task.progress || 0)} style={{ '--fill-color': statusColor[task.status] || theme.info }} />
          {task.error_message && <span className="mobile-error-text">{task.error_message}</span>}
        </button>
      ))}
      {!data?.tasks.length && <div className="mobile-empty">目前没有 AI 工作单</div>}

      <div className="section-header mobile-section-gap"><span className="section-title">最近运行日志</span></div>
      <div className="mobile-timeline">
        {(data?.logs ?? []).map(log => (
          <div key={log.name}>
            <i style={{ background: log.level === '错误' ? theme.danger : log.level === '警告' ? theme.warning : theme.info }} />
            <span>
              <strong>{log.event_type}</strong>
              <small>{new Date(log.creation).toLocaleString('zh-CN')} · {log.agent || log.model_name || '系统'}</small>
              <p>{log.message}</p>
            </span>
            {log.task && <button aria-label="打开工作单" onClick={() => openFrappeRoute(`/app/i-one-ai-task/${encodeURIComponent(log.task)}`)}><RightOutline /></button>}
          </div>
        ))}
      </div>
      {!data?.logs.length && <div className="mobile-empty">尚无运行日志</div>}
    </div>
  )
}

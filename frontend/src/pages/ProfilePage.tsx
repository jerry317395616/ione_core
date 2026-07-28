import React from 'react'
import { Avatar, Button, DotLoading, ErrorBlock } from 'antd-mobile'
import { RightOutline } from 'antd-mobile-icons'
import { useRemoteData } from '../hooks/useRemoteData'
import { getMobileProfile, openFrappeRoute } from '../lib/mobileData'
import { getLayoutTheme, type LayoutMode } from '../LayoutThemes'
import type { AppState, TabId } from '../types'

export default function ProfilePage({ layoutMode, state, setState, setActiveTab }: {
  layoutMode: LayoutMode
  state: AppState
  setState: (value: Partial<AppState>) => void
  setActiveTab: (tab: TabId) => void
}) {
  const theme = getLayoutTheme(layoutMode)
  const { data, loading, error, refresh } = useRemoteData(getMobileProfile)

  if (loading && !data) {
    return <div className="page remote-page-state"><DotLoading color="primary" /> 正在读取公司档案</div>
  }
  if (error && !data) {
    return <div className="page"><ErrorBlock title="公司档案加载失败" description={error} /><Button block onClick={refresh}>重新加载</Button></div>
  }

  const company = data?.company ?? {}
  return (
    <div className="page" style={{ background: theme.bgColor }}>
      <div className="mobile-profile-head">
        <Avatar src={data?.user.user_image || ''} fallback={data?.user.full_name?.slice(0, 1) || 'I'} />
        <span>
          <strong>{data?.user.full_name || state.userName}</strong>
          <small>{data?.user.username}</small>
        </span>
      </div>

      <div className="card mobile-company-card">
        <strong>{company.company_name || company.name || '尚未设置默认公司'}</strong>
        <small>{[company.country, company.domain, company.default_currency].filter(Boolean).join(' · ') || '请在 ERPNext 公司资料中维护信息'}</small>
        {company.tax_id && <p>税号：{company.tax_id}</p>}
        {company.date_of_establishment && <p>成立日期：{company.date_of_establishment}</p>}
      </div>

      <div className="mobile-metric-grid">
        {[
          ['在职员工', data?.employee_count ?? '—'],
          ['部门', data?.department_count ?? '—'],
          ['经验值', data?.totals.points ?? 0],
          ['成就', data?.achievements.length ?? 0],
        ].map(([label, value]) => (
          <div className="stat-card" key={String(label)}>
            <strong style={{ color: theme.accentLight }}>{String(value)}</strong>
            <small>{String(label)}</small>
          </div>
        ))}
      </div>

      <div className="section-header mobile-section-gap"><span className="section-title">Frappe 应用</span></div>
      <div className="mobile-app-grid">
        {(data?.apps ?? []).map(app => (
          <button key={app.name} onClick={() => openFrappeRoute(app.route)}>
            {app.logo ? <img src={app.logo} alt="" /> : <span>{app.title.slice(0, 1)}</span>}
            <strong>{app.title}</strong>
            <small>{app.category}</small>
          </button>
        ))}
      </div>

      <div className="section-header mobile-section-gap"><span className="section-title">显示主题</span></div>
      <div className="mobile-segmented-buttons">
        {(['standard', 'minimal', 'rich'] as LayoutMode[]).map(mode => (
          <button
            key={mode}
            className={state.layoutMode === mode ? 'active' : ''}
            onClick={() => setState({ layoutMode: mode })}
          >
            {getLayoutTheme(mode).name}
          </button>
        ))}
      </div>

      <div className="section-header mobile-section-gap"><span className="section-title">业务导航</span></div>
      {[
        ['财务概览', '查看 ERPNext 总账、应收应付', 5],
        ['AI 运行记录', '查看工作单和运行日志', 6],
        ['任务与成长', '查看待办、成长计划和成就', 7],
        ['渠道中心', '管理内容发布渠道', 10],
        ['主动关怀', '查看待办和审批提醒', 11],
        ['评估看板', '查看 AI 员工质量评估', 12],
        ['经验共享', '沉淀和复用业务经验', 13],
      ].map(([title, desc, tab]) => (
        <button className="mobile-data-row" key={String(title)} onClick={() => setActiveTab(tab as TabId)}>
          <span className="mobile-data-main"><strong>{String(title)}</strong><small>{String(desc)}</small></span>
          <RightOutline />
        </button>
      ))}
    </div>
  )
}

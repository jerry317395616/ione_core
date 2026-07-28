import React from 'react'
import { Button, DotLoading, ErrorBlock } from 'antd-mobile'
import { RightOutline } from 'antd-mobile-icons'
import { useRemoteData } from '../hooks/useRemoteData'
import { getMobileFinance, openFrappeRoute } from '../lib/mobileData'
import { getLayoutTheme, type LayoutMode } from '../LayoutThemes'

function money(value: number | null | undefined, currency: string) {
  if (value === null || value === undefined) return '无权限'
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: currency || 'CNY',
    maximumFractionDigits: 2,
  }).format(value)
}

export default function AssetsPage({ layoutMode }: { layoutMode: LayoutMode }) {
  const theme = getLayoutTheme(layoutMode)
  const { data, loading, error, refresh } = useRemoteData(getMobileFinance)

  if (loading && !data) {
    return <div className="page remote-page-state"><DotLoading color="primary" /> 正在读取 ERPNext 财务数据</div>
  }
  if (error && !data) {
    return <div className="page"><ErrorBlock title="财务数据加载失败" description={error} /><Button block onClick={refresh}>重新加载</Button></div>
  }
  if (!data?.available) {
    return (
      <div className="page">
        <div className="page-title">财务概览</div>
        <ErrorBlock title="暂无可查看的财务数据" description="当前公司未配置，或当前账号没有总账读取权限。" />
      </div>
    )
  }

  const weeklyMax = Math.max(1, ...data.weekly_income.map(item => Number(item.income || 0)))
  const metrics = [
    ['总资产', data.balance.assets, theme.info],
    ['总负债', data.balance.liabilities, theme.warning],
    ['所有者权益', data.balance.equity, theme.success],
    ['本月利润', data.month.profit, theme.accentLight],
  ] as const

  return (
    <div className="page" style={{ background: theme.bgColor }}>
      <div className="page-title">财务概览</div>
      <div className="page-desc">{data.company} · 截至 {data.as_of_date}</div>

      <div className="mobile-metric-grid">
        {metrics.map(([label, value, color]) => (
          <div className="stat-card" key={label}>
            <small>{label}</small>
            <strong style={{ color }}>{money(value, data.currency)}</strong>
          </div>
        ))}
      </div>

      <button className="mobile-wide-card" onClick={() => openFrappeRoute(data.routes.accounting)}>
        <span><strong>应收账款</strong><small>{data.receivable.count ?? 0} 笔待收</small></span>
        <b style={{ color: theme.warning }}>{money(data.receivable.amount, data.currency)}</b>
        <RightOutline />
      </button>
      <button className="mobile-wide-card" onClick={() => openFrappeRoute(data.routes.payable)}>
        <span><strong>应付账款</strong><small>{data.payable.count ?? 0} 笔待付</small></span>
        <b style={{ color: theme.danger }}>{money(data.payable.amount, data.currency)}</b>
        <RightOutline />
      </button>

      <div className="section-header mobile-section-gap"><span className="section-title">近 7 日收入</span></div>
      <div className="mobile-bar-chart">
        {data.weekly_income.map(item => (
          <div key={item.date}>
            <span>{item.income == null ? '—' : Math.round(item.income)}</span>
            <i style={{ height: `${Math.max(5, Number(item.income || 0) / weeklyMax * 74)}px` }} />
            <small>{item.date.slice(5)}</small>
          </div>
        ))}
      </div>

      <div className="section-header mobile-section-gap"><span className="section-title">主要科目余额</span></div>
      {data.accounts.map(account => (
        <button className="mobile-data-row" key={account.name} onClick={() => openFrappeRoute(account.route)}>
          <span className="mobile-data-main">
            <strong>{account.label}</strong>
            <small>{account.code || account.root_type}</small>
          </span>
          <b>{money(account.balance, data.currency)}</b>
          <RightOutline />
        </button>
      ))}
      {!data.accounts.length && <div className="mobile-empty">总账中暂无科目余额</div>}
    </div>
  )
}

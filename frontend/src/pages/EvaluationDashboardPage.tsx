import React, { useMemo, useState } from 'react'
import { Button, Dialog, DotLoading, ErrorBlock, ProgressBar } from 'antd-mobile'
import { useRemoteData } from '../hooks/useRemoteData'
import { getMobileEvaluations, type MobileEvaluation } from '../lib/mobileData'
import { getLayoutTheme, type LayoutMode } from '../LayoutThemes'

const gradeColor: Record<string, string> = {
  S: '#16a34a',
  A: '#22c55e',
  B: '#2563eb',
  C: '#ca8a04',
  D: '#dc2626',
  F: '#991b1b',
}
const dimensionLabel: Record<string, string> = {
  accuracy: '准确性',
  completeness: '完整性',
  speed: '响应速度',
  satisfaction: '满意度',
}

function EvaluationDetail({ item }: { item: MobileEvaluation }) {
  return (
    <div className="mobile-evaluation-detail">
      <div className="mobile-evaluation-score" style={{ color: gradeColor[item.grade] }}>
        <strong>{item.score}</strong><span>{item.grade} 级</span>
      </div>
      {item.dimensions.map(dimension => (
        <div key={dimension.dimension}>
          <span>{dimensionLabel[dimension.dimension] || dimension.dimension}</span>
          <ProgressBar percent={dimension.score} style={{ '--fill-color': gradeColor[item.grade] }} />
          <b>{dimension.score}</b>
        </div>
      ))}
      <p>{item.comments || '暂无评估意见'}</p>
    </div>
  )
}

export default function EvaluationDashboardPage({ layoutMode = 'standard' }: { layoutMode?: LayoutMode }) {
  const theme = getLayoutTheme(layoutMode)
  const { data, loading, error, refresh } = useRemoteData(getMobileEvaluations)
  const [selected, setSelected] = useState<MobileEvaluation | null>(null)
  const rows = useMemo(() => data?.evaluations ?? [], [data?.evaluations])

  const summary = useMemo(() => {
    const average = rows.length ? rows.reduce((sum, row) => sum + Number(row.score || 0), 0) / rows.length : 0
    const grades = rows.reduce<Record<string, number>>((result, row) => {
      result[row.grade] = (result[row.grade] || 0) + 1
      return result
    }, {})
    const agents = rows.reduce<Record<string, { total: number; count: number }>>((result, row) => {
      const key = row.agent_name || '未分配'
      result[key] = result[key] || { total: 0, count: 0 }
      result[key].total += Number(row.score || 0)
      result[key].count += 1
      return result
    }, {})
    const best = Object.entries(agents)
      .map(([name, score]) => [name, score.total / score.count] as const)
      .sort((a, b) => b[1] - a[1])[0]
    return { average, grades, best }
  }, [rows])

  if (loading && !data) {
    return <div className="page remote-page-state"><DotLoading color="primary" /> 正在读取 AI 评估</div>
  }
  if (error && !data) {
    return <div className="page"><ErrorBlock title="评估数据加载失败" description={error} /><Button block onClick={refresh}>重新加载</Button></div>
  }

  return (
    <div className="page" style={{ background: theme.bgColor }}>
      <div className="page-title">AI 评估看板</div>
      <div className="page-desc">基于 I-ONE Evaluation 的真实质量记录</div>

      <div className="mobile-metric-grid">
        {[
          ['评估次数', rows.length],
          ['平均分', summary.average ? summary.average.toFixed(1) : '—'],
          ['最佳员工', summary.best?.[0] || '—'],
          ['S/A 级', (summary.grades.S || 0) + (summary.grades.A || 0)],
        ].map(([label, value]) => (
          <div className="stat-card" key={String(label)}>
            <strong style={{ color: theme.accentLight }}>{String(value)}</strong>
            <small>{String(label)}</small>
          </div>
        ))}
      </div>

      <div className="section-header mobile-section-gap"><span className="section-title">等级分布</span></div>
      <div className="mobile-grade-grid">
        {['S', 'A', 'B', 'C', 'D'].map(grade => (
          <div key={grade}>
            <strong style={{ color: gradeColor[grade] }}>{summary.grades[grade] || 0}</strong>
            <span style={{ borderColor: gradeColor[grade], color: gradeColor[grade] }}>{grade}</span>
          </div>
        ))}
      </div>

      <div className="section-header mobile-section-gap"><span className="section-title">最近评估</span></div>
      {rows.map(item => (
        <button className="mobile-evaluation-row" key={item.name} onClick={() => setSelected(item)}>
          <span style={{ background: `${gradeColor[item.grade]}18`, color: gradeColor[item.grade] }}>{item.grade}</span>
          <span>
            <strong>{item.task_title || item.task}</strong>
            <small>{item.agent_name} · {new Date(item.evaluated_at).toLocaleString('zh-CN')}</small>
          </span>
          <b style={{ color: gradeColor[item.grade] }}>{item.score}</b>
        </button>
      ))}
      {!rows.length && <div className="mobile-empty">尚无 AI 评估记录</div>}

      <Dialog
        visible={Boolean(selected)}
        title={selected?.task_title || '评估详情'}
        content={selected ? <EvaluationDetail item={selected} /> : null}
        closeOnMaskClick
        onClose={() => setSelected(null)}
        actions={[{ key: 'close', text: '关闭', onClick: () => setSelected(null) }]}
      />
    </div>
  )
}

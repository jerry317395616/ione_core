import React, { useState } from 'react'
import { Button, DotLoading, ErrorBlock, Input, Space, TextArea, Toast } from 'antd-mobile'
import { LikeOutline, RightOutline } from 'antd-mobile-icons'
import { useRemoteData } from '../hooks/useRemoteData'
import {
  createMobileExperience,
  getMobileExperiences,
  markExperienceUseful,
  openFrappeRoute,
} from '../lib/mobileData'
import { getLayoutTheme, type LayoutMode } from '../LayoutThemes'

function plainText(html: string) {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
}

export default function ExperienceSharingPage({ layoutMode = 'standard' }: { layoutMode?: LayoutMode }) {
  const theme = getLayoutTheme(layoutMode)
  const { data, loading, error, refresh } = useRemoteData(getMobileExperiences)
  const [showCreate, setShowCreate] = useState(false)
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('')
  const [tags, setTags] = useState('')
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)

  const create = async () => {
    if (!title.trim() || !content.trim()) {
      Toast.show({ icon: 'fail', content: '请填写标题和经验内容' })
      return
    }
    setSaving(true)
    try {
      await createMobileExperience(title, content, category, tags)
      setTitle('')
      setCategory('')
      setTags('')
      setContent('')
      setShowCreate(false)
      Toast.show({ icon: 'success', content: '经验已发布' })
      await refresh()
    } catch (reason) {
      Toast.show({ icon: 'fail', content: reason instanceof Error ? reason.message : '发布失败' })
    } finally {
      setSaving(false)
    }
  }

  const useful = async (name: string) => {
    await markExperienceUseful(name)
    await refresh()
  }

  if (loading && !data) {
    return <div className="page remote-page-state"><DotLoading color="primary" /> 正在读取经验库</div>
  }
  if (error && !data) {
    return <div className="page"><ErrorBlock title="经验库加载失败" description={error} /><Button block onClick={refresh}>重新加载</Button></div>
  }

  const rows = data?.experiences ?? []
  return (
    <div className="page" style={{ background: theme.bgColor }}>
      <div className="mobile-title-actions">
        <span><strong>经验共享</strong><small>团队方法沉淀在 Frappe 中，持续复用</small></span>
        <Button size="small" color="primary" onClick={() => setShowCreate(value => !value)}>{showCreate ? '收起' : '发布'}</Button>
      </div>

      {showCreate && (
        <div className="card mobile-inline-form">
          <label><span>标题</span><Input value={title} onChange={setTitle} placeholder="经验标题" clearable /></label>
          <label><span>分类</span><Input value={category} onChange={setCategory} placeholder="例如：财务、销售" clearable /></label>
          <label><span>标签</span><Input value={tags} onChange={setTags} placeholder="多个标签用逗号分隔" clearable /></label>
          <label><span>内容</span><TextArea value={content} onChange={setContent} rows={5} placeholder="说明背景、处理方法和结果" maxLength={10000} showCount /></label>
          <Space block>
            <Button block onClick={() => setShowCreate(false)}>取消</Button>
            <Button block color="primary" loading={saving} onClick={() => void create()}>发布经验</Button>
          </Space>
        </div>
      )}

      {rows.map(item => (
        <article className="mobile-experience-card" key={item.name}>
          <button className="mobile-experience-main" onClick={() => openFrappeRoute(item.route)}>
            <span><em>{item.category || '未分类'}</em><small>{item.author_user}</small></span>
            <strong>{item.title}</strong>
            <p>{plainText(item.content).slice(0, 160)}</p>
            {item.tags && <small>{item.tags}</small>}
            <RightOutline />
          </button>
          <button className="mobile-like-button" onClick={() => useful(item.name)}>
            <LikeOutline /> 有用 {item.useful_count || 0}
          </button>
        </article>
      ))}
      {!rows.length && <div className="mobile-empty">暂无已发布经验，发布第一条团队经验吧</div>}
    </div>
  )
}

import React, { useState } from 'react'
import { Button, DotLoading, ErrorBlock, Input, Selector, Space, TextArea, Toast } from 'antd-mobile'
import { RightOutline } from 'antd-mobile-icons'
import { useRemoteData } from '../hooks/useRemoteData'
import {
  createMobileChannel,
  createMobilePublishJobs,
  getMobileChannels,
  openFrappeRoute,
} from '../lib/mobileData'
import { getLayoutTheme, type LayoutMode } from '../LayoutThemes'
import type { TabId } from '../types'

const channelTypes = ['微信公众号', '视频号', '抖音', '小红书', '微博', '网站', '邮件', '其他']
  .map(value => ({ label: value, value }))

export default function ChannelCenterPage({ layoutMode = 'standard' }: {
  layoutMode?: LayoutMode
  setActiveTab?: (tab: TabId) => void
}) {
  const theme = getLayoutTheme(layoutMode)
  const { data, loading, error, refresh } = useRemoteData(getMobileChannels)
  const [content, setContent] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [publishing, setPublishing] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [channelName, setChannelName] = useState('')
  const [channelType, setChannelType] = useState('网站')
  const [accountName, setAccountName] = useState('')

  const addChannel = async () => {
    if (!channelName.trim()) {
      Toast.show({ icon: 'fail', content: '请输入渠道名称' })
      return
    }
    try {
      await createMobileChannel(channelName, channelType, accountName)
      setChannelName('')
      setChannelType('网站')
      setAccountName('')
      setShowAdd(false)
      Toast.show({ icon: 'success', content: '渠道已创建' })
      await refresh()
    } catch (reason) {
      Toast.show({ icon: 'fail', content: reason instanceof Error ? reason.message : '创建失败' })
    }
  }

  const publish = async () => {
    if (!content.trim() || !selected.length) return
    setPublishing(true)
    try {
      await createMobilePublishJobs(content, selected)
      setContent('')
      setSelected([])
      Toast.show({ icon: 'success', content: '发布任务已进入 Frappe 队列' })
      await refresh()
    } catch (reason) {
      Toast.show({ icon: 'fail', content: reason instanceof Error ? reason.message : '创建失败' })
    } finally {
      setPublishing(false)
    }
  }

  if (loading && !data) {
    return <div className="page remote-page-state"><DotLoading color="primary" /> 正在读取发布渠道</div>
  }
  if (error && !data) {
    return <div className="page"><ErrorBlock title="渠道加载失败" description={error} /><Button block onClick={refresh}>重新加载</Button></div>
  }

  return (
    <div className="page" style={{ background: theme.bgColor }}>
      <div className="mobile-title-actions">
        <span><strong>渠道中心</strong><small>统一管理 I-ONE 内容发布</small></span>
        <Button size="small" color="primary" onClick={() => setShowAdd(value => !value)}>{showAdd ? '收起' : '新增'}</Button>
      </div>

      {showAdd && (
        <div className="card mobile-inline-form">
          <label><span>渠道名称</span><Input value={channelName} onChange={setChannelName} placeholder="例如：公司官网" clearable /></label>
          <label><span>渠道类型</span><Selector columns={4} options={channelTypes} value={[channelType]} onChange={values => values[0] && setChannelType(String(values[0]))} /></label>
          <label><span>账号名称</span><Input value={accountName} onChange={setAccountName} placeholder="可选" clearable /></label>
          <Space block>
            <Button block onClick={() => setShowAdd(false)}>取消</Button>
            <Button block color="primary" onClick={() => void addChannel()}>保存渠道</Button>
          </Space>
        </div>
      )}

      <div className="section-header"><span className="section-title">发布内容</span></div>
      <div className="card">
        <TextArea value={content} onChange={setContent} rows={5} maxLength={2000} showCount placeholder="输入需要发布的内容" />
        <div className="mobile-channel-pills">
          {(data?.channels ?? []).filter(channel => channel.status === '启用').map(channel => (
            <button
              key={channel.name}
              className={selected.includes(channel.name) ? 'active' : ''}
              onClick={() => setSelected(current => current.includes(channel.name)
                ? current.filter(name => name !== channel.name)
                : [...current, channel.name])}
            >
              {channel.channel_name}
            </button>
          ))}
        </div>
        <Button block color="primary" loading={publishing} disabled={!content.trim() || !selected.length} onClick={publish}>
          {selected.length ? `创建 ${selected.length} 个发布任务` : '创建发布任务'}
        </Button>
      </div>

      <div className="section-header mobile-section-gap"><span className="section-title">已配置渠道</span></div>
      {(data?.channels ?? []).map(channel => (
        <button className="mobile-data-row" key={channel.name} onClick={() => openFrappeRoute(`/app/i-one-channel/${encodeURIComponent(channel.name)}`)}>
          <span className="mobile-data-main">
            <strong>{channel.channel_name}</strong>
            <small>{channel.channel_type}{channel.account_name ? ` · ${channel.account_name}` : ''}</small>
          </span>
          <span style={{ color: channel.status === '启用' ? theme.success : theme.textColor3 }}>{channel.status}</span>
          <RightOutline />
        </button>
      ))}
      {!data?.channels.length && <div className="mobile-empty">暂无渠道，请先新增</div>}

      <div className="section-header mobile-section-gap"><span className="section-title">最近发布任务</span></div>
      {(data?.jobs ?? []).slice(0, 20).map(job => (
        <button className="mobile-data-row" key={job.name} onClick={() => openFrappeRoute(`/app/i-one-publish-job/${encodeURIComponent(job.name)}`)}>
          <span className="mobile-data-main"><strong>{job.title}</strong><small>{job.channel} · {job.status}</small></span>
          <RightOutline />
        </button>
      ))}
      {!data?.jobs.length && <div className="mobile-empty">尚无发布任务</div>}
    </div>
  )
}

import React, { useCallback, useEffect, useState } from 'react'
import {
  Button,
  Card,
  Dialog,
  Grid,
  Input,
  List,
  NavBar,
  NoticeBar,
  Selector,
  Space,
  Switch,
  Tag,
  Toast,
} from 'antd-mobile'
import {
  AppstoreOutline,
  BellOutline,
  CheckShieldOutline,
  CloseCircleOutline,
  HistogramOutline,
  InformationCircleOutline,
  KeyOutline,
  PieOutline,
  SetOutline,
  UserOutline,
} from 'antd-mobile-icons'
import {
  clearUsageStats,
  getUsageStats,
} from '../lib/apiConfig'
import { getFrappeBootstrap, getFrappeUrl, type FrappeApp } from '../lib/frappeCore'
import { frappeCall } from '../lib/frappeRequest'
import type { LayoutMode } from '../LayoutThemes'
import { getLayoutTheme } from '../LayoutThemes'
import type { AppState, TabId } from '../types'

type SettingsPanel = 'module' | 'notif' | 'theme' | 'account' | 'apiKey' | 'about' | 'usage' | null

function PanelShell({
  title,
  onBack,
  extra,
  children,
}: {
  title: string
  onBack: () => void
  extra?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="page settings-page">
      <NavBar onBack={onBack} right={extra} className="subpage-nav">
        {title}
      </NavBar>
      <div className="settings-panel-content">{children}</div>
    </div>
  )
}

export default function SettingsPage({
  layoutMode,
  state,
  setState,
  setActiveTab,
  onLogout,
}: {
  layoutMode: LayoutMode
  state: AppState
  setState: (state: Partial<AppState>) => void
  setActiveTab?: (tab: TabId) => void
  onLogout?: () => void | Promise<void>
}) {
  const [activePanel, setActivePanel] = useState<SettingsPanel>(null)
  const [keyInput, setKeyInput] = useState('')
  const [baseUrlInput, setBaseUrlInput] = useState('')
  const [modelNameInput, setModelNameInput] = useState('')
  const [hasServerConfig, setHasServerConfig] = useState(false)
  const [canWriteServerConfig, setCanWriteServerConfig] = useState(false)
  const [apiStatus, setApiStatus] = useState('')
  const [checking, setChecking] = useState(false)
  const [usageStats, setUsageStats] = useState(getUsageStats())
  const [frappeApps, setFrappeApps] = useState<FrappeApp[]>([])
  const [notificationSettings, setNotificationSettings] = useState({
    sound: true,
    desktop: true,
    progress: true,
  })

  useEffect(() => {
    const timer = setInterval(() => setUsageStats(getUsageStats()), 5000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    getFrappeBootstrap().then(bootstrap => setFrappeApps(bootstrap.apps)).catch(() => setFrappeApps([]))
  }, [])

  const loadConfig = useCallback(async () => {
    setApiStatus('正在读取 Frappe 配置')
    try {
      const config = await frappeCall<{
        can_write: boolean
        model_name: string
        llm_base_url: string
        api_key_configured: boolean
      }>('ione_core.api.get_mobile_settings')
      setKeyInput('')
      setBaseUrlInput(config.llm_base_url || '')
      setModelNameInput(config.model_name || 'qwen')
      setHasServerConfig(Boolean(config.llm_base_url))
      setCanWriteServerConfig(Boolean(config.can_write))
      setApiStatus('')
    } catch (error) {
      setApiStatus(error instanceof Error ? error.message : '读取配置失败')
    }
  }, [])

  const closePanel = () => setActivePanel(null)

  const saveConfig = async () => {
    setChecking(true)
    try {
      const config = await frappeCall<{
        llm_base_url: string
        api_key_configured: boolean
      }>(
        'ione_core.api.update_mobile_settings',
        {
          api_key: keyInput.trim() || undefined,
          llm_base_url: baseUrlInput.trim(),
          model_name: modelNameInput.trim() || 'qwen',
        },
        'POST',
      )
      setHasServerConfig(Boolean(config.llm_base_url))
      setKeyInput('')
      setApiStatus('配置已保存')
      Toast.show({ icon: 'success', content: 'Frappe 模型配置已保存' })
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存失败'
      setApiStatus(message)
      Toast.show({ icon: 'fail', content: message })
    } finally {
      setChecking(false)
    }
  }

  const checkConfig = async () => {
    setChecking(true)
    setApiStatus('正在验证连接')
    try {
      const result = await frappeCall<{ available: boolean }>(
        'ione_core.api.test_mobile_model',
        {},
        'POST',
      )
      if (!result.available) throw new Error('模型服务连接不可用')
      setApiStatus('连接可用')
      Toast.show({ icon: 'success', content: 'API 连接正常' })
    } catch (error) {
      const message = error instanceof Error ? error.message : '连接不可用'
      setApiStatus(message)
      Toast.show({ icon: 'fail', content: message })
    } finally {
      setChecking(false)
    }
  }

  const resetUsage = async () => {
    const confirmed = await Dialog.confirm({
      title: '清空用量统计',
      content: '将删除当前设备保存的 Token 用量和调用次数。',
      confirmText: '清空',
      cancelText: '取消',
    })
    if (!confirmed) return
    clearUsageStats()
    setUsageStats(getUsageStats())
    Toast.show({ icon: 'success', content: '用量统计已清空' })
  }

  if (activePanel === 'module') {
    return (
      <PanelShell
        title="Frappe 应用"
        onBack={closePanel}
        extra={<Tag color="primary">{frappeApps.length}</Tag>}
      >
        <List header="当前账号可访问的已安装应用">
          {frappeApps.map(app => (
            <List.Item
              key={app.name}
              prefix={app.logo ? <img className="settings-module-logo" src={app.logo} alt="" /> : <span className="settings-module-icon">{app.title.slice(0, 1)}</span>}
              description={app.category}
              clickable
              onClick={() => window.open(getFrappeUrl(app.route), '_blank', 'noopener,noreferrer')}
            >
              {app.title}
            </List.Item>
          ))}
          {!frappeApps.length && <List.Item description="请检查应用权限">当前没有可访问应用</List.Item>}
        </List>
      </PanelShell>
    )
  }

  if (activePanel === 'notif') {
    return (
      <PanelShell title="通知设置" onBack={closePanel}>
        <List header="提醒方式">
          <List.Item
            description="启用系统提示音"
            extra={(
              <Switch
                checked={notificationSettings.sound}
                onChange={sound => setNotificationSettings(value => ({ ...value, sound }))}
              />
            )}
          >
            声音提醒
          </List.Item>
          <List.Item
            description="在设备状态栏显示通知"
            extra={(
              <Switch
                checked={notificationSettings.desktop}
                onChange={desktop => setNotificationSettings(value => ({ ...value, desktop }))}
              />
            )}
          >
            桌面通知
          </List.Item>
          <List.Item
            description={`当前 ${state.nightStartTime} - ${state.nightEndTime}`}
            extra={(
              <Switch
                checked={state.nightModeEnabled}
                onChange={nightModeEnabled => setState({ nightModeEnabled })}
              />
            )}
          >
            免打扰时段
          </List.Item>
          <List.Item
            description="AI 完成任务时推送消息"
            extra={(
              <Switch
                checked={notificationSettings.progress}
                onChange={progress => setNotificationSettings(value => ({ ...value, progress }))}
              />
            )}
          >
            任务进度播报
          </List.Item>
        </List>
      </PanelShell>
    )
  }

  if (activePanel === 'theme') {
    const options = (['standard', 'minimal', 'rich'] as LayoutMode[]).map(mode => {
      const item = getLayoutTheme(mode)
      return {
        value: mode,
        label: `${mode === 'standard' ? '◐' : mode === 'minimal' ? '○' : '●'} ${item.name}`,
        description: mode === 'standard' ? 'Ant Design Mobile 标准界面' : mode === 'minimal' ? '更轻量的留白界面' : '更清晰的高对比界面',
      }
    })
    return (
      <PanelShell title="主题外观" onBack={closePanel}>
        <Card title="界面模式">
          <Selector
            columns={1}
            options={options}
            value={[layoutMode]}
            onChange={values => values[0] && setState({ layoutMode: values[0] })}
          />
        </Card>
      </PanelShell>
    )
  }

  if (activePanel === 'account') {
    return (
      <PanelShell title="账号管理" onBack={closePanel}>
        <List header="企业资料">
          <List.Item extra={state.userName}>用户名</List.Item>
          <List.Item extra={state.companyName}>公司名称</List.Item>
          <List.Item extra={state.industry}>行业</List.Item>
        </List>
        <List header="经营档案" className="settings-spaced-list">
          <List.Item extra={`${state.streak} 天`}>连续使用</List.Item>
          <List.Item extra={state.xp}>经验值</List.Item>
          <List.Item extra={state.gold}>金币</List.Item>
        </List>
        <Button
          block
          color="danger"
          fill="outline"
          className="settings-logout-button"
          onClick={async () => {
            const confirmed = await Dialog.confirm({
              title: '退出登录',
              content: '退出当前 I-ONE 工作台账号？',
              confirmText: '退出',
            })
            if (confirmed) await onLogout?.()
          }}
        >
          <CloseCircleOutline /> 退出登录
        </Button>
      </PanelShell>
    )
  }

  if (activePanel === 'apiKey') {
    return (
      <PanelShell title="API 配置" onBack={closePanel}>
        <NoticeBar
          color="info"
          wrap
          content="模型配置统一保存在 Frappe 服务端，手机浏览器不会保存接口密钥。"
          className="settings-notice"
        />
        <List header="连接信息">
          <List.Item>
            <div className="settings-field"><label>API Key</label><Input type="password" value={keyInput} onChange={setKeyInput} placeholder="留空表示不修改" clearable disabled={!canWriteServerConfig} /></div>
          </List.Item>
          <List.Item>
            <div className="settings-field"><label>Base URL</label><Input value={baseUrlInput} onChange={setBaseUrlInput} placeholder="http://模型服务/v1" clearable disabled={!canWriteServerConfig} /></div>
          </List.Item>
          <List.Item>
            <div className="settings-field"><label>模型名称</label><Input value={modelNameInput} onChange={setModelNameInput} placeholder="qwen" clearable disabled={!canWriteServerConfig} /></div>
          </List.Item>
        </List>
        <Space block className="settings-actions">
          <Button block color="primary" loading={checking} disabled={!canWriteServerConfig} onClick={() => void saveConfig()}>保存配置</Button>
          <Button block fill="outline" loading={checking} onClick={checkConfig}>验证连接</Button>
        </Space>
        {apiStatus && (
          <NoticeBar
            color={apiStatus === '连接可用' || apiStatus === '配置已保存' ? 'success' : 'default'}
            content={apiStatus}
            className="settings-status"
          />
        )}
      </PanelShell>
    )
  }

  if (activePanel === 'usage') {
    return (
      <PanelShell title="用量统计" onBack={closePanel}>
        <Grid columns={3} gap={8}>
          {[
            { label: '本次会话', value: usageStats.session.toLocaleString() },
            { label: '累计总量', value: usageStats.total.toLocaleString() },
            { label: '调用次数', value: usageStats.calls.toLocaleString() },
          ].map(item => (
            <Grid.Item key={item.label}>
              <Card className="settings-metric-card">
                <strong>{item.value}</strong>
                <span>{item.label}</span>
              </Card>
            </Grid.Item>
          ))}
        </Grid>
        <Button block color="danger" fill="outline" onClick={resetUsage} className="settings-danger-action">
          清空统计
        </Button>
      </PanelShell>
    )
  }

  if (activePanel === 'about') {
    return (
      <PanelShell title="关于" onBack={closePanel}>
        <Card className="about-card">
          <div className="about-icon"><AppstoreOutline /></div>
          <h2>一人公司 AI 助手</h2>
          <Tag color="primary" fill="outline">ERP 版 v1.0.0</Tag>
          <p>让一个人也能拥有一支清晰、可靠、持续运转的 AI 团队。</p>
        </Card>
      </PanelShell>
    )
  }

  return (
    <div className="page settings-page">
      <div className="page-title">系统设置</div>
      <div className="page-desc">管理工作台、模型连接和账号信息</div>

      <List header="应用">
        <List.Item
          prefix={<AppstoreOutline />}
          description={`${frappeApps.length} 个当前可访问应用`}
          clickable
          onClick={() => setActivePanel('module')}
        >
          Frappe 应用
        </List.Item>
        <List.Item
          prefix={<BellOutline />}
          description="提醒方式和免打扰时段"
          clickable
          onClick={() => setActivePanel('notif')}
        >
          通知设置
        </List.Item>
        <List.Item
          prefix={<SetOutline />}
          description="标准、简洁或高对比模式"
          clickable
          onClick={() => setActivePanel('theme')}
        >
          主题外观
        </List.Item>
      </List>

      <List header="账号与安全" className="settings-spaced-list">
        <List.Item
          prefix={<UserOutline />}
          description="用户名、行业和公司信息"
          clickable
          onClick={() => setActivePanel('account')}
        >
          账号管理
        </List.Item>
        <List.Item
          prefix={<KeyOutline />}
          description={hasServerConfig ? 'Frappe 服务端已配置' : '点击读取配置'}
          extra={<Tag color={hasServerConfig ? 'success' : 'default'}>{hasServerConfig ? '已配置' : '服务端'}</Tag>}
          clickable
          onClick={() => {
            setActivePanel('apiKey')
            void loadConfig()
          }}
        >
          API 配置
        </List.Item>
        <List.Item
          prefix={<HistogramOutline />}
          description="Token 用量与调用次数"
          clickable
          onClick={() => setActivePanel('usage')}
        >
          用量统计
        </List.Item>
      </List>

      <List header="数据" className="settings-spaced-list">
        {setActiveTab && [
          { tab: 5, title: '财务概览', description: 'ERPNext 总账、应收与应付' },
          { tab: 6, title: 'AI 运行记录', description: '工作单与运行日志' },
          { tab: 7, title: '任务与成长', description: '待办、成长计划和成就' },
          { tab: 8, title: '公司档案', description: '公司、员工和应用入口' },
          { tab: 10, title: '渠道中心', description: '内容渠道和发布任务' },
          { tab: 11, title: '主动关怀', description: '待办与审批提醒' },
          { tab: 12, title: '评估看板', description: 'AI 员工表现量化分析' },
          { tab: 13, title: '经验共享', description: '团队方法沉淀与复用' },
        ].map(item => (
          <List.Item
            key={item.tab}
            prefix={<PieOutline />}
            description={item.description}
            clickable
            onClick={() => setActiveTab(item.tab as TabId)}
          >
            {item.title}
          </List.Item>
        ))}
        <List.Item
          prefix={<InformationCircleOutline />}
          description="版本和产品信息"
          clickable
          onClick={() => setActivePanel('about')}
        >
          关于
        </List.Item>
      </List>

      <div className="settings-security-note">
        <CheckShieldOutline />
        <span>身份、权限和敏感配置由 Frappe 统一管理</span>
      </div>
    </div>
  )
}

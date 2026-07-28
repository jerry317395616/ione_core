import React, { lazy, Suspense, useState, useEffect, useCallback } from 'react'
import { Button, NavBar, Space, SpinLoading, TabBar } from 'antd-mobile'
import {
  AddSquareOutline,
  FileOutline,
  MessageOutline,
  PieOutline,
  SetOutline,
  TeamOutline,
} from 'antd-mobile-icons'
import OnboardingPage, { type UserData } from './OnboardingPage'
import LoginPhonePage, { type AuthUser } from './LoginPhonePage'
import { getLayoutTheme, LayoutMode } from './LayoutThemes'
import type { AppState, TabId } from './types'
import HomePage from './pages/HomePage'
import { setItemJSON, storage } from './lib/storageAdapter'
import { getMobileOnboarding, onboardingToUserData, type MobileOnboardingState } from './lib/onboardingApi'
import { getFrappeBootstrap } from './lib/frappeCore'
import { logoutFromFrappe } from './lib/frappeRequest'

const AssetsPage = lazy(() => import('./pages/AssetsPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const AIEmployeesPage = lazy(() => import('./pages/AIEmployeesPage'))
const IntelligentInputPage = lazy(() => import('./pages/IntelligentInputPage'))
const ExpertPage = lazy(() => import('./pages/ExpertPage'))
const PerformancePage = lazy(() => import('./pages/PerformancePage'))
const TasksPage = lazy(() => import('./pages/TasksPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const ChannelCenterPage = lazy(() => import('./pages/ChannelCenter'))
const ProactiveCarePage = lazy(() => import('./pages/ProactiveCarePage'))
const EvaluationDashboardPage = lazy(() => import('./pages/EvaluationDashboardPage'))
const ExperienceSharingPage = lazy(() => import('./pages/ExperienceSharingPage'))

const STORAGE_KEY = 'one_company_state'

function loadState(): Partial<AppState> {
  try {
    const saved = storage.getItem(STORAGE_KEY)
    return saved ? JSON.parse(saved) : {}
  } catch { return {} }
}

function saveState(state: Partial<AppState>) {
  try { setItemJSON(STORAGE_KEY, state) } catch { return }
}

// Bottom nav: 4 core tabs (删除了调度tab，合并到智能tab)
const TABS: { icon: React.ReactNode; label: string; id: TabId }[] = [
  { icon: <PieOutline />, label: '仪表', id: 0 },
  { icon: <AddSquareOutline />, label: '智能', id: 1 },
  { icon: <MessageOutline />, label: '专家', id: 9 },
  { icon: <TeamOutline />, label: 'AI 团队', id: 3 },
  { icon: <SetOutline />, label: '设置', id: 4 },
]

const EMAIL_STORAGE_KEY = 'ope_login_email'

export default function App() {
  const [saved] = useState<Partial<AppState>>(() => loadState())
  const savedEmail = storage.getItem(EMAIL_STORAGE_KEY)

  const [email, setEmail] = useState(savedEmail || '')
  const [state, setStateRaw] = useState<AppState>({
    onboardingComplete: saved.onboardingComplete || false,
    industry: saved.industry || '通用',
    userName: saved.userName || '',
    companyName: saved.companyName || '',
    xp: saved.xp || 0,
    gold: saved.gold || 0,
    streak: saved.streak || 0,
    layoutMode: (saved.layoutMode as LayoutMode) || 'standard',
    autoMode: (saved.autoMode as AppState['autoMode']) || 'off',
    nightMode: false,
    nightModeEnabled: saved.nightModeEnabled || false,
    nightStartTime: saved.nightStartTime || '22:00',
    nightEndTime: saved.nightEndTime || '08:00',
    receivable: saved.receivable || {},
    payable: saved.payable || {},
    projectCount: saved.projectCount || 0,
    modules: saved.modules || ['dashboard', 'finance', 'crm', 'ticket'],
    departmentCount: saved.departmentCount || 0,
  })

  const setState = useCallback((s: Partial<AppState>) => {
    setStateRaw(prev => {
      const next = { ...prev, ...s }
      saveState(next)
      return next
    })
  }, [])

  // Tab IDs: 0=仪表, 1=智能, 3=AI, 4=设置
  // Extra pages: 5=报表, 6=财务, 7=任务, 8=档案, 12=评估看板
  const [activeTab, setActiveTab] = useState<TabId>(0)
  const [authReady, setAuthReady] = useState(false)
  const [showLogin, setShowLogin] = useState(true)
  const [showOnboarding, setShowOnboarding] = useState(false)

  const theme = getLayoutTheme(state.layoutMode)

  const applyOnboardingState = useCallback((onboarding: MobileOnboardingState) => {
    if (!onboarding.progress.completed) {
      setState({ onboardingComplete: false })
      setShowOnboarding(true)
      return
    }

    const data = onboardingToUserData(onboarding)
    setState({
      onboardingComplete: true,
      industry: data.industry,
      userName: data.userName,
      companyName: data.companyName,
    })
    setShowOnboarding(false)
  }, [setState])

  // ---- Frappe 会话恢复 ----
  useEffect(() => {
    let cancelled = false

    const restoreSession = async () => {
      try {
        const bootstrap = await getFrappeBootstrap()
        if (cancelled) return
        const user: AuthUser = {
          username: bootstrap.user.username,
          fullName: bootstrap.user.full_name || bootstrap.user.username,
        }

        setEmail(user.username)
        storage.setItem(EMAIL_STORAGE_KEY, user.username)
        setState({ userName: user.fullName || user.username })
        setShowLogin(false)
        try {
          applyOnboardingState(await getMobileOnboarding())
        } catch {
          setState({ onboardingComplete: false })
          setShowOnboarding(true)
        }
      } catch {
        if (cancelled) return
        storage.removeItem(EMAIL_STORAGE_KEY)
        setEmail('')
        setShowOnboarding(false)
        setShowLogin(true)
      } finally {
        if (!cancelled) setAuthReady(true)
      }
    }

    restoreSession()
    return () => { cancelled = true }
  }, [applyOnboardingState, setState])

  // ---- 每日签到 streak ----
  useEffect(() => {
    const today = new Date().toISOString().split('T')[0]
    const lastActive = storage.getItem('last_active_date')
    if (lastActive !== today) {
      storage.setItem('last_active_date', today)
      const prev = parseInt(storage.getItem('streak_count') || '0')
      const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0]
      const isConsecutive = lastActive === yesterday
      const newStreak = isConsecutive ? prev + 1 : 1
      storage.setItem('streak_count', String(newStreak))
      setState({ streak: newStreak })
    }
  }, [setState])

  // ---- 登录完成 ----
  const handleLoginComplete = useCallback(async (user: AuthUser) => {
    try {
      const bootstrap = await getFrappeBootstrap()
      const activeUser: AuthUser = {
        username: bootstrap.user.username,
        fullName: bootstrap.user.full_name || user.fullName || bootstrap.user.username,
      }
      setEmail(activeUser.username)
      storage.setItem(EMAIL_STORAGE_KEY, activeUser.username)
      setState({ userName: activeUser.fullName })
      setShowLogin(false)
      applyOnboardingState(await getMobileOnboarding())
    } catch {
      setEmail(user.username)
      storage.setItem(EMAIL_STORAGE_KEY, user.username)
      setState({ userName: user.fullName || user.username })
      setShowLogin(false)
      setState({ onboardingComplete: false })
      setShowOnboarding(true)
    }
  }, [applyOnboardingState, setState])

  const handleLogout = useCallback(async () => {
    try {
      await logoutFromFrappe()
    } catch {
      // Clear the local login state even if the network is unavailable.
    }
    storage.removeItem(EMAIL_STORAGE_KEY)
    setEmail('')
    setActiveTab(0 as TabId)
    setShowOnboarding(false)
    setShowLogin(true)
  }, [])

  // ---- 建档完成 ----
  const handleOnboardingComplete = useCallback((data: UserData) => {
    const p = email || storage.getItem(EMAIL_STORAGE_KEY) || ''
    setState({
      onboardingComplete: true,
      email: p,
      industry: data.industry || '通用',
      userName: data.userName || email,
      companyName: data.companyName || '',
    })
    setShowOnboarding(false)
  }, [setState, email])

  // ---- 页面路由 ----
  const renderPage = () => {
    switch (activeTab) {
      case 0:
        return <HomePage industry={state.industry} state={state} setState={setState} layoutMode={state.layoutMode} setActiveTab={setActiveTab} />
      case 1:
        return <IntelligentInputPage layoutMode={state.layoutMode} />
      case 9:
        return <ExpertPage layoutMode={state.layoutMode} />
      case 3:
        return <AIEmployeesPage layoutMode={state.layoutMode} state={state} setState={setState} />
      case 4:
        return <SettingsPage layoutMode={state.layoutMode} state={state} setState={setState} setActiveTab={setActiveTab} onLogout={handleLogout} />
      // Extra pages — accessible from within other pages
      case 5:
        return <AssetsPage layoutMode={state.layoutMode} />
      case 6:
        return <PerformancePage layoutMode={state.layoutMode} />
      case 7:
        return <TasksPage layoutMode={state.layoutMode} />
      case 8:
        return <ProfilePage layoutMode={state.layoutMode} state={state} setState={setState} setActiveTab={setActiveTab} />
      case 10:
        return <ChannelCenterPage layoutMode={state.layoutMode} setActiveTab={setActiveTab} />
      case 11:
        return <ProactiveCarePage layoutMode={state.layoutMode} />
      case 12:
        return <EvaluationDashboardPage layoutMode={state.layoutMode} />
      case 13:
        return <ExperienceSharingPage layoutMode={state.layoutMode} />
      default:
        return <HomePage industry={state.industry} state={state} setState={setState} layoutMode={state.layoutMode} setActiveTab={setActiveTab} />
    }
  }

  // ---- 会话检查 ----
  if (!authReady) {
    return (
      <div className="app">
        <div className="auth-session-loading">
          <SpinLoading color="primary" />
          <span>正在连接统一身份认证</span>
        </div>
      </div>
    )
  }

  // ---- 登录页 ----
  if (showLogin) {
    return (
      <div className="app">
        <LoginPhonePage onComplete={handleLoginComplete} />
      </div>
    )
  }

  // ---- 建档页 ----
  if (showOnboarding) {
    return (
      <div className="app">
        <OnboardingPage onComplete={handleOnboardingComplete} />
      </div>
    )
  }

  // ---- 主应用 ----
  return (
    <>
      <div className={`app app-theme-${state.layoutMode}`} style={{
        background: theme.bgColor,
        fontFamily: theme.fontFamily,
      }}>
        <header className="app-header">
          <NavBar
            backIcon={false}
            right={(
              <Space className="app-header-actions">
                <Button
                  fill="none"
                  size="mini"
                  aria-label="智能记录"
                  onClick={() => setActiveTab(1 as TabId)}
                >
                  <AddSquareOutline />
                </Button>
                <Button
                  fill="none"
                  size="mini"
                  aria-label="打开管理平台"
                  onClick={() => { window.open('/app', '_blank', 'noopener,noreferrer') }}
                >
                  <FileOutline />
                </Button>
              </Space>
            )}
          >
            <span className="app-title">I-ONE 工作台</span>
          </NavBar>
        </header>

        {/* 页面内容 */}
        <main className="app-content" style={{
          flex: 1, overflowY: 'auto',
          WebkitOverflowScrolling: 'touch',
        }}>
          <Suspense fallback={<div className="remote-page-state"><SpinLoading color="primary" /> 正在打开页面</div>}>
            {renderPage()}
          </Suspense>
        </main>

        {/* 底部导航 — 4个核心tab */}
        <nav className="bottom-nav" aria-label="主导航">
          <TabBar
            activeKey={String(activeTab)}
            onChange={key => setActiveTab(Number(key) as TabId)}
            safeArea
          >
            {TABS.map(tab => (
              <TabBar.Item
                key={String(tab.id)}
                icon={tab.icon}
                title={tab.label}
              />
            ))}
          </TabBar>
        </nav>
      </div>
    </>
  )
}

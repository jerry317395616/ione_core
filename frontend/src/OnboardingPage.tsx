import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Card,
  Input,
  List,
  NavBar,
  ProgressBar,
  Selector,
  Space,
  SpinLoading,
  Tag,
  Toast,
} from 'antd-mobile'
import {
  AppstoreOutline,
  CheckCircleOutline,
  ClockCircleOutline,
  LeftOutline,
  PieOutline,
  TeamOutline,
} from 'antd-mobile-icons'
import { getIndustryConfig } from './industryConfig'
import {
  completeMobileOnboarding,
  getMobileOnboarding,
  onboardingToUserData,
  prepareMobileOnboardingReport,
  saveMobileOnboarding,
  type MobileOnboardingFlow,
  type MobileOnboardingProfile,
  type MobileOnboardingReport,
  type MobileOnboardingState,
  type MobileOnboardingStep,
  type UserData,
} from './lib/onboardingApi'

export type { UserData } from './lib/onboardingApi'

const EMPTY_PROFILE: MobileOnboardingProfile = {
  company_name: '',
  display_name: '',
  user_role: '',
  city: '',
  skipped_info: false,
}

function normalizeAnswers(values: MobileOnboardingState['progress']['answers']) {
  return Object.fromEntries(
    Object.entries(values || {}).map(([key, value]) => [key, Array.isArray(value) ? value : value ? [value] : []]),
  )
}

export default function OnboardingPage({ onComplete }: { onComplete: (data: UserData) => void }) {
  const [flow, setFlow] = useState<MobileOnboardingFlow | null>(null)
  const [stepCode, setStepCode] = useState('welcome')
  const [answers, setAnswers] = useState<Record<string, string[]>>({})
  const [profile, setProfile] = useState<MobileOnboardingProfile>(EMPTY_PROFILE)
  const [report, setReport] = useState<MobileOnboardingReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const loadOnboarding = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const state = await getMobileOnboarding()
      setFlow(state.flow)
      setAnswers(normalizeAnswers(state.progress.answers))
      setProfile({ ...EMPTY_PROFILE, ...state.progress.profile })
      setReport(state.progress.report)
      const savedStep = state.flow.steps.some(step => step.code === state.progress.current_step)
        ? state.progress.current_step
        : state.flow.steps[0]?.code || 'welcome'
      setStepCode(savedStep)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '无法加载引导流程')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadOnboarding()
  }, [loadOnboarding])

  const steps = useMemo(() => flow?.steps || [], [flow])
  const stepIndex = Math.max(0, steps.findIndex(step => step.code === stepCode))
  const currentStep = steps[stepIndex]
  const progress = steps.length ? ((stepIndex + 1) / steps.length) * 100 : 0

  const previousStepCode = useMemo(() => steps[stepIndex - 1]?.code, [stepIndex, steps])
  const nextStepCode = useMemo(() => steps[stepIndex + 1]?.code, [stepIndex, steps])

  const saveAndMove = async (
    targetStep: string,
    nextAnswers = answers,
    nextProfile = profile,
  ) => {
    setSubmitting(true)
    try {
      await saveMobileOnboarding({
        current_step: targetStep,
        answers: nextAnswers,
        profile: nextProfile,
      })
      setStepCode(targetStep)
    } catch (saveError) {
      Toast.show({
        content: saveError instanceof Error ? saveError.message : '进度保存失败，请重试',
        icon: 'fail',
      })
    } finally {
      setSubmitting(false)
    }
  }

  const goBack = () => {
    if (!previousStepCode || submitting) return
    void saveAndMove(previousStepCode)
  }

  const prepareReport = async (nextProfile = profile) => {
    setSubmitting(true)
    try {
      const state = await prepareMobileOnboardingReport({ answers, profile: nextProfile })
      setProfile({ ...EMPTY_PROFILE, ...state.progress.profile })
      setReport(state.progress.report)
      setStepCode('report')
    } catch (prepareError) {
      Toast.show({
        content: prepareError instanceof Error ? prepareError.message : '经营方案生成失败，请重试',
        icon: 'fail',
      })
    } finally {
      setSubmitting(false)
    }
  }

  const finishOnboarding = async () => {
    setSubmitting(true)
    try {
      const state = await completeMobileOnboarding({ answers, profile })
      onComplete(onboardingToUserData(state))
    } catch (completeError) {
      Toast.show({
        content: completeError instanceof Error ? completeError.message : '引导完成失败，请重试',
        icon: 'fail',
      })
    } finally {
      setSubmitting(false)
    }
  }

  const StepHeader = ({ step }: { step: MobileOnboardingStep }) => (
    <>
      <NavBar onBack={goBack} className="onboarding-nav">
        建立经营档案
      </NavBar>
      <div className="onboarding-progress">
        <span>步骤 {stepIndex + 1} / {steps.length}</span>
        <ProgressBar percent={progress} />
      </div>
      <div className="onboarding-heading">
        <h1>{step.title}</h1>
        {step.description && <p>{step.description}</p>}
      </div>
    </>
  )

  if (loading) {
    return (
      <div className="onboarding-page onboarding-welcome">
        <div className="auth-session-loading">
          <SpinLoading color="primary" />
          <span>正在加载经营引导</span>
        </div>
      </div>
    )
  }

  if (error || !flow || !currentStep) {
    return (
      <div className="onboarding-page onboarding-welcome">
        <Card title="引导流程暂时不可用" className="onboarding-welcome-content">
          <p>{error || '管理员尚未发布手机端引导流程。'}</p>
          <Button block color="primary" loading={loading} onClick={() => void loadOnboarding()}>
            重新加载
          </Button>
        </Card>
      </div>
    )
  }

  if (currentStep.type === 'welcome') {
    return (
      <div className="onboarding-page onboarding-welcome">
        <div className="onboarding-welcome-content">
          <div className="onboarding-logo"><AppstoreOutline /></div>
          <Tag color="primary" fill="outline">{flow.welcome.badge}</Tag>
          <h1>{flow.welcome.title}</h1>
          <p>{flow.welcome.description}</p>
          <Button
            block
            color="primary"
            size="large"
            loading={submitting}
            onClick={() => nextStepCode && void saveAndMove(nextStepCode)}
          >
            {flow.start_button_label}
          </Button>
        </div>
      </div>
    )
  }

  if (currentStep.type === 'single' || currentStep.type === 'multiple') {
    const selected = answers[currentStep.code] || []
    const isIndustry = currentStep.code === 'industry'
    return (
      <div className="onboarding-page onboarding-choice-page">
        <div className="onboarding-choice-content">
          <StepHeader step={currentStep} />
          <Selector
            columns={1}
            multiple={currentStep.multiple}
            value={selected}
            options={currentStep.options.map(option => ({
              value: option.code,
              label: (
                <div className={isIndustry ? 'industry-option' : 'onboarding-option'}>
                  <span className={isIndustry ? 'industry-option-icon' : undefined}>{option.icon}</span>
                  <div>
                    <strong>{option.label}</strong>
                    {option.description && <small>{option.description}</small>}
                  </div>
                </div>
              ),
            }))}
            onChange={values => {
              setAnswers({ ...answers, [currentStep.code]: values })
            }}
            className="onboarding-selector"
          />
        </div>
        <div className="onboarding-choice-footer">
          <div className="onboarding-step-actions">
            <Button
              block
              fill="outline"
              size="large"
              loading={submitting}
              onClick={goBack}
            >
              返回
            </Button>
            <Button
              block
              color="primary"
              size="large"
              loading={submitting}
              disabled={currentStep.required && selected.length === 0}
              onClick={() => nextStepCode && void saveAndMove(nextStepCode)}
              className="onboarding-next"
            >
              下一步
            </Button>
          </div>
        </div>
      </div>
    )
  }

  if (currentStep.type === 'profile') {
    const fields: Array<{
      label: string
      key: keyof Pick<MobileOnboardingProfile, 'company_name' | 'display_name' | 'user_role' | 'city'>
      placeholder: string
    }> = [
      { label: '公司名称', key: 'company_name', placeholder: '请输入公司名称' },
      { label: '你的名字', key: 'display_name', placeholder: '例如：张三' },
      { label: '你的角色', key: 'user_role', placeholder: '例如：创始人 / 总经理' },
      { label: '所在城市', key: 'city', placeholder: '例如：西安' },
    ]
    return (
      <div className="onboarding-page">
        <StepHeader step={currentStep} />
        <List className="onboarding-form">
          {fields.map(field => (
            <List.Item key={field.key} title={field.label}>
              <div className="onboarding-field">
                <label>{field.label}</label>
                <Input
                  value={profile[field.key]}
                  placeholder={field.placeholder}
                  clearable
                  onChange={value => setProfile(previous => ({
                    ...previous,
                    [field.key]: value,
                    skipped_info: false,
                  }))}
                />
              </div>
            </List.Item>
          ))}
        </List>
        <div className="onboarding-actions onboarding-profile-actions">
          <Button
            block
            fill="outline"
            loading={submitting}
            onClick={goBack}
          >
            返回
          </Button>
          <Button
            block
            fill="outline"
            loading={submitting}
            onClick={() => {
              const nextProfile = { ...profile, skipped_info: true }
              setProfile(nextProfile)
              void prepareReport(nextProfile)
            }}
          >
            稍后填写
          </Button>
          <Button
            block
            color="primary"
            loading={submitting}
            onClick={() => void prepareReport({ ...profile, skipped_info: false })}
          >
            生成方案
          </Button>
        </div>
      </div>
    )
  }

  const industryConfig = getIndustryConfig(report?.industry || '通用')
  const strengths = report?.strengths || []
  const team = report?.team || []
  const automation = report?.automation || []
  const manual = report?.manual || []
  const workstreamCount = automation.length + manual.length
  const automationCoverage = workstreamCount
    ? Math.round((automation.length / workstreamCount) * 100)
    : 0

  return (
    <div className="onboarding-page onboarding-report">
      <div className="onboarding-result-hero">
        <div className="onboarding-result-icon" aria-hidden="true">
          <CheckCircleOutline />
        </div>
        <h1>分析完成！</h1>
        <p>你的专属运营方案已生成</p>
      </div>

      <Card
        className="onboarding-result-card onboarding-core-card"
        title={<span className="onboarding-result-card-title"><AppstoreOutline />你的核心优势</span>}
        style={{ borderColor: industryConfig.color }}
      >
        <strong className="report-type">{report?.type || '经营方案'}</strong>
        <p className="report-description">{report?.description || '正在准备你的经营方案。'}</p>
      </Card>

      <Card
        className="onboarding-result-card"
        title={<span className="onboarding-result-card-title"><PieOutline />能力评分</span>}
      >
        <div className="report-strengths">
          {strengths.map(([label, value]) => {
            const score = Math.max(0, Math.min(100, Number(value) || 0))
            return (
              <div key={label}>
                <div className="report-strength-label">
                  <span>{label}</span>
                  <span>{score}/100</span>
                </div>
                <ProgressBar percent={score} style={{ '--fill-color': industryConfig.color }} />
              </div>
            )
          })}
        </div>
      </Card>

      <Card
        className="onboarding-result-card"
        title={(
          <span className="onboarding-result-card-title">
            <TeamOutline />{report?.industry || '经营'}推荐方案
          </span>
        )}
      >
        <div className="report-group">
          <span>核心定位</span>
          <strong className="report-position">{report?.role || '由你负责关键决策，AI 团队协同执行'}</strong>
        </div>
        <div className="report-group">
          <span>推荐雇佣</span>
          <Space wrap>{team.map(item => <Tag key={item} color="primary" fill="outline">{item}</Tag>)}</Space>
        </div>
        <div className="report-group">
          <span>自动化流程</span>
          <Space wrap>{automation.map(item => <Tag key={item} color="success" fill="outline">{item}</Tag>)}</Space>
        </div>
        {manual.length > 0 && (
          <div className="report-group">
            <span>需要你关注</span>
            <Space wrap>{manual.map(item => <Tag key={item} color="warning" fill="outline">{item}</Tag>)}</Space>
          </div>
        )}
      </Card>

      <div className="onboarding-efficiency-card">
        <ClockCircleOutline aria-hidden="true" />
        <strong>自动化覆盖 {automationCoverage}%</strong>
        <p>已规划 {automation.length} 项自动化流程，配置 {team.length} 位 AI 员工协同执行</p>
      </div>

      <div className="onboarding-actions onboarding-report-actions">
        <Button
          block
          color="primary"
          size="large"
          loading={submitting}
          disabled={!report}
          className="onboarding-complete"
          onClick={() => void finishOnboarding()}
        >
          {flow.completion_button_label}
        </Button>
        <Button
          block
          fill="outline"
          size="large"
          loading={submitting}
          onClick={goBack}
        >
          <LeftOutline /> 返回调整
        </Button>
      </div>
    </div>
  )
}

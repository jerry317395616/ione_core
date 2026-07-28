export interface MobileOnboardingOption {
  code: string
  label: string
  icon: string
  description: string
}

export type MobileOnboardingStepType = 'welcome' | 'single' | 'multiple' | 'profile' | 'report'

export interface MobileOnboardingStep {
  code: string
  type: MobileOnboardingStepType
  title: string
  description: string
  required: boolean
  multiple: boolean
  options: MobileOnboardingOption[]
}

export interface MobileOnboardingFlow {
  code: string
  name: string
  version: number
  welcome: {
    badge: string
    title: string
    description: string
  }
  start_button_label: string
  completion_button_label: string
  steps: MobileOnboardingStep[]
}

export interface MobileOnboardingProfile {
  company_name: string
  display_name: string
  user_role: string
  city: string
  skipped_info: boolean
}

export interface MobileOnboardingReport {
  type: string
  description: string
  strengths: Array<[string, number]>
  team: string[]
  automation: string[]
  manual: string[]
  role: string
  industry: string
}

export interface MobileOnboardingState {
  flow: MobileOnboardingFlow
  progress: {
    record: string | null
    status: '未开始' | '进行中' | '已完成'
    completed: boolean
    current_step: string
    answers: Record<string, string[] | string>
    profile: MobileOnboardingProfile
    report: MobileOnboardingReport | null
  }
}

export interface UserData {
  industry: string
  advantage: string[]
  painPoint: string[]
  timeAvailable: string
  companyName: string
  userName: string
  userRole: string
  city: string
  skippedInfo: boolean
}

import { frappeCall } from './frappeRequest'

interface SavePayload {
  current_step?: string
  answers: Record<string, string[]>
  profile: MobileOnboardingProfile
}

export function getMobileOnboarding() {
  return frappeCall<MobileOnboardingState>('ione_core.onboarding.get_mobile_onboarding')
}

export function saveMobileOnboarding(payload: SavePayload) {
  return frappeCall<MobileOnboardingState>(
    'ione_core.onboarding.save_mobile_onboarding_progress',
    { ...payload },
    'POST',
  )
}

export function prepareMobileOnboardingReport(payload: Omit<SavePayload, 'current_step'>) {
  return frappeCall<MobileOnboardingState>(
    'ione_core.onboarding.prepare_mobile_onboarding_report',
    { ...payload },
    'POST',
  )
}

export function completeMobileOnboarding(payload: Omit<SavePayload, 'current_step'>) {
  return frappeCall<MobileOnboardingState>(
    'ione_core.onboarding.complete_mobile_onboarding',
    { ...payload },
    'POST',
  )
}

export function resetMobileOnboarding() {
  return frappeCall<MobileOnboardingState>(
    'ione_core.onboarding.reset_mobile_onboarding',
    {},
    'POST',
  )
}

function selectedCodes(value: string[] | string | undefined): string[] {
  if (Array.isArray(value)) return value
  return value ? [value] : []
}

function selectedLabels(state: MobileOnboardingState, stepCode: string): string[] {
  const options = state.flow.steps.find(step => step.code === stepCode)?.options || []
  const labels = new Map(options.map(option => [option.code, option.label]))
  return selectedCodes(state.progress.answers[stepCode]).map(code => labels.get(code) || code)
}

export function onboardingToUserData(state: MobileOnboardingState): UserData {
  const profile = state.progress.profile
  return {
    industry: selectedLabels(state, 'industry')[0] || '通用',
    advantage: selectedLabels(state, 'advantage'),
    painPoint: selectedLabels(state, 'pain_point'),
    timeAvailable: selectedLabels(state, 'time_available')[0] || '',
    companyName: profile.company_name || '',
    userName: profile.display_name || '',
    userRole: profile.user_role || '创始人/总经理',
    city: profile.city || '中国',
    skippedInfo: profile.skipped_info,
  }
}

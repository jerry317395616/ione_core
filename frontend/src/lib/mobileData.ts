import { frappeCall } from './frappeRequest'

export interface MobileTodo {
  id: string
  title: string
  source: string
  status: string
  priority?: string
  due_date?: string | null
  route: string
}

export interface GrowthPlanRecord {
  name: string
  title: string
  category?: string
  status: string
  progress: number
  start_date?: string
  end_date?: string
  objective?: string
  route: string
}

export interface AchievementRecord {
  name: string
  achievement_code?: string
  title: string
  achievement_type?: string
  points: number
  gold: number
  awarded_at?: string
  description?: string
}

export interface MobileTaskCenter {
  todos: MobileTodo[]
  plans: GrowthPlanRecord[]
  achievements: AchievementRecord[]
}

export interface MobileFinance {
  available: boolean
  company?: string
  currency: string
  as_of_date: string
  balance: {
    assets: number | null
    liabilities: number | null
    equity: number | null
  }
  month: {
    available: boolean
    income: number | null
    expense: number | null
    profit: number | null
  }
  receivable: { amount: number | null; count: number | null }
  payable: { amount: number | null; count: number | null }
  weekly_income: { date: string; income: number | null }[]
  accounts: {
    name: string
    code: string
    label: string
    root_type: string
    balance: number
    route: string
  }[]
  routes: Record<string, string>
}

export interface MobileActivity {
  tasks: {
    name: string
    title: string
    status: string
    priority: string
    progress: number
    assigned_agent?: string
    started_at?: string
    completed_at?: string
    modified: string
    error_message?: string
    route: string
  }[]
  logs: {
    name: string
    task: string
    agent?: string
    event_type: string
    level: string
    duration_ms?: number
    message: string
    model_name?: string
    creation: string
  }[]
  stats: { total: number; completed: number; running: number; failed: number }
}

export interface MobileProfile {
  user: {
    username: string
    full_name: string
    user_image?: string
    roles: string[]
  }
  company: {
    name?: string
    company_name?: string
    abbr?: string
    default_currency?: string
    country?: string
    tax_id?: string
    date_of_establishment?: string
    domain?: string
  }
  employee_count: number | null
  department_count: number | null
  apps: { name: string; title: string; route: string; logo?: string; category: string }[]
  achievements: AchievementRecord[]
  totals: { points: number; gold: number }
}

export interface MobileNotification {
  id: string
  title: string
  message: string
  priority: string
  status: string
  due_date?: string
  source: string
  route: string
}

export interface MobileChannel {
  name: string
  channel_name: string
  channel_type: string
  status: string
  account_name?: string
  last_published_at?: string
}

export interface MobilePublishJob {
  name: string
  title: string
  channel: string
  status: string
  scheduled_at?: string
  published_at?: string
  result_url?: string
}

export interface MobileEvaluation {
  name: string
  task: string
  task_title: string
  agent?: string
  agent_name: string
  score: number
  grade: 'S' | 'A' | 'B' | 'C' | 'D' | 'F'
  evaluated_at: string
  dimensions: { dimension: 'accuracy' | 'completeness' | 'speed' | 'satisfaction'; score: number }[]
  comments?: string
}

export interface MobileExperience {
  name: string
  title: string
  category?: string
  author_user: string
  status: string
  useful_count: number
  content: string
  tags?: string
  modified: string
  route: string
}

export const getMobileTaskCenter = () =>
  frappeCall<MobileTaskCenter>('ione_core.api.get_mobile_task_center')

export const getMobileFinance = () =>
  frappeCall<MobileFinance>('ione_core.api.get_mobile_finance')

export const getMobileActivity = () =>
  frappeCall<MobileActivity>('ione_core.api.get_mobile_activity')

export const getMobileProfile = () =>
  frappeCall<MobileProfile>('ione_core.api.get_mobile_profile')

export const getMobileNotifications = () =>
  frappeCall<{ notifications: MobileNotification[] }>('ione_core.api.get_mobile_notifications')

export const getMobileChannels = () =>
  frappeCall<{ channels: MobileChannel[]; jobs: MobilePublishJob[] }>('ione_core.api.get_mobile_channels')

export const createMobileChannel = (channel_name: string, channel_type: string, account_name?: string) =>
  frappeCall<{ name: string }>(
    'ione_core.api.create_mobile_channel',
    { channel_name, channel_type, account_name },
    'POST',
  )

export const createMobilePublishJobs = (content: string, channels: string[]) =>
  frappeCall<{ jobs: string[] }>(
    'ione_core.api.create_mobile_publish_jobs',
    { content, channels: JSON.stringify(channels) },
    'POST',
  )

export const getMobileEvaluations = () =>
  frappeCall<{ evaluations: MobileEvaluation[] }>('ione_core.api.get_mobile_evaluations')

export const getMobileExperiences = () =>
  frappeCall<{ experiences: MobileExperience[] }>('ione_core.api.get_mobile_experiences')

export const createMobileExperience = (title: string, content: string, category?: string, tags?: string) =>
  frappeCall<{ name: string }>(
    'ione_core.api.create_mobile_experience',
    { title, content, category, tags },
    'POST',
  )

export const markExperienceUseful = (name: string) =>
  frappeCall<{ useful_count: number }>(
    'ione_core.api.mark_experience_useful',
    { name },
    'POST',
  )

export function openFrappeRoute(route: string) {
  window.open(route, '_blank', 'noopener,noreferrer')
}

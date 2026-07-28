export interface FrappeApp {
  name: string
  title: string
  route: string
  logo?: string | null
  category: string
  sequence: number
}

export interface FrappeMetric {
  key: string
  label: string
  value: number
  source: string
  route: string
}

export interface FrappeOverviewMetric {
  key: string
  label: string
  value: number | null
  source: string
  route: string
  format: 'number' | 'currency'
  tone: 'primary' | 'positive' | 'negative'
  available: boolean
}

export interface FrappeProfitProgress {
  actual: number | null
  target: number | null
  percent: number | null
  currency: string
  route: string
}

export interface FrappeTodo {
  id: string
  title: string
  source: string
  status: string
  priority?: string | null
  due_date?: string | null
  route: string
}

export interface FrappeDashboard {
  metrics: FrappeMetric[]
  overview: FrappeOverviewMetric[]
  currency: string
  company?: string | null
  as_of_date: string
  profit_progress: FrappeProfitProgress
  todos: FrappeTodo[]
  apps: FrappeApp[]
}

export interface FrappeBootstrap {
  user: {
    username: string
    full_name: string
    user_image?: string | null
    language?: string | null
    time_zone?: string | null
    roles: string[]
  }
  site: string
  csrf_token: string
  apps: FrappeApp[]
  features: {
    ai_employees?: boolean
    ai_tasks: boolean
    approvals: boolean
    background_jobs: boolean
  }
}

import { frappeCall, setCsrfToken } from './frappeRequest'

export async function getFrappeBootstrap() {
  const bootstrap = await frappeCall<FrappeBootstrap>('ione_core.api.get_bootstrap')
  setCsrfToken(bootstrap.csrf_token)
  return bootstrap
}

export function getFrappeDashboard() {
  return frappeCall<FrappeDashboard>('ione_core.api.get_dashboard')
}

export function getFrappeTodos() {
  return frappeCall<FrappeTodo[]>('ione_core.api.get_unified_todos')
}

export function getFrappeUrl(route: string) {
  const normalizedRoute = route.startsWith('/') ? route : `/${route}`
  return `${window.location.origin}${normalizedRoute}`
}

export type AiEmployeeStatus = '草稿' | '试用' | '在职' | '暂停' | '离职'
export type AiTaskStatus =
  | '草稿'
  | '待审批'
  | '已排队'
  | '执行中'
  | '等待确认'
  | '已完成'
  | '执行失败'
  | '已取消'

export interface AiEmployeeSummary {
  name: string
  agent_code: string
  agent_name: string
  agent_type: string
  status: AiEmployeeStatus
  avatar?: string | null
  company?: string | null
  department?: string | null
  designation?: string | null
  operating_mode?: '辅助' | '半自动' | '自动' | null
  last_active?: string | null
  open_tasks: number
  completed_tasks: number
  route: string
}

export interface AiTaskSummary {
  name: string
  title: string
  status: AiTaskStatus
  priority: '低' | '普通' | '高' | '紧急'
  progress: number
  due_date?: string | null
  modified: string
}

export interface AiEmployeeDetail {
  employee: AiEmployeeSummary & {
    supervisor?: string | null
    description?: string | null
    responsibilities?: string | null
  }
  metrics: {
    open: number
    completed: number
    failed: number
  }
  tasks: AiTaskSummary[]
}

export interface AiTaskDocument extends AiTaskSummary {
  assigned_agent?: string | null
  prompt?: string | null
  result_summary?: string | null
  error_message?: string | null
  approval_required?: 0 | 1
  risk_level?: string | null
  started_at?: string | null
  completed_at?: string | null
}

export interface QueueAiTaskInput {
  title: string
  prompt: string
  assigned_agent: string
  priority: '低' | '普通' | '高' | '紧急'
  approval_required: boolean
}

export interface QueueAiTaskResult {
  name: string
  status: AiTaskStatus
}

import { frappeCall } from './frappeRequest'

export function listAiEmployees(limit = 50) {
  return frappeCall<AiEmployeeSummary[]>('ione_core.api.get_ai_employees', { limit })
}

export function getAiEmployee(name: string) {
  return frappeCall<AiEmployeeDetail>('ione_core.api.get_ai_employee', { name })
}

export function getAiTask(name: string) {
  return frappeCall<AiTaskDocument>('ione_core.api.get_ai_task', { name })
}

export function queueAiTask(input: QueueAiTaskInput) {
  return frappeCall<QueueAiTaskResult>(
    'ione_core.ai.queue_ai_task',
    {
      title: input.title,
      prompt: input.prompt,
      assigned_agent: input.assigned_agent,
      priority: input.priority,
      approval_required: input.approval_required,
    },
    'POST',
  )
}

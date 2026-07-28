export type SmartRecordStatus =
  | '草稿'
  | '分析中'
  | '待确认'
  | '待审批'
  | '执行中'
  | '已完成'
  | '部分完成'
  | '失败'
  | '已取消'

export type SmartRecordInputType = '文字' | '语音' | '图片' | '文件'

export interface SmartRecordCapability {
  action_type: string
  label: string
  source: string
  placeholder: string
}

export interface SmartRecordCapabilities {
  provider: string
  actions: SmartRecordCapability[]
}

export interface SmartRecordAction {
  name: string
  action_index: number
  title: string
  action_type: string
  target_app: string
  target_doctype?: string | null
  operation: string
  payload: Record<string, unknown>
  confidence: number
  risk_level: '低' | '中' | '高' | '关键'
  approval_required: boolean
  status: string
  target_name?: string | null
  target_route?: string | null
  result_message?: string | null
}

export interface SmartRecord {
  name: string
  title: string
  input_type: SmartRecordInputType
  preferred_action?: string | null
  status: SmartRecordStatus
  raw_text?: string | null
  attachment?: string | null
  file_name?: string | null
  content_type?: string | null
  summary?: string | null
  record_type?: string | null
  confidence: number
  analysis_task?: string | null
  execution_task?: string | null
  approval?: string | null
  error_message?: string | null
  confirmed_at?: string | null
  completed_at?: string | null
  creation: string
  modified: string
  actions: SmartRecordAction[]
}

export interface SmartRecordListItem {
  name: string
  title: string
  input_type: SmartRecordInputType
  status: SmartRecordStatus
  record_type?: string | null
  confidence?: number
  summary?: string | null
  file_name?: string | null
  creation: string
  modified: string
}

import { frappeCall } from './frappeRequest'

interface CreateSmartRecordInput {
  title?: string
  rawText: string
  inputType: SmartRecordInputType
  preferredAction?: string | null
  file?: File | null
}

interface EditableAction {
  name: string
  action_index: number
  title: string
  payload: Record<string, unknown>
  approval_required?: boolean
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('无法读取附件'))
    reader.readAsDataURL(file)
  })
}

export async function extractImageText(file: File): Promise<string> {
  const imageBase64 = await fileToDataUrl(file)
  const record = await frappeCall<SmartRecord>(
    'ione_core.smart_record.create_smart_record',
    {
      title: `识别 ${file.name}`,
      raw_text: '',
      input_type: '图片',
      file_name: file.name,
      content_type: file.type,
      file_content: imageBase64,
    },
    'POST',
  )
  return record.raw_text || record.summary || ''
}

export async function createSmartRecord(input: CreateSmartRecordInput) {
  const fileContent = input.file ? await fileToDataUrl(input.file) : undefined
  return frappeCall<SmartRecord>(
    'ione_core.smart_record.create_smart_record',
    {
      title: input.title,
      raw_text: input.rawText,
      input_type: input.inputType,
      preferred_action: input.preferredAction,
      file_name: input.file?.name,
      content_type: input.file?.type,
      file_content: fileContent,
    },
    'POST',
  )
}

export function listSmartRecords(limit = 20) {
  return frappeCall<SmartRecordListItem[]>(
    'ione_core.smart_record.list_smart_records',
    { limit },
  )
}

export function getSmartRecordCapabilities() {
  return frappeCall<SmartRecordCapabilities>('ione_core.smart_record.get_smart_record_capabilities')
}

export function getSmartRecord(name: string) {
  return frappeCall<SmartRecord>('ione_core.smart_record.get_smart_record', { record_name: name })
}

export function confirmSmartRecord(name: string, actions: EditableAction[]) {
  return frappeCall<SmartRecord>(
    'ione_core.smart_record.confirm_smart_record',
    { record_name: name, actions },
    'POST',
  )
}

export function retrySmartRecord(name: string) {
  return frappeCall<SmartRecord>(
    'ione_core.smart_record.retry_smart_record',
    { record_name: name },
    'POST',
  )
}

export function cancelSmartRecord(name: string) {
  return frappeCall<SmartRecord>(
    'ione_core.smart_record.cancel_smart_record',
    { record_name: name },
    'POST',
  )
}

export function getManagerUrl(route: string) {
  const normalized = route.startsWith('/') ? route : `/${route}`
  return `${window.location.origin}${normalized}`
}

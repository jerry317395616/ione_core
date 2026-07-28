import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Button,
  Card,
  Empty,
  Grid,
  Input,
  List,
  NoticeBar,
  ProgressBar,
  Segmented,
  Skeleton,
  Space,
  Tag,
  TextArea,
  Toast,
} from 'antd-mobile'
import {
  AudioOutline,
  BillOutline,
  CalendarOutline,
  CameraOutline,
  CheckOutline,
  ClockCircleOutline,
  CloseOutline,
  FileOutline,
  MessageOutline,
  RedoOutline,
  RightOutline,
  SendOutline,
  StopOutline,
  UnorderedListOutline,
  UserAddOutline,
  UserContactOutline,
} from 'antd-mobile-icons'
import type { LayoutMode } from '../LayoutThemes'
import {
  cancelSmartRecord,
  confirmSmartRecord,
  createSmartRecord,
  extractImageText,
  getManagerUrl,
  getSmartRecord,
  getSmartRecordCapabilities,
  listSmartRecords,
  retrySmartRecord,
  type SmartRecord,
  type SmartRecordAction,
  type SmartRecordCapabilities,
  type SmartRecordInputType,
  type SmartRecordListItem,
} from '../lib/smartRecord'

interface SpeechRecognitionResultLike {
  0: { transcript: string }
}

interface SpeechRecognitionEventLike {
  results: { 0: SpeechRecognitionResultLike }
}

interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: (() => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

const STATUS_COLOR: Record<string, 'default' | 'primary' | 'success' | 'warning' | 'danger'> = {
  草稿: 'default',
  分析中: 'primary',
  待确认: 'warning',
  待审批: 'warning',
  执行中: 'primary',
  已完成: 'success',
  部分完成: 'warning',
  失败: 'danger',
  已取消: 'default',
}

const CAPABILITY_ICONS: Record<string, ReactNode> = {
  创建待办: <UnorderedListOutline />,
  创建客户: <UserAddOutline />,
  创建销售线索: <UserContactOutline />,
  创建客户工单: <MessageOutline />,
  创建请假: <CalendarOutline />,
  创建财务草稿: <BillOutline />,
}

const FIELD_LABELS: Record<string, string> = {
  description: '业务说明',
  customer_name: '客户名称',
  first_name: '联系人',
  organization: '企业名称',
  subject: '工单主题',
  leave_type: '请假类型',
  from_date: '开始日期',
  to_date: '结束日期',
  employee: '员工',
  direction: '收支方向',
  amount: '金额',
  date: '发生日期',
  attachment: '附件',
}

const POLLING_STATUSES = new Set(['分析中', '待审批', '执行中'])
const PENDING_STATUSES = new Set(['待确认', '待审批', '执行中'])
const ACCEPTED_FILES = 'image/*,.pdf,.txt,.csv,.doc,.docx,.xls,.xlsx'

function fieldValue(payload: Record<string, unknown>, key: string) {
  const value = payload[key]
  return value === null || value === undefined ? '' : String(value)
}

function actionDescription(action: SmartRecordAction) {
  if (action.result_message) return action.result_message
  if (action.target_doctype) return `${action.target_app} · ${action.target_doctype}`
  return action.target_app
}

function requiredMissingFields(action: SmartRecordAction) {
  const payload = action.payload
  const empty = (key: string) => !fieldValue(payload, key).trim()

  switch (action.action_type) {
    case '创建待办':
      return empty('description') ? ['description'] : []
    case '创建客户':
      return empty('customer_name') ? ['customer_name'] : []
    case '创建销售线索':
      return empty('first_name') && empty('organization') ? ['first_name 或 organization'] : []
    case '创建客户工单':
      return ['subject', 'description'].filter(empty)
    case '创建请假':
      return ['leave_type', 'from_date', 'to_date'].filter(empty)
    case '创建财务草稿':
      return ['direction', 'amount', 'date', 'description'].filter(empty)
    default:
      return []
  }
}

function missingFieldLabel(field: string) {
  if (field === 'first_name 或 organization') return '联系人或企业名称'
  return FIELD_LABELS[field] || field
}

function ActionEditor({
  action,
  onChange,
}: {
  action: SmartRecordAction
  onChange: (next: SmartRecordAction) => void
}) {
  const updatePayload = (key: string, value: unknown) => {
    onChange({ ...action, payload: { ...action.payload, [key]: value } })
  }
  const missingFields = requiredMissingFields(action)

  return (
    <Card className="smart-action-card">
      <div className="smart-action-heading">
        <div>
          <Tag color="primary" fill="outline">{action.action_type}</Tag>
          <span className="smart-action-target">
            {action.target_app}{action.target_doctype ? ` · ${action.target_doctype}` : ''}
          </span>
        </div>
        <Space>
          <Tag fill="outline">风险 {action.risk_level}</Tag>
          {action.approval_required && <Tag color="warning" fill="outline">需审批</Tag>}
        </Space>
      </div>

      {missingFields.length > 0 && (
        <NoticeBar
          color="alert"
          content={`待补充：${missingFields.map(missingFieldLabel).join('、')}`}
        />
      )}

      <label className="smart-field">
        <span>操作名称</span>
        <Input value={action.title} onChange={value => onChange({ ...action, title: value })} />
      </label>

      {action.action_type === '创建待办' && (
        <>
          <label className="smart-field">
            <span>事项内容</span>
            <TextArea
              value={fieldValue(action.payload, 'description')}
              onChange={value => updatePayload('description', value)}
              autoSize={{ minRows: 2, maxRows: 4 }}
            />
          </label>
          <div className="smart-field-row">
            <label className="smart-field">
              <span>截止日期</span>
              <input
                type="date"
                value={fieldValue(action.payload, 'date')}
                onChange={event => updatePayload('date', event.target.value)}
              />
            </label>
            <label className="smart-field">
              <span>优先级</span>
              <Segmented
                options={[
                  { label: '低', value: 'Low' },
                  { label: '普通', value: 'Medium' },
                  { label: '高', value: 'High' },
                ]}
                value={fieldValue(action.payload, 'priority') || 'Medium'}
                onChange={value => updatePayload('priority', value)}
              />
            </label>
          </div>
        </>
      )}

      {action.action_type === '创建客户' && (
        <>
          <label className="smart-field">
            <span>客户名称</span>
            <Input value={fieldValue(action.payload, 'customer_name')} onChange={value => updatePayload('customer_name', value)} />
          </label>
          <label className="smart-field">
            <span>客户类型</span>
            <Segmented
              options={[{ label: '企业', value: 'Company' }, { label: '个人', value: 'Individual' }]}
              value={fieldValue(action.payload, 'customer_type') || 'Company'}
              onChange={value => updatePayload('customer_type', value)}
            />
          </label>
          <div className="smart-field-row">
            <label className="smart-field">
              <span>手机号</span>
              <Input value={fieldValue(action.payload, 'mobile_no')} onChange={value => updatePayload('mobile_no', value)} />
            </label>
            <label className="smart-field">
              <span>邮箱</span>
              <Input value={fieldValue(action.payload, 'email_id')} onChange={value => updatePayload('email_id', value)} />
            </label>
          </div>
        </>
      )}

      {action.action_type === '创建销售线索' && (
        <>
          <div className="smart-field-row">
            <label className="smart-field">
              <span>联系人</span>
              <Input value={fieldValue(action.payload, 'first_name')} onChange={value => updatePayload('first_name', value)} />
            </label>
            <label className="smart-field">
              <span>企业</span>
              <Input value={fieldValue(action.payload, 'organization')} onChange={value => updatePayload('organization', value)} />
            </label>
          </div>
          <div className="smart-field-row">
            <label className="smart-field">
              <span>邮箱</span>
              <Input value={fieldValue(action.payload, 'email')} onChange={value => updatePayload('email', value)} />
            </label>
            <label className="smart-field">
              <span>手机号</span>
              <Input value={fieldValue(action.payload, 'mobile_no')} onChange={value => updatePayload('mobile_no', value)} />
            </label>
          </div>
        </>
      )}

      {action.action_type === '创建客户工单' && (
        <>
          <label className="smart-field">
            <span>工单主题</span>
            <Input value={fieldValue(action.payload, 'subject')} onChange={value => updatePayload('subject', value)} />
          </label>
          <label className="smart-field">
            <span>问题描述</span>
            <TextArea
              value={fieldValue(action.payload, 'description')}
              onChange={value => updatePayload('description', value)}
              autoSize={{ minRows: 2, maxRows: 5 }}
            />
          </label>
          <label className="smart-field">
            <span>客户邮箱</span>
            <Input value={fieldValue(action.payload, 'raised_by')} onChange={value => updatePayload('raised_by', value)} />
          </label>
        </>
      )}

      {action.action_type === '创建请假' && (
        <>
          <div className="smart-field-row">
            <label className="smart-field">
              <span>员工</span>
              <Input
                placeholder="默认匹配当前用户"
                value={fieldValue(action.payload, 'employee')}
                onChange={value => updatePayload('employee', value)}
              />
            </label>
            <label className="smart-field">
              <span>请假类型</span>
              <Input value={fieldValue(action.payload, 'leave_type')} onChange={value => updatePayload('leave_type', value)} />
            </label>
          </div>
          <div className="smart-field-row">
            <label className="smart-field">
              <span>开始日期</span>
              <input type="date" value={fieldValue(action.payload, 'from_date')} onChange={event => updatePayload('from_date', event.target.value)} />
            </label>
            <label className="smart-field">
              <span>结束日期</span>
              <input type="date" value={fieldValue(action.payload, 'to_date')} onChange={event => updatePayload('to_date', event.target.value)} />
            </label>
          </div>
          <label className="smart-field">
            <span>请假原因</span>
            <TextArea value={fieldValue(action.payload, 'description')} onChange={value => updatePayload('description', value)} autoSize={{ minRows: 2, maxRows: 4 }} />
          </label>
        </>
      )}

      {action.action_type === '创建财务草稿' && (
        <>
          <div className="smart-field-row">
            <label className="smart-field">
              <span>收支方向</span>
              <Segmented
                options={['收入', '支出']}
                value={fieldValue(action.payload, 'direction') || '支出'}
                onChange={value => updatePayload('direction', value)}
              />
            </label>
            <label className="smart-field">
              <span>金额</span>
              <Input type="number" value={fieldValue(action.payload, 'amount')} onChange={value => updatePayload('amount', value)} />
            </label>
          </div>
          <div className="smart-field-row">
            <label className="smart-field">
              <span>往来单位</span>
              <Input value={fieldValue(action.payload, 'party')} onChange={value => updatePayload('party', value)} />
            </label>
            <label className="smart-field">
              <span>发生日期</span>
              <input type="date" value={fieldValue(action.payload, 'date')} onChange={event => updatePayload('date', event.target.value)} />
            </label>
          </div>
          <label className="smart-field">
            <span>业务说明</span>
            <TextArea value={fieldValue(action.payload, 'description')} onChange={value => updatePayload('description', value)} autoSize={{ minRows: 2, maxRows: 4 }} />
          </label>
        </>
      )}

      {(action.action_type === '归档文件' || action.action_type === '仅记录') && (
        <label className="smart-field">
          <span>记录说明</span>
          <TextArea value={fieldValue(action.payload, 'description')} onChange={value => updatePayload('description', value)} autoSize={{ minRows: 2, maxRows: 4 }} />
        </label>
      )}
    </Card>
  )
}

export default function IntelligentInputPage({ layoutMode }: { layoutMode: LayoutMode }) {
  const [view, setView] = useState<'capture' | 'history'>('capture')
  const [inputType, setInputType] = useState<SmartRecordInputType>('文字')
  const [rawText, setRawText] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selectedAction, setSelectedAction] = useState<string | null>(null)
  const [capabilities, setCapabilities] = useState<SmartRecordCapabilities>({ provider: 'OpenClaw', actions: [] })
  const [capabilityError, setCapabilityError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [activeRecord, setActiveRecord] = useState<SmartRecord | null>(null)
  const [draftActions, setDraftActions] = useState<SmartRecordAction[]>([])
  const [history, setHistory] = useState<SmartRecordListItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)

  const selectedCapability = capabilities.actions.find(item => item.action_type === selectedAction) || null
  const pendingRecords = useMemo(() => history.filter(item => PENDING_STATUSES.has(item.status)).slice(0, 4), [history])
  const recentRecords = useMemo(() => history.filter(item => !PENDING_STATUSES.has(item.status)).slice(0, 5), [history])
  const unresolvedFields = useMemo(
    () => draftActions.flatMap(action => requiredMissingFields(action).map(field => `${action.title}：${missingFieldLabel(field)}`)),
    [draftActions]
  )

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await listSmartRecords(30))
    } catch (error) {
      Toast.show({ icon: 'fail', content: error instanceof Error ? error.message : '加载记录失败' })
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshHistory()
    getSmartRecordCapabilities()
      .then(result => {
        setCapabilities(result)
        setCapabilityError('')
      })
      .catch(error => setCapabilityError(error instanceof Error ? error.message : '无法读取业务权限'))
  }, [refreshHistory])

  useEffect(() => {
    setDraftActions(activeRecord?.actions.map(action => ({ ...action, payload: { ...action.payload } })) || [])
  }, [activeRecord])

  const activeRecordName = activeRecord?.name
  const activeRecordStatus = activeRecord?.status

  useEffect(() => {
    if (!activeRecordName || !activeRecordStatus || !POLLING_STATUSES.has(activeRecordStatus)) return
    let cancelled = false
    const poll = async () => {
      try {
        const next = await getSmartRecord(activeRecordName)
        if (!cancelled) {
          setActiveRecord(next)
          if (!POLLING_STATUSES.has(next.status)) refreshHistory()
        }
      } catch (error) {
        if (!cancelled) console.error('智能记录状态刷新失败', error)
      }
    }
    const interval = window.setInterval(poll, 1800)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [activeRecordName, activeRecordStatus, refreshHistory])

  const resetCapture = () => {
    setActiveRecord(null)
    setRawText('')
    setSelectedFile(null)
    setSelectedAction(null)
    setInputType('文字')
    setView('capture')
  }

  const selectFile = (file: File | undefined, type: SmartRecordInputType) => {
    if (!file) return
    if (file.size > 10 * 1024 * 1024) {
      Toast.show({ icon: 'fail', content: '单个附件不能超过 10 MB' })
      return
    }
    setSelectedFile(file)
    setInputType(type)
  }

  const toggleVoice = () => {
    if (isListening) {
      recognitionRef.current?.stop()
      return
    }
    const speechWindow = window as typeof window & {
      SpeechRecognition?: SpeechRecognitionConstructor
      webkitSpeechRecognition?: SpeechRecognitionConstructor
    }
    const Recognition = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition
    if (!Recognition) {
      Toast.show({ content: '当前浏览器不支持语音识别' })
      return
    }
    const recognition = new Recognition()
    recognition.lang = 'zh-CN'
    recognition.continuous = false
    recognition.interimResults = false
    recognition.onresult = event => {
      setRawText(current => [current, event.results[0][0].transcript].filter(Boolean).join('\n'))
      setInputType('语音')
    }
    recognition.onerror = () => Toast.show({ icon: 'fail', content: '语音识别失败' })
    recognition.onend = () => setIsListening(false)
    recognitionRef.current = recognition
    setIsListening(true)
    recognition.start()
  }

  const submitRecord = async () => {
    if (!rawText.trim() && !selectedFile) {
      Toast.show({ content: '请输入业务内容或选择附件' })
      return
    }
    setSubmitting(true)
    try {
      let analysisText = rawText.trim()
      if (selectedFile?.type.startsWith('image/')) {
        const recognizedText = await extractImageText(selectedFile)
        if (!recognizedText.trim()) throw new Error('图片中没有识别到可分析的文字')
        analysisText = [analysisText, `图片识别文本：\n${recognizedText}`].filter(Boolean).join('\n\n')
      } else if (selectedFile && (selectedFile.type.startsWith('text/') || /\.(txt|csv)$/i.test(selectedFile.name))) {
        const fileText = await selectedFile.text()
        analysisText = [analysisText, `附件文本：\n${fileText.slice(0, 20000)}`].filter(Boolean).join('\n\n')
      } else if (selectedFile && !analysisText) {
        throw new Error('该文件类型需要补充业务说明后再处理')
      }
      const record = await createSmartRecord({
        rawText: analysisText,
        inputType,
        preferredAction: selectedCapability?.action_type,
        file: selectedFile,
      })
      setActiveRecord(record)
      refreshHistory()
    } catch (error) {
      Toast.show({ icon: 'fail', content: error instanceof Error ? error.message : '提交失败' })
    } finally {
      setSubmitting(false)
    }
  }

  const confirmRecord = async () => {
    if (!activeRecord || unresolvedFields.length > 0) return
    setSubmitting(true)
    try {
      const record = await confirmSmartRecord(
        activeRecord.name,
        draftActions.map(action => ({
          name: action.name,
          action_index: action.action_index,
          title: action.title,
          payload: action.payload,
          approval_required: action.approval_required,
        }))
      )
      setActiveRecord(record)
      refreshHistory()
    } catch (error) {
      Toast.show({ icon: 'fail', content: error instanceof Error ? error.message : '确认失败' })
    } finally {
      setSubmitting(false)
    }
  }

  const cancelRecord = async () => {
    if (!activeRecord) return
    setSubmitting(true)
    try {
      setActiveRecord(await cancelSmartRecord(activeRecord.name))
      refreshHistory()
    } catch (error) {
      Toast.show({ icon: 'fail', content: error instanceof Error ? error.message : '取消失败' })
    } finally {
      setSubmitting(false)
    }
  }

  const retryRecord = async () => {
    if (!activeRecord) return
    setSubmitting(true)
    try {
      setActiveRecord(await retrySmartRecord(activeRecord.name))
    } catch (error) {
      Toast.show({ icon: 'fail', content: error instanceof Error ? error.message : '重新分析失败' })
    } finally {
      setSubmitting(false)
    }
  }

  const openHistoryRecord = async (name: string) => {
    setSubmitting(true)
    try {
      setActiveRecord(await getSmartRecord(name))
      setView('capture')
    } catch (error) {
      Toast.show({ icon: 'fail', content: error instanceof Error ? error.message : '打开记录失败' })
    } finally {
      setSubmitting(false)
    }
  }

  const renderRecordList = (items: SmartRecordListItem[], emptyText: string) => {
    if (historyLoading) return <Skeleton.Paragraph lineCount={3} animated />
    if (items.length === 0) return <div className="smart-empty-state"><Empty description={emptyText} /></div>
    return (
      <List className="smart-history-list">
        {items.map(item => (
          <List.Item
            key={item.name}
            clickable
            prefix={<span className={`smart-history-dot smart-history-dot-${STATUS_COLOR[item.status] || 'default'}`} />}
            description={item.summary || item.file_name || item.input_type}
            extra={<Tag color={STATUS_COLOR[item.status] || 'default'} fill="outline">{item.status}</Tag>}
            onClick={() => openHistoryRecord(item.name)}
          >
            {item.title}
          </List.Item>
        ))}
      </List>
    )
  }

  const renderCapture = () => (
    <>
      {capabilityError && <NoticeBar color="alert" content={capabilityError} className="smart-page-notice" />}

      {capabilities.actions.length > 0 && (
        <section className="smart-capability-section">
          <div className="smart-section-title">
            <h2>业务操作</h2>
            <span>按当前权限</span>
          </div>
          <Grid columns={3} gap={8}>
            {capabilities.actions.map(capability => (
              <Grid.Item key={capability.action_type}>
                <button
                  type="button"
                  className={`smart-capability${selectedAction === capability.action_type ? ' smart-capability-active' : ''}`}
                  aria-pressed={selectedAction === capability.action_type}
                  onClick={() => setSelectedAction(current => current === capability.action_type ? null : capability.action_type)}
                >
                  <span aria-hidden="true">{CAPABILITY_ICONS[capability.action_type] || <SendOutline />}</span>
                  <strong>{capability.label}</strong>
                  <small>{capability.source}</small>
                </button>
              </Grid.Item>
            ))}
          </Grid>
        </section>
      )}

      <section className="smart-capture-panel">
        {selectedCapability && (
          <div className="smart-selected-action">
            <Tag color="primary">{selectedCapability.label}</Tag>
            <span>{selectedCapability.source}</span>
            <Button fill="none" size="mini" aria-label="取消指定操作" onClick={() => setSelectedAction(null)}>
              <CloseOutline />
            </Button>
          </div>
        )}
        <div className="smart-text-entry">
          <TextArea
            placeholder={selectedCapability?.placeholder || '输入要办理的业务'}
            value={rawText}
            onChange={setRawText}
            autoSize={{ minRows: 5, maxRows: 10 }}
            maxLength={10000}
            showCount
          />
        </div>
        {selectedFile && (
          <div className="smart-selected-file">
            <FileOutline />
            <div>
              <strong>{selectedFile.name}</strong>
              <span>{(selectedFile.size / 1024).toFixed(1)} KB</span>
            </div>
            <Button fill="none" size="mini" aria-label="移除附件" onClick={() => setSelectedFile(null)}>
              <CloseOutline />
            </Button>
          </div>
        )}
        {isListening && <NoticeBar color="alert" content="正在聆听" />}
        <div className="smart-capture-toolbar">
          <Space>
            <Button fill="outline" aria-label={isListening ? '停止语音输入' : '语音输入'} onClick={toggleVoice}>
              {isListening ? <StopOutline /> : <AudioOutline />}
            </Button>
            <Button fill="outline" aria-label="拍照或选择图片" onClick={() => imageInputRef.current?.click()}>
              <CameraOutline />
            </Button>
            <Button fill="outline" aria-label="选择文件" onClick={() => fileInputRef.current?.click()}>
              <FileOutline />
            </Button>
          </Space>
          <Button color="primary" loading={submitting} disabled={submitting} onClick={submitRecord}>
            <SendOutline /> 智能处理
          </Button>
        </div>
        <input ref={imageInputRef} type="file" accept="image/*" capture="environment" hidden onChange={event => selectFile(event.target.files?.[0], '图片')} />
        <input ref={fileInputRef} type="file" accept={ACCEPTED_FILES} hidden onChange={event => selectFile(event.target.files?.[0], '文件')} />
      </section>

      {pendingRecords.length > 0 && (
        <section className="smart-history-section">
          <div className="smart-section-title"><h2>待确认操作</h2><span>{pendingRecords.length} 项</span></div>
          {renderRecordList(pendingRecords, '暂无待确认操作')}
        </section>
      )}

      <section className="smart-history-section">
        <div className="smart-section-title"><h2>最近处理</h2><span>{recentRecords.length} 项</span></div>
        {renderRecordList(recentRecords, '暂无处理记录')}
      </section>
    </>
  )

  const renderRecord = (record: SmartRecord) => {
    const processing = POLLING_STATUSES.has(record.status)
    const finished = record.status === '已完成' || record.status === '部分完成'
    return (
      <div className="smart-record-detail">
        <section className="smart-record-summary">
          <div className="smart-record-status-row">
            <Space>
              <Tag color={STATUS_COLOR[record.status] || 'default'}>{record.status}</Tag>
              {record.preferred_action && <Tag fill="outline">{record.preferred_action}</Tag>}
            </Space>
            <span>{record.name}</span>
          </div>
          <h2>{record.summary || record.title}</h2>
          {record.record_type && (
            <div className="smart-record-type-row">
              <span>{record.record_type}</span>
              <strong>{Math.round(record.confidence || 0)}%</strong>
            </div>
          )}
          {record.record_type && <ProgressBar percent={record.confidence || 0} />}
          {record.file_name && <div className="smart-record-file"><FileOutline /> {record.file_name}</div>}
        </section>

        {processing && (
          <section className="smart-processing" role="status">
            <Tag color="primary" fill="outline">{capabilities.provider}</Tag>
            <Skeleton.Title animated />
            <Skeleton.Paragraph lineCount={3} animated />
            <span>{record.status === '待审批' ? '等待审批结果' : record.status === '执行中' ? '正在写入业务应用' : '正在理解业务意图并生成操作方案'}</span>
          </section>
        )}

        {record.error_message && <NoticeBar color="alert" content={record.error_message} />}

        {record.status === '待确认' && (
          <>
            <div className="smart-section-title">
              <h2>待确认操作</h2>
              <span>{draftActions.length} 项</span>
            </div>
            <div className="smart-action-list">
              {draftActions.map((action, index) => (
                <ActionEditor
                  key={action.name || action.action_index}
                  action={action}
                  onChange={next => setDraftActions(current => current.map((item, itemIndex) => itemIndex === index ? next : item))}
                />
              ))}
            </div>
            {unresolvedFields.length > 0 && (
              <NoticeBar color="alert" content={`确认前请补充：${unresolvedFields.join('；')}`} />
            )}
            <div className="smart-confirm-actions">
              <Button fill="outline" loading={submitting} disabled={submitting} onClick={cancelRecord}>取消</Button>
              <Button color="primary" loading={submitting} disabled={submitting || unresolvedFields.length > 0} onClick={confirmRecord}>
                <CheckOutline /> 确认执行
              </Button>
            </div>
          </>
        )}

        {record.status === '待审批' && record.approval && (
          <Button block fill="outline" onClick={() => { window.open(getManagerUrl(`/app/i-one-approval-request/${record.approval}`), '_blank', 'noopener,noreferrer') }}>
            查看审批 <RightOutline />
          </Button>
        )}

        {finished && (
          <>
            <div className="smart-section-title"><h2>执行结果</h2></div>
            <List className="smart-result-list">
              {record.actions.map(action => (
                <List.Item
                  key={action.name}
                  prefix={action.status === '已执行' ? <CheckOutline /> : <ClockCircleOutline />}
                  description={actionDescription(action)}
                  extra={action.target_route ? <RightOutline /> : <Tag fill="outline">{action.status}</Tag>}
                  clickable={Boolean(action.target_route)}
                  onClick={() => action.target_route && window.open(getManagerUrl(action.target_route), '_blank', 'noopener,noreferrer')}
                >
                  {action.title}
                </List.Item>
              ))}
            </List>
          </>
        )}

        {record.status === '失败' && (
          <Button block fill="outline" loading={submitting} disabled={submitting} onClick={retryRecord}>
            <RedoOutline /> 重新分析
          </Button>
        )}

        {record.status === '已取消' && <Button block fill="outline" onClick={resetCapture}>新建操作</Button>}
      </div>
    )
  }

  const renderHistory = () => (
    <section className="smart-history-section smart-history-all">
      <div className="smart-section-title"><h2>全部记录</h2><span>{history.length} 项</span></div>
      {renderRecordList(history, '暂无智能记录')}
    </section>
  )

  return (
    <div className="page smart-record-page" data-layout={layoutMode}>
      <header className="smart-page-header">
        <div>
          <h1>智能工作台</h1>
          <div className="smart-provider"><span>{capabilities.provider}</span><i />manager.myyr.top</div>
        </div>
        <Space>
          {(activeRecord || view === 'history') && <Button size="small" fill="outline" onClick={resetCapture}>新操作</Button>}
          <Button
            size="small"
            fill={view === 'history' ? 'solid' : 'outline'}
            color={view === 'history' ? 'primary' : 'default'}
            onClick={() => { setView('history'); setActiveRecord(null); refreshHistory() }}
          >
            <ClockCircleOutline /> 记录
          </Button>
        </Space>
      </header>
      {view === 'history' ? renderHistory() : activeRecord ? renderRecord(activeRecord) : renderCapture()}
    </div>
  )
}

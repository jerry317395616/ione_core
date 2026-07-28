import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Empty,
  Popup,
  ProgressBar,
  Selector,
  Skeleton,
  Switch,
  Tag,
  TextArea,
  Toast,
} from 'antd-mobile'
import {
  AddOutline,
  CheckCircleOutline,
  ClockCircleOutline,
  ExclamationCircleOutline,
  FileOutline,
  LoopOutline,
  MoreOutline,
  RightOutline,
  SendOutline,
  SetOutline,
  UserSetOutline,
} from 'antd-mobile-icons'
import {
  getAiEmployee,
  getAiTask,
  listAiEmployees,
  queueAiTask,
  type AiEmployeeDetail,
  type AiEmployeeStatus,
  type AiEmployeeSummary,
  type AiTaskDocument,
  type AiTaskStatus,
  type AiTaskSummary,
  type QueueAiTaskResult,
} from '../lib/aiTeamApi'
import { getFrappeUrl } from '../lib/frappeCore'
import type { LayoutMode } from '../LayoutThemes'
import type { AppState } from '../types'
import './AIEmployeesPage.css'

const PRIORITIES = [
  { label: '普通', value: '普通' },
  { label: '高', value: '高' },
  { label: '紧急', value: '紧急' },
] as const

const QUICK_COMMANDS = [
  '汇总今天未完成的工作，标记风险并给出处理顺序',
  '分析本月经营数据，列出三个最值得关注的问题',
  '整理待跟进客户，生成今天的行动清单',
  '检查逾期应收，拟定分级催款计划',
]

const TERMINAL_TASK_STATUSES = new Set<AiTaskStatus>(['已完成', '执行失败', '已取消'])
const AVAILABLE_EMPLOYEE_STATUSES = new Set<AiEmployeeStatus>(['试用', '在职'])

const EMPLOYEE_STATUS_META: Record<AiEmployeeStatus, { label: string; tone: string }> = {
  草稿: { label: '未发布', tone: 'muted' },
  试用: { label: '试运行', tone: 'warning' },
  在职: { label: '可工作', tone: 'success' },
  暂停: { label: '已暂停', tone: 'warning' },
  离职: { label: '已停用', tone: 'muted' },
}

const TASK_STATUS_META: Record<AiTaskStatus, { icon: React.ReactNode; tone: string }> = {
  草稿: { icon: <FileOutline />, tone: 'muted' },
  待审批: { icon: <ClockCircleOutline />, tone: 'warning' },
  已排队: { icon: <ClockCircleOutline />, tone: 'primary' },
  执行中: { icon: <LoopOutline />, tone: 'primary' },
  等待确认: { icon: <ExclamationCircleOutline />, tone: 'warning' },
  已完成: { icon: <CheckCircleOutline />, tone: 'success' },
  执行失败: { icon: <ExclamationCircleOutline />, tone: 'danger' },
  已取消: { icon: <ExclamationCircleOutline />, tone: 'muted' },
}

function formatRelativeTime(value?: string | null) {
  if (!value) return '尚未运行'
  const time = new Date(value.replace(' ', 'T')).getTime()
  if (Number.isNaN(time)) return value
  const minutes = Math.max(0, Math.floor((Date.now() - time) / 60000))
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.floor(hours / 24)} 天前`
}

function plainText(value?: string | null) {
  return (value || '').replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim()
}

function employeeInitial(employee: AiEmployeeSummary) {
  return employee.agent_name.trim().slice(0, 1).toUpperCase() || 'AI'
}

function avatarUrl(value?: string | null) {
  if (!value) return null
  if (/^https?:\/\//.test(value)) return value
  return getFrappeUrl(value)
}

function taskTitle(prompt: string) {
  const firstLine = prompt.split(/\r?\n/).find(Boolean)?.trim() || 'AI 工作单'
  return firstLine.length > 36 ? `${firstLine.slice(0, 36)}…` : firstLine
}

function EmployeeAvatar({ employee, large = false }: { employee: AiEmployeeSummary; large?: boolean }) {
  const image = avatarUrl(employee.avatar)
  return (
    <div className={`ai-team-avatar${large ? ' ai-team-avatar-large' : ''}`}>
      {image ? <img src={image} alt="" /> : employeeInitial(employee)}
    </div>
  )
}

function TaskStatus({ status }: { status: AiTaskStatus }) {
  const meta = TASK_STATUS_META[status] || TASK_STATUS_META.草稿
  return (
    <span className={`ai-team-status ai-team-status-${meta.tone}`}>
      {meta.icon}
      {status}
    </span>
  )
}

function TaskRow({
  task,
  onClick,
}: {
  task: AiTaskSummary
  onClick: (task: AiTaskSummary) => void
}) {
  return (
    <button className="ai-team-task-row" type="button" onClick={() => onClick(task)}>
      <div className="ai-team-task-main">
        <strong>{task.title}</strong>
        <div className="ai-team-task-meta">
          <TaskStatus status={task.status} />
          <span>{task.priority}优先级</span>
          <span>{formatRelativeTime(task.modified)}</span>
        </div>
        {!TERMINAL_TASK_STATUSES.has(task.status) && (
          <ProgressBar
            percent={Number(task.progress || 0)}
            style={{ '--fill-color': '#1677ff', '--track-color': '#e7e8eb' }}
          />
        )}
      </div>
      <RightOutline />
    </button>
  )
}

export default function AIEmployeesPage({
  layoutMode,
}: {
  layoutMode?: LayoutMode
  state?: AppState
  setState?: (state: Partial<AppState>) => void
}) {
  void layoutMode
  const [employees, setEmployees] = useState<AiEmployeeSummary[]>([])
  const [selectedAgent, setSelectedAgent] = useState('')
  const [detailAgentName, setDetailAgentName] = useState('')
  const [employeeDetail, setEmployeeDetail] = useState<AiEmployeeDetail | null>(null)
  const [selectedTask, setSelectedTask] = useState<AiTaskDocument | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [taskLoading, setTaskLoading] = useState(false)
  const [error, setError] = useState('')
  const [command, setCommand] = useState('')
  const [priority, setPriority] = useState<'普通' | '高' | '紧急'>('普通')
  const [approvalRequired, setApprovalRequired] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [employeePopupVisible, setEmployeePopupVisible] = useState(false)
  const [taskPopupVisible, setTaskPopupVisible] = useState(false)
  const [lastCreatedTask, setLastCreatedTask] = useState<QueueAiTaskResult | null>(null)

  const loadEmployees = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true)
    try {
      const data = await listAiEmployees()
      setEmployees(data)
      setError('')
      setSelectedAgent(current => {
        if (current && data.some(employee => employee.name === current)) return current
        return data.find(employee => AVAILABLE_EMPLOYEE_STATUSES.has(employee.status))?.name || data[0]?.name || ''
      })
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '无法读取 AI 团队')
    } finally {
      if (showLoading) setLoading(false)
    }
  }, [])

  const loadEmployeeDetail = useCallback(async (name: string, showLoading = false) => {
    if (!name) return
    if (showLoading) setDetailLoading(true)
    try {
      setEmployeeDetail(await getAiEmployee(name))
    } catch (loadError) {
      if (showLoading) {
        Toast.show({
          icon: 'fail',
          content: loadError instanceof Error ? loadError.message : '无法读取员工详情',
        })
      }
    } finally {
      if (showLoading) setDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadEmployees(true)
  }, [loadEmployees])

  const hasActiveWork = useMemo(
    () => employees.some(employee => employee.open_tasks > 0)
      || Boolean(lastCreatedTask && !TERMINAL_TASK_STATUSES.has(lastCreatedTask.status)),
    [employees, lastCreatedTask],
  )

  useEffect(() => {
    if (!hasActiveWork) return
    const timer = window.setInterval(() => {
      void loadEmployees()
      if (employeePopupVisible && detailAgentName) void loadEmployeeDetail(detailAgentName)
      if (lastCreatedTask) {
        void getAiTask(lastCreatedTask.name).then(task => {
          setSelectedTask(current => current?.name === task.name ? task : current)
          setLastCreatedTask({ name: task.name, status: task.status })
        }).catch(() => undefined)
      }
    }, 5000)
    return () => window.clearInterval(timer)
  }, [
    detailAgentName,
    employeePopupVisible,
    hasActiveWork,
    lastCreatedTask,
    loadEmployeeDetail,
    loadEmployees,
  ])

  const availableEmployees = employees.filter(employee => AVAILABLE_EMPLOYEE_STATUSES.has(employee.status))
  const selectedEmployee = employees.find(employee => employee.name === selectedAgent) || null
  const teamMetrics = useMemo(() => ({
    available: availableEmployees.length,
    open: employees.reduce((sum, employee) => sum + Number(employee.open_tasks || 0), 0),
    completed: employees.reduce((sum, employee) => sum + Number(employee.completed_tasks || 0), 0),
  }), [availableEmployees.length, employees])

  const openEmployee = (employee: AiEmployeeSummary) => {
    setDetailAgentName(employee.name)
    setEmployeeDetail(null)
    setEmployeePopupVisible(true)
    void loadEmployeeDetail(employee.name, true)
  }

  const openTask = async (task: AiTaskSummary) => {
    setEmployeePopupVisible(false)
    setTaskPopupVisible(true)
    setTaskLoading(true)
    setSelectedTask(null)
    try {
      setSelectedTask(await getAiTask(task.name))
    } catch (loadError) {
      Toast.show({
        icon: 'fail',
        content: loadError instanceof Error ? loadError.message : '无法读取工作单',
      })
      setTaskPopupVisible(false)
    } finally {
      setTaskLoading(false)
    }
  }

  const submitTask = async () => {
    const prompt = command.trim()
    if (!prompt || !selectedAgent || submitting) return
    setSubmitting(true)
    try {
      const result = await queueAiTask({
        title: taskTitle(prompt),
        prompt,
        assigned_agent: selectedAgent,
        priority,
        approval_required: approvalRequired,
      })
      setLastCreatedTask(result)
      setCommand('')
      Toast.show({
        icon: 'success',
        content: result.status === '待审批' ? '工作单已提交，等待审批' : '工作单已进入执行队列',
      })
      await loadEmployees()
      if (employeePopupVisible && detailAgentName) {
        await loadEmployeeDetail(detailAgentName)
      }
    } catch (submitError) {
      Toast.show({
        icon: 'fail',
        content: submitError instanceof Error ? submitError.message : '工作单提交失败',
      })
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="page ai-team-page">
        <div className="ai-team-heading">
          <Skeleton.Title animated />
          <Skeleton.Paragraph lineCount={2} animated />
        </div>
        <div className="ai-team-loading-grid">
          <Skeleton.Paragraph lineCount={3} animated />
          <Skeleton.Paragraph lineCount={3} animated />
        </div>
      </div>
    )
  }

  return (
    <div className="page ai-team-page">
      <section className="ai-team-heading">
        <div>
          <span className="ai-team-eyebrow">I-ONE AI</span>
          <h1>AI 团队</h1>
          <p>分配工作、查看进度，并在关键动作前完成确认。</p>
        </div>
        <Button
          className="ai-team-icon-button"
          fill="none"
          aria-label="刷新 AI 团队"
          onClick={() => void loadEmployees(true)}
        >
          <LoopOutline />
        </Button>
      </section>

      {error && (
        <section className="ai-team-alert ai-team-alert-danger">
          <ExclamationCircleOutline />
          <div>
            <strong>AI 团队暂时不可用</strong>
            <p>{error}</p>
          </div>
          <Button size="mini" fill="outline" onClick={() => void loadEmployees(true)}>重试</Button>
        </section>
      )}

      {!error && employees.length === 0 ? (
        <section className="ai-team-empty">
          <Empty description="还没有创建 AI 员工" />
          <Button
            color="primary"
            onClick={() => {
              window.open(getFrappeUrl('/app/i-one-agent/new'), '_blank', 'noopener,noreferrer')
            }}
          >
            <AddOutline />
            创建第一个 AI 员工
          </Button>
        </section>
      ) : (
        <>
          <section className="ai-team-overview">
            <div className="ai-team-overview-copy">
              <span className={`ai-team-live-dot${teamMetrics.open > 0 ? ' is-running' : ''}`} />
              <div>
                <strong>{teamMetrics.open > 0 ? '团队正在处理工作' : '团队已就绪'}</strong>
                <p>{teamMetrics.open > 0 ? `${teamMetrics.open} 个工作单正在流转` : '可以分派新的经营任务'}</p>
              </div>
            </div>
            <div className="ai-team-metrics">
              <div><strong>{teamMetrics.available}</strong><span>可用成员</span></div>
              <div><strong>{teamMetrics.open}</strong><span>处理中</span></div>
              <div><strong>{teamMetrics.completed}</strong><span>累计完成</span></div>
            </div>
          </section>

          <section className="ai-team-section ai-team-dispatch">
            <div className="ai-team-section-title">
              <div>
                <h2>创建工作单</h2>
                <p>任务将进入 Frappe，执行过程和结果完整留痕。</p>
              </div>
              <SendOutline />
            </div>

            <button
              className="ai-team-assignee"
              type="button"
              onClick={() => selectedEmployee && openEmployee(selectedEmployee)}
            >
              {selectedEmployee ? (
                <>
                  <EmployeeAvatar employee={selectedEmployee} />
                  <span>
                    <small>执行员工</small>
                    <strong>{selectedEmployee.agent_name}</strong>
                  </span>
                  <Tag fill="outline">{selectedEmployee.operating_mode || '辅助'}模式</Tag>
                </>
              ) : (
                <span>请选择可用的 AI 员工</span>
              )}
              <RightOutline />
            </button>

            <TextArea
              className="ai-team-command"
              value={command}
              onChange={setCommand}
              placeholder="描述目标、数据范围和期望交付物，例如：检查本月逾期应收，按风险分级并生成跟进清单。"
              rows={4}
              maxLength={4000}
              showCount
              disabled={submitting}
            />

            <div className="ai-team-quick-commands">
              {QUICK_COMMANDS.map(item => (
                <button key={item} type="button" onClick={() => setCommand(item)}>
                  {item}
                </button>
              ))}
            </div>

            <div className="ai-team-dispatch-options">
              <div>
                <span>优先级</span>
                <Selector
                  options={[...PRIORITIES]}
                  value={[priority]}
                  onChange={value => value[0] && setPriority(value[0])}
                />
              </div>
              <label>
                <span>
                  <strong>执行前人工审批</strong>
                  <small>涉及业务写入时建议开启</small>
                </span>
                <Switch checked={approvalRequired} onChange={setApprovalRequired} />
              </label>
            </div>

            <Button
              block
              color="primary"
              loading={submitting}
              disabled={!command.trim() || !selectedAgent}
              onClick={() => void submitTask()}
            >
              <SendOutline />
              {approvalRequired ? '提交并申请审批' : '立即分派'}
            </Button>

            {lastCreatedTask && (
              <button
                type="button"
                className="ai-team-last-created"
                onClick={() => {
                  setTaskPopupVisible(true)
                  setTaskLoading(true)
                  void getAiTask(lastCreatedTask.name)
                    .then(setSelectedTask)
                    .finally(() => setTaskLoading(false))
                }}
              >
                <TaskStatus status={lastCreatedTask.status} />
                <span>工作单 {lastCreatedTask.name}</span>
                <RightOutline />
              </button>
            )}
          </section>

          <section className="ai-team-section">
            <div className="ai-team-section-title">
              <div>
                <h2>团队成员</h2>
                <p>状态由 I-ONE Agent 实时提供。</p>
              </div>
              <span>{employees.length} 人</span>
            </div>

            <div className="ai-team-member-list">
              {employees.map(employee => {
                const statusMeta = EMPLOYEE_STATUS_META[employee.status] || EMPLOYEE_STATUS_META.草稿
                return (
                  <button
                    key={employee.name}
                    className={`ai-team-member${selectedAgent === employee.name ? ' is-selected' : ''}`}
                    type="button"
                    onClick={() => openEmployee(employee)}
                  >
                    <EmployeeAvatar employee={employee} />
                    <span className="ai-team-member-copy">
                      <span>
                        <strong>{employee.agent_name}</strong>
                        <em className={`ai-team-member-state ai-team-member-state-${statusMeta.tone}`}>
                          {statusMeta.label}
                        </em>
                      </span>
                      <small>{employee.agent_type} · {employee.operating_mode || '辅助'}模式</small>
                      <small>最近运行：{formatRelativeTime(employee.last_active)}</small>
                    </span>
                    <span className="ai-team-member-work">
                      <strong>{employee.open_tasks}</strong>
                      <small>处理中</small>
                    </span>
                    <RightOutline />
                  </button>
                )
              })}
            </div>
          </section>
        </>
      )}

      <Popup
        visible={employeePopupVisible}
        onMaskClick={() => setEmployeePopupVisible(false)}
        onClose={() => setEmployeePopupVisible(false)}
        bodyClassName="ai-team-popup"
        bodyStyle={{ height: '78vh' }}
      >
        <div className="ai-team-popup-handle" />
        {detailLoading || !employeeDetail ? (
          <div className="ai-team-popup-loading">
            <Skeleton.Title animated />
            <Skeleton.Paragraph lineCount={5} animated />
          </div>
        ) : (
          <div className="ai-team-popup-content">
            <header className="ai-team-profile">
              <EmployeeAvatar employee={employeeDetail.employee} large />
              <div>
                <h2>{employeeDetail.employee.agent_name}</h2>
                <p>{employeeDetail.employee.agent_type} · {employeeDetail.employee.operating_mode || '辅助'}模式</p>
              </div>
              <Button
                className="ai-team-icon-button"
                fill="none"
                onClick={() => {
                  window.open(
                    getFrappeUrl(employeeDetail.employee.route || `/app/i-one-agent/${employeeDetail.employee.name}`),
                    '_blank',
                    'noopener,noreferrer',
                  )
                }}
              >
                <SetOutline />
              </Button>
            </header>

            <div className="ai-team-profile-metrics">
              <div><strong>{employeeDetail.metrics.open}</strong><span>进行中</span></div>
              <div><strong>{employeeDetail.metrics.completed}</strong><span>已完成</span></div>
              <div><strong>{employeeDetail.metrics.failed}</strong><span>失败</span></div>
            </div>

            {AVAILABLE_EMPLOYEE_STATUSES.has(employeeDetail.employee.status) ? (
              <Button
                block
                className="ai-team-select-employee"
                color={selectedAgent === employeeDetail.employee.name ? 'default' : 'primary'}
                fill={selectedAgent === employeeDetail.employee.name ? 'outline' : 'solid'}
                disabled={selectedAgent === employeeDetail.employee.name}
                onClick={() => {
                  setSelectedAgent(employeeDetail.employee.name)
                  setEmployeePopupVisible(false)
                  Toast.show({ icon: 'success', content: `已选择${employeeDetail.employee.agent_name}` })
                }}
              >
                {selectedAgent === employeeDetail.employee.name ? '当前执行员工' : '设为执行员工'}
              </Button>
            ) : (
              <div className="ai-team-unavailable-note">
                <ExclamationCircleOutline />
                该员工当前不可接收新工作单
              </div>
            )}

            {(employeeDetail.employee.description || employeeDetail.employee.responsibilities) && (
              <section className="ai-team-profile-description">
                <h3>岗位职责</h3>
                <p>{plainText(employeeDetail.employee.description || employeeDetail.employee.responsibilities)}</p>
              </section>
            )}

            <section className="ai-team-profile-tasks">
              <div className="ai-team-section-title">
                <div>
                  <h2>最近工作单</h2>
                  <p>点击查看指令、结果和错误信息。</p>
                </div>
              </div>
              {employeeDetail.tasks.length > 0 ? (
                employeeDetail.tasks.map(task => (
                  <TaskRow key={task.name} task={task} onClick={openTask} />
                ))
              ) : (
                <Empty description="这个员工还没有工作单" />
              )}
            </section>
          </div>
        )}
      </Popup>

      <Popup
        visible={taskPopupVisible}
        onMaskClick={() => setTaskPopupVisible(false)}
        onClose={() => setTaskPopupVisible(false)}
        bodyClassName="ai-team-popup ai-team-task-popup"
        bodyStyle={{ minHeight: '52vh', maxHeight: '82vh' }}
      >
        <div className="ai-team-popup-handle" />
        {taskLoading || !selectedTask ? (
          <div className="ai-team-popup-loading">
            <Skeleton.Title animated />
            <Skeleton.Paragraph lineCount={4} animated />
          </div>
        ) : (
          <div className="ai-team-popup-content">
            <header className="ai-team-task-header">
              <div>
                <TaskStatus status={selectedTask.status} />
                <h2>{selectedTask.title}</h2>
                <p>{selectedTask.name} · {selectedTask.priority}优先级</p>
              </div>
              <Button
                className="ai-team-icon-button"
                fill="none"
                onClick={() => {
                  window.open(
                    getFrappeUrl(`/app/i-one-ai-task/${selectedTask.name}`),
                    '_blank',
                    'noopener,noreferrer',
                  )
                }}
              >
                <MoreOutline />
              </Button>
            </header>

            {!TERMINAL_TASK_STATUSES.has(selectedTask.status) && (
              <div className="ai-team-task-progress">
                <span>执行进度</span>
                <strong>{Number(selectedTask.progress || 0)}%</strong>
                <ProgressBar
                  percent={Number(selectedTask.progress || 0)}
                  style={{ '--fill-color': '#1677ff', '--track-color': '#e7e8eb' }}
                />
              </div>
            )}

            <section className="ai-team-task-block">
              <h3>工作指令</h3>
              <p>{selectedTask.prompt || '未记录工作指令'}</p>
            </section>

            {plainText(selectedTask.result_summary) && (
              <section className="ai-team-task-block ai-team-task-result">
                <h3><CheckCircleOutline /> 交付结果</h3>
                <p>{plainText(selectedTask.result_summary)}</p>
              </section>
            )}

            {selectedTask.error_message && (
              <section className="ai-team-task-block ai-team-task-error">
                <h3><ExclamationCircleOutline /> 执行失败</h3>
                <p>{selectedTask.error_message}</p>
              </section>
            )}

            <div className="ai-team-task-actions">
              <Button
                fill="outline"
                onClick={() => {
                  window.open(
                    getFrappeUrl(`/app/i-one-ai-task/${selectedTask.name}`),
                    '_blank',
                    'noopener,noreferrer',
                  )
                }}
              >
                <FileOutline />
                在管理端查看
              </Button>
              {selectedTask.status === '等待确认' && (
                <Button
                  color="primary"
                  onClick={() => {
                    window.open(
                      getFrappeUrl(`/app/i-one-ai-task/${selectedTask.name}`),
                      '_blank',
                      'noopener,noreferrer',
                    )
                  }}
                >
                  <UserSetOutline />
                  去确认
                </Button>
              )}
            </div>
          </div>
        )}
      </Popup>
    </div>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, DotLoading, List, NoticeBar, Popup, Space, TextArea, Toast } from 'antd-mobile'
import {
  CheckCircleOutline,
  CloseOutline,
  DeleteOutline,
  FileOutline,
  SendOutline,
  UnorderedListOutline,
  UserOutline,
} from 'antd-mobile-icons'
import { frappeCall } from '../lib/frappeRequest'
import { getLayoutTheme, type LayoutMode } from '../LayoutThemes'
import {
  type ExpertConversation,
  type ExpertMessage,
  useExpertStore,
} from '../stores/expertStore'

const SUGGESTED_QUESTIONS = [
  '审查一份合作合同需要重点关注什么？',
  '小规模企业如何规范日常财税管理？',
  '新员工入职需要准备哪些文件？',
]

function formatDateTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function pendingLabel(message: ExpertMessage, queueDepth: number) {
  if (message.status === '排队中') return queueDepth > 0 ? `队列中还有 ${queueDepth} 项` : '等待模型接收问题'
  return 'I-ONE 专家正在分析'
}

export default function ExpertPage({ layoutMode }: { layoutMode: LayoutMode }) {
  const theme = getLayoutTheme(layoutMode)
  const {
    conversations,
    currentConversationId,
    currentMessages,
    serviceStatus,
    loadingHistory,
    sending,
    error,
    fetchConversations,
    fetchServiceStatus,
    askExpert,
    resumePendingMessages,
    cancelMessage,
    loadConversation,
    clearMessages,
    setError,
  } = useExpertStore()
  const [input, setInput] = useState('')
  const [showHistory, setShowHistory] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    void fetchConversations()
    void fetchServiceStatus()
    resumePendingMessages()
  }, [fetchConversations, fetchServiceStatus, resumePendingMessages])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [currentMessages])

  const pendingCount = useMemo(
    () => currentMessages.filter(message => ['排队中', '处理中'].includes(message.status)).length,
    [currentMessages],
  )
  const canSubmit = Boolean(input.trim()) && !sending

  const sendQuestion = async () => {
    const question = input.trim()
    if (!question || !canSubmit) return
    setInput('')
    await askExpert(question)
  }

  const storeEvidence = async (message: ExpertMessage) => {
    try {
      await frappeCall('ione_core.expert.save_expert_evidence', {
        content: message.content,
        conversation_id: currentConversationId,
      }, 'POST')
      Toast.show({ icon: 'success', content: '已存入经营档案' })
    } catch (reason) {
      Toast.show({ icon: 'fail', content: reason instanceof Error ? reason.message : '存入失败' })
    }
  }

  const addGrowthTask = async (message: ExpertMessage) => {
    try {
      await frappeCall('ione_core.expert.add_expert_growth_plan', {
        content: message.content,
        conversation_id: currentConversationId,
      }, 'POST')
      Toast.show({ icon: 'success', content: '已加入增长计划' })
    } catch (reason) {
      Toast.show({ icon: 'fail', content: reason instanceof Error ? reason.message : '创建失败' })
    }
  }

  const openConversation = async (conversation: ExpertConversation) => {
    await loadConversation(conversation.id)
    setShowHistory(false)
  }

  return (
    <div className="page expert-workbench" style={{ background: theme.bgColor }}>
      <header className="expert-toolbar">
        <div className="expert-title-block">
          <h1>专家咨询</h1>
          <div className="expert-provider-line">
            <span className={`expert-status-dot ${serviceStatus ? 'is-online' : 'is-offline'}`} />
            <span>{serviceStatus?.provider || 'I-ONE 模型服务'}</span>
            {serviceStatus?.busy && <span>处理中</span>}
          </div>
        </div>
        <Space className="expert-toolbar-actions">
          <Button fill="none" size="mini" aria-label="对话历史" onClick={() => setShowHistory(true)}><UnorderedListOutline /></Button>
          <Button fill="none" size="mini" aria-label="新对话" onClick={clearMessages}><DeleteOutline /></Button>
        </Space>
      </header>

      {error && <NoticeBar className="expert-notice" color="alert" closeable wrap content={error} onClose={() => setError(null)} />}

      <main className="expert-conversation" aria-live="polite">
        {!currentMessages.length ? (
          <section className="expert-welcome">
            <div className="expert-mark">I</div>
            <h2>企业专家</h2>
            <p>合同、财税、用工与企业经营决策</p>
            <div className="expert-suggestions">
              {SUGGESTED_QUESTIONS.map(question => (
                <button key={question} type="button" onClick={() => setInput(question)}>{question}</button>
              ))}
            </div>
          </section>
        ) : currentMessages.map(message => {
          const isUser = message.role === 'user'
          const pending = ['排队中', '处理中'].includes(message.status)
          return (
            <article key={message.id} className={`expert-message ${isUser ? 'is-user' : 'is-assistant'}`}>
              {!isUser && <div className="expert-avatar">I</div>}
              <div className="expert-message-main">
                {!isUser && <div className="expert-message-meta"><strong>I-ONE 专家</strong><span>{serviceStatus?.provider || '模型服务'}</span></div>}
                <div className={`expert-bubble ${pending ? 'is-pending' : ''}`}>
                  {pending ? (
                    <div className="expert-pending-state"><DotLoading color="primary" /><span>{pendingLabel(message, serviceStatus?.queueDepth || 0)}</span></div>
                  ) : message.status === '失败' ? (
                    <div className="expert-failed-state"><strong>本次咨询未完成</strong><span>{message.error || '模型处理失败'}</span></div>
                  ) : <div className="expert-answer">{message.content}</div>}
                </div>
                <div className="expert-message-footer">
                  <time>{formatDateTime(message.completedAt || message.timestamp)}</time>
                  {!isUser && message.status === '已完成' && (
                    <Space>
                      <Button fill="none" size="mini" onClick={() => void storeEvidence(message)}><FileOutline /> 存档</Button>
                      <Button fill="none" size="mini" onClick={() => void addGrowthTask(message)}><CheckCircleOutline /> 转计划</Button>
                    </Space>
                  )}
                  {!isUser && message.status === '排队中' && <Button fill="none" size="mini" onClick={() => void cancelMessage(message.id)}>取消</Button>}
                </div>
              </div>
            </article>
          )
        })}
        <div ref={messagesEndRef} />
      </main>

      <footer className="expert-composer">
        {pendingCount > 0 && <div className="expert-active-jobs">{pendingCount} 个问题正在处理</div>}
        <div className="expert-composer-row">
          <TextArea
            value={input}
            onChange={setInput}
            placeholder="输入需要专家分析的问题"
            autoSize={{ minRows: 1, maxRows: 5 }}
            maxLength={12000}
            onEnterPress={event => {
              if (!event.shiftKey) {
                event.preventDefault()
                void sendQuestion()
              }
            }}
          />
          <Button className="expert-send-button" color="primary" disabled={!canSubmit} loading={sending} aria-label="发送问题" onClick={() => void sendQuestion()}>
            <SendOutline />
          </Button>
        </div>
      </footer>

      <Popup visible={showHistory} onMaskClick={() => setShowHistory(false)} position="right" bodyClassName="expert-history-drawer">
        <div className="expert-drawer-header">
          <div><h2>对话历史</h2><span>{conversations.length} 个对话</span></div>
          <Button fill="none" aria-label="关闭" onClick={() => setShowHistory(false)}><CloseOutline /></Button>
        </div>
        {loadingHistory ? <div className="expert-drawer-empty"><DotLoading color="primary" /></div> : !conversations.length ? (
          <div className="expert-drawer-empty">暂无历史对话</div>
        ) : (
          <List className="expert-history-list">
            {conversations.map(conversation => (
              <List.Item
                key={conversation.id}
                prefix={<UserOutline />}
                description={`${conversation.messageCount} 条消息 · ${formatDateTime(conversation.updatedAt)}`}
                extra={conversation.status}
                clickable
                onClick={() => void openConversation(conversation)}
              >
                {conversation.topic}
              </List.Item>
            ))}
          </List>
        )}
      </Popup>
    </div>
  )
}

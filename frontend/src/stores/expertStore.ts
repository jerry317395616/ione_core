import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { frappeCall } from '../lib/frappeRequest'

export type ExpertMessageStatus = '已发送' | '排队中' | '处理中' | '已完成' | '失败' | '已取消'

export interface ExpertMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  status: ExpertMessageStatus
  timestamp: string
  completedAt?: string
  source?: 'user' | 'deepseek-web'
  oracleJobId?: string
  error?: string
}

export interface ExpertConversation {
  id: string
  topic: string
  summary: string
  scenario: string
  status: string
  provider: string
  messageCount: number
  createdAt: string
  updatedAt: string
  messages?: ExpertMessage[]
}

export interface ExpertServiceStatus {
  provider: string
  canManage: boolean
  loggedIn: boolean
  requiresLogin: boolean
  requiresMobileVerification: boolean
  blocked: boolean
  busy: boolean
  queueDepth: number
  error?: string
}

interface AskResult {
  conversationId: string
  conversation: ExpertConversation
  userMessage: ExpertMessage
  assistantMessage: ExpertMessage
  jobId: string
  status: string
}

export interface ExpertState {
  conversations: ExpertConversation[]
  currentConversationId: string | null
  currentMessages: ExpertMessage[]
  serviceStatus: ExpertServiceStatus | null
  loadingHistory: boolean
  sending: boolean
  error: string | null

  fetchConversations: () => Promise<void>
  fetchServiceStatus: () => Promise<void>
  askExpert: (question: string) => Promise<void>
  pollMessage: (messageId: string) => Promise<void>
  resumePendingMessages: () => void
  cancelMessage: (messageId: string) => Promise<void>
  loadConversation: (conversationId: string) => Promise<void>
  clearMessages: () => void
  setError: (error: string | null) => void
}

const activePolls = new Set<string>()

function replaceMessage(messages: ExpertMessage[], message: ExpertMessage): ExpertMessage[] {
  const index = messages.findIndex((item) => item.id === message.id)
  if (index < 0) return [...messages, message]
  return messages.map((item) => (item.id === message.id ? message : item))
}

function isPending(message: ExpertMessage): boolean {
  return message.role === 'assistant' && ['排队中', '处理中'].includes(message.status)
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export const useExpertStore = create<ExpertState>()(
  persist(
    (set, get) => ({
      conversations: [],
      currentConversationId: null,
      currentMessages: [],
      serviceStatus: null,
      loadingHistory: false,
      sending: false,
      error: null,

      fetchConversations: async () => {
        set({ loadingHistory: true })
        try {
          const conversations = await frappeCall<ExpertConversation[]>(
            'ione_core.expert.list_expert_conversations',
          )
          set({ conversations: conversations || [], loadingHistory: false })
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : '获取对话历史失败',
            loadingHistory: false,
          })
        }
      },

      fetchServiceStatus: async () => {
        try {
          const serviceStatus = await frappeCall<ExpertServiceStatus>(
            'ione_core.expert.get_expert_service_access',
          )
          set({ serviceStatus })
        } catch (error) {
          set({
            serviceStatus: null,
            error: error instanceof Error ? error.message : '专家服务暂时不可用',
          })
        }
      },

      askExpert: async (question: string) => {
        const cleanQuestion = question.trim()
        if (!cleanQuestion || get().sending) return
        set({ sending: true, error: null })
        try {
          const data = await frappeCall<AskResult>(
            'ione_core.expert.submit_expert_request',
            {
              question: cleanQuestion,
              conversation_id: get().currentConversationId || undefined,
            },
            'POST',
          )
          if (!data) throw new Error('专家服务未返回任务信息')
          set((state) => ({
            currentConversationId: data.conversationId,
            currentMessages: replaceMessage(
              replaceMessage(state.currentMessages, data.userMessage),
              data.assistantMessage,
            ),
            conversations: [
              data.conversation,
              ...state.conversations.filter((item) => item.id !== data.conversationId),
            ],
            sending: false,
          }))
          void get().pollMessage(data.jobId)
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : '提交专家问题失败',
            sending: false,
          })
        }
      },

      pollMessage: async (messageId: string) => {
        if (!messageId || activePolls.has(messageId)) return
        activePolls.add(messageId)
        let transientFailures = 0
        try {
          while (activePolls.has(messageId)) {
            try {
              const message = await frappeCall<ExpertMessage>(
                'ione_core.expert.get_expert_job',
                { message_id: messageId },
              )
              if (!message) throw new Error('专家任务没有返回状态')
              set((state) => ({
                currentMessages: replaceMessage(state.currentMessages, message),
              }))
              transientFailures = 0
              if (!isPending(message)) {
                void get().fetchConversations()
                void get().fetchServiceStatus()
                break
              }
              await wait(2500)
            } catch (error) {
              transientFailures += 1
              if (transientFailures >= 5) {
                set({ error: error instanceof Error ? error.message : '查询专家任务失败' })
                break
              }
              await wait(Math.min(10000, transientFailures * 2000))
            }
          }
        } finally {
          activePolls.delete(messageId)
        }
      },

      resumePendingMessages: () => {
        for (const message of get().currentMessages.filter(isPending)) {
          void get().pollMessage(message.id)
        }
      },

      cancelMessage: async (messageId: string) => {
        try {
          const message = await frappeCall<ExpertMessage>(
            'ione_core.expert.cancel_expert_request',
            { message_id: messageId },
            'POST',
          )
          if (message) {
            activePolls.delete(messageId)
            set((state) => ({
              currentMessages: replaceMessage(state.currentMessages, message),
            }))
          }
        } catch (error) {
          set({ error: error instanceof Error ? error.message : '取消专家任务失败' })
        }
      },

      loadConversation: async (conversationId: string) => {
        set({ loadingHistory: true, error: null })
        try {
          const conversation = await frappeCall<ExpertConversation>(
            'ione_core.expert.get_expert_conversation',
            { conversation_id: conversationId },
          )
          if (!conversation) throw new Error('专家对话不存在')
          set({
            currentMessages: conversation.messages || [],
            currentConversationId: conversationId,
            loadingHistory: false,
          })
          get().resumePendingMessages()
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : '加载对话失败',
            loadingHistory: false,
          })
        }
      },

      clearMessages: () => {
        set({ currentMessages: [], currentConversationId: null, error: null })
      },

      setError: (error: string | null) => set({ error }),
    }),
    {
      name: 'expert-storage-v2',
      partialize: (state) => ({
        currentMessages: state.currentMessages,
        currentConversationId: state.currentConversationId,
      }),
    },
  ),
)

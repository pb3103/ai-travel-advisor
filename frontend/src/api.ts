import type { Conversation, ConversationDetail, SystemPrompt, TripPlan, TripPlanInput } from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`Request to ${path} failed: ${res.status}`)
  }
  if (res.status === 204) {
    return undefined as T
  }
  return res.json()
}

export function listConversations(): Promise<Conversation[]> {
  return request<Conversation[]>('/api/conversations')
}

export function createConversation(title?: string): Promise<Conversation> {
  return request<Conversation>('/api/conversations', {
    method: 'POST',
    body: JSON.stringify({ title: title ?? null }),
  })
}

export function getConversation(id: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/api/conversations/${id}`)
}

export function deleteConversation(id: string): Promise<void> {
  return request<void>(`/api/conversations/${id}`, { method: 'DELETE' })
}

export function setConversationPinned(id: string, pinned: boolean): Promise<Conversation> {
  return request<Conversation>(`/api/conversations/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ pinned }),
  })
}

export async function getTripPlan(id: string): Promise<TripPlan | null> {
  const res = await fetch(`${API_URL}/api/conversations/${id}/trip-plan`)
  if (res.status === 404) {
    return null
  }
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`)
  }
  return res.json()
}

export function saveTripPlan(id: string, plan: TripPlanInput): Promise<TripPlan> {
  return request<TripPlan>(`/api/conversations/${id}/trip-plan`, {
    method: 'PATCH',
    body: JSON.stringify(plan),
  })
}

export function getSystemPrompt(): Promise<SystemPrompt> {
  return request<SystemPrompt>('/api/system-prompt')
}

export function saveSystemPrompt(content: string): Promise<SystemPrompt> {
  return request<SystemPrompt>('/api/system-prompt', {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

export async function sendMessage(
  conversationId: string,
  content: string,
  onDelta: (delta: string) => void,
  onTool?: (toolName: string) => void,
  onTitle?: (title: string) => void,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!res.ok || !res.body) {
    throw new Error(`Request failed: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''

    for (const event of events) {
      const dataLine = event.split('\n').find((line) => line.startsWith('data: '))
      if (!dataLine) continue
      const payload = JSON.parse(dataLine.slice('data: '.length))
      if (payload.error) {
        throw new Error(payload.error)
      }
      if (payload.delta) {
        onDelta(payload.delta)
      }
      if (payload.tool) {
        onTool?.(payload.tool)
      }
      if (payload.title) {
        onTitle?.(payload.title)
      }
    }
  }
}

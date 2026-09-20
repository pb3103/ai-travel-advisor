export interface Conversation {
  id: string
  title: string
  pinned: boolean
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

export interface Activity {
  time: string
  title: string
  description: string
}

export interface Day {
  day: number
  date: string
  location: string
  title: string
  activities: Activity[]
}

export interface TripPlan {
  destination: string | null
  start_date: string | null
  end_date: string | null
  days: Day[]
  version: number
  updated_at: string
}

export interface TripPlanInput {
  destination: string | null
  start_date: string | null
  end_date: string | null
  days: Day[]
}

export interface SystemPrompt {
  content: string
  updated_at: string
}

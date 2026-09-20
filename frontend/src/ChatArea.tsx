import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getConversation, sendMessage } from './api'
import { IconChat, IconCompass, IconPlus, IconSend } from './icons'
import { TravelIllustration } from './illustrations'

interface ChatAreaProps {
  conversationId: string | null
  onCreate: () => void
  onCreateWithPrompt: (prompt: string) => void
  onMessageSent: () => void
  onTitleChange: (conversationId: string, title: string) => void
  initialDraft?: string | null
  onInitialDraftConsumed?: () => void
}

const EXAMPLE_PROMPTS = [
  'Plan a 4-day trip to Lisbon',
  "What's the weather like in Tokyo?",
  'Best time to visit Iceland',
  'Is Vietnam expensive to visit?',
]

interface DisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  status?: string
}

const TOOL_LABELS: Record<string, string> = {
  get_weather: 'Checking the weather…',
  get_exchange_rate: 'Checking exchange rates…',
  web_search: 'Searching the web…',
}

// Open markdown links in a new tab — otherwise clicking a source link navigates the
// single-page app away entirely, losing all in-memory state.
const MARKDOWN_COMPONENTS = {
  a: (props: JSX.IntrinsicElements['a']) => <a {...props} target="_blank" rel="noopener noreferrer" />,
}

function ChatArea({
  conversationId,
  onCreate,
  onCreateWithPrompt,
  onMessageSent,
  onTitleChange,
  initialDraft,
  onInitialDraftConsumed,
}: ChatAreaProps) {
  const [title, setTitle] = useState('Conversation')
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [loading, setLoading] = useState(false)
  // Which conversation ids currently have a send in flight — not a single flag, since this
  // component instance is reused across conversation switches. A plain boolean would leave
  // the composer disabled on a different conversation while an earlier one is still
  // generating (or, worse, re-enable a conversation that's still actually generating).
  const [sendingIds, setSendingIds] = useState<Set<string>>(() => new Set())
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  // Guards the initial-draft auto-send effect below against firing twice for the same
  // conversation+prompt — React StrictMode double-invokes effects in dev, and without this
  // guard that would send the suggestion as two separate messages.
  const consumedDraftRef = useRef<string | null>(null)

  const sending = conversationId !== null && sendingIds.has(conversationId)

  useEffect(() => {
    if (!conversationId) {
      setMessages([])
      return
    }
    if (initialDraft) {
      // This conversation was just created for an auto-sent suggestion, so it's guaranteed
      // to have no messages yet — skip the fetch. Otherwise it can resolve after the send
      // below has optimistically added messages and overwrite them with a stale empty list.
      setTitle('New conversation')
      setMessages([])
      setError(null)
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    getConversation(conversationId)
      .then((conversation) => {
        setTitle(conversation.title)
        setMessages(
          conversation.messages.map((message) => ({
            id: message.id,
            role: message.role,
            content: message.content,
          })),
        )
      })
      .catch(() => setError('Could not load this conversation.'))
      .finally(() => setLoading(false))
  }, [conversationId])

  useEffect(() => {
    if (!conversationId || !initialDraft) return
    const key = `${conversationId}:${initialDraft}`
    if (consumedDraftRef.current === key) return
    consumedDraftRef.current = key
    handleSend(initialDraft)
    onInitialDraftConsumed?.()
    // Only re-run when a new conversation actually mounts or a prefill arrives for it —
    // consuming clears initialDraft (and the ref guard above), which prevents this from looping.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, initialDraft])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async (overrideContent?: string) => {
    const content = (overrideContent ?? draft).trim()
    if (!content || !conversationId || sending) return
    const targetId = conversationId

    setDraft('')
    setError(null)
    setMessages((prev) => [...prev, { id: `local-user-${Date.now()}`, role: 'user', content }])

    const assistantId = `local-assistant-${Date.now()}`
    setMessages((prev) => [...prev, { id: assistantId, role: 'assistant', content: '' }])
    setSendingIds((prev) => new Set(prev).add(targetId))

    try {
      await sendMessage(
        targetId,
        content,
        (delta) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? { ...message, content: message.content + delta, status: undefined }
                : message,
            ),
          )
        },
        (toolName) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? { ...message, status: TOOL_LABELS[toolName] ?? 'Using a tool…' }
                : message,
            ),
          )
        },
        (newTitle) => {
          // Sent by the backend as soon as it's generated (first message only) — update
          // both the header and the sidebar immediately, without waiting for the rest of
          // the request (profile extraction) to finish.
          setTitle(newTitle)
          onTitleChange(targetId, newTitle)
        },
      )
    } catch {
      setError('The advisor is unavailable right now.')
    } finally {
      setSendingIds((prev) => {
        const next = new Set(prev)
        next.delete(targetId)
        return next
      })
      onMessageSent()
    }
  }

  if (!conversationId) {
    return (
      <main className="chat-area chat-area--empty">
        <div className="chat-area__empty-state chat-area__empty-state--landing">
          <span className="chat-area__badge">Plan your next trip</span>
          <div className="chat-area__empty-illustration-wrap">
            <TravelIllustration className="chat-area__empty-illustration" />
          </div>
          <h1>Where to next?</h1>
          <p>
            Tell your travel advisor where you're headed and get real-time weather, exchange rates, and a
            day-by-day plan built around it.
          </p>
          <button className="btn btn--primary" onClick={onCreate}>
            <IconPlus />
            <span>New conversation</span>
          </button>

          <div className="chat-area__suggestions">
            <span className="chat-area__suggestions-label">Or try asking</span>
            <div className="chat-area__suggestions-list">
              {EXAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  className="chat-area__suggestion"
                  onClick={() => onCreateWithPrompt(prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="chat-area">
      <header className="chat-area__header">
        <span className="chat-area__eyebrow">AI Travel Advisor</span>
        <h2>{loading ? 'Loading…' : title}</h2>
      </header>

      <div className="chat-area__messages">
        {!loading && messages.length === 0 && (
          <div className="chat-area__empty-state chat-area__empty-state--inline">
            <IconChat className="chat-area__empty-icon" />
            <p>No messages yet.</p>
            <p className="chat-area__hint">Ask about a destination, dates, or anything travel-related.</p>
          </div>
        )}
        {messages.map((message) => (
          <div key={message.id} className={`message-row message-row--${message.role}`}>
            {message.role === 'assistant' && (
              <div className="message-avatar">
                <IconCompass />
              </div>
            )}
            <div className={`bubble bubble--${message.role}`}>
              {message.status ? (
                <span className="bubble__status">{message.status}</span>
              ) : message.content ? (
                message.role === 'assistant' ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                    {message.content}
                  </ReactMarkdown>
                ) : (
                  message.content
                )
              ) : (
                message.role === 'assistant' && sending ? '…' : ''
              )}
            </div>
          </div>
        ))}
        {error && <p className="chat-area__error">{error}</p>}
        <div ref={bottomRef} />
      </div>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault()
          handleSend()
        }}
      >
        <div className="composer__bar">
          <textarea
            className="composer__input"
            placeholder="Ask your travel advisor…"
            value={draft}
            rows={1}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                handleSend()
              }
            }}
          />
          <button type="submit" className="btn btn--primary composer__send" disabled={!draft.trim() || sending}>
            <IconSend />
          </button>
        </div>
      </form>
    </main>
  )
}

export default ChatArea

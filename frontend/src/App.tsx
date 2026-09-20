import { useCallback, useEffect, useState } from 'react'
import Sidebar from './Sidebar'
import ChatArea from './ChatArea'
import TripPlanPanel from './TripPlanPanel'
import SettingsPage from './SettingsPage'
import { createConversation, deleteConversation, listConversations, setConversationPinned } from './api'
import type { Conversation } from './types'
import { IconMap, IconMenu } from './icons'

type View = 'chat' | 'settings'

function App() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [planPanelOpen, setPlanPanelOpen] = useState(false)
  const [messageTick, setMessageTick] = useState(0)
  const [view, setView] = useState<View>('chat')
  const [pendingDraft, setPendingDraft] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setLoading(true)
    listConversations()
      .then(setConversations)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleCreate = async () => {
    setCreating(true)
    try {
      const conversation = await createConversation()
      setConversations((prev) => [conversation, ...prev])
      setSelectedId(conversation.id)
      setSidebarOpen(false)
      setPlanPanelOpen(false)
      setView('chat')
    } finally {
      setCreating(false)
    }
  }

  const handleCreateWithPrompt = async (prompt: string) => {
    setPendingDraft(prompt)
    await handleCreate()
  }

  const handleDelete = async (id: string) => {
    await deleteConversation(id)
    setConversations((prev) => prev.filter((conversation) => conversation.id !== id))
    if (selectedId === id) setSelectedId(null)
  }

  const handlePin = async (id: string, pinned: boolean) => {
    await setConversationPinned(id, pinned)
    refresh()
  }

  const handleSelect = (id: string) => {
    setSelectedId(id)
    setSidebarOpen(false)
    setPlanPanelOpen(false)
    setView('chat')
  }

  const handleMessageSent = () => {
    refresh()
    setMessageTick((tick) => tick + 1)
  }

  const handleTitleChange = (conversationId: string, title: string) => {
    setConversations((prev) =>
      prev.map((conversation) => (conversation.id === conversationId ? { ...conversation, title } : conversation)),
    )
  }

  const handleOpenSettings = () => {
    setSidebarOpen(false)
    setView('settings')
  }

  return (
    <div className="app">
      <button
        type="button"
        className="app__menu-toggle"
        onClick={() => setSidebarOpen((open) => !open)}
        aria-label="Toggle menu"
      >
        <IconMenu />
      </button>

      {view === 'chat' && selectedId && (
        <button
          type="button"
          className="app__plan-toggle"
          onClick={() => setPlanPanelOpen((open) => !open)}
          aria-label="Toggle trip plan"
        >
          <IconMap />
        </button>
      )}

      {sidebarOpen && <div className="app__backdrop" onClick={() => setSidebarOpen(false)} />}
      {planPanelOpen && selectedId && <div className="app__backdrop" onClick={() => setPlanPanelOpen(false)} />}

      <div className={`app__sidebar-wrap ${sidebarOpen ? 'app__sidebar-wrap--open' : ''}`}>
        <Sidebar
          conversations={conversations}
          selectedId={selectedId}
          loading={loading}
          creating={creating}
          onSelect={handleSelect}
          onCreate={handleCreate}
          onDelete={handleDelete}
          onPin={handlePin}
          onOpenSettings={handleOpenSettings}
        />
      </div>

      {view === 'settings' ? (
        <SettingsPage onBack={() => setView('chat')} />
      ) : (
        <>
          <ChatArea
            conversationId={selectedId}
            onCreate={handleCreate}
            onCreateWithPrompt={handleCreateWithPrompt}
            onMessageSent={handleMessageSent}
            onTitleChange={handleTitleChange}
            initialDraft={pendingDraft}
            onInitialDraftConsumed={() => setPendingDraft(null)}
          />

          {selectedId && (
            <div className={`app__plan-wrap ${planPanelOpen ? 'app__plan-wrap--open' : ''}`}>
              <TripPlanPanel conversationId={selectedId} refreshToken={messageTick} />
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default App

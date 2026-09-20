import { useState } from 'react'
import type { KeyboardEvent, MouseEvent } from 'react'
import type { Conversation } from './types'
import { IconCompass, IconPlus, IconSettings, IconTrash } from './icons'
import ConfirmDialog from './ConfirmDialog'

interface SidebarProps {
  conversations: Conversation[]
  selectedId: string | null
  loading: boolean
  creating: boolean
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
  onPin: (id: string, pinned: boolean) => void
  onOpenSettings: () => void
}

function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

function Sidebar({
  conversations,
  selectedId,
  loading,
  creating,
  onSelect,
  onCreate,
  onDelete,
  onPin,
  onOpenSettings,
}: SidebarProps) {
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)

  const handleDeleteClick = (event: MouseEvent, id: string) => {
    event.stopPropagation()
    setPendingDeleteId(id)
  }

  const confirmDelete = () => {
    if (pendingDeleteId) onDelete(pendingDeleteId)
    setPendingDeleteId(null)
  }

  const handlePinClick = (event: MouseEvent, conversation: Conversation) => {
    event.stopPropagation()
    onPin(conversation.id, !conversation.pinned)
  }

  const renderItem = (conversation: Conversation) => (
    <div
      key={conversation.id}
      className={`sidebar__item ${conversation.id === selectedId ? 'sidebar__item--active' : ''} ${conversation.pinned ? 'sidebar__item--pinned' : ''}`}
      role="button"
      tabIndex={0}
      onClick={() => onSelect(conversation.id)}
      onKeyDown={(event: KeyboardEvent) => {
        if (event.key === 'Enter') onSelect(conversation.id)
      }}
    >
      <div className="sidebar__item-text">
        <span className="sidebar__item-title">{conversation.title}</span>
        <span className="sidebar__item-time">{formatRelativeTime(conversation.updated_at)}</span>
      </div>
      <div className="sidebar__item-actions">
        <button
          type="button"
          className="sidebar__item-pin"
          aria-label={conversation.pinned ? 'Unpin conversation' : 'Pin conversation'}
          aria-pressed={conversation.pinned}
          onClick={(event) => handlePinClick(event, conversation)}
        >
          <span aria-hidden="true">📌</span>
        </button>
        <button
          type="button"
          className="sidebar__item-delete"
          aria-label="Delete conversation"
          onClick={(event) => handleDeleteClick(event, conversation.id)}
        >
          <IconTrash />
        </button>
      </div>
    </div>
  )

  const pinnedConversations = conversations.filter((conversation) => conversation.pinned)
  const unpinnedConversations = conversations.filter((conversation) => !conversation.pinned)

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__brand-badge">
          <IconCompass />
        </span>
        <span>
          <span className="sidebar__brand-name">Travel Advisor</span>
          <span className="sidebar__brand-tag">Trip Planning</span>
        </span>
      </div>

      <button className="btn btn--primary sidebar__new-btn" onClick={onCreate} disabled={creating}>
        <IconPlus />
        <span>{creating ? 'Creating…' : 'New conversation'}</span>
      </button>

      <div className="sidebar__list">
        {loading && <p className="sidebar__hint">Loading conversations…</p>}
        {!loading && conversations.length === 0 && (
          <p className="sidebar__hint">No trips yet — start planning!</p>
        )}
        {!loading && pinnedConversations.length > 0 && (
          <>
            <span className="sidebar__list-label">Pinned conversations</span>
            {pinnedConversations.map(renderItem)}
          </>
        )}
        {!loading && unpinnedConversations.length > 0 && (
          <>
            <span className="sidebar__list-label">Conversations</span>
            {unpinnedConversations.map(renderItem)}
          </>
        )}
      </div>

      <div className="sidebar__footer">
        <button type="button" className="sidebar__settings-btn" onClick={onOpenSettings}>
          <IconSettings />
          <span>Advisor Settings</span>
        </button>
      </div>

      {pendingDeleteId && (
        <ConfirmDialog
          title="Delete conversation?"
          message="This conversation and its messages can't be recovered."
          confirmLabel="Delete"
          onConfirm={confirmDelete}
          onCancel={() => setPendingDeleteId(null)}
        />
      )}
    </aside>
  )
}

export default Sidebar

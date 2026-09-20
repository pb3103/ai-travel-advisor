import { useEffect, useState } from 'react'
import { getSystemPrompt, saveSystemPrompt } from './api'
import { IconArrowLeft, IconCompass } from './icons'

interface SettingsPageProps {
  onBack: () => void
}

function SettingsPage({ onBack }: SettingsPageProps) {
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    getSystemPrompt()
      .then((prompt) => setContent(prompt.content))
      .catch(() => setError('Could not load the system prompt.'))
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const updated = await saveSystemPrompt(content)
      setContent(updated.content)
      setSaved(true)
    } catch {
      setError('Could not save the system prompt.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="settings-page">
      <div className="settings-page__card">
        <div className="settings-page__header">
          <button type="button" className="btn btn--secondary settings-page__back" onClick={onBack}>
            <IconArrowLeft />
            <span>Back to chat</span>
          </button>
          <div className="settings-page__title">
            <span className="settings-page__badge">
              <IconCompass />
            </span>
            <h1>Advisor Settings</h1>
          </div>
          <p className="settings-page__hint">
            This is the travel advisor's system prompt — its core instructions. Changes apply
            immediately to new messages.
          </p>
        </div>

        {loading ? (
          <p className="plan-panel__hint">Loading…</p>
        ) : (
          <>
            <textarea
              className="settings-page__textarea"
              value={content}
              onChange={(event) => {
                setContent(event.target.value)
                setSaved(false)
              }}
              rows={16}
            />
            <div className="settings-page__actions">
              <button
                type="button"
                className="btn btn--primary"
                onClick={handleSave}
                disabled={saving || !content.trim()}
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
              {saved && <span className="settings-page__saved">Saved</span>}
              {error && <span className="chat-area__error">{error}</span>}
            </div>
          </>
        )}
      </div>
    </main>
  )
}

export default SettingsPage

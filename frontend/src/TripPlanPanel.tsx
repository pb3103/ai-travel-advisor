import { useEffect, useState } from 'react'
import { getTripPlan, saveTripPlan } from './api'
import type { Activity, Day, TripPlan } from './types'
import {
  IconClock,
  IconEdit,
  IconMap,
  IconMoon,
  IconPin,
  IconPlus,
  IconSun,
  IconSunrise,
  IconSunset,
  IconTrash,
} from './icons'
import { TravelIllustration } from './illustrations'

interface TripPlanPanelProps {
  conversationId: string | null
  refreshToken: number
}

// A small curated set of gradients, all within the app's warm/blue palette — picked
// deterministically per destination so each trip gets a consistent "identity" without
// needing real photos (and the network dependency/failure mode that would come with them).
const DESTINATION_GRADIENTS: [string, string][] = [
  ['#e2764a', '#a8431f'],
  ['#e3ab5c', '#bd7a34'],
  ['#3d7f88', '#204349'],
  ['#4a8f75', '#255c48'],
  ['#c9694a', '#2c6a72'],
]

function getDestinationGradient(destination: string | null): string {
  const key = destination || 'trip'
  let hash = 0
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) | 0
  }
  const [from, to] = DESTINATION_GRADIENTS[Math.abs(hash) % DESTINATION_GRADIENTS.length]
  return `linear-gradient(135deg, ${from}, ${to})`
}

function getTimeIcon(time: string) {
  const t = time.toLowerCase()
  if (t.includes('morning') || t.includes('sunrise') || t.includes('breakfast')) return IconSunrise
  if (t.includes('evening') || t.includes('sunset') || t.includes('dusk') || t.includes('dinner')) return IconSunset
  if (t.includes('night') || t.includes('late')) return IconMoon
  if (t.includes('afternoon') || t.includes('noon') || t.includes('midday') || t.includes('lunch')) return IconSun
  return IconClock
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  const parsed = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatDateRange(start: string | null, end: string | null): string {
  if (!start && !end) return 'Dates not set yet'
  if (start && end) return `${formatDate(start)} – ${formatDate(end)}`
  return formatDate(start ?? end)
}

function emptyActivity(): Activity {
  return { time: '', title: '', description: '' }
}

function findMissingDate(plan: TripPlan): string | null {
  const missing = plan.days.find((day) => !day.date)
  return missing ? `Day ${missing.day} is missing a date — please set one before saving.` : null
}

function TripPlanPanel({ conversationId, refreshToken }: TripPlanPanelProps) {
  const [plan, setPlan] = useState<TripPlan | null>(null)
  const [draft, setDraft] = useState<TripPlan | null>(null)
  const [editing, setEditing] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setEditing(false)
    setDraft(null)
    setError(null)
    if (!conversationId) {
      setPlan(null)
      return
    }
    setLoading(true)
    getTripPlan(conversationId)
      .then(setPlan)
      .catch(() => setError('Could not load the trip plan.'))
      .finally(() => setLoading(false))
  }, [conversationId, refreshToken])

  const startEditing = () => {
    if (!plan) return
    setDraft(JSON.parse(JSON.stringify(plan)))
    setEditing(true)
    setError(null)
  }

  const cancelEditing = () => {
    setDraft(null)
    setEditing(false)
    setError(null)
  }

  const updateDay = (index: number, patch: Partial<Day>) => {
    setDraft((d) => (d ? { ...d, days: d.days.map((day, i) => (i === index ? { ...day, ...patch } : day)) } : d))
  }

  const updateActivity = (dayIndex: number, actIndex: number, patch: Partial<Activity>) => {
    setDraft((d) => {
      if (!d) return d
      const days = d.days.map((day, i) => {
        if (i !== dayIndex) return day
        const activities = day.activities.map((activity, j) => (j === actIndex ? { ...activity, ...patch } : activity))
        return { ...day, activities }
      })
      return { ...d, days }
    })
  }

  const addActivity = (dayIndex: number) => {
    setDraft((d) => {
      if (!d) return d
      const days = d.days.map((day, i) =>
        i === dayIndex ? { ...day, activities: [...day.activities, emptyActivity()] } : day,
      )
      return { ...d, days }
    })
  }

  const removeActivity = (dayIndex: number, actIndex: number) => {
    setDraft((d) => {
      if (!d) return d
      const days = d.days.map((day, i) =>
        i === dayIndex ? { ...day, activities: day.activities.filter((_, j) => j !== actIndex) } : day,
      )
      return { ...d, days }
    })
  }

  const addDay = () => {
    setDraft((d) => {
      if (!d) return d
      const nextNum = d.days.length > 0 ? Math.max(...d.days.map((day) => day.day)) + 1 : 1
      return { ...d, days: [...d.days, { day: nextNum, date: '', location: '', title: '', activities: [] }] }
    })
  }

  const removeDay = (index: number) => {
    setDraft((d) => (d ? { ...d, days: d.days.filter((_, i) => i !== index) } : d))
  }

  const validationError = editing && draft ? findMissingDate(draft) : null

  const handleSave = async () => {
    if (!draft || !conversationId) return
    if (validationError) {
      setError(validationError)
      return
    }
    setSaving(true)
    setError(null)
    try {
      const saved = await saveTripPlan(conversationId, {
        destination: draft.destination || null,
        start_date: draft.start_date || null,
        end_date: draft.end_date || null,
        days: draft.days,
      })
      setPlan(saved)
      setEditing(false)
      setDraft(null)
    } catch {
      setError('Could not save the trip plan.')
    } finally {
      setSaving(false)
    }
  }

  const shown = editing ? draft : plan

  return (
    <aside className="plan-panel">
      <div className="plan-panel__header">
        <div className="plan-panel__title">
          <span className="plan-panel__badge">
            <IconMap />
          </span>
          <h2>Trip Plan</h2>
        </div>
        {plan && !editing && (
          <button type="button" className="plan-panel__edit-btn" onClick={startEditing} aria-label="Edit trip plan">
            <IconEdit />
          </button>
        )}
      </div>

      <div className="plan-panel__body">
        {loading && <p className="plan-panel__hint">Loading…</p>}

        {!loading && !shown && (
          <div className="plan-empty">
            <TravelIllustration className="plan-empty__illustration" />
            <p>No trip plan yet.</p>
            <p className="plan-panel__hint">Ask your advisor to help plan a trip and it'll show up here.</p>
          </div>
        )}

        {!loading && shown && (
          <>
            {editing ? (
              <div className="plan-summary">
                <input
                  type="text"
                  placeholder="Destination"
                  value={shown.destination ?? ''}
                  onChange={(event) => setDraft((d) => (d ? { ...d, destination: event.target.value } : d))}
                />
                <div className="plan-summary__dates-edit">
                  <input
                    type="date"
                    value={shown.start_date ?? ''}
                    onChange={(event) => setDraft((d) => (d ? { ...d, start_date: event.target.value || null } : d))}
                  />
                  <input
                    type="date"
                    value={shown.end_date ?? ''}
                    onChange={(event) => setDraft((d) => (d ? { ...d, end_date: event.target.value || null } : d))}
                  />
                </div>
              </div>
            ) : (
              <div className="plan-hero" style={{ backgroundImage: getDestinationGradient(shown.destination) }}>
                <div className="plan-hero__pattern" />
                <span className="plan-hero__eyebrow">Your itinerary</span>
                <h3 className="plan-hero__destination">{shown.destination || 'Untitled trip'}</h3>
                <p className="plan-hero__dates">{formatDateRange(shown.start_date, shown.end_date)}</p>
              </div>
            )}

            <div className="plan-timeline">
              {shown.days.map((day, dayIndex) => (
                <div className="plan-day" key={dayIndex}>
                  <div className="plan-day__badge">{day.day}</div>
                  <div className="plan-day__content">
                    <div className="plan-day__header">
                      {editing ? (
                        <input
                          type="date"
                          value={day.date}
                          onChange={(event) => updateDay(dayIndex, { date: event.target.value })}
                        />
                      ) : (
                        <span className="plan-day__date">{formatDate(day.date)}</span>
                      )}
                      {editing && (
                        <button
                          type="button"
                          className="plan-day__delete"
                          aria-label="Remove day"
                          onClick={() => removeDay(dayIndex)}
                        >
                          <IconTrash />
                        </button>
                      )}
                    </div>

                    {editing ? (
                      <>
                        <input
                          type="text"
                          placeholder="Day title"
                          value={day.title}
                          onChange={(event) => updateDay(dayIndex, { title: event.target.value })}
                        />
                        <input
                          type="text"
                          placeholder="Location"
                          value={day.location}
                          onChange={(event) => updateDay(dayIndex, { location: event.target.value })}
                        />
                      </>
                    ) : (
                      <>
                        <h4 className="plan-day__title">{day.title}</h4>
                        {day.location && (
                          <p className="plan-day__location">
                            <IconPin />
                            <span>{day.location}</span>
                          </p>
                        )}
                      </>
                    )}

                    <ul className="plan-activities">
                      {day.activities.map((activity, actIndex) => {
                        const TimeIcon = getTimeIcon(activity.time)
                        return (
                          <li className="plan-activity" key={actIndex}>
                            {editing ? (
                              <div className="plan-activity__edit">
                                <input
                                  type="text"
                                  placeholder="Time"
                                  value={activity.time}
                                  onChange={(event) =>
                                    updateActivity(dayIndex, actIndex, { time: event.target.value })
                                  }
                                />
                                <input
                                  type="text"
                                  placeholder="Title"
                                  value={activity.title}
                                  onChange={(event) =>
                                    updateActivity(dayIndex, actIndex, { title: event.target.value })
                                  }
                                />
                                <textarea
                                  placeholder="Description"
                                  value={activity.description}
                                  onChange={(event) =>
                                    updateActivity(dayIndex, actIndex, { description: event.target.value })
                                  }
                                />
                                <button
                                  type="button"
                                  className="plan-activity__delete"
                                  aria-label="Remove activity"
                                  onClick={() => removeActivity(dayIndex, actIndex)}
                                >
                                  <IconTrash />
                                </button>
                              </div>
                            ) : (
                              <>
                                <span className="plan-activity__time">
                                  <TimeIcon />
                                  {activity.time}
                                </span>
                                <div className="plan-activity__text">
                                  <strong>{activity.title}</strong>
                                  {activity.description && <p>{activity.description}</p>}
                                </div>
                              </>
                            )}
                          </li>
                        )
                      })}
                    </ul>

                    {editing && (
                      <button type="button" className="plan-add-btn" onClick={() => addActivity(dayIndex)}>
                        <IconPlus />
                        <span>Add activity</span>
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {editing && (
              <button type="button" className="plan-add-btn" onClick={addDay}>
                <IconPlus />
                <span>Add day</span>
              </button>
            )}
          </>
        )}

        {(validationError || error) && <p className="chat-area__error">{validationError || error}</p>}
      </div>

      {editing && (
        <div className="plan-panel__actions">
          <button type="button" className="btn btn--secondary" onClick={cancelEditing} disabled={saving}>
            Cancel
          </button>
          <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving || !!validationError}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      )}
    </aside>
  )
}

export default TripPlanPanel

import { useState, useEffect, useCallback } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const API_KEY  = import.meta.env.VITE_DASHBOARD_API_KEY || ''
const PASSWORD = import.meta.env.VITE_DASHBOARD_PASSWORD || ''

// ─── API helpers ─────────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'x-dashboard-key': API_KEY,
      ...(options.headers || {}),
    },
  })
  if (res.status === 204) return null
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

// ─── Auth gate ────────────────────────────────────────────────────────────────

function AuthGate({ onAuth }) {
  const [input, setInput]   = useState('')
  const [error, setError]   = useState('')

  function submit(e) {
    e.preventDefault()
    if (input === PASSWORD) {
      sessionStorage.setItem('dash_auth', '1')
      onAuth()
    } else {
      setError('Incorrect password')
      setInput('')
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-box">
        <h1>Lucentive Dashboard</h1>
        <p>Enter the team password to continue.</p>
        <form onSubmit={submit}>
          <input
            type="password"
            value={input}
            onChange={e => { setInput(e.target.value); setError('') }}
            placeholder="Password"
            autoFocus
          />
          {error && <p className="field-error">{error}</p>}
          <button type="submit">Enter</button>
        </form>
      </div>
    </div>
  )
}

// ─── Modal ────────────────────────────────────────────────────────────────────

function Modal({ title, fields, onSave, onClose, saving, error }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{title}</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        {fields}
        {error && <p className="field-error">{error}</p>}
        <div className="modal-actions">
          <button className="btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button className="btn-primary" onClick={onSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── QA Tab ───────────────────────────────────────────────────────────────────

function QATab() {
  const [rows, setRows]         = useState([])
  const [loading, setLoading]   = useState(true)
  const [fetchError, setFetch]  = useState('')
  const [modal, setModal]       = useState(null) // null | { mode: 'add'|'edit', row?: {} }
  const [question, setQuestion] = useState('')
  const [answer, setAnswer]     = useState('')
  const [saving, setSaving]     = useState(false)
  const [modalError, setModalError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setFetch('')
    try {
      const data = await apiFetch('/knowledge/qa')
      setRows(data)
    } catch (e) {
      setFetch(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function openAdd() {
    setQuestion(''); setAnswer(''); setModalError('')
    setModal({ mode: 'add' })
  }

  function openEdit(row) {
    setQuestion(row.question); setAnswer(row.answer); setModalError('')
    setModal({ mode: 'edit', row })
  }

  function closeModal() { setModal(null) }

  async function handleSave() {
    const q = question.trim()
    const a = answer.trim()
    if (q.length < 10) { setModalError('Question must be at least 10 characters'); return }
    if (a.length < 10) { setModalError('Answer must be at least 10 characters'); return }
    setSaving(true)
    setModalError('')
    try {
      if (modal.mode === 'add') {
        await apiFetch('/knowledge/qa', { method: 'POST', body: JSON.stringify({ question: q, answer: a }) })
      } else {
        await apiFetch(`/knowledge/qa/${modal.row.id}`, { method: 'PUT', body: JSON.stringify({ question: q, answer: a }) })
      }
      closeModal()
      await load()
    } catch (e) {
      setModalError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleToggle(row) {
    try {
      await apiFetch(`/knowledge/qa/${row.id}`, { method: 'PUT', body: JSON.stringify({ active: !row.active }) })
      await load()
    } catch (e) {
      alert(e.message)
    }
  }

  async function handleDelete(row) {
    if (!confirm(`Delete this Q&A pair?\n\n"${row.question.slice(0, 80)}"`)) return
    try {
      await apiFetch(`/knowledge/qa/${row.id}`, { method: 'DELETE' })
      await load()
    } catch (e) {
      alert(e.message)
    }
  }

  return (
    <div className="tab-content">
      <div className="tab-toolbar">
        <span className="row-count">{rows.length} entries</span>
        <button className="btn-primary" onClick={openAdd}>+ Add Question</button>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}

      {!loading && !fetchError && rows.length === 0 && (
        <p className="status-msg">No Q&A pairs yet. Add your first one above.</p>
      )}

      {rows.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Question</th>
              <th>Answer</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.id} className={row.active ? '' : 'row-inactive'}>
                <td className="cell-truncate">{row.question}</td>
                <td className="cell-truncate">{row.answer}</td>
                <td>
                  <span className={`badge ${row.active ? 'badge-active' : 'badge-inactive'}`}>
                    {row.active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td className="cell-actions">
                  <button className="btn-icon" title="Edit" onClick={() => openEdit(row)}>✏️</button>
                  <button className="btn-icon" title={row.active ? 'Deactivate' : 'Activate'} onClick={() => handleToggle(row)}>
                    {row.active ? '🔴' : '🟢'}
                  </button>
                  <button className="btn-icon" title="Delete" onClick={() => handleDelete(row)}>🗑️</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {modal && (
        <Modal
          title={modal.mode === 'add' ? 'Add Q&A Pair' : 'Edit Q&A Pair'}
          onSave={handleSave}
          onClose={closeModal}
          saving={saving}
          error={modalError}
          fields={
            <>
              <div className="field">
                <label>Question</label>
                <input
                  type="text"
                  value={question}
                  onChange={e => { setQuestion(e.target.value); setModalError('') }}
                  placeholder="e.g. What is the minimum deposit?"
                  autoFocus
                />
              </div>
              <div className="field">
                <label>Answer</label>
                <textarea
                  value={answer}
                  onChange={e => { setAnswer(e.target.value); setModalError('') }}
                  placeholder="The full answer the bot will use…"
                  rows={5}
                />
              </div>
            </>
          }
        />
      )}
    </div>
  )
}

// ─── Handoff Tab ──────────────────────────────────────────────────────────────

const DEFAULT_RESPONSE = 'אחד רגע בבקשה 🙏'

function HandoffTab() {
  const [rows, setRows]           = useState([])
  const [loading, setLoading]     = useState(true)
  const [fetchError, setFetch]    = useState('')
  const [modal, setModal]         = useState(null)
  const [scenario, setScenario]   = useState('')
  const [defResp, setDefResp]     = useState(DEFAULT_RESPONSE)
  const [saving, setSaving]       = useState(false)
  const [modalError, setModalError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setFetch('')
    try {
      const data = await apiFetch('/knowledge/handoff')
      setRows(data)
    } catch (e) {
      setFetch(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function openAdd() {
    setScenario(''); setDefResp(DEFAULT_RESPONSE); setModalError('')
    setModal({ mode: 'add' })
  }

  function openEdit(row) {
    setScenario(row.scenario); setDefResp(row.default_response); setModalError('')
    setModal({ mode: 'edit', row })
  }

  function closeModal() { setModal(null) }

  async function handleSave() {
    const s = scenario.trim()
    const d = defResp.trim()
    if (s.length < 10) { setModalError('Scenario must be at least 10 characters'); return }
    if (!d) { setModalError('Default response cannot be empty'); return }
    setSaving(true)
    setModalError('')
    try {
      if (modal.mode === 'add') {
        await apiFetch('/knowledge/handoff', {
          method: 'POST',
          body: JSON.stringify({ scenario: s, default_response: d }),
        })
      } else {
        await apiFetch(`/knowledge/handoff/${modal.row.id}`, {
          method: 'PUT',
          body: JSON.stringify({ scenario: s, default_response: d }),
        })
      }
      closeModal()
      await load()
    } catch (e) {
      setModalError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleToggle(row) {
    try {
      await apiFetch(`/knowledge/handoff/${row.id}`, { method: 'PUT', body: JSON.stringify({ active: !row.active }) })
      await load()
    } catch (e) {
      alert(e.message)
    }
  }

  async function handleDelete(row) {
    if (!confirm(`Delete this handoff rule?\n\n"${row.scenario.slice(0, 80)}"`)) return
    try {
      await apiFetch(`/knowledge/handoff/${row.id}`, { method: 'DELETE' })
      await load()
    } catch (e) {
      alert(e.message)
    }
  }

  return (
    <div className="tab-content">
      <div className="tab-toolbar">
        <span className="row-count">{rows.length} rules</span>
        <button className="btn-primary" onClick={openAdd}>+ Add Handoff Rule</button>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}

      {!loading && !fetchError && rows.length === 0 && (
        <p className="status-msg">No handoff rules yet. Add your first one above.</p>
      )}

      {rows.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Default Response</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.id} className={row.active ? '' : 'row-inactive'}>
                <td className="cell-truncate">{row.scenario}</td>
                <td className="cell-truncate">{row.default_response}</td>
                <td>
                  <span className={`badge ${row.active ? 'badge-active' : 'badge-inactive'}`}>
                    {row.active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td className="cell-actions">
                  <button className="btn-icon" title="Edit" onClick={() => openEdit(row)}>✏️</button>
                  <button className="btn-icon" title={row.active ? 'Deactivate' : 'Activate'} onClick={() => handleToggle(row)}>
                    {row.active ? '🔴' : '🟢'}
                  </button>
                  <button className="btn-icon" title="Delete" onClick={() => handleDelete(row)}>🗑️</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {modal && (
        <Modal
          title={modal.mode === 'add' ? 'Add Handoff Rule' : 'Edit Handoff Rule'}
          onSave={handleSave}
          onClose={closeModal}
          saving={saving}
          error={modalError}
          fields={
            <>
              <div className="field">
                <label>Scenario</label>
                <textarea
                  value={scenario}
                  onChange={e => { setScenario(e.target.value); setModalError('') }}
                  placeholder="Describe when the bot should hand off to a human, e.g. 'User asks about a withdrawal problem or payment issue'"
                  rows={4}
                  autoFocus
                />
              </div>
              <div className="field">
                <label>Default Response <span className="label-hint">(sent to user before handoff)</span></label>
                <input
                  type="text"
                  value={defResp}
                  onChange={e => { setDefResp(e.target.value); setModalError('') }}
                />
              </div>
            </>
          }
        />
      )}
    </div>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [authed, setAuthed] = useState(() => sessionStorage.getItem('dash_auth') === '1')
  const [tab, setTab]       = useState('qa')

  if (!authed) return <AuthGate onAuth={() => setAuthed(true)} />

  return (
    <div className="app">
      <header className="app-header">
        <span className="app-title">Lucentive Dashboard</span>
        <button
          className="btn-logout"
          onClick={() => { sessionStorage.removeItem('dash_auth'); setAuthed(false) }}
        >
          Log out
        </button>
      </header>

      <nav className="tab-nav">
        <button
          className={`tab-btn ${tab === 'qa' ? 'active' : ''}`}
          onClick={() => setTab('qa')}
        >
          Knowledge Base
        </button>
        <button
          className={`tab-btn ${tab === 'handoff' ? 'active' : ''}`}
          onClick={() => setTab('handoff')}
        >
          Handoff Rules
        </button>
      </nav>

      {tab === 'qa'      && <QATab />}
      {tab === 'handoff' && <HandoffTab />}
    </div>
  )
}

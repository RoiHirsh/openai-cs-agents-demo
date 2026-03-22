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

// ─── Bulk Import Modal ────────────────────────────────────────────────────────

function BulkImportModal({ title, placeholder, hint, parseRow, endpoint, onDone, onClose }) {
  const [text, setText]       = useState('')
  const [phase, setPhase]     = useState('input') // 'input' | 'importing' | 'done'
  const [error, setError]     = useState('')
  const [progress, setProgress] = useState({ done: 0, total: 0, failed: 0 })

  async function handleImport() {
    let raw
    try {
      raw = JSON.parse(text.trim())
      if (!Array.isArray(raw)) throw new Error('Expected a JSON array [ ... ]')
    } catch (e) {
      setError('Invalid JSON: ' + e.message)
      return
    }

    const valid = raw.map(parseRow).filter(Boolean)
    const skipped = raw.length - valid.length

    if (valid.length === 0) {
      setError(`No valid rows found (${skipped} skipped due to validation). Check the format.`)
      return
    }

    setPhase('importing')
    setProgress({ done: 0, total: valid.length, failed: 0 })

    let failed = 0
    for (let i = 0; i < valid.length; i++) {
      try {
        await apiFetch(endpoint, { method: 'POST', body: JSON.stringify(valid[i]) })
      } catch {
        failed++
      }
      setProgress({ done: i + 1, total: valid.length, failed })
    }

    onDone()
    setPhase('done')
    setProgress({ done: valid.length, total: valid.length, failed })
  }

  return (
    <div className="modal-overlay" onClick={phase === 'importing' ? undefined : onClose}>
      <div className="modal modal-wide" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{title}</h2>
          {phase !== 'importing' && (
            <button className="modal-close" onClick={onClose}>✕</button>
          )}
        </div>

        {phase === 'input' && (
          <>
            <p className="bulk-hint">{hint}</p>
            <div className="field">
              <textarea
                value={text}
                onChange={e => { setText(e.target.value); setError('') }}
                rows={12}
                placeholder={placeholder}
                autoFocus
              />
            </div>
            {error && <p className="field-error">{error}</p>}
            <div className="modal-actions">
              <button className="btn-secondary" onClick={onClose}>Cancel</button>
              <button className="btn-primary" onClick={handleImport} disabled={!text.trim()}>
                Import
              </button>
            </div>
          </>
        )}

        {phase === 'importing' && (
          <div className="bulk-progress">
            <p>Importing {progress.done} of {progress.total}…</p>
            <div className="progress-bar-wrap">
              <div
                className="progress-bar-fill"
                style={{ width: `${(progress.done / progress.total) * 100}%` }}
              />
            </div>
          </div>
        )}

        {phase === 'done' && (
          <>
            <p className="bulk-done">
              Done — {progress.total - progress.failed} imported
              {progress.failed > 0 ? `, ${progress.failed} failed` : ''}.
            </p>
            <div className="modal-actions">
              <button className="btn-primary" onClick={onClose}>Close</button>
            </div>
          </>
        )}
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
  const [search, setSearch]     = useState('')
  const [showBulk, setShowBulk] = useState(false)

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

  const filtered = search.trim()
    ? rows.filter(r =>
        r.question.toLowerCase().includes(search.toLowerCase()) ||
        r.answer.toLowerCase().includes(search.toLowerCase())
      )
    : rows

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

  function parseQARow(r) {
    const q = (r.question || '').trim()
    const a = (r.answer || '').trim()
    if (q.length < 10 || a.length < 10) return null
    return { question: q, answer: a }
  }

  return (
    <div className="tab-content">
      <div className="search-bar">
        <input
          className="search-input"
          type="text"
          placeholder="Search questions or answers…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        {search && (
          <button className="search-clear" onClick={() => setSearch('')} title="Clear">×</button>
        )}
      </div>

      <div className="tab-toolbar">
        <span className="row-count">
          {search.trim()
            ? `${filtered.length} of ${rows.length} entries`
            : `${rows.length} entries`}
        </span>
        <div className="toolbar-actions">
          <button className="btn-outline" onClick={() => setShowBulk(true)}>Bulk Import</button>
          <button className="btn-primary" onClick={openAdd}>+ Add Question</button>
        </div>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}

      {!loading && !fetchError && rows.length === 0 && (
        <p className="status-msg">No Q&A pairs yet. Add your first one above.</p>
      )}
      {!loading && !fetchError && rows.length > 0 && filtered.length === 0 && (
        <p className="status-msg">No matches for "{search}".</p>
      )}

      {filtered.length > 0 && (
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
            {filtered.map(row => (
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

      {showBulk && (
        <BulkImportModal
          title="Bulk Import Q&A Pairs"
          hint='Paste a JSON array. Each item must have "question" and "answer" (min 10 chars each).'
          placeholder={'[\n  { "question": "What is the minimum deposit?", "answer": "The minimum deposit is $500." },\n  { "question": "...", "answer": "..." }\n]'}
          parseRow={parseQARow}
          endpoint="/knowledge/qa"
          onDone={load}
          onClose={() => setShowBulk(false)}
        />
      )}
    </div>
  )
}

// ─── Handoff Tab ──────────────────────────────────────────────────────────────

const DEFAULT_RESPONSE = 'Please wait one sec'

function HandoffTab() {
  const [rows, setRows]           = useState([])
  const [loading, setLoading]     = useState(true)
  const [fetchError, setFetch]    = useState('')
  const [modal, setModal]         = useState(null)
  const [scenario, setScenario]   = useState('')
  const [defResp, setDefResp]     = useState(DEFAULT_RESPONSE)
  const [saving, setSaving]       = useState(false)
  const [modalError, setModalError] = useState('')
  const [search, setSearch]       = useState('')
  const [showBulk, setShowBulk]   = useState(false)

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

  const filtered = search.trim()
    ? rows.filter(r => r.scenario.toLowerCase().includes(search.toLowerCase()))
    : rows

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

  function parseHandoffRow(r) {
    const s = (r.scenario || '').trim()
    if (s.length < 10) return null
    return { scenario: s, default_response: (r.default_response || DEFAULT_RESPONSE).trim() }
  }

  return (
    <div className="tab-content">
      <div className="search-bar">
        <input
          className="search-input"
          type="text"
          placeholder="Search scenarios…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        {search && (
          <button className="search-clear" onClick={() => setSearch('')} title="Clear">×</button>
        )}
      </div>

      <div className="tab-toolbar">
        <span className="row-count">
          {search.trim()
            ? `${filtered.length} of ${rows.length} rules`
            : `${rows.length} rules`}
        </span>
        <div className="toolbar-actions">
          <button className="btn-outline" onClick={() => setShowBulk(true)}>Bulk Import</button>
          <button className="btn-primary" onClick={openAdd}>+ Add Handoff Rule</button>
        </div>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}

      {!loading && !fetchError && rows.length === 0 && (
        <p className="status-msg">No handoff rules yet. Add your first one above.</p>
      )}
      {!loading && !fetchError && rows.length > 0 && filtered.length === 0 && (
        <p className="status-msg">No matches for "{search}".</p>
      )}

      {filtered.length > 0 && (
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
            {filtered.map(row => (
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

      {showBulk && (
        <BulkImportModal
          title="Bulk Import Handoff Rules"
          hint='Paste a JSON array. Each item must have "scenario" (min 10 chars). "default_response" is optional.'
          placeholder={'[\n  { "scenario": "User asks about a withdrawal problem or payment issue" },\n  { "scenario": "..." }\n]'}
          parseRow={parseHandoffRow}
          endpoint="/knowledge/handoff"
          onDone={load}
          onClose={() => setShowBulk(false)}
        />
      )}
    </div>
  )
}

// ─── Broker Assets Tab ────────────────────────────────────────────────────────

const BROKERS   = ['bybit', 'vantage', 'pu_prime']
const PURPOSES  = ['registration', 'copy_trade_open_account', 'copy_trade_connect', 'copy_trade_start']
const ASSET_TYPES = ['link', 'video']
const COUNTRY_GROUPS = ['AUSTRALIA', 'CANADA', 'UK', 'OTHER']

function BrokerAssetsTab() {
  const [rows, setRows]             = useState([])
  const [loading, setLoading]       = useState(true)
  const [fetchError, setFetch]      = useState('')
  const [modal, setModal]           = useState(null)
  const [saving, setSaving]         = useState(false)
  const [modalError, setModalError] = useState('')
  const [filterBroker, setFilterBroker]   = useState('all')
  const [filterPurpose, setFilterPurpose] = useState('all')

  // form fields
  const [fBroker, setFBroker]       = useState('bybit')
  const [fPurpose, setFPurpose]     = useState('registration')
  const [fAssetType, setFAssetType] = useState('link')
  const [fTitle, setFTitle]         = useState('')
  const [fUrl, setFUrl]             = useState('')
  const [fOrder, setFOrder]         = useState(0)

  const load = useCallback(async () => {
    setLoading(true); setFetch('')
    try { setRows(await apiFetch('/knowledge/broker-assets')) }
    catch (e) { setFetch(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = rows.filter(r =>
    (filterBroker  === 'all' || r.broker  === filterBroker) &&
    (filterPurpose === 'all' || r.purpose === filterPurpose)
  )

  function openAdd() {
    setFBroker('bybit'); setFPurpose('registration'); setFAssetType('link')
    setFTitle(''); setFUrl(''); setFOrder(0); setModalError('')
    setModal({ mode: 'add' })
  }

  function openEdit(row) {
    setFBroker(row.broker); setFPurpose(row.purpose); setFAssetType(row.asset_type)
    setFTitle(row.title); setFUrl(row.url); setFOrder(row.sort_order ?? 0); setModalError('')
    setModal({ mode: 'edit', row })
  }

  async function handleSave() {
    const t = fTitle.trim(), u = fUrl.trim()
    if (!t) { setModalError('Title is required'); return }
    if (!u) { setModalError('URL is required'); return }
    setSaving(true); setModalError('')
    const payload = { broker: fBroker, purpose: fPurpose, asset_type: fAssetType, title: t, url: u, sort_order: fOrder }
    try {
      if (modal.mode === 'add') {
        await apiFetch('/knowledge/broker-assets', { method: 'POST', body: JSON.stringify(payload) })
      } else {
        await apiFetch(`/knowledge/broker-assets/${modal.row.id}`, { method: 'PUT', body: JSON.stringify(payload) })
      }
      setModal(null); await load()
    } catch (e) { setModalError(e.message) }
    finally { setSaving(false) }
  }

  async function handleToggle(row) {
    try {
      await apiFetch(`/knowledge/broker-assets/${row.id}`, { method: 'PUT', body: JSON.stringify({ active: !row.active }) })
      await load()
    } catch (e) { alert(e.message) }
  }

  async function handleDelete(row) {
    if (!confirm(`Delete "${row.title}"?`)) return
    try { await apiFetch(`/knowledge/broker-assets/${row.id}`, { method: 'DELETE' }); await load() }
    catch (e) { alert(e.message) }
  }

  return (
    <div className="tab-content">
      <div className="tab-toolbar">
        <div className="toolbar-filters">
          <select value={filterBroker} onChange={e => setFilterBroker(e.target.value)}>
            <option value="all">All brokers</option>
            {BROKERS.map(b => <option key={b} value={b}>{b}</option>)}
          </select>
          <select value={filterPurpose} onChange={e => setFilterPurpose(e.target.value)}>
            <option value="all">All purposes</option>
            {PURPOSES.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <span className="row-count">{filtered.length} of {rows.length} assets</span>
        </div>
        <button className="btn-primary" onClick={openAdd}>+ Add Asset</button>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}
      {!loading && !fetchError && rows.length === 0 && (
        <p className="status-msg">No broker assets yet.</p>
      )}

      {filtered.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Broker</th>
              <th>Purpose</th>
              <th>Type</th>
              <th>Title</th>
              <th>URL</th>
              <th>Order</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(row => (
              <tr key={row.id} className={row.active ? '' : 'row-inactive'}>
                <td>{row.broker}</td>
                <td>{row.purpose}</td>
                <td>{row.asset_type}</td>
                <td className="cell-truncate">{row.title}</td>
                <td className="cell-truncate"><a href={row.url} target="_blank" rel="noreferrer">{row.url}</a></td>
                <td>{row.sort_order}</td>
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
          title={modal.mode === 'add' ? 'Add Broker Asset' : 'Edit Broker Asset'}
          onSave={handleSave}
          onClose={() => setModal(null)}
          saving={saving}
          error={modalError}
          fields={
            <>
              <div className="field">
                <label>Broker</label>
                <select value={fBroker} onChange={e => { setFBroker(e.target.value); setModalError('') }}>
                  {BROKERS.map(b => <option key={b} value={b}>{b}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Purpose</label>
                <select value={fPurpose} onChange={e => { setFPurpose(e.target.value); setModalError('') }}>
                  {PURPOSES.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Type</label>
                <select value={fAssetType} onChange={e => { setFAssetType(e.target.value); setModalError('') }}>
                  {ASSET_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Title</label>
                <input type="text" value={fTitle} onChange={e => { setFTitle(e.target.value); setModalError('') }} placeholder="e.g. Bybit link for sign up" autoFocus />
              </div>
              <div className="field">
                <label>URL</label>
                <input type="text" value={fUrl} onChange={e => { setFUrl(e.target.value); setModalError('') }} placeholder="https://…" />
              </div>
              <div className="field">
                <label>Sort order <span className="label-hint">(lower = first)</span></label>
                <input type="number" value={fOrder} onChange={e => { setFOrder(Number(e.target.value)); setModalError('') }} min={0} />
              </div>
            </>
          }
        />
      )}
    </div>
  )
}

// ─── Country Offers Tab ───────────────────────────────────────────────────────

function CountryOffersTab() {
  const [rows, setRows]             = useState([])
  const [loading, setLoading]       = useState(true)
  const [fetchError, setFetch]      = useState('')
  const [modal, setModal]           = useState(null)
  const [saving, setSaving]         = useState(false)
  const [modalError, setModalError] = useState('')

  // form fields
  const [fGroup, setFGroup]               = useState('OTHER')
  const [fBroker, setFBroker]             = useState('')
  const [fBots, setFBots]                 = useState('')           // comma-separated
  const [fBrokerNotes, setFBrokerNotes]   = useState('')           // newline-separated
  const [fGroupNotes, setFGroupNotes]     = useState('')           // newline-separated
  const [fOrder, setFOrder]               = useState(0)

  const load = useCallback(async () => {
    setLoading(true); setFetch('')
    try { setRows(await apiFetch('/knowledge/country-offers')) }
    catch (e) { setFetch(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  function openAdd() {
    setFGroup('OTHER'); setFBroker(''); setFBots(''); setFBrokerNotes(''); setFGroupNotes(''); setFOrder(0); setModalError('')
    setModal({ mode: 'add' })
  }

  function openEdit(row) {
    setFGroup(row.country_group); setFBroker(row.broker_name)
    setFBots((row.bots || []).join(', '))
    setFBrokerNotes((row.broker_notes || []).join('\n'))
    setFGroupNotes((row.group_notes || []).join('\n'))
    setFOrder(row.sort_order ?? 0); setModalError('')
    setModal({ mode: 'edit', row })
  }

  function parseList(str) {
    return str.split('\n').map(s => s.trim()).filter(Boolean)
  }

  async function handleSave() {
    const b = fBroker.trim()
    if (!b) { setModalError('Broker name is required'); return }
    setSaving(true); setModalError('')
    const payload = {
      country_group: fGroup,
      broker_name: b,
      bots: fBots.split(',').map(s => s.trim()).filter(Boolean),
      broker_notes: parseList(fBrokerNotes),
      group_notes: parseList(fGroupNotes),
      sort_order: fOrder,
    }
    try {
      if (modal.mode === 'add') {
        await apiFetch('/knowledge/country-offers', { method: 'POST', body: JSON.stringify(payload) })
      } else {
        await apiFetch(`/knowledge/country-offers/${modal.row.id}`, { method: 'PUT', body: JSON.stringify(payload) })
      }
      setModal(null); await load()
    } catch (e) { setModalError(e.message) }
    finally { setSaving(false) }
  }

  async function handleToggle(row) {
    try {
      await apiFetch(`/knowledge/country-offers/${row.id}`, { method: 'PUT', body: JSON.stringify({ active: !row.active }) })
      await load()
    } catch (e) { alert(e.message) }
  }

  async function handleDelete(row) {
    if (!confirm(`Delete ${row.country_group} / ${row.broker_name}?`)) return
    try { await apiFetch(`/knowledge/country-offers/${row.id}`, { method: 'DELETE' }); await load() }
    catch (e) { alert(e.message) }
  }

  return (
    <div className="tab-content">
      <div className="tab-toolbar">
        <span className="row-count">{rows.length} entries</span>
        <button className="btn-primary" onClick={openAdd}>+ Add Entry</button>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}
      {!loading && !fetchError && rows.length === 0 && (
        <p className="status-msg">No country offers yet.</p>
      )}

      {rows.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Country</th>
              <th>Broker</th>
              <th>Bots</th>
              <th>Broker Notes</th>
              <th>Group Notes</th>
              <th>Order</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.id} className={row.active ? '' : 'row-inactive'}>
                <td>{row.country_group}</td>
                <td>{row.broker_name}</td>
                <td className="cell-truncate">{(row.bots || []).join(', ')}</td>
                <td className="cell-truncate">{(row.broker_notes || []).join('; ')}</td>
                <td className="cell-truncate">{(row.group_notes || []).join('; ')}</td>
                <td>{row.sort_order}</td>
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
          title={modal.mode === 'add' ? 'Add Country Entry' : 'Edit Country Entry'}
          onSave={handleSave}
          onClose={() => setModal(null)}
          saving={saving}
          error={modalError}
          fields={
            <>
              <div className="field">
                <label>Country Group</label>
                <select value={fGroup} onChange={e => { setFGroup(e.target.value); setModalError('') }}>
                  {COUNTRY_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Broker Name</label>
                <input type="text" value={fBroker} onChange={e => { setFBroker(e.target.value); setModalError('') }} placeholder="e.g. Vantage" autoFocus />
              </div>
              <div className="field">
                <label>Bots <span className="label-hint">(comma-separated)</span></label>
                <input type="text" value={fBots} onChange={e => { setFBots(e.target.value); setModalError('') }} placeholder="e.g. Gold, Crypto" />
              </div>
              <div className="field">
                <label>Broker Notes <span className="label-hint">(one per line)</span></label>
                <textarea value={fBrokerNotes} onChange={e => { setFBrokerNotes(e.target.value); setModalError('') }} rows={3} placeholder="e.g. Gold/Silver only in cents" />
              </div>
              <div className="field">
                <label>Group Notes <span className="label-hint">(one per line, shown for all brokers in this country)</span></label>
                <textarea value={fGroupNotes} onChange={e => { setFGroupNotes(e.target.value); setModalError('') }} rows={3} />
              </div>
              <div className="field">
                <label>Sort order <span className="label-hint">(lower = first)</span></label>
                <input type="number" value={fOrder} onChange={e => { setFOrder(Number(e.target.value)); setModalError('') }} min={0} />
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
        <button className={`tab-btn ${tab === 'qa'      ? 'active' : ''}`} onClick={() => setTab('qa')}>Knowledge Base</button>
        <button className={`tab-btn ${tab === 'handoff' ? 'active' : ''}`} onClick={() => setTab('handoff')}>Handoff Rules</button>
        <button className={`tab-btn ${tab === 'brokers' ? 'active' : ''}`} onClick={() => setTab('brokers')}>Broker Links</button>
        <button className={`tab-btn ${tab === 'country' ? 'active' : ''}`} onClick={() => setTab('country')}>Country Offers</button>
      </nav>

      {tab === 'qa'      && <QATab />}
      {tab === 'handoff' && <HandoffTab />}
      {tab === 'brokers' && <BrokerAssetsTab />}
      {tab === 'country' && <CountryOffersTab />}
    </div>
  )
}

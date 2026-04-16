import { useState, useEffect, useCallback } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const API_KEY  = import.meta.env.VITE_DASHBOARD_API_KEY || ''
const PASSWORD = import.meta.env.VITE_DASHBOARD_PASSWORD || ''

const PURPOSES    = ['registration', 'copy_trade_open_account', 'copy_trade_connect', 'copy_trade_start']
const ASSET_TYPES = ['link', 'video']

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

function downloadJsonFile(filename, payload) {
  const json = JSON.stringify(payload, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

// ─── Auth gate ────────────────────────────────────────────────────────────────

function AuthGate({ onAuth }) {
  const [input, setInput] = useState('')
  const [error, setError] = useState('')

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
  const [text, setText]         = useState('')
  const [phase, setPhase]       = useState('input')
  const [error, setError]       = useState('')
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

    const valid   = raw.map(parseRow).filter(Boolean)
    const skipped = raw.length - valid.length

    if (valid.length === 0) {
      setError(`No valid rows found (${skipped} skipped). Check the format.`)
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
          {phase !== 'importing' && <button className="modal-close" onClick={onClose}>✕</button>}
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
              <button className="btn-primary" onClick={handleImport} disabled={!text.trim()}>Import</button>
            </div>
          </>
        )}

        {phase === 'importing' && (
          <div className="bulk-progress">
            <p>Importing {progress.done} of {progress.total}…</p>
            <div className="progress-bar-wrap">
              <div className="progress-bar-fill" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
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

// ─── Hint ─────────────────────────────────────────────────────────────────────

function Hint({ text }) {
  return (
    <span className="label-hint" title={text} style={{ cursor: 'help', marginLeft: 5 }}>(?)</span>
  )
}

// ─── QA Tab ───────────────────────────────────────────────────────────────────

function QATab() {
  const [rows, setRows]             = useState([])
  const [loading, setLoading]       = useState(true)
  const [fetchError, setFetch]      = useState('')
  const [modal, setModal]           = useState(null)
  const [question, setQuestion]     = useState('')
  const [answer, setAnswer]         = useState('')
  const [saving, setSaving]         = useState(false)
  const [modalError, setModalError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')
  const [search, setSearch]         = useState('')
  const [showBulk, setShowBulk]     = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setFetch('')
    try { setRows(await apiFetch('/knowledge/qa')) }
    catch (e) { setFetch(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = search.trim()
    ? rows.filter(r =>
        r.question.toLowerCase().includes(search.toLowerCase()) ||
        r.answer.toLowerCase().includes(search.toLowerCase())
      )
    : rows

  function openAdd() { setQuestion(''); setAnswer(''); setModalError(''); setModal({ mode: 'add' }) }
  function openEdit(row) { setQuestion(row.question); setAnswer(row.answer); setModalError(''); setModal({ mode: 'edit', row }) }
  function closeModal() { setModal(null) }

  function showSuccess(msg) {
    setSuccessMsg(msg)
    setTimeout(() => setSuccessMsg(''), 3000)
  }

  async function handleSave() {
    const q = question.trim(), a = answer.trim()
    if (q.length < 10) { setModalError('Question must be at least 10 characters'); return }
    if (a.length < 10) { setModalError('Answer must be at least 10 characters'); return }
    setSaving(true); setModalError('')
    try {
      if (modal.mode === 'add') {
        await apiFetch('/knowledge/qa', { method: 'POST', body: JSON.stringify({ question: q, answer: a }) })
        showSuccess('Question added successfully')
      } else {
        await apiFetch(`/knowledge/qa/${modal.row.id}`, { method: 'PUT', body: JSON.stringify({ question: q, answer: a }) })
        showSuccess('Question updated successfully')
      }
      closeModal(); await load()
    } catch (e) { setModalError(e.message) }
    finally { setSaving(false) }
  }

  async function handleToggle(row) {
    try {
      await apiFetch(`/knowledge/qa/${row.id}`, { method: 'PUT', body: JSON.stringify({ active: !row.active }) })
      await load()
      showSuccess(row.active ? 'Question deactivated' : 'Question activated')
    }
    catch (e) { alert(e.message) }
  }

  async function handleDelete(row) {
    if (!confirm(`Delete this Q&A pair?\n\n"${row.question.slice(0, 80)}"`)) return
    try {
      await apiFetch(`/knowledge/qa/${row.id}`, { method: 'DELETE' })
      await load()
      showSuccess('Question deleted')
    }
    catch (e) { alert(e.message) }
  }

  function parseQARow(r) {
    const q = (r.question || '').trim(), a = (r.answer || '').trim()
    if (q.length < 10 || a.length < 10) return null
    return { question: q, answer: a }
  }

  return (
    <div className="tab-content">
      <div className="search-bar">
        <input className="search-input" type="text" placeholder="Search questions or answers…" value={search} onChange={e => setSearch(e.target.value)} />
        {search && <button className="search-clear" onClick={() => setSearch('')} title="Clear">×</button>}
      </div>
      <div className="tab-toolbar">
        <span className="row-count">{search.trim() ? `${filtered.length} of ${rows.length} entries` : `${rows.length} entries`}</span>
        <div className="toolbar-actions">
          <button className="btn-outline" onClick={() => setShowBulk(true)}>Bulk Import</button>
          <button className="btn-primary" onClick={openAdd}>+ Add Question</button>
        </div>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}
      {successMsg && <p className="status-msg success">{successMsg}</p>}
      {!loading && !fetchError && rows.length === 0 && <p className="status-msg">No Q&A pairs yet.</p>}
      {!loading && !fetchError && rows.length > 0 && filtered.length === 0 && <p className="status-msg">No matches for "{search}".</p>}

      {filtered.length > 0 && (
        <table className="data-table">
          <thead><tr><th>Question</th><th>Answer</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {filtered.map(row => (
              <tr key={row.id} className={row.active ? '' : 'row-inactive'}>
                <td className="cell-truncate">{row.question}</td>
                <td className="cell-truncate">{row.answer}</td>
                <td><span className={`badge ${row.active ? 'badge-active' : 'badge-inactive'}`}>{row.active ? 'Active' : 'Inactive'}</span></td>
                <td className="cell-actions">
                  <button className="btn-icon" title="Edit" onClick={() => openEdit(row)}>✏️</button>
                  <button className="btn-icon" title={row.active ? 'Deactivate' : 'Activate'} onClick={() => handleToggle(row)}>{row.active ? '🔴' : '🟢'}</button>
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
          onSave={handleSave} onClose={closeModal} saving={saving} error={modalError}
          fields={
            <>
              <div className="field"><label>Question</label>
                <input type="text" value={question} onChange={e => { setQuestion(e.target.value); setModalError('') }} placeholder="e.g. What is the minimum deposit?" autoFocus />
              </div>
              <div className="field"><label>Answer</label>
                <textarea value={answer} onChange={e => { setAnswer(e.target.value); setModalError('') }} placeholder="The full answer the bot will use…" rows={5} />
              </div>
            </>
          }
        />
      )}

      {showBulk && (
        <BulkImportModal
          title="Bulk Import Q&A Pairs"
          hint='Paste a JSON array. Each item must have "question" and "answer" (min 10 chars each).'
          placeholder={'[\n  { "question": "What is the minimum deposit?", "answer": "The minimum deposit is $500." }\n]'}
          parseRow={parseQARow} endpoint="/knowledge/qa" onDone={load} onClose={() => setShowBulk(false)}
        />
      )}
    </div>
  )
}

// ─── Handoff Tab ──────────────────────────────────────────────────────────────

const DEFAULT_RESPONSE = 'Please wait one sec'

function HandoffTab() {
  const [rows, setRows]             = useState([])
  const [loading, setLoading]       = useState(true)
  const [fetchError, setFetch]      = useState('')
  const [modal, setModal]           = useState(null)
  const [scenario, setScenario]     = useState('')
  const [defResp, setDefResp]       = useState(DEFAULT_RESPONSE)
  const [saving, setSaving]         = useState(false)
  const [modalError, setModalError] = useState('')
  const [search, setSearch]         = useState('')
  const [showBulk, setShowBulk]     = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setFetch('')
    try { setRows(await apiFetch('/knowledge/handoff')) }
    catch (e) { setFetch(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = search.trim()
    ? rows.filter(r => r.scenario.toLowerCase().includes(search.toLowerCase()))
    : rows

  function openAdd() { setScenario(''); setDefResp(DEFAULT_RESPONSE); setModalError(''); setModal({ mode: 'add' }) }
  function openEdit(row) { setScenario(row.scenario); setDefResp(row.default_response); setModalError(''); setModal({ mode: 'edit', row }) }
  function closeModal() { setModal(null) }

  async function handleSave() {
    const s = scenario.trim(), d = defResp.trim()
    if (s.length < 10) { setModalError('Scenario must be at least 10 characters'); return }
    if (!d) { setModalError('Default response cannot be empty'); return }
    setSaving(true); setModalError('')
    try {
      if (modal.mode === 'add') {
        await apiFetch('/knowledge/handoff', { method: 'POST', body: JSON.stringify({ scenario: s, default_response: d }) })
      } else {
        await apiFetch(`/knowledge/handoff/${modal.row.id}`, { method: 'PUT', body: JSON.stringify({ scenario: s, default_response: d }) })
      }
      closeModal(); await load()
    } catch (e) { setModalError(e.message) }
    finally { setSaving(false) }
  }

  async function handleToggle(row) {
    try { await apiFetch(`/knowledge/handoff/${row.id}`, { method: 'PUT', body: JSON.stringify({ active: !row.active }) }); await load() }
    catch (e) { alert(e.message) }
  }

  async function handleDelete(row) {
    if (!confirm(`Delete this handoff rule?\n\n"${row.scenario.slice(0, 80)}"`)) return
    try { await apiFetch(`/knowledge/handoff/${row.id}`, { method: 'DELETE' }); await load() }
    catch (e) { alert(e.message) }
  }

  function parseHandoffRow(r) {
    const s = (r.scenario || '').trim()
    if (s.length < 10) return null
    return { scenario: s, default_response: (r.default_response || DEFAULT_RESPONSE).trim() }
  }

  return (
    <div className="tab-content">
      <div className="search-bar">
        <input className="search-input" type="text" placeholder="Search scenarios…" value={search} onChange={e => setSearch(e.target.value)} />
        {search && <button className="search-clear" onClick={() => setSearch('')} title="Clear">×</button>}
      </div>
      <div className="tab-toolbar">
        <span className="row-count">{search.trim() ? `${filtered.length} of ${rows.length} rules` : `${rows.length} rules`}</span>
        <div className="toolbar-actions">
          <button className="btn-outline" onClick={() => setShowBulk(true)}>Bulk Import</button>
          <button className="btn-primary" onClick={openAdd}>+ Add Handoff Rule</button>
        </div>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}
      {!loading && !fetchError && rows.length === 0 && <p className="status-msg">No handoff rules yet.</p>}
      {!loading && !fetchError && rows.length > 0 && filtered.length === 0 && <p className="status-msg">No matches for "{search}".</p>}

      {filtered.length > 0 && (
        <table className="data-table">
          <thead><tr><th>Scenario</th><th>Default Response</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {filtered.map(row => (
              <tr key={row.id} className={row.active ? '' : 'row-inactive'}>
                <td className="cell-truncate">{row.scenario}</td>
                <td className="cell-truncate">{row.default_response}</td>
                <td><span className={`badge ${row.active ? 'badge-active' : 'badge-inactive'}`}>{row.active ? 'Active' : 'Inactive'}</span></td>
                <td className="cell-actions">
                  <button className="btn-icon" title="Edit" onClick={() => openEdit(row)}>✏️</button>
                  <button className="btn-icon" title={row.active ? 'Deactivate' : 'Activate'} onClick={() => handleToggle(row)}>{row.active ? '🔴' : '🟢'}</button>
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
          onSave={handleSave} onClose={closeModal} saving={saving} error={modalError}
          fields={
            <>
              <div className="field"><label>Scenario</label>
                <textarea value={scenario} onChange={e => { setScenario(e.target.value); setModalError('') }}
                  placeholder="Describe when the bot should hand off to a human" rows={4} autoFocus />
              </div>
              <div className="field">
                <label>Default Response <span className="label-hint">(sent to user before handoff)</span></label>
                <input type="text" value={defResp} onChange={e => { setDefResp(e.target.value); setModalError('') }} />
              </div>
            </>
          }
        />
      )}

      {showBulk && (
        <BulkImportModal
          title="Bulk Import Handoff Rules"
          hint='Paste a JSON array. Each item must have "scenario" (min 10 chars). "default_response" is optional.'
          placeholder={'[\n  { "scenario": "User asks about a withdrawal problem or payment issue" }\n]'}
          parseRow={parseHandoffRow} endpoint="/knowledge/handoff" onDone={load} onClose={() => setShowBulk(false)}
        />
      )}
    </div>
  )
}

// ─── Broker Assets Tab ────────────────────────────────────────────────────────

function BrokerAssetsTab() {
  const [rows, setRows]             = useState([])
  const [loading, setLoading]       = useState(true)
  const [fetchError, setFetch]      = useState('')
  const [modal, setModal]           = useState(null)
  const [saving, setSaving]         = useState(false)
  const [modalError, setModalError] = useState('')
  const [search, setSearch]         = useState('')
  const [filterBroker, setFilterBroker]   = useState('all')
  const [filterPurpose, setFilterPurpose] = useState('all')
  const [filterType, setFilterType]       = useState('all')
  const [filterBot, setFilterBot]         = useState('all')
  const [brokerOptions, setBrokerOptions] = useState([])

  const [fBroker, setFBroker]       = useState('')
  const [fPurpose, setFPurpose]     = useState('registration')
  const [fAssetType, setFAssetType] = useState('link')
  const [fTitle, setFTitle]         = useState('')
  const [fUrl, setFUrl]             = useState('')
  const [fBot, setFBot]             = useState('')
  const [fOrder, setFOrder]         = useState(0)
  const [botOptions, setBotOptions] = useState([])

  const load = useCallback(async () => {
    setLoading(true); setFetch('')
    try { setRows(await apiFetch('/knowledge/broker-assets')) }
    catch (e) { setFetch(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    Promise.all([
      apiFetch('/knowledge/brokers'),
      apiFetch('/knowledge/bots'),
    ]).then(([brokers, bots]) => {
      const active = (brokers || []).filter(b => b.active)
      setBrokerOptions(active)
      if (active.length > 0) setFBroker(active[0].broker_id)
      setBotOptions((bots || []).filter(b => b.active))
    }).catch(() => {})
  }, [])

  const filtered = rows.filter(r => {
    const matchesBroker  = filterBroker  === 'all' || r.broker      === filterBroker
    const matchesPurpose = filterPurpose === 'all' || r.purpose     === filterPurpose
    const matchesType    = filterType    === 'all' || r.asset_type  === filterType
    const matchesBot     = filterBot     === 'all' || (filterBot === '_generic' ? !r.bot : r.bot === filterBot)
    const matchesSearch  = !search.trim() ||
      r.title.toLowerCase().includes(search.toLowerCase()) ||
      r.url.toLowerCase().includes(search.toLowerCase())
    return matchesBroker && matchesPurpose && matchesType && matchesBot && matchesSearch
  })

  function openAdd() {
    const first = brokerOptions[0]?.broker_id || ''
    setFBroker(first); setFPurpose('registration'); setFAssetType('link')
    setFTitle(''); setFUrl(''); setFBot(''); setFOrder(0); setModalError('')
    setModal({ mode: 'add' })
  }

  function openEdit(row) {
    setFBroker(row.broker); setFPurpose(row.purpose); setFAssetType(row.asset_type)
    setFTitle(row.title); setFUrl(row.url); setFBot(row.bot || ''); setFOrder(row.sort_order ?? 0); setModalError('')
    setModal({ mode: 'edit', row })
  }

  async function handleSave() {
    const t = fTitle.trim(), u = fUrl.trim()
    if (!t) { setModalError('Title is required'); return }
    if (!u) { setModalError('URL is required'); return }
    setSaving(true); setModalError('')
    const payload = { broker: fBroker, purpose: fPurpose, asset_type: fAssetType, title: t, url: u, bot: fBot.trim() || null, sort_order: fOrder }
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
    try { await apiFetch(`/knowledge/broker-assets/${row.id}`, { method: 'PUT', body: JSON.stringify({ active: !row.active }) }); await load() }
    catch (e) { alert(e.message) }
  }

  async function handleDelete(row) {
    if (!confirm(`Delete "${row.title}"?`)) return
    try { await apiFetch(`/knowledge/broker-assets/${row.id}`, { method: 'DELETE' }); await load() }
    catch (e) { alert(e.message) }
  }

  const uniqueBrokers = [...new Set(rows.map(r => r.broker))]

  return (
    <div className="tab-content">
      <div className="search-bar">
        <input className="search-input" type="text" placeholder="Search title or URL…" value={search} onChange={e => setSearch(e.target.value)} />
        {search && <button className="search-clear" onClick={() => setSearch('')} title="Clear">×</button>}
      </div>
      <div className="tab-toolbar">
        <div className="toolbar-filters">
          <select value={filterBroker} onChange={e => setFilterBroker(e.target.value)}>
            <option value="all">All brokers</option>
            {uniqueBrokers.map(b => <option key={b} value={b}>{b}</option>)}
          </select>
          <select value={filterPurpose} onChange={e => setFilterPurpose(e.target.value)}>
            <option value="all">All purposes</option>
            {PURPOSES.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <select value={filterType} onChange={e => setFilterType(e.target.value)}>
            <option value="all">All types</option>
            {ASSET_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={filterBot} onChange={e => setFilterBot(e.target.value)}>
            <option value="all">All bots</option>
            <option value="_generic">Generic (no bot)</option>
            {botOptions.map(b => <option key={b.id} value={b.name}>{b.name}</option>)}
          </select>
          <span className="row-count">{filtered.length} of {rows.length} assets</span>
        </div>
        <button className="btn-primary" onClick={openAdd}>+ Add Asset</button>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}
      {!loading && !fetchError && rows.length === 0 && <p className="status-msg">No broker assets yet.</p>}

      {filtered.length > 0 && (
        <table className="data-table">
          <thead>
            <tr><th>Broker</th><th>Purpose</th><th>Type</th><th>Bot</th><th>Title</th><th>URL</th><th>Order</th><th>Status</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {filtered.map(row => (
              <tr key={row.id} className={row.active ? '' : 'row-inactive'}>
                <td>{row.broker}</td>
                <td>{row.purpose}</td>
                <td>{row.asset_type}</td>
                <td>{row.bot || <span style={{color:'#999',fontStyle:'italic'}}>all</span>}</td>
                <td className="cell-truncate">{row.title}</td>
                <td className="cell-truncate"><a href={row.url} target="_blank" rel="noreferrer">{row.url}</a></td>
                <td>{row.sort_order}</td>
                <td><span className={`badge ${row.active ? 'badge-active' : 'badge-inactive'}`}>{row.active ? 'Active' : 'Inactive'}</span></td>
                <td className="cell-actions">
                  <button className="btn-icon" title="Edit" onClick={() => openEdit(row)}>✏️</button>
                  <button className="btn-icon" title={row.active ? 'Deactivate' : 'Activate'} onClick={() => handleToggle(row)}>{row.active ? '🔴' : '🟢'}</button>
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
          onSave={handleSave} onClose={() => setModal(null)} saving={saving} error={modalError}
          fields={
            <>
              <div className="field"><label>Broker</label>
                <select value={fBroker} onChange={e => { setFBroker(e.target.value); setModalError('') }}>
                  {brokerOptions.map(b => <option key={b.id} value={b.broker_id}>{b.display_name}</option>)}
                </select>
              </div>
              <div className="field"><label>Purpose</label>
                <select value={fPurpose} onChange={e => { setFPurpose(e.target.value); setModalError('') }}>
                  {PURPOSES.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div className="field"><label>Type</label>
                <select value={fAssetType} onChange={e => { setFAssetType(e.target.value); setModalError('') }}>
                  {ASSET_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="field">
                <label>
                  Bot
                  <Hint text="Leave blank if this link/video applies to all bots (e.g. registration links). Set to a specific bot (e.g. Bronze) if it only applies to that bot's copy trade setup." />
                  <span className="label-hint"> (optional)</span>
                </label>
                <select value={fBot} onChange={e => { setFBot(e.target.value); setModalError('') }}>
                  <option value="">— all bots (generic) —</option>
                  {botOptions.map(b => <option key={b.id} value={b.name}>{b.name}</option>)}
                </select>
              </div>
              <div className="field"><label>Title</label>
                <input type="text" value={fTitle} onChange={e => { setFTitle(e.target.value); setModalError('') }} placeholder="e.g. Bybit sign up link" autoFocus />
              </div>
              <div className="field"><label>URL</label>
                <input type="text" value={fUrl} onChange={e => { setFUrl(e.target.value); setModalError('') }} placeholder="https://…" />
              </div>
              <div className="field">
                <label>
                  Sort order
                  <Hint text="Controls which asset appears first when there are multiple of the same type for the same broker + purpose. 0 = first, 1 = second, and so on." />
                </label>
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
  const [search, setSearch]         = useState('')
  const [filterCountry, setFilterCountry] = useState('all')
  const [filterBroker, setFilterBroker]   = useState('all')
  const [filterBot, setFilterBot]         = useState('all')

  const [brokerOptions, setBrokerOptions]           = useState([])
  const [countryGroupOptions, setCountryGroupOptions] = useState([])
  const [botOptions, setBotOptions]                 = useState([])

  const [fGroup, setFGroup]               = useState('')
  const [fBroker, setFBroker]             = useState('')
  const [fSelectedBots, setFSelectedBots] = useState([])
  const [fBrokerNotes, setFBrokerNotes]   = useState('')
  const [fGroupNotes, setFGroupNotes]     = useState('')
  const [fOrder, setFOrder]               = useState(0)

  const load = useCallback(async () => {
    setLoading(true); setFetch('')
    try { setRows(await apiFetch('/knowledge/country-offers')) }
    catch (e) { setFetch(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    Promise.all([
      apiFetch('/knowledge/brokers'),
      apiFetch('/knowledge/country-groups'),
      apiFetch('/knowledge/bots'),
    ]).then(([b, cg, bo]) => {
      const activeBrokers = (b || []).filter(x => x.active)
      const activeGroups  = (cg || []).filter(x => x.active)
      setBrokerOptions(activeBrokers)
      setCountryGroupOptions(activeGroups)
      setBotOptions((bo || []).filter(x => x.active))
      if (activeGroups.length > 0) setFGroup(activeGroups[0].name)
      if (activeBrokers.length > 0) setFBroker(activeBrokers[0].display_name)
    }).catch(() => {})
  }, [])

  const filtered = rows.filter(r => {
    const matchesCountry = filterCountry === 'all' || r.country_group === filterCountry
    const matchesBroker  = filterBroker  === 'all' || r.broker_name  === filterBroker
    const matchesBot     = filterBot     === 'all' || (r.bots || []).includes(filterBot)
    const matchesSearch  = !search.trim() ||
      r.country_group.toLowerCase().includes(search.toLowerCase()) ||
      r.broker_name.toLowerCase().includes(search.toLowerCase()) ||
      (r.bots || []).some(b => b.toLowerCase().includes(search.toLowerCase()))
    return matchesCountry && matchesBroker && matchesBot && matchesSearch
  })

  function toggleBot(botName) {
    setFSelectedBots(prev =>
      prev.includes(botName) ? prev.filter(b => b !== botName) : [...prev, botName]
    )
  }

  function openAdd() {
    setFGroup(countryGroupOptions[0]?.name || '')
    setFBroker(brokerOptions[0]?.display_name || '')
    setFSelectedBots([]); setFBrokerNotes(''); setFGroupNotes(''); setFOrder(0); setModalError('')
    setModal({ mode: 'add' })
  }

  function openEdit(row) {
    setFGroup(row.country_group); setFBroker(row.broker_name)
    setFSelectedBots(row.bots || [])
    setFBrokerNotes((row.broker_notes || []).join('\n'))
    setFGroupNotes((row.group_notes || []).join('\n'))
    setFOrder(row.sort_order ?? 0); setModalError('')
    setModal({ mode: 'edit', row })
  }

  function parseNotes(str) { return str.split('\n').map(s => s.trim()).filter(Boolean) }

  async function handleSave() {
    if (!fGroup)                { setModalError('Country group is required'); return }
    if (!fBroker.trim())        { setModalError('Broker is required'); return }
    if (fSelectedBots.length === 0) { setModalError('At least one bot must be selected'); return }
    setSaving(true); setModalError('')
    const payload = {
      country_group: fGroup,
      broker_name: fBroker.trim(),
      bots: fSelectedBots,
      broker_notes: parseNotes(fBrokerNotes),
      group_notes: parseNotes(fGroupNotes),
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
    try { await apiFetch(`/knowledge/country-offers/${row.id}`, { method: 'PUT', body: JSON.stringify({ active: !row.active }) }); await load() }
    catch (e) { alert(e.message) }
  }

  async function handleDelete(row) {
    if (!confirm(`Delete ${row.country_group} / ${row.broker_name}?`)) return
    try { await apiFetch(`/knowledge/country-offers/${row.id}`, { method: 'DELETE' }); await load() }
    catch (e) { alert(e.message) }
  }

  const uniqueCountries = [...new Set(rows.map(r => r.country_group))]
  const uniqueBrokers   = [...new Set(rows.map(r => r.broker_name))]

  return (
    <div className="tab-content">
      <div className="search-bar">
        <input className="search-input" type="text" placeholder="Search country, broker or bot…" value={search} onChange={e => setSearch(e.target.value)} />
        {search && <button className="search-clear" onClick={() => setSearch('')} title="Clear">×</button>}
      </div>
      <div className="tab-toolbar">
        <div className="toolbar-filters">
          <select value={filterCountry} onChange={e => setFilterCountry(e.target.value)}>
            <option value="all">All countries</option>
            {uniqueCountries.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={filterBroker} onChange={e => setFilterBroker(e.target.value)}>
            <option value="all">All brokers</option>
            {uniqueBrokers.map(b => <option key={b} value={b}>{b}</option>)}
          </select>
          <select value={filterBot} onChange={e => setFilterBot(e.target.value)}>
            <option value="all">All bots</option>
            {botOptions.map(b => <option key={b.id} value={b.name}>{b.name}</option>)}
          </select>
          <span className="row-count">{filtered.length} of {rows.length} entries</span>
        </div>
        <button className="btn-primary" onClick={openAdd}>+ Add Entry</button>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}
      {!loading && !fetchError && rows.length === 0 && <p className="status-msg">No country offers yet.</p>}

      {filtered.length > 0 && (
        <table className="data-table">
          <thead>
            <tr><th>Country</th><th>Broker</th><th>Bots</th><th>Broker Notes</th><th>Group Notes</th><th>Order</th><th>Status</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {filtered.map(row => (
              <tr key={row.id} className={row.active ? '' : 'row-inactive'}>
                <td>{row.country_group}</td>
                <td>{row.broker_name}</td>
                <td className="cell-truncate">{(row.bots || []).join(', ')}</td>
                <td className="cell-truncate">{(row.broker_notes || []).join('; ')}</td>
                <td className="cell-truncate">{(row.group_notes || []).join('; ')}</td>
                <td>{row.sort_order}</td>
                <td><span className={`badge ${row.active ? 'badge-active' : 'badge-inactive'}`}>{row.active ? 'Active' : 'Inactive'}</span></td>
                <td className="cell-actions">
                  <button className="btn-icon" title="Edit" onClick={() => openEdit(row)}>✏️</button>
                  <button className="btn-icon" title={row.active ? 'Deactivate' : 'Activate'} onClick={() => handleToggle(row)}>{row.active ? '🔴' : '🟢'}</button>
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
          onSave={handleSave} onClose={() => setModal(null)} saving={saving} error={modalError}
          fields={
            <>
              <div className="field"><label>Country Group</label>
                <select value={fGroup} onChange={e => { setFGroup(e.target.value); setModalError('') }}>
                  {countryGroupOptions.map(cg => <option key={cg.id} value={cg.name}>{cg.name}</option>)}
                </select>
              </div>
              <div className="field"><label>Broker</label>
                <select value={fBroker} onChange={e => { setFBroker(e.target.value); setModalError('') }}>
                  {brokerOptions.map(b => <option key={b.id} value={b.display_name}>{b.display_name}</option>)}
                </select>
              </div>
              <div className="field">
                <label>Bots <span className="label-hint">(select all that this broker supports in this country)</span></label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 6 }}>
                  {botOptions.map(bot => (
                    <label key={bot.id} style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
                      <input type="checkbox" checked={fSelectedBots.includes(bot.name)} onChange={() => toggleBot(bot.name)} />
                      {bot.name}
                    </label>
                  ))}
                </div>
              </div>
              <div className="field">
                <label>
                  Broker Notes
                  <Hint text="Notes specific to this broker in this country — e.g. account limits or restrictions. The agent mentions these when discussing this broker." />
                  <span className="label-hint"> (one per line)</span>
                </label>
                <textarea value={fBrokerNotes} onChange={e => { setFBrokerNotes(e.target.value); setModalError('') }} rows={3} placeholder="e.g. Gold/Silver only in cents; $500–$10,000 USD only" />
              </div>
              <div className="field">
                <label>
                  Group Notes
                  <Hint text="Notes shown for the entire country group regardless of which broker is selected — e.g. a warning that applies to all brokers in this country." />
                  <span className="label-hint"> (one per line)</span>
                </label>
                <textarea value={fGroupNotes} onChange={e => { setFGroupNotes(e.target.value); setModalError('') }} rows={3} />
              </div>
              <div className="field">
                <label>
                  Sort order
                  <Hint text="Controls the order brokers appear for this country. 0 = first broker shown to the agent, 1 = second, and so on." />
                </label>
                <input type="number" value={fOrder} onChange={e => { setFOrder(Number(e.target.value)); setModalError('') }} min={0} />
              </div>
            </>
          }
        />
      )}
    </div>
  )
}

// ─── Brokers Tab ──────────────────────────────────────────────────────────────

function BrokersTab() {
  const [rows, setRows]             = useState([])
  const [loading, setLoading]       = useState(true)
  const [fetchError, setFetch]      = useState('')
  const [modal, setModal]           = useState(null)
  const [saving, setSaving]         = useState(false)
  const [modalError, setModalError] = useState('')
  const [search, setSearch]         = useState('')

  const [fBrokerId, setFBrokerId]       = useState('')
  const [fDisplayName, setFDisplayName] = useState('')
  const [fAliases, setFAliases]         = useState('')

  const load = useCallback(async () => {
    setLoading(true); setFetch('')
    try { setRows(await apiFetch('/knowledge/brokers')) }
    catch (e) { setFetch(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  function openAdd() { setFBrokerId(''); setFDisplayName(''); setFAliases(''); setModalError(''); setModal({ mode: 'add' }) }
  function openEdit(row) {
    setFBrokerId(row.broker_id); setFDisplayName(row.display_name)
    setFAliases((row.aliases || []).join(', ')); setModalError('')
    setModal({ mode: 'edit', row })
  }

  async function handleSave() {
    const id = fBrokerId.trim(), name = fDisplayName.trim()
    if (modal.mode === 'add' && !id) { setModalError('Broker ID is required'); return }
    if (!name) { setModalError('Display name is required'); return }
    setSaving(true); setModalError('')
    const aliases = fAliases.split(',').map(s => s.trim().toLowerCase()).filter(Boolean)
    const payload = modal.mode === 'add'
      ? { broker_id: id, display_name: name, aliases }
      : { display_name: name, aliases }
    try {
      if (modal.mode === 'add') {
        await apiFetch('/knowledge/brokers', { method: 'POST', body: JSON.stringify(payload) })
      } else {
        await apiFetch(`/knowledge/brokers/${modal.row.id}`, { method: 'PUT', body: JSON.stringify(payload) })
      }
      setModal(null); await load()
    } catch (e) { setModalError(e.message) }
    finally { setSaving(false) }
  }

  async function handleToggle(row) {
    try { await apiFetch(`/knowledge/brokers/${row.id}`, { method: 'PUT', body: JSON.stringify({ active: !row.active }) }); await load() }
    catch (e) { alert(e.message) }
  }

  async function handleDelete(row) {
    if (!confirm(`Delete broker "${row.display_name}"?`)) return
    try { await apiFetch(`/knowledge/brokers/${row.id}`, { method: 'DELETE' }); await load() }
    catch (e) { alert(e.message) }
  }

  const filtered = search.trim()
    ? rows.filter(r =>
        r.broker_id.toLowerCase().includes(search.toLowerCase()) ||
        r.display_name.toLowerCase().includes(search.toLowerCase()) ||
        (r.aliases || []).some(a => a.toLowerCase().includes(search.toLowerCase()))
      )
    : rows

  return (
    <div className="tab-content">
      <div className="search-bar">
        <input className="search-input" type="text" placeholder="Search brokers…" value={search} onChange={e => setSearch(e.target.value)} />
        {search && <button className="search-clear" onClick={() => setSearch('')} title="Clear">×</button>}
      </div>
      <div className="tab-toolbar">
        <span className="row-count">{search.trim() ? `${filtered.length} of ${rows.length} brokers` : `${rows.length} brokers`}</span>
        <button className="btn-primary" onClick={openAdd}>+ Add Broker</button>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}
      {!loading && !fetchError && rows.length === 0 && <p className="status-msg">No brokers yet.</p>}
      {!loading && !fetchError && rows.length > 0 && filtered.length === 0 && <p className="status-msg">No matches for "{search}".</p>}

      {filtered.length > 0 && (
        <table className="data-table">
          <thead><tr><th>ID (slug)</th><th>Display Name</th><th>Aliases</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {filtered.map(row => (
              <tr key={row.id} className={row.active ? '' : 'row-inactive'}>
                <td><code>{row.broker_id}</code></td>
                <td>{row.display_name}</td>
                <td className="cell-truncate">{(row.aliases || []).join(', ')}</td>
                <td><span className={`badge ${row.active ? 'badge-active' : 'badge-inactive'}`}>{row.active ? 'Active' : 'Inactive'}</span></td>
                <td className="cell-actions">
                  <button className="btn-icon" title="Edit" onClick={() => openEdit(row)}>✏️</button>
                  <button className="btn-icon" title={row.active ? 'Deactivate' : 'Activate'} onClick={() => handleToggle(row)}>{row.active ? '🔴' : '🟢'}</button>
                  <button className="btn-icon" title="Delete" onClick={() => handleDelete(row)}>🗑️</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {modal && (
        <Modal
          title={modal.mode === 'add' ? 'Add Broker' : 'Edit Broker'}
          onSave={handleSave} onClose={() => setModal(null)} saving={saving} error={modalError}
          fields={
            <>
              <div className="field">
                <label>
                  Broker ID (slug)
                  <Hint text='Internal identifier used in Broker Links records. Lowercase with underscores, e.g. "pu_prime". Cannot be changed after creation.' />
                </label>
                {modal.mode === 'add'
                  ? <input type="text" value={fBrokerId} onChange={e => { setFBrokerId(e.target.value); setModalError('') }} placeholder="e.g. pu_prime" autoFocus />
                  : <code style={{ display: 'block', padding: '6px 0', color: '#666' }}>{fBrokerId}</code>
                }
              </div>
              <div className="field"><label>Display Name</label>
                <input type="text" value={fDisplayName} onChange={e => { setFDisplayName(e.target.value); setModalError('') }}
                  placeholder="e.g. PU Prime" autoFocus={modal.mode === 'edit'} />
              </div>
              <div className="field">
                <label>
                  Aliases
                  <Hint text='Comma-separated lowercase names the agent might use when referring to this broker, e.g. "pu prime, puprime, pu-prime". Used so the agent can match the broker name correctly.' />
                </label>
                <input type="text" value={fAliases} onChange={e => { setFAliases(e.target.value); setModalError('') }} placeholder="e.g. pu prime, puprime, pu-prime" />
              </div>
            </>
          }
        />
      )}
    </div>
  )
}

// ─── Countries Tab ────────────────────────────────────────────────────────────

function CountriesTab() {
  const [rows, setRows]             = useState([])
  const [loading, setLoading]       = useState(true)
  const [fetchError, setFetch]      = useState('')
  const [modal, setModal]           = useState(null)
  const [saving, setSaving]         = useState(false)
  const [modalError, setModalError] = useState('')
  const [search, setSearch]         = useState('')

  const [fName, setFName]       = useState('')
  const [fAliases, setFAliases] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setFetch('')
    try { setRows(await apiFetch('/knowledge/country-groups')) }
    catch (e) { setFetch(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  function openAdd() { setFName(''); setFAliases(''); setModalError(''); setModal({ mode: 'add' }) }
  function openEdit(row) {
    setFName(row.name); setFAliases((row.aliases || []).join(', ')); setModalError('')
    setModal({ mode: 'edit', row })
  }

  async function handleSave() {
    const name = fName.trim()
    if (!name) { setModalError('Name is required'); return }
    setSaving(true); setModalError('')
    const aliases = fAliases.split(',').map(s => s.trim().toLowerCase()).filter(Boolean)
    try {
      if (modal.mode === 'add') {
        await apiFetch('/knowledge/country-groups', { method: 'POST', body: JSON.stringify({ name, aliases }) })
      } else {
        await apiFetch(`/knowledge/country-groups/${modal.row.id}`, { method: 'PUT', body: JSON.stringify({ name, aliases }) })
      }
      setModal(null); await load()
    } catch (e) { setModalError(e.message) }
    finally { setSaving(false) }
  }

  async function handleToggle(row) {
    try { await apiFetch(`/knowledge/country-groups/${row.id}`, { method: 'PUT', body: JSON.stringify({ active: !row.active }) }); await load() }
    catch (e) { alert(e.message) }
  }

  async function handleDelete(row) {
    if (!confirm(`Delete country group "${row.name}"?`)) return
    try { await apiFetch(`/knowledge/country-groups/${row.id}`, { method: 'DELETE' }); await load() }
    catch (e) { alert(e.message) }
  }

  const filtered = search.trim()
    ? rows.filter(r =>
        r.name.toLowerCase().includes(search.toLowerCase()) ||
        (r.aliases || []).some(a => a.toLowerCase().includes(search.toLowerCase()))
      )
    : rows

  return (
    <div className="tab-content">
      <div className="search-bar">
        <input className="search-input" type="text" placeholder="Search countries…" value={search} onChange={e => setSearch(e.target.value)} />
        {search && <button className="search-clear" onClick={() => setSearch('')} title="Clear">×</button>}
      </div>
      <div className="tab-toolbar">
        <span className="row-count">{search.trim() ? `${filtered.length} of ${rows.length} country groups` : `${rows.length} country groups`}</span>
        <button className="btn-primary" onClick={openAdd}>+ Add Country</button>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}
      {!loading && !fetchError && rows.length === 0 && <p className="status-msg">No country groups yet.</p>}
      {!loading && !fetchError && rows.length > 0 && filtered.length === 0 && <p className="status-msg">No matches for "{search}".</p>}

      {filtered.length > 0 && (
        <table className="data-table">
          <thead><tr><th>Name</th><th>Aliases</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {filtered.map(row => (
              <tr key={row.id} className={row.active ? '' : 'row-inactive'}>
                <td><strong>{row.name}</strong></td>
                <td className="cell-truncate">{(row.aliases || []).join(', ')}</td>
                <td><span className={`badge ${row.active ? 'badge-active' : 'badge-inactive'}`}>{row.active ? 'Active' : 'Inactive'}</span></td>
                <td className="cell-actions">
                  <button className="btn-icon" title="Edit" onClick={() => openEdit(row)}>✏️</button>
                  <button className="btn-icon" title={row.active ? 'Deactivate' : 'Activate'} onClick={() => handleToggle(row)}>{row.active ? '🔴' : '🟢'}</button>
                  <button className="btn-icon" title="Delete" onClick={() => handleDelete(row)}>🗑️</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {modal && (
        <Modal
          title={modal.mode === 'add' ? 'Add Country Group' : 'Edit Country Group'}
          onSave={handleSave} onClose={() => setModal(null)} saving={saving} error={modalError}
          fields={
            <>
              <div className="field">
                <label>
                  Name
                  <Hint text='The canonical group name used internally, e.g. "UAE". Stored in uppercase. All countries that share the same broker/bot options should use the same group.' />
                </label>
                <input type="text" value={fName} onChange={e => { setFName(e.target.value.toUpperCase()); setModalError('') }} placeholder="e.g. UAE" autoFocus />
              </div>
              <div className="field">
                <label>
                  Aliases
                  <Hint text='Comma-separated lowercase names a user might type when asked their country, e.g. "united arab emirates, uae, ae". The agent uses these to match what the user says to the correct group.' />
                </label>
                <input type="text" value={fAliases} onChange={e => { setFAliases(e.target.value); setModalError('') }} placeholder="e.g. united arab emirates, uae, ae" />
              </div>
            </>
          }
        />
      )}
    </div>
  )
}

// ─── Bots Tab ─────────────────────────────────────────────────────────────────

function BotsTab() {
  const [rows, setRows]             = useState([])
  const [loading, setLoading]       = useState(true)
  const [fetchError, setFetch]      = useState('')
  const [modal, setModal]           = useState(null)
  const [saving, setSaving]         = useState(false)
  const [modalError, setModalError] = useState('')
  const [search, setSearch]         = useState('')
  const [fName, setFName]           = useState('')

  const load = useCallback(async () => {
    setLoading(true); setFetch('')
    try { setRows(await apiFetch('/knowledge/bots')) }
    catch (e) { setFetch(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  function openAdd() { setFName(''); setModalError(''); setModal({ mode: 'add' }) }
  function openEdit(row) { setFName(row.name); setModalError(''); setModal({ mode: 'edit', row }) }

  async function handleSave() {
    const name = fName.trim()
    if (!name) { setModalError('Name is required'); return }
    setSaving(true); setModalError('')
    try {
      if (modal.mode === 'add') {
        await apiFetch('/knowledge/bots', { method: 'POST', body: JSON.stringify({ name }) })
      } else {
        await apiFetch(`/knowledge/bots/${modal.row.id}`, { method: 'PUT', body: JSON.stringify({ name }) })
      }
      setModal(null); await load()
    } catch (e) { setModalError(e.message) }
    finally { setSaving(false) }
  }

  async function handleToggle(row) {
    try { await apiFetch(`/knowledge/bots/${row.id}`, { method: 'PUT', body: JSON.stringify({ active: !row.active }) }); await load() }
    catch (e) { alert(e.message) }
  }

  async function handleDelete(row) {
    if (!confirm(`Delete bot "${row.name}"?`)) return
    try { await apiFetch(`/knowledge/bots/${row.id}`, { method: 'DELETE' }); await load() }
    catch (e) { alert(e.message) }
  }

  const filtered = search.trim()
    ? rows.filter(r => r.name.toLowerCase().includes(search.toLowerCase()))
    : rows

  return (
    <div className="tab-content">
      <div className="search-bar">
        <input className="search-input" type="text" placeholder="Search bots…" value={search} onChange={e => setSearch(e.target.value)} />
        {search && <button className="search-clear" onClick={() => setSearch('')} title="Clear">×</button>}
      </div>
      <div className="tab-toolbar">
        <span className="row-count">{search.trim() ? `${filtered.length} of ${rows.length} bots` : `${rows.length} bots`}</span>
        <button className="btn-primary" onClick={openAdd}>+ Add Bot</button>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}
      {!loading && !fetchError && rows.length === 0 && <p className="status-msg">No bots yet.</p>}
      {!loading && !fetchError && rows.length > 0 && filtered.length === 0 && <p className="status-msg">No matches for "{search}".</p>}

      {filtered.length > 0 && (
        <table className="data-table">
          <thead><tr><th>Bot Name</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {filtered.map(row => (
              <tr key={row.id} className={row.active ? '' : 'row-inactive'}>
                <td>{row.name}</td>
                <td><span className={`badge ${row.active ? 'badge-active' : 'badge-inactive'}`}>{row.active ? 'Active' : 'Inactive'}</span></td>
                <td className="cell-actions">
                  <button className="btn-icon" title="Edit" onClick={() => openEdit(row)}>✏️</button>
                  <button className="btn-icon" title={row.active ? 'Deactivate' : 'Activate'} onClick={() => handleToggle(row)}>{row.active ? '🔴' : '🟢'}</button>
                  <button className="btn-icon" title="Delete" onClick={() => handleDelete(row)}>🗑️</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {modal && (
        <Modal
          title={modal.mode === 'add' ? 'Add Bot' : 'Edit Bot'}
          onSave={handleSave} onClose={() => setModal(null)} saving={saving} error={modalError}
          fields={
            <div className="field">
              <label>Bot Name</label>
              <input type="text" value={fName} onChange={e => { setFName(e.target.value); setModalError('') }} placeholder="e.g. Gold" autoFocus />
            </div>
          }
        />
      )}
    </div>
  )
}

// ─── Threads Tab ──────────────────────────────────────────────────────────────

const EVENT_TYPE_LABEL = {
  user_message:   { icon: '👤', color: '#b45309' },
  message:        { icon: '💬', color: '#1a1a2e' },
  handoff:        { icon: '↪️',  color: '#6d28d9' },
  tool_call:      { icon: '🔧', color: '#0369a1' },
  tool_output:    { icon: '📋', color: '#0891b2' },
  guardrail:      { icon: '🛡️', color: '#15803d' },
  context_update: { icon: '📝', color: '#92400e' },
}

function EventRow({ ev, correction, onCorrectionClick }) {
  const meta      = EVENT_TYPE_LABEL[ev.type] || { icon: '•', color: '#555' }
  const ts        = ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : ''
  const isUser    = ev.type === 'user_message'
  const isCorrect = correction?.feedback_type === 'correction'
  const isPraise  = correction?.feedback_type === 'praise'

  function handleClick() {
    if (correction) { onCorrectionClick(); return }
  }

  return (
    <div
      className="event-row"
      onClick={handleClick}
      style={correction ? {
        background: isCorrect ? '#fef2f2' : '#f0fdf4',
        border: isCorrect ? '1px solid #fca5a5' : '1px solid #86efac',
        borderRadius: 6,
        cursor: 'pointer',
      } : {}}
    >
      <span className="event-icon">{meta.icon}</span>
      <div className="event-body">
        {ev.agent && <span className="event-agent">{ev.agent}</span>}
        {isUser && ev.active_agent && (
          <span className="event-active-agent">Active: {ev.active_agent}</span>
        )}
        {isUser ? (
          <pre className="event-detail">{ev.label}</pre>
        ) : (
          <>
            <span className="event-label" style={{ color: meta.color }}>{ev.label}</span>
            {correction && (
              <span style={{ fontSize: 11, marginLeft: 8, color: isCorrect ? '#dc2626' : '#16a34a', fontWeight: 600 }}>
                {isCorrect ? '✗ correction — click to view' : '✓ good response — click to view'}
              </span>
            )}
            {!correction && ev.detail && <pre className="event-detail">{ev.detail}</pre>}
          </>
        )}
      </div>
      <span className="event-time">{ts}</span>
    </div>
  )
}

function ThreadsTab() {
  const [threads, setThreads]       = useState(null)
  const [selected, setSelected]     = useState(null)
  const [events, setEvents]         = useState(null)
  const [corrMap, setCorrMap]       = useState({})   // event index → correction row
  const [selectedCorr, setSelectedCorr] = useState(null)  // read-only modal
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState('')
  const [filter, setFilter]         = useState('all')  // 'all' | 'correction' | 'praise'

  function loadThreads() {
    setLoading(true); setError('')
    apiFetch('/admin/threads')
      .then(data => { setThreads(data); setLoading(false) })
      .catch(e   => { setError(e.message); setLoading(false) })
  }
  useEffect(() => { loadThreads() }, [])

  async function loadThread(t) {
    setEvents(null); setCorrMap({}); setSelectedCorr(null)
    try {
      // Corrections are now matched and embedded server-side in each event
      const evs = await apiFetch(`/admin/threads/${t.thread_id}`)
      setEvents(evs || [])
      // Build corrMap from embedded corrections for modal lookup
      const map = {}
      ;(evs || []).forEach((ev, i) => { if (ev.correction) map[i] = ev.correction })
      setCorrMap(map)
    } catch (e) { setError(e.message); setEvents([]) }
  }

  function openThread(t) { setSelected(t); loadThread(t) }
  function refreshThread() { if (selected) loadThread(selected) }
  function exportSelectedThread() {
    if (!selected || !events) return
    downloadJsonFile(
      `thread-${selected.thread_id || 'unknown'}-${new Date().toISOString().replace(/[:.]/g, '-')}.json`,
      {
        exported_at: new Date().toISOString(),
        source: 'threads_tab',
        thread: selected,
        events,
      },
    )
  }

  const filteredThreads = (threads || []).filter(t => {
    if (filter === 'correction') return t.has_corrections
    if (filter === 'praise')     return t.has_praise
    return true
  })

  if (selected) {
    return (
      <div className="tab-content">
        <div className="tab-toolbar">
          <button className="btn-secondary" onClick={() => { setSelected(null); setEvents(null); setCorrMap({}); setSelectedCorr(null); loadThreads() }}>
            ← Back to threads
          </button>
          <span style={{ marginLeft: 16, color: '#555', fontSize: 13 }}>
            {selected.phone_number} &nbsp;·&nbsp; {selected.thread_id}
          </span>
          <button className="btn-secondary" style={{ marginLeft: 'auto' }} onClick={refreshThread}>
            ↺ Refresh
          </button>
          <button className="btn-primary" style={{ marginLeft: 8 }} onClick={exportSelectedThread} disabled={!events}>
            Export as JSON
          </button>
        </div>

        {!events && <p style={{ padding: '24px 0', color: '#888' }}>Loading events…</p>}
        {events && events.length === 0 && <p style={{ padding: '24px 0', color: '#888' }}>No events recorded for this thread.</p>}
        {events && events.length > 0 && (
          <div className="event-list">
            {events.map((ev, i) => (
              <EventRow
                key={i}
                ev={ev}
                correction={ev.correction}
                onCorrectionClick={() => setSelectedCorr(ev.correction)}
              />
            ))}
          </div>
        )}

        {/* Read-only feedback modal */}
        {selectedCorr && (
          <div className="modal-overlay" onClick={() => setSelectedCorr(null)}>
            <div className="modal" onClick={e => e.stopPropagation()}>
              <div className="modal-header">
                <h2 style={{ color: selectedCorr.feedback_type === 'praise' ? '#16a34a' : '#dc2626', fontSize: 15 }}>
                  {selectedCorr.feedback_type === 'praise' ? '✓ Good Response' : '✗ Correction'}
                </h2>
                <button className="modal-close" onClick={() => setSelectedCorr(null)}>✕</button>
              </div>

              <div className="field">
                <label style={{ fontSize: 12, color: '#64748b' }}>AI message</label>
                <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 6, padding: '8px 10px', fontSize: 13, color: '#7f1d1d', whiteSpace: 'pre-wrap', maxHeight: 160, overflowY: 'auto' }}>
                  {selectedCorr.original_message}
                </div>
              </div>

              {selectedCorr.feedback_type === 'praise' && (
                <p style={{ color: '#16a34a', fontSize: 13, margin: 0 }}>Marked as a good response by the team.</p>
              )}

              {selectedCorr.feedback_type !== 'praise' && selectedCorr.corrected_message && (
                <div className="field">
                  <label style={{ fontSize: 12, color: '#64748b' }}>Corrected message</label>
                  <div style={{ background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 6, padding: '8px 10px', fontSize: 13, color: '#14532d', whiteSpace: 'pre-wrap', maxHeight: 160, overflowY: 'auto' }}>
                    {selectedCorr.corrected_message}
                  </div>
                </div>
              )}

              {selectedCorr.note && (
                <div className="field">
                  <label style={{ fontSize: 12, color: '#64748b' }}>Note</label>
                  <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 6, padding: '8px 10px', fontSize: 13, color: '#78350f', whiteSpace: 'pre-wrap' }}>
                    {selectedCorr.note}
                  </div>
                </div>
              )}

              <div className="modal-actions">
                <button className="btn-secondary" onClick={() => setSelectedCorr(null)}>Close</button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="tab-content">
      <div className="tab-toolbar">
        <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>Conversation Threads</h2>
        <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
          {[['all', 'All'], ['correction', '✗ Corrections'], ['praise', '✓ Good responses']].map(([k, l]) => (
            <button key={k} className={filter === k ? 'btn-primary' : 'btn-outline'} style={{ fontSize: 12, padding: '4px 10px' }} onClick={() => setFilter(k)}>{l}</button>
          ))}
          <button className="btn-secondary" style={{ fontSize: 12, padding: '4px 10px' }} onClick={loadThreads}>↺ Refresh</button>
        </div>
      </div>
      {loading && <p style={{ color: '#888', padding: '24px 0' }}>Loading…</p>}
      {error   && <p className="field-error">{error}</p>}
      {threads && filteredThreads.length === 0 && <p style={{ color: '#888', padding: '24px 0' }}>No threads match this filter.</p>}
      {filteredThreads.length > 0 && (
        <table className="data-table">
          <thead>
            <tr><th>Thread ID</th><th>Phone</th><th>Last active</th><th>Events</th><th>Status</th><th>Feedback</th><th></th></tr>
          </thead>
          <tbody>
            {filteredThreads.map(t => (
              <tr key={t.thread_id}>
                <td style={{ fontFamily: 'monospace', fontSize: 11, color: '#94a3b8' }}>{t.thread_id || '—'}</td>
                <td>{t.phone_number || '—'}</td>
                <td>{t.last_active ? new Date(t.last_active).toLocaleString() : '—'}</td>
                <td>{t.event_count}</td>
                <td>
                  {t.reset_at
                    ? <span className="badge badge-inactive" title={`Reset on ${new Date(t.reset_at).toLocaleString()}`}>Reset</span>
                    : <span className="badge badge-active">Active</span>}
                </td>
                <td style={{ fontSize: 15, letterSpacing: 2 }}>
                  {t.has_corrections && <span title="Has corrections" style={{ color: '#ef4444' }}>✗</span>}
                  {t.has_praise      && <span title="Has good responses" style={{ color: '#16a34a', marginLeft: t.has_corrections ? 4 : 0 }}>✓</span>}
                  {!t.has_corrections && !t.has_praise && <span style={{ color: '#d1d5db' }}>—</span>}
                </td>
                <td><button className="btn-secondary" onClick={() => openThread(t)}>Review</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ─── Conversations Tab ────────────────────────────────────────────────────────

function ConversationsTab() {
  const [threads, setThreads]           = useState(null)
  const [loadingList, setLoadingList]   = useState(false)
  const [listError, setListError]       = useState('')
  const [filter, setFilter]             = useState('all') // 'all'|'correction'|'praise'|'clean'

  const [selected, setSelected]         = useState(null)
  const [messages, setMessages]         = useState(null)
  const [corrections, setCorrections]   = useState({})  // message_index → correction row
  const [loadingMsgs, setLoadingMsgs]   = useState(false)

  const [correcting, setCorrecting]     = useState(null)
  const [correctedText, setCorrectedText] = useState('')
  const [noteText, setNoteText]         = useState('')
  const [saving, setSaving]             = useState(false)
  const [saveMsg, setSaveMsg]           = useState('')

  const loadList = useCallback(async () => {
    setLoadingList(true); setListError('')
    try { setThreads(await apiFetch('/admin/conversations')) }
    catch (e) { setListError(e.message) }
    finally { setLoadingList(false) }
  }, [])

  useEffect(() => { loadList() }, [loadList])

  async function loadThread(t) {
    setMessages(null); setCorrections({}); setCorrecting(null); setLoadingMsgs(true)
    try {
      const [msgs, corrs] = await Promise.all([
        apiFetch(`/admin/conversations/${t.thread_id}/messages`),
        apiFetch(`/admin/corrections?thread_id=${t.thread_id}`),
      ])
      setMessages(msgs || [])
      // Build content → current message index map so corrections saved with
      // stale Chatwoot IDs (before the input_items index fix) still match.
      const contentToIdx = {}
      for (const msg of (msgs || [])) {
        if (msg.role === 'assistant' && msg.content) contentToIdx[msg.content.trim()] = msg.index
      }
      const map = {}
      for (const c of (corrs || [])) {
        const remapped = c.original_message ? contentToIdx[c.original_message.trim()] : undefined
        map[remapped !== undefined ? remapped : c.message_index] = c
      }
      setCorrections(map)
    } catch { setMessages([]) }
    finally { setLoadingMsgs(false) }
  }

  function openThread(t) { setSelected(t); loadThread(t) }
  function refreshThread() { loadThread(selected) }
  function exportSelectedConversation() {
    if (!selected || !messages) return
    downloadJsonFile(
      `conversation-${selected.thread_id || 'unknown'}-${new Date().toISOString().replace(/[:.]/g, '-')}.json`,
      {
        exported_at: new Date().toISOString(),
        source: 'conversations_tab',
        thread: selected,
        messages,
        corrections: Object.values(corrections),
      },
    )
  }

  function startCorrection(e, msg) {
    e.stopPropagation()
    const existing = corrections[msg.index]
    setCorrectedText(existing?.feedback_type === 'correction' ? (existing.corrected_message || '') : '')
    setNoteText(existing?.feedback_type === 'correction' ? (existing.note || '') : '')
    setSaveMsg('')
    setCorrecting(msg)
  }

  async function saveCorrection() {
    if (!correctedText.trim()) return
    setSaving(true); setSaveMsg('')
    try {
      await apiFetch('/admin/corrections', {
        method: 'POST',
        body: JSON.stringify({
          thread_id: selected.thread_id,
          message_index: correcting.index,
          original_message: correcting.content,
          corrected_message: correctedText.trim(),
          note: noteText.trim() || null,
          feedback_type: 'correction',
        }),
      })
      setCorrections(prev => ({ ...prev, [correcting.index]: { message_index: correcting.index, original_message: correcting.content, corrected_message: correctedText.trim(), note: noteText.trim() || null, feedback_type: 'correction' } }))
      setSaveMsg('Saved!')
      setTimeout(() => setSaveMsg(''), 2500)
    } catch (e) { setSaveMsg('Error: ' + e.message) }
    finally { setSaving(false) }
  }

  async function togglePraise(e, msg) {
    e.stopPropagation()
    const existing = corrections[msg.index]
    if (existing?.feedback_type === 'praise') {
      // Toggle off
      try {
        await apiFetch(`/admin/corrections/${selected.thread_id}/${msg.index}`, { method: 'DELETE' })
        setCorrections(prev => { const n = { ...prev }; delete n[msg.index]; return n })
      } catch {}
      return
    }
    try {
      await apiFetch('/admin/corrections', {
        method: 'POST',
        body: JSON.stringify({ thread_id: selected.thread_id, message_index: msg.index, original_message: msg.content, feedback_type: 'praise' }),
      })
      setCorrections(prev => ({ ...prev, [msg.index]: { message_index: msg.index, original_message: msg.content, feedback_type: 'praise' } }))
      if (correcting?.index === msg.index) setCorrecting(null)
    } catch {}
  }

  const filteredThreads = (threads || []).filter(t => {
    if (filter === 'correction') return t.has_corrections
    if (filter === 'praise')      return t.has_praise
    if (filter === 'clean')       return !t.has_corrections && !t.has_praise
    return true
  })

  // ── Detail view ──────────────────────────────────────────────────────────────
  if (selected) {
    return (
      <div className="tab-content" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div className="tab-toolbar">
          <button className="btn-secondary" onClick={() => { setSelected(null); setCorrecting(null); loadList() }}>← Back</button>
          <span style={{ marginLeft: 16, color: '#555', fontSize: 13 }}>
            {selected.phone_number || 'Unknown'} · {selected.thread_id}
          </span>
          <button className="btn-outline" style={{ marginLeft: 'auto', fontSize: 13 }} onClick={refreshThread} title="Reload messages">
            ↻ Refresh
          </button>
          <button className="btn-primary" style={{ marginLeft: 8 }} onClick={exportSelectedConversation} disabled={!messages}>
            Export as JSON
          </button>
        </div>

        {/* Click on background closes the panel */}
        <div style={{ display: 'flex', flex: 1, gap: 16, overflow: 'hidden', marginTop: 12 }} onClick={() => setCorrecting(null)}>

          {/* Chat column */}
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10, paddingRight: 4 }}>
            {loadingMsgs && <p style={{ color: '#888' }}>Loading…</p>}
            {!loadingMsgs && messages && messages.length === 0 && <p style={{ color: '#888' }}>No messages in this conversation.</p>}
            {messages && messages.map(msg => {
              const isUser     = msg.role === 'user'
              const entry      = corrections[msg.index]
              const isCorrect  = entry?.feedback_type === 'correction'
              const isPraise   = entry?.feedback_type === 'praise'
              const isActive   = correcting?.index === msg.index

              let bg = isUser ? '#2563eb' : '#f1f5f9'
              let border = '2px solid transparent'
              if (!isUser) {
                if (isActive)    { bg = '#fef3c7'; border = '2px solid #f59e0b' }
                else if (isCorrect) { bg = '#fef2f2'; border = '2px solid #fca5a5' }
                else if (isPraise)  { bg = '#f0fdf4'; border = '2px solid #86efac' }
              }

              return (
                <div key={msg.index} style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, maxWidth: '80%' }}>
                    <div
                      onClick={!isUser ? e => startCorrection(e, msg) : undefined}
                      style={{ padding: '10px 14px', borderRadius: isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px', background: bg, color: isUser ? '#fff' : '#1a1a2e', fontSize: 13.5, lineHeight: 1.5, cursor: !isUser ? 'pointer' : 'default', border, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                      title={!isUser ? (isCorrect ? 'Click to edit correction' : 'Click to flag as wrong') : undefined}
                    >
                      {msg.content}
                    </div>
                    {!isUser && (
                      <button
                        onClick={e => togglePraise(e, msg)}
                        title={isPraise ? 'Remove good-response mark' : 'Mark as good response'}
                        style={{ flexShrink: 0, width: 26, height: 26, borderRadius: '50%', border: isPraise ? '2px solid #22c55e' : '2px solid #d1fae5', background: isPraise ? '#22c55e' : '#f0fdf4', color: isPraise ? '#fff' : '#16a34a', fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}
                      >✓</button>
                    )}
                  </div>
                  {!isUser && (isCorrect || isPraise) && (
                    <span style={{ fontSize: 11, marginTop: 3, marginLeft: 4, color: isCorrect ? '#ef4444' : '#16a34a' }}>
                      {isCorrect ? '✗ correction saved' : '✓ good response'}
                    </span>
                  )}
                </div>
              )
            })}
          </div>

          {/* Correction panel — stopPropagation so clicks inside don't close it */}
          {correcting && (
            <div onClick={e => e.stopPropagation()} style={{ width: 340, flexShrink: 0, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: 16, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong style={{ fontSize: 13 }}>Flag AI Message</strong>
                <button className="modal-close" onClick={() => setCorrecting(null)}>✕</button>
              </div>
              <div className="field">
                <label style={{ fontSize: 12, color: '#64748b' }}>Original (AI message)</label>
                <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 6, padding: '8px 10px', fontSize: 13, color: '#7f1d1d', whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 140, overflowY: 'auto' }}>
                  {correcting.content}
                </div>
              </div>
              <div className="field">
                <label style={{ fontSize: 12, color: '#64748b' }}>Corrected message</label>
                <textarea value={correctedText} onChange={e => setCorrectedText(e.target.value)} placeholder="Write the correct response the AI should have given…" rows={5} autoFocus />
              </div>
              <div className="field">
                <label style={{ fontSize: 12, color: '#64748b' }}>Note (optional)</label>
                <textarea value={noteText} onChange={e => setNoteText(e.target.value)} placeholder="What went wrong? Any context for the team…" rows={3} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <button className="btn-primary" onClick={saveCorrection} disabled={saving || !correctedText.trim()} style={{ flex: 1 }}>
                  {saving ? 'Saving…' : 'Save correction'}
                </button>
                {corrections[correcting.index]?.feedback_type === 'correction' && (
                  <button className="btn-secondary" disabled={saving} onClick={async () => {
                    setSaving(true)
                    try {
                      await apiFetch(`/admin/corrections/${selected.thread_id}/${correcting.index}`, { method: 'DELETE' })
                      setCorrections(prev => { const n = { ...prev }; delete n[correcting.index]; return n })
                      setCorrecting(null)
                    } catch (e) { setSaveMsg('Error: ' + e.message) }
                    finally { setSaving(false) }
                  }}>Delete</button>
                )}
                {saveMsg && <span style={{ fontSize: 12, color: saveMsg.startsWith('Error') ? '#dc2626' : '#16a34a' }}>{saveMsg}</span>}
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  // ── List view ────────────────────────────────────────────────────────────────
  const filterOpts = [
    { key: 'all',         label: 'All' },
    { key: 'correction', label: '✗ Corrections' },
    { key: 'praise',      label: '✓ Good responses' },
    { key: 'clean',       label: 'No feedback' },
  ]

  return (
    <div className="tab-content">
      <div className="tab-toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>Conversations</h2>
        <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
          {filterOpts.map(o => (
            <button key={o.key} className={filter === o.key ? 'btn-primary' : 'btn-outline'} style={{ fontSize: 12, padding: '4px 10px' }} onClick={() => setFilter(o.key)}>
              {o.label}
            </button>
          ))}
        </div>
      </div>
      {loadingList && <p style={{ color: '#888', padding: '24px 0' }}>Loading…</p>}
      {listError   && <p className="field-error">{listError}</p>}
      {threads && filteredThreads.length === 0 && <p style={{ color: '#888', padding: '24px 0' }}>No conversations match this filter.</p>}
      {filteredThreads.length > 0 && (
        <table className="data-table">
          <thead>
            <tr><th>#</th><th>Thread ID</th><th>Phone</th><th>Last active</th><th>Messages</th><th>Status</th><th>Feedback</th><th></th></tr>
          </thead>
          <tbody>
            {filteredThreads.map((t, i) => (
              <tr key={t.thread_id}>
                <td style={{ color: '#94a3b8', fontSize: 12 }}>{filteredThreads.length - i}</td>
                <td style={{ fontFamily: 'monospace', fontSize: 11, color: '#94a3b8' }}>{t.thread_id || '—'}</td>
                <td>{t.phone_number || '—'}</td>
                <td>{t.last_active ? new Date(t.last_active).toLocaleString() : '—'}</td>
                <td>{t.message_count ?? '—'}</td>
                <td>
                  {t.reset_at
                    ? <span className="badge badge-inactive" title={`Reset on ${new Date(t.reset_at).toLocaleString()}`}>Reset</span>
                    : <span className="badge badge-active">Active</span>}
                </td>
                <td style={{ fontSize: 15, letterSpacing: 2 }}>
                  {t.has_corrections && <span title="Has corrections" style={{ color: '#ef4444' }}>✗</span>}
                  {t.has_praise      && <span title="Has good responses" style={{ color: '#16a34a', marginLeft: t.has_corrections ? 4 : 0 }}>✓</span>}
                  {!t.has_corrections && !t.has_praise && <span style={{ color: '#d1d5db' }}>—</span>}
                </td>
                <td><button className="btn-secondary" onClick={() => openThread(t)}>Review</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ─── Results Videos Tab ───────────────────────────────────────────────────────

function ResultsVideosTab() {
  const [rows, setRows]               = useState([])
  const [bots, setBots]               = useState([])
  const [loading, setLoading]         = useState(true)
  const [fetchError, setFetchError]   = useState('')
  const [market, setMarket]           = useState('')
  const [file, setFile]               = useState(null)
  const [uploading, setUploading]     = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [uploadSuccess, setUploadSuccess] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setFetchError('')
    try {
      const [videos, botList] = await Promise.all([
        apiFetch('/knowledge/results-videos'),
        apiFetch('/knowledge/bots'),
      ])
      setRows(videos)
      const activeBots = (botList || []).filter(b => b.active).map(b => b.name.toLowerCase())
      setBots(activeBots)
      if (activeBots.length > 0 && !market) setMarket(activeBots[0])
    }
    catch (e) { setFetchError(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleUpload(e) {
    e.preventDefault()
    if (!file) { setUploadError('Please select a video file.'); return }
    setUploading(true); setUploadError(''); setUploadSuccess('')
    try {
      const fd = new FormData()
      fd.append('market', market)
      fd.append('file', file)
      await fetch(`${API_BASE}/knowledge/results-videos/upload`, {
        method: 'POST',
        headers: { 'x-dashboard-key': API_KEY },
        body: fd,
      }).then(async r => {
        if (!r.ok) throw new Error((await r.text()))
        return r.json()
      })
      setUploadSuccess(`Video for ${market} updated successfully.`)
      setFile(null)
      e.target.reset()
      await load()
    } catch (err) {
      setUploadError(err.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="tab-content">
      <div style={{ marginBottom: 24, padding: 16, background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 8 }}>
        <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 600 }}>Upload Results Video</h3>
        <form onSubmit={handleUpload} style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <select value={market} onChange={e => setMarket(e.target.value)} style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db' }}>
            {bots.map(m => <option key={m} value={m}>{m.charAt(0).toUpperCase() + m.slice(1)}</option>)}
          </select>
          <input type="file" accept="video/*" onChange={e => setFile(e.target.files[0])} required />
          <button className="btn-primary" type="submit" disabled={uploading}>
            {uploading ? 'Uploading…' : 'Upload'}
          </button>
        </form>
        {uploadError   && <p style={{ margin: '8px 0 0', color: '#dc2626', fontSize: 13 }}>{uploadError}</p>}
        {uploadSuccess && <p style={{ margin: '8px 0 0', color: '#16a34a', fontSize: 13 }}>{uploadSuccess}</p>}
      </div>

      {loading    && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}

      {!loading && rows.length === 0 && <p className="status-msg">No videos uploaded yet.</p>}

      {rows.length > 0 && (
        <table className="data-table">
          <thead>
            <tr><th>Market</th><th>URL</th><th>Last Updated</th></tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.market}>
                <td style={{ textTransform: 'capitalize', fontWeight: 500 }}>{r.market}</td>
                <td><a href={r.url} target="_blank" rel="noreferrer" style={{ color: '#2563eb', fontSize: 13 }}>{r.url}</a></td>
                <td style={{ fontSize: 13, color: '#6b7280' }}>{r.updated_at ? new Date(r.updated_at).toLocaleString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ─── Corrections Tab (developer review) ──────────────────────────────────────


// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [authed, setAuthed] = useState(() => sessionStorage.getItem('dash_auth') === '1')
  const [tab, setTab]       = useState('qa')

  if (!authed) return <AuthGate onAuth={() => setAuthed(true)} />

  return (
    <div className="app">
      <header className="app-header">
        <span className="app-title">Lucentive Dashboard</span>
        <button className="btn-logout" onClick={() => { sessionStorage.removeItem('dash_auth'); setAuthed(false) }}>
          Log out
        </button>
      </header>

      <nav className="tab-nav">
        <button className={`tab-btn ${tab === 'qa'             ? 'active' : ''}`} onClick={() => setTab('qa')}>Knowledge Base</button>
        <button className={`tab-btn ${tab === 'handoff'        ? 'active' : ''}`} onClick={() => setTab('handoff')}>Handoff Rules</button>
        <button className={`tab-btn ${tab === 'broker-links'   ? 'active' : ''}`} onClick={() => setTab('broker-links')}>Broker Links</button>
        <button className={`tab-btn ${tab === 'country-offers' ? 'active' : ''}`} onClick={() => setTab('country-offers')}>Country Offers</button>
        <button className={`tab-btn ${tab === 'brokers'        ? 'active' : ''}`} onClick={() => setTab('brokers')}>Brokers</button>
        <button className={`tab-btn ${tab === 'countries'      ? 'active' : ''}`} onClick={() => setTab('countries')}>Countries</button>
        <button className={`tab-btn ${tab === 'bots'           ? 'active' : ''}`} onClick={() => setTab('bots')}>Bots</button>
        <button className={`tab-btn ${tab === 'results-videos' ? 'active' : ''}`} onClick={() => setTab('results-videos')}>Results Videos</button>
        <button className={`tab-btn ${tab === 'threads'        ? 'active' : ''}`} onClick={() => setTab('threads')}>Threads</button>
        <button className={`tab-btn ${tab === 'conversations'  ? 'active' : ''}`} onClick={() => setTab('conversations')}>Conversations</button>
      </nav>

      {tab === 'qa'             && <QATab />}
      {tab === 'handoff'        && <HandoffTab />}
      {tab === 'broker-links'   && <BrokerAssetsTab />}
      {tab === 'country-offers' && <CountryOffersTab />}
      {tab === 'brokers'        && <BrokersTab />}
      {tab === 'countries'      && <CountriesTab />}
      {tab === 'bots'           && <BotsTab />}
      {tab === 'results-videos' && <ResultsVideosTab />}
      {tab === 'threads'        && <ThreadsTab />}
      {tab === 'conversations'  && <ConversationsTab />}
    </div>
  )
}

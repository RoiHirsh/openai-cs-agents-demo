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

  async function handleSave() {
    const q = question.trim(), a = answer.trim()
    if (q.length < 10) { setModalError('Question must be at least 10 characters'); return }
    if (a.length < 10) { setModalError('Answer must be at least 10 characters'); return }
    setSaving(true); setModalError('')
    try {
      if (modal.mode === 'add') {
        await apiFetch('/knowledge/qa', { method: 'POST', body: JSON.stringify({ question: q, answer: a }) })
      } else {
        await apiFetch(`/knowledge/qa/${modal.row.id}`, { method: 'PUT', body: JSON.stringify({ question: q, answer: a }) })
      }
      closeModal(); await load()
    } catch (e) { setModalError(e.message) }
    finally { setSaving(false) }
  }

  async function handleToggle(row) {
    try { await apiFetch(`/knowledge/qa/${row.id}`, { method: 'PUT', body: JSON.stringify({ active: !row.active }) }); await load() }
    catch (e) { alert(e.message) }
  }

  async function handleDelete(row) {
    if (!confirm(`Delete this Q&A pair?\n\n"${row.question.slice(0, 80)}"`)) return
    try { await apiFetch(`/knowledge/qa/${row.id}`, { method: 'DELETE' }); await load() }
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
    const matchesBroker  = filterBroker  === 'all' || r.broker  === filterBroker
    const matchesPurpose = filterPurpose === 'all' || r.purpose === filterPurpose
    const matchesBot     = filterBot     === 'all' || (filterBot === '_generic' ? !r.bot : r.bot === filterBot)
    const matchesSearch  = !search.trim() ||
      r.title.toLowerCase().includes(search.toLowerCase()) ||
      r.url.toLowerCase().includes(search.toLowerCase())
    return matchesBroker && matchesPurpose && matchesBot && matchesSearch
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
    const matchesSearch  = !search.trim() ||
      r.country_group.toLowerCase().includes(search.toLowerCase()) ||
      r.broker_name.toLowerCase().includes(search.toLowerCase()) ||
      (r.bots || []).some(b => b.toLowerCase().includes(search.toLowerCase()))
    return matchesCountry && matchesBroker && matchesSearch
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

  return (
    <div className="tab-content">
      <div className="tab-toolbar">
        <span className="row-count">{rows.length} brokers</span>
        <button className="btn-primary" onClick={openAdd}>+ Add Broker</button>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}
      {!loading && !fetchError && rows.length === 0 && <p className="status-msg">No brokers yet.</p>}

      {rows.length > 0 && (
        <table className="data-table">
          <thead><tr><th>ID (slug)</th><th>Display Name</th><th>Aliases</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {rows.map(row => (
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

  return (
    <div className="tab-content">
      <div className="tab-toolbar">
        <span className="row-count">{rows.length} country groups</span>
        <button className="btn-primary" onClick={openAdd}>+ Add Country</button>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}
      {!loading && !fetchError && rows.length === 0 && <p className="status-msg">No country groups yet.</p>}

      {rows.length > 0 && (
        <table className="data-table">
          <thead><tr><th>Name</th><th>Aliases</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {rows.map(row => (
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

  return (
    <div className="tab-content">
      <div className="tab-toolbar">
        <span className="row-count">{rows.length} bots</span>
        <button className="btn-primary" onClick={openAdd}>+ Add Bot</button>
      </div>

      {loading && <p className="status-msg">Loading…</p>}
      {fetchError && <p className="status-msg error">{fetchError}</p>}
      {!loading && !fetchError && rows.length === 0 && <p className="status-msg">No bots yet.</p>}

      {rows.length > 0 && (
        <table className="data-table">
          <thead><tr><th>Bot Name</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {rows.map(row => (
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
      </nav>

      {tab === 'qa'             && <QATab />}
      {tab === 'handoff'        && <HandoffTab />}
      {tab === 'broker-links'   && <BrokerAssetsTab />}
      {tab === 'country-offers' && <CountryOffersTab />}
      {tab === 'brokers'        && <BrokersTab />}
      {tab === 'countries'      && <CountriesTab />}
      {tab === 'bots'           && <BotsTab />}
    </div>
  )
}

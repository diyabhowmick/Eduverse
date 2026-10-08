import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, num, when } from '../api'
import { useLoad, Page, Modal, Field, Tag, useToast, useForm, Icon } from '../ui'

function Upload({ books, onClose, onDone }) {
  const [v, setV, bind] = useForm({ kind: 'auto', book_id: '', title: '', subject: '', board: 'Tamil Nadu State Board', grade: '', medium: 'English', reviewer_id: '' })
  const { data: reviewers } = useLoad('/api/reviewers')
  const [file, setFile] = useState(null); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  // Set when the server recognises this exact file. It is not an error — the
  // book already exists and can simply be assigned — so it gets its own panel
  // with a way through for the rare case where processing again is wanted.
  const [dup, setDup] = useState('')
  const input = useRef()
  async function go(force) {
    if (!file) return setErr('Choose a PDF or Word file')
    const f = new FormData(); f.append('file', file)
    Object.entries(v).forEach(([k, x]) => x !== '' && f.append(k, x))
    if (force) f.append('force', 'true')
    setBusy(true); setErr(''); setDup('')
    try { await api('/api/jobs', { method: 'POST', form: f }); onDone() }
    catch (e) {
      const m = e.message || ''
      if (/already have this book/i.test(m)) setDup(m); else setErr(m)
    } finally { setBusy(false) }
  }
  return (
    <Modal title="Add document" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={() => go(false)} disabled={busy}>{busy ? 'Uploading' : 'Add and send to review'}</button></>}>
      <div className="note">A printed book (PDF or Word, scanned is fine) goes through M1, the converter and M2. An M1 flow document skips M1. Either way the book goes to the reviewer and is <b>not</b> published until they approve it.</div>
      {err && <div className="err">{err}</div>}
      {dup && <div className="note warn">
        <b>We already have this book.</b> {dup.replace(/^We already have this book[.:]?\s*/i, '')}
        <div className="muted" style={{ fontSize: 12.5, marginTop: 7 }}>
          One textbook serves every school on that syllabus, so processing it again costs the same
          money for an identical result.
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 11 }}>
          <button className="btn sm" onClick={onClose}>Assign the existing one</button>
          <button className="btn ghost sm" onClick={() => go(true)} disabled={busy}>
            Process it anyway</button>
        </div>
      </div>}
      <Field label="What is this file?" hint={v.kind === 'auto' ? 'A Word file made by M1 is spotted by its styles; anything else is read as a printed book' : ''}>
        <div className="seg" role="radiogroup">{[['auto', 'Detect'], ['book', 'Printed book (run M1)'], ['flow', 'M1 flow document']].map(([k, l]) =>
          <button key={k} type="button" className={v.kind === k ? 'on' : ''} onClick={() => setV(x => ({ ...x, kind: k }))} role="radio" aria-checked={v.kind === k}>{l}</button>)}</div></Field>
      <div className="card" style={{ padding: 18, textAlign: 'center', borderStyle: 'dashed', cursor: 'pointer' }} onClick={() => input.current.click()}>
        <Icon n="upload" s={22} /><div style={{ marginTop: 6 }}>{file ? <b>{file.name}</b> : 'Choose a PDF or Word file'}</div>
        <input ref={input} type="file" accept=".pdf,.doc,.docx" hidden onChange={e => setFile(e.target.files[0])} />
      </div>
      <Field label="Catalogue entry"><select className="input" {...bind('book_id')}><option value="">Create a new book</option>{books.filter(b => ['upcoming', 'retired'].includes(b.status)).map(b => <option key={b.id} value={b.id}>{b.title}, {b.board}</option>)}</select></Field>
      <Field label="Send to reviewer" hint="Only this reviewer sees it. Leave on Any to let any reviewer pick it up."><select className="input" {...bind('reviewer_id')}><option value="">Any reviewer</option>{reviewers?.filter(r => r.status === 'active').map(r => <option key={r.id} value={r.id}>{r.name}, {r.in_review} books with them</option>)}</select></Field>
      {!v.book_id && <div className="grid2">
        <Field label="Title"><input className="input" {...bind('title')} /></Field><Field label="Subject"><input className="input" {...bind('subject')} /></Field>
        <Field label="Board"><input className="input" {...bind('board')} /></Field><Field label="Class"><input className="input" {...bind('grade')} /></Field>
      </div>}
    </Modal>)
}

export default function Processing() {
  const jobs = useLoad('/api/jobs'); const sum = useLoad('/api/jobs/summary'); const books = useLoad('/api/books')
  const [params, setParams] = useSearchParams()
  const [up, setUp] = useState(params.get('add') === '1'); const [err, setErr] = useState(null); const [used, setUsed] = useState(null)
  useEffect(() => { if (params.get('add')) setParams({}, { replace: true }) }, [])
  const toast = useToast()
  const reload = () => { jobs.reload(); sum.reload(); books.reload() }
  // refresh every 3 seconds while anything is still working
  const busy = jobs.data?.some(j => j.status === 'running' || j.status === 'queued')
  useEffect(() => { if (!busy) return; const t = setInterval(reload, 3000); return () => clearInterval(t) }, [busy])
  const stage = j => j.status === 'running' ? ({ 'M1 read': 'M1 reading pages', 'M1 build': 'M1 building', Convert: 'Converting', M2: 'M2 redrawing figures' }[j.stage] || 'Working')
    : j.status === 'queued' ? (j.kind === 'book' && jobs.data.some(x => x.status === 'running' && x.kind === 'book') ? 'Waiting, one book at a time' : 'Starting')
    : j.status === 'done' ? ({ in_review: 'With the reviewer', live: 'Published', rejected: 'Sent back' }[j.book_status] || 'Done') : null
  const act = async (j, a, m) => { try { await api(`/api/jobs/${j.id}/${a}`, { method: 'POST' }); toast(m); reload() } catch (e) { toast(e.message, true) } }
  const s = sum.data
  const extra = async (j, name) => {
    try {
      const r = await fetch(`/api/jobs/${j.id}/extras/${name}`, { headers: { Authorization: 'Bearer ' + localStorage.getItem('ev_token') } })
      if (!r.ok) throw new Error('Not available for this job')
      if (name === 'settings') return setUsed({ job: j, v: await r.json() })
      const url = URL.createObjectURL(new Blob([await r.text()], { type: 'text/html' })); window.open(url, '_blank')
    } catch (e) { toast(e.message, true) }
  }
  return (
    <Page title="Processing" sub="Printed books go through M1, the converter and M2; flow documents skip M1. Every book then waits for a reviewer."
      actions={<button className="btn primary" onClick={() => setUp(true)}><Icon n="upload" s={16} />Add document</button>}>
      <div className="stack">
        {s && <div className="metrics">
          <div className="metric"><div className="v">{s.running}</div><div className="l">Running</div></div>
          <div className="metric"><div className="v">{s.queued}</div><div className="l">Queued</div></div>
          <div className="metric"><div className="v" style={{ color: s.failed ? 'var(--red)' : undefined }}>{s.failed}</div><div className="l">Failed</div></div>
          <div className="metric"><div className="v">{num(s.credits_used)}</div><div className="l">Credits used, all time</div></div>
        </div>}
        <div className="card">
          <table className="t"><thead><tr><th>File</th><th>Book</th><th>Progress</th><th className="num">Cost</th><th>Status</th><th>Started</th><th /></tr></thead>
            <tbody>{jobs.data?.map(j => (
              <tr key={j.id}>
                <td><b>{j.filename}</b><div className="muted">{j.kind === 'flow' ? 'Flow document' : 'Printed book'}, by {j.triggered_by}</div></td><td>{j.book}</td>
                <td style={{ minWidth: 150 }}><div className="bar-track"><i style={{ width: (j.pages ? j.pages_done / j.pages * 100 : 0) + '%', background: j.status === 'failed' ? 'var(--ink-3)' : undefined }} /></div><div className="muted">{j.status === 'running' && j.stage === 'M2' ? `${j.pages_done} of ${j.pages} figures` : `${j.pages_done} of ${j.pages || '?'} pages`}</div></td>
                <td className="num">{num(j.cost_credits)}</td>
                <td><Tag s={j.status === 'done' ? (j.book_status === 'live' ? 'live' : j.book_status === 'rejected' ? 'rejected' : 'in_review') : j.status}>{stage(j) || undefined}</Tag>
                  {j.status === 'running' && <div className="muted" style={{ fontSize: 12 }}>updating live<span className="dots" /></div>}</td>
                <td className="muted">{when(j.created_at)}</td>
                <td className="acts">
                  {j.status === 'done' && j.book_status === 'in_review' && <Link className="btn ghost sm" to="/sa/catalogue">See in catalogue</Link>}
                  {j.has_extras && j.status === 'done' && <button className="btn ghost sm" onClick={() => extra(j, 'report')}>M1 report</button>}
                  {j.has_extras && <button className="btn ghost sm" onClick={() => extra(j, 'settings')}>Settings used</button>}
                  {j.status === 'failed' && <button className="btn ghost sm" onClick={() => setErr(j)}>See error</button>}
                  {['failed', 'cancelled'].includes(j.status) && <button className="btn sm" onClick={() => act(j, 'retry', 'Job queued again')}>Retry</button>}
                  {['queued', 'running'].includes(j.status) && <button className="btn ghost sm" onClick={() => act(j, 'cancel', j.status === 'running' ? 'Stopping after this page' : 'Job cancelled')}>Stop</button>}
                </td>
              </tr>))}</tbody></table>
          {jobs.data && !jobs.data.length && <div className="empty">No runs yet. Upload a book to start.</div>}
        </div>
      </div>
      {up && books.data && <Upload books={books.data} onClose={() => setUp(false)} onDone={() => { setUp(false); toast('Document added. Converting now; it goes to the reviewer when done.'); reload() }} />}
      {used && <Modal title={'M1 settings used for ' + used.job.filename} onClose={() => setUsed(null)} footer={<Link className="btn" to="/sa/extraction">Current M1 settings</Link>}>
        <div className="note">A copy taken when this job started. Changing M1 settings later does not change it.</div>
        <div className="secret" style={{ maxHeight: 380, overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: 12 }}>{Object.entries(used.v).filter(([k]) => k !== 'styles').map(([k, x]) => `${k}: ${Array.isArray(x) ? x.join(', ') : x}`).join('\n')}</div></Modal>}
      {err && <Modal title={'Error in ' + err.filename} onClose={() => setErr(null)} footer={<button className="btn primary" onClick={() => { act(err, 'retry', 'Job queued again'); setErr(null) }}>Retry job</button>}><div className="secret" style={{ whiteSpace: 'pre-wrap' }}>{err.error}</div></Modal>}
    </Page>
  )
}

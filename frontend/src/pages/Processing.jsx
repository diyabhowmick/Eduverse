import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, num, when } from '../api'
import { useLoad, Page, Modal, Tag, useToast, Icon } from '../ui'

export default function Processing() {
  const jobs = useLoad('/api/jobs'); const sum = useLoad('/api/jobs/summary')
  const [err, setErr] = useState(null); const [used, setUsed] = useState(null)
  const toast = useToast()
  const reload = () => { jobs.reload(); sum.reload() }
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
      actions={<Link className="btn primary" to="/sa/add"><Icon n="upload" s={16} />Add content</Link>}>
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
                  {j.status === 'running' && <div className="muted" style={{ fontSize: 12 }}>updating live<span className="dots" /></div>}
                  {j.note && <div className="note" style={{ fontSize: 12, marginTop: 6, maxWidth: 320 }}>{j.note}</div>}</td>
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
          {jobs.data && !jobs.data.length && <div className="empty">Nothing is being processed. <Link to="/sa/add" style={{ color: 'var(--red)', fontWeight: 650 }}>Add a book or document</Link> to start.</div>}
        </div>
      </div>
      {used && <Modal title={'M1 settings used for ' + used.job.filename} onClose={() => setUsed(null)} footer={<Link className="btn" to="/sa/extraction">Current M1 settings</Link>}>
        <div className="note">A copy taken when this job started. Changing M1 settings later does not change it.</div>
        <div className="secret" style={{ maxHeight: 380, overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: 12 }}>{Object.entries(used.v).filter(([k]) => k !== 'styles').map(([k, x]) => `${k}: ${Array.isArray(x) ? x.join(', ') : x}`).join('\n')}</div></Modal>}
      {err && <Modal title={'Error in ' + err.filename} onClose={() => setErr(null)} footer={<button className="btn primary" onClick={() => { act(err, 'retry', 'Job queued again'); setErr(null) }}>Retry job</button>}><div className="secret" style={{ whiteSpace: 'pre-wrap' }}>{err.error}</div></Modal>}
    </Page>
  )
}

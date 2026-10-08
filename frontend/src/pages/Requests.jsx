import { useState } from 'react'
import { api, when } from '../api'
import { useLoad, Page, Modal, Field, Tag, useToast } from '../ui'

export const reqTitle = r => r.kind === 'seats' ? `${r.detail.seats} more seats` : r.kind === 'plan' ? `Move to ${r.detail.plan} plan` : r.kind === 'book' ? `New book: ${r.detail.book_title}` : 'Other request'
const TONE = { open: 'warn', approved: 'ok', declined: 'bad' }

export default function Requests() {
  const [status, setStatus] = useState('open')
  const { data, reload } = useLoad('/api/requests?status=' + status, [status])
  const [pick, setPick] = useState(null); const [resp, setResp] = useState('')
  const toast = useToast()
  async function decide(d) {
    try { await api(`/api/requests/${pick.id}/${d}`, { method: 'POST', body: { response: resp } }); toast(d === 'approve' ? 'Request approved' : 'Request declined'); setPick(null); setResp(''); reload() }
    catch (e) { toast(e.message, true) }
  }
  return (
    <Page title="School requests" sub="Seats, plan changes and books asked for by school admins">
      <div className="toolbar"><div className="seg">{[['open', 'Open'], ['approved', 'Approved'], ['declined', 'Declined'], ['', 'All']].map(([k, l]) => <button key={k} className={status === k ? 'on' : ''} onClick={() => setStatus(k)}>{l}</button>)}</div></div>
      <div className="card">
        <table className="t"><thead><tr><th>Request</th><th>School</th><th>Note</th><th>Sent</th><th>Status</th><th /></tr></thead>
          <tbody>{data?.map(r => <tr key={r.id}><td className="req-kind">{reqTitle(r)}</td><td>{r.school}<div className="muted">{r.created_by}</div></td>
            <td className="muted" style={{ maxWidth: 320 }}>{r.message}{r.response && <div><b>Reply:</b> {r.response}</div>}</td><td className="muted">{when(r.created_at)}</td>
            <td><Tag s={TONE[r.status]}>{r.status[0].toUpperCase() + r.status.slice(1)}</Tag></td>
            <td className="acts">{r.status === 'open' && <button className="btn primary sm" onClick={() => setPick(r)}>Review</button>}</td></tr>)}</tbody></table>
        {data && !data.length && <div className="empty">No requests here</div>}
      </div>
      {pick && <Modal title={reqTitle(pick)} onClose={() => setPick(null)} footer={<><button className="btn" onClick={() => decide('decline')}>Decline</button><button className="btn primary" onClick={() => decide('approve')}>Approve</button></>}>
        <div className="note"><b>{pick.school}</b> asked on {when(pick.created_at)}. {pick.message}</div>
        {pick.kind === 'seats' && <div>Approving adds {pick.detail.seats} seats to the school straight away.</div>}
        {pick.kind === 'plan' && <div>Approving moves the school from {pick.detail.from || 'no plan'} to {pick.detail.plan}.</div>}
        {pick.kind === 'book' && <div>Approving records the request. Add the book in Book catalogue or upload it in Processing.</div>}
        <Field label="Reply to the school (optional)"><textarea className="input" rows="3" value={resp} onChange={e => setResp(e.target.value)} /></Field>
      </Modal>}
    </Page>
  )
}

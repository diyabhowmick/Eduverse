import { useState } from 'react'
import { api, inr, when } from '../../api'
import { useLoad, Page, Modal, Field, Tag, useToast, useForm, Icon } from '../../ui'
import { reqTitle } from '../Requests'

const TONE = { open: 'warn', approved: 'ok', declined: 'bad' }

function NewRequest({ onClose, onSaved }) {
  const [v, , bind] = useForm({ kind: 'seats', seats: 20, plan_id: '', book_title: '', message: '' }); const [err, setErr] = useState('')
  const { data: plans } = useLoad('/api/school/plans'); const { data: ov } = useLoad('/api/school/overview')
  async function send() { try { await api('/api/school/requests', { method: 'POST', body: { ...v, seats: +v.seats || null, plan_id: v.plan_id ? +v.plan_id : null } }); onSaved() } catch (e) { setErr(e.message) } }
  return <Modal title="New request to EduVerse" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={send}>Send request</button></>}>
    {err && <div className="err">{err}</div>}
    <Field label="What do you need?"><select className="input" {...bind('kind')}><option value="seats">More seats</option><option value="plan">A different plan</option><option value="book">A book that is not listed</option><option value="other">Something else</option></select></Field>
    {v.kind === 'seats' && <Field label="Extra seats" hint={ov ? `You have ${ov.seats} seats, ${ov.seats_used} used` : ''}><input className="input" type="number" min="1" {...bind('seats')} /></Field>}
    {v.kind === 'plan' && <Field label="Plan" hint={ov ? 'Now on ' + ov.school.plan : ''}><select className="input" {...bind('plan_id')}><option value="">Choose a plan</option>{plans?.map(p => <option key={p.id} value={p.id}>{p.name}, {inr(p.price_per_seat)} per seat, {p.max_books || 'all'} books</option>)}</select></Field>}
    {v.kind === 'book' && <Field label="Book"><input className="input" placeholder="Mathematics Standard 7, Tamil Nadu" {...bind('book_title')} /></Field>}
    <Field label="Note"><textarea className="input" rows="3" {...bind('message')} /></Field>
  </Modal>
}

export default function Requests() {
  const { data, reload } = useLoad('/api/school/requests'); const [open, setOpen] = useState(false); const toast = useToast()
  return (
    <Page title="Requests" sub="Ask EduVerse for more seats, a plan change or a new book" actions={<button className="btn primary" onClick={() => setOpen(true)}><Icon n="plus" s={16} />New request</button>}>
      <div className="card"><table className="t"><thead><tr><th>Request</th><th>Note</th><th>Sent</th><th>Status</th><th>Reply from EduVerse</th></tr></thead>
        <tbody>{data?.map(r => <tr key={r.id}><td className="req-kind">{reqTitle(r)}</td><td className="muted">{r.message}</td><td className="muted">{when(r.created_at)}<div>{r.created_by}</div></td>
          <td><Tag s={TONE[r.status]}>{r.status[0].toUpperCase() + r.status.slice(1)}</Tag></td><td className="muted">{r.book
            ? <><b>{r.book.stage}</b><div style={{ fontSize: 11 }}>{r.book.title}</div></>
            : (r.response || (r.status === 'open' ? 'Waiting' : ''))}</td></tr>)}</tbody></table>
        {data && !data.length && <div className="empty">No requests yet</div>}</div>
      {open && <NewRequest onClose={() => setOpen(false)} onSaved={() => { setOpen(false); toast('Request sent'); reload() }} />}
    </Page>
  )
}

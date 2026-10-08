import { useState } from 'react'
import { api, inr, num, day } from '../api'
import { useLoad, Page, Modal, Field, Tag, useToast, useForm, Icon, Confirm } from '../ui'

const BOARDS = ['Tamil Nadu State Board', 'CBSE', 'ICSE', 'Kerala State Board', 'Karnataka State Board', 'Andhra Pradesh State Board', 'Telangana State Board', 'Maharashtra State Board']
const blank = { name: '', board: BOARDS[0], medium: 'English', city: '', contact_name: '', contact_email: '', academic_year: '', plan_id: '', seats: 0, discount_id: '', status: 'active' }

function SchoolForm({ school, plans, discounts, onClose, onSaved }) {
  const [v, , bind] = useForm(school ? { ...school, plan_id: school.plan_id ?? '', discount_id: school.discount_id ?? '' } : blank)
  const [err, setErr] = useState('')
  const plan = plans.find(p => p.id === +v.plan_id); const disc = discounts.find(d => d.id === +v.discount_id)
  const yearly = plan ? v.seats * plan.price_per_seat * (plan.billing_cycle === 'monthly' ? 12 : 1) * (1 - (disc?.percent || 0) / 100) : 0
  async function save() {
    setErr('')
    const body = { ...v, seats: +v.seats || 0, plan_id: v.plan_id ? +v.plan_id : null, discount_id: v.discount_id ? +v.discount_id : null }
    try { await api(school ? '/api/schools/' + school.id : '/api/schools', { method: school ? 'PUT' : 'POST', body }); onSaved(school ? 'School updated' : 'School added') }
    catch (e) { setErr(e.message) }
  }
  return (
    <Modal title={school ? 'Edit school' : 'Add school'} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>{school ? 'Save changes' : 'Add school'}</button></>}>
      {err && <div className="err">{err}</div>}
      <Field label="School name"><input className="input" {...bind('name')} /></Field>
      <div className="grid2">
        <Field label="Board"><select className="input" {...bind('board')}>{BOARDS.map(b => <option key={b}>{b}</option>)}</select></Field>
        <Field label="Medium"><select className="input" {...bind('medium')}>{['English', 'Tamil', 'Hindi', 'Malayalam', 'Kannada', 'Telugu'].map(m => <option key={m}>{m}</option>)}</select></Field>
        <Field label="City"><input className="input" {...bind('city')} /></Field>
        <Field label="Academic year"><input className="input" placeholder="2026-27" {...bind('academic_year')} /></Field>
        <Field label="Contact person"><input className="input" {...bind('contact_name')} /></Field>
        <Field label="Contact email"><input className="input" type="email" {...bind('contact_email')} /></Field>
        <Field label="Plan"><select className="input" {...bind('plan_id')}><option value="">No plan</option>{plans.filter(p => p.active || p.id === +v.plan_id).map(p => <option key={p.id} value={p.id}>{p.name}, {inr(p.price_per_seat)} per seat</option>)}</select></Field>
        <Field label="Seats"><input className="input" type="number" min="0" {...bind('seats')} /></Field>
        <Field label="Discount"><select className="input" {...bind('discount_id')}><option value="">None</option>{discounts.filter(d => d.active).map(d => <option key={d.id} value={d.id}>{d.code}, {d.percent}% off</option>)}</select></Field>
        <Field label="Status"><select className="input" {...bind('status')}><option value="active">Active</option><option value="suspended">Suspended</option></select></Field>
      </div>
      <div className="note">Contract value: <b>{inr(yearly)}</b> a year{disc ? `, after ${disc.percent}% off` : ''}</div>
    </Modal>)
}

export default function Schools() {
  const { data, reload } = useLoad('/api/schools')
  const { data: plans } = useLoad('/api/pricing/plans'); const { data: discounts } = useLoad('/api/pricing/discounts')
  const [edit, setEdit] = useState(null); const [del, setDel] = useState(null)
  const toast = useToast()
  return (
    <Page title="Schools" sub="Every school onboarded to EduVerse, its plan and seat use"
      actions={<button className="btn primary" onClick={() => setEdit({})}><Icon n="plus" s={16} />Add school</button>}>
      <div className="card">
        <table className="t"><thead><tr><th>School</th><th>Board</th><th>Plan</th><th>Seat use</th><th className="num">Annual value</th><th>Status</th><th /></tr></thead>
          <tbody>{data?.map(s => (
            <tr key={s.id}>
              <td><b>{s.name}</b><div className="muted">{s.city}{s.academic_year ? ', ' + s.academic_year : ''}. Since {day(s.created_at)}</div></td>
              <td>{s.board}<div className="muted">{s.medium} medium</div></td>
              <td>{s.plan || <span className="muted">None</span>}{s.discount && <div className="muted">{s.discount}</div>}</td>
              <td style={{ minWidth: 150 }}><div className="bar-track"><i style={{ width: Math.min(100, s.students / Math.max(1, s.seats) * 100) + '%' }} /></div><div className="muted">{num(s.students)} of {num(s.seats)} seats</div></td>
              <td className="num">{inr(s.annual_value)}</td><td><Tag s={s.status} /></td>
              <td className="acts"><button className="btn ghost sm" onClick={() => setEdit(s)}>Edit</button><button className="btn ghost sm" style={{ color: 'var(--red)' }} onClick={() => setDel(s)}>Delete</button></td>
            </tr>))}</tbody></table>
        {data && !data.length && <div className="empty">No schools yet. Add the first school to start selling seats.</div>}
      </div>
      {edit && plans && discounts && <SchoolForm school={edit.id ? edit : null} plans={plans} discounts={discounts} onClose={() => setEdit(null)} onSaved={m => { setEdit(null); toast(m); reload() }} />}
      {del && <Confirm text={`Delete ${del.name}? This only works when it has no admins or students.`} yes="Delete school" onClose={() => setDel(null)}
        onYes={async () => { try { await api('/api/schools/' + del.id, { method: 'DELETE' }); toast('School deleted'); reload() } catch (e) { toast(e.message, true) } setDel(null) }} />}
    </Page>
  )
}

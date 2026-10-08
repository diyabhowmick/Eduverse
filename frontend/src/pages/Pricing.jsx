import { useState } from 'react'
import { api, inr, day } from '../api'
import { useLoad, Page, Modal, Field, Tag, useToast, useForm, Icon, Switch, Confirm } from '../ui'

const FEATS = [['explain_panel', 'Explain panel'], ['notebook', 'Notebook'], ['practice_questions', 'Practice questions'], ['knowledge_graph', 'Knowledge graph']]

function PlanForm({ plan, onClose, onSaved }) {
  const [v, setV, bind] = useForm(plan || { name: '', price_per_seat: 0, billing_cycle: 'yearly', credits_per_seat: 0, max_books: 0, features: {}, active: true })
  const [err, setErr] = useState('')
  async function save() {
    try { await api(plan ? '/api/pricing/plans/' + plan.id : '/api/pricing/plans', { method: plan ? 'PUT' : 'POST', body: { ...v, price_per_seat: +v.price_per_seat, credits_per_seat: +v.credits_per_seat, max_books: +v.max_books } }); onSaved(plan ? 'Plan updated' : 'Plan created') }
    catch (e) { setErr(e.message) }
  }
  return (
    <Modal title={plan ? 'Edit plan' : 'New plan'} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save plan</button></>}>
      {err && <div className="err">{err}</div>}
      <div className="grid2">
        <Field label="Plan name"><input className="input" {...bind('name')} /></Field>
        <Field label="Billing"><select className="input" {...bind('billing_cycle')}><option value="yearly">Yearly</option><option value="monthly">Monthly</option></select></Field>
        <Field label="Price per seat (₹)"><input className="input" type="number" min="0" {...bind('price_per_seat')} /></Field>
        <Field label="AI credits per seat" hint="One explanation uses one credit"><input className="input" type="number" min="0" {...bind('credits_per_seat')} /></Field>
        <Field label="Books per student" hint="0 means every book"><input className="input" type="number" min="0" {...bind('max_books')} /></Field>
        <Field label="Available for sale"><Switch checked={v.active} onChange={a => setV(x => ({ ...x, active: a }))} label="Active" /></Field>
      </div>
      <Field label="Included features">
        {FEATS.map(([k, l]) => <label key={k} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '4px 0' }}><Switch checked={v.features?.[k]} onChange={on => setV(x => ({ ...x, features: { ...x.features, [k]: on } }))} label={l} />{l}</label>)}
      </Field>
    </Modal>)
}

function DiscountForm({ d, onClose, onSaved }) {
  const [v, setV, bind] = useForm(d ? { ...d, valid_until: d.valid_until?.slice(0, 10) || '' } : { code: '', percent: 10, max_uses: 0, valid_until: '', active: true })
  const [err, setErr] = useState('')
  async function save() {
    try { await api(d ? '/api/pricing/discounts/' + d.id : '/api/pricing/discounts', { method: d ? 'PUT' : 'POST', body: { ...v, percent: +v.percent, max_uses: +v.max_uses, valid_until: v.valid_until || null } }); onSaved(d ? 'Discount updated' : 'Discount created') }
    catch (e) { setErr(e.message) }
  }
  return (
    <Modal title={d ? 'Edit discount' : 'New discount'} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save discount</button></>}>
      {err && <div className="err">{err}</div>}
      <div className="grid2">
        <Field label="Code"><input className="input" {...bind('code')} style={{ textTransform: 'uppercase' }} /></Field>
        <Field label="Percent off"><input className="input" type="number" min="1" max="100" {...bind('percent')} /></Field>
        <Field label="Max uses" hint="0 means no limit"><input className="input" type="number" min="0" {...bind('max_uses')} /></Field>
        <Field label="Valid until" hint="Leave empty for no end date"><input className="input" type="date" {...bind('valid_until')} /></Field>
      </div>
      <label style={{ display: 'flex', gap: 10, alignItems: 'center' }}><Switch checked={v.active} onChange={a => setV(x => ({ ...x, active: a }))} label="Active" />Active</label>
    </Modal>)
}

export default function Pricing() {
  const plans = useLoad('/api/pricing/plans'); const discs = useLoad('/api/pricing/discounts')
  const [ep, setEp] = useState(null); const [ed, setEd] = useState(null); const [del, setDel] = useState(null)
  const toast = useToast()
  const saved = m => { setEp(null); setEd(null); toast(m); plans.reload(); discs.reload() }
  return (
    <Page title="Pricing" sub="Plans schools buy per seat, and discount codes">
      <div className="stack">
        <div className="card">
          <div className="card-h"><h3>Plans</h3><button className="btn primary sm right" onClick={() => setEp({})}><Icon n="plus" s={14} />New plan</button></div>
          <table className="t"><thead><tr><th>Plan</th><th className="num">Price per seat</th><th className="num">AI credits</th><th className="num">Books</th><th>Features</th><th className="num">Schools</th><th>Status</th><th /></tr></thead>
            <tbody>{plans.data?.map(p => (
              <tr key={p.id}><td><b>{p.name}</b></td>
                <td className="num">{inr(p.price_per_seat)}<div className="muted">{p.billing_cycle}</div></td>
                <td className="num">{p.credits_per_seat}</td><td className="num">{p.max_books || 'All'}</td>
                <td className="muted">{FEATS.filter(([k]) => p.features[k]).map(([, l]) => l).join(', ') || 'Reader only'}</td>
                <td className="num">{p.schools}</td><td><Tag s={p.active ? 'active' : 'inactive'}>{p.active ? 'On sale' : 'Hidden'}</Tag></td>
                <td className="acts"><button className="btn ghost sm" onClick={() => setEp(p)}>Edit</button><button className="btn ghost sm" style={{ color: 'var(--red)' }} onClick={() => setDel({ kind: 'plans', id: p.id, name: p.name })}>Delete</button></td></tr>))}</tbody></table>
        </div>
        <div className="card">
          <div className="card-h"><h3>Discount codes</h3><button className="btn sm right" onClick={() => setEd({})}><Icon n="plus" s={14} />New code</button></div>
          <table className="t"><thead><tr><th>Code</th><th className="num">Off</th><th className="num">Used</th><th>Valid until</th><th>Status</th><th /></tr></thead>
            <tbody>{discs.data?.map(d => (
              <tr key={d.id}><td className="mono"><b>{d.code}</b></td><td className="num">{d.percent}%</td>
                <td className="num">{d.used}{d.max_uses ? ' of ' + d.max_uses : ''}</td><td className="muted">{d.valid_until ? day(d.valid_until) : 'No end date'}</td>
                <td><Tag s={d.active ? 'active' : 'inactive'}>{d.active ? 'Active' : 'Off'}</Tag></td>
                <td className="acts"><button className="btn ghost sm" onClick={() => setEd(d)}>Edit</button><button className="btn ghost sm" style={{ color: 'var(--red)' }} onClick={() => setDel({ kind: 'discounts', id: d.id, name: d.code })}>Delete</button></td></tr>))}</tbody></table>
          {discs.data && !discs.data.length && <div className="empty">No discount codes</div>}
        </div>
      </div>
      {ep && <PlanForm plan={ep.id ? ep : null} onClose={() => setEp(null)} onSaved={saved} />}
      {ed && <DiscountForm d={ed.id ? ed : null} onClose={() => setEd(null)} onSaved={saved} />}
      {del && <Confirm text={`Delete ${del.name}?`} yes="Delete" onClose={() => setDel(null)} onYes={async () => { try { await api(`/api/pricing/${del.kind}/${del.id}`, { method: 'DELETE' }); saved('Deleted') } catch (e) { toast(e.message, true) } setDel(null) }} />}
    </Page>
  )
}

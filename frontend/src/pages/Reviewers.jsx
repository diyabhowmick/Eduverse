import { useState } from 'react'
import { api, when } from '../api'
import { useLoad, Page, Modal, Field, Tag, useToast, useForm, Icon } from '../ui'

export default function Reviewers() {
  const { data, reload } = useLoad('/api/reviewers')
  const [add, setAdd] = useState(false); const [made, setMade] = useState(null); const [err, setErr] = useState('')
  const [v, setV, bind] = useForm({ name: '', email: '' }); const toast = useToast()
  const [hand, setHand] = useState(null); const [to, setTo] = useState('')
  const act = async (fn, m) => { try { await fn(); toast(m); reload() } catch (e) { toast(e.message, true) } }
  async function create() { try { setMade(await api('/api/reviewers', { method: 'POST', body: v })); setAdd(false); setV({ name: '', email: '' }); reload() } catch (e) { setErr(e.message) } }
  return (
    <Page title="Reviewers" sub="People who check every extracted book before it is published" actions={<button className="btn primary" onClick={() => { setErr(''); setAdd(true) }}><Icon n="plus" s={16} />Add reviewer</button>}>
      <div className="card"><table className="t"><thead><tr><th>Reviewer</th><th className="num">Books with them</th><th>Waiting</th><th className="num">Published</th><th>Last sign in</th><th>Status</th><th /></tr></thead>
        <tbody>{data?.map(r => <tr key={r.id}><td><b>{r.name}</b><div className="muted">{r.email}</div></td><td className="num">{r.in_review}</td>
          <td>{r.tag
            ? <><Tag s={r.tag === 'Newly sent' ? 'active' : 'suspended'}>
                {r.tag === 'Newly sent' ? 'Newly sent' : `${r.tag} · ${r.oldest_days}d`}</Tag>
              {r.oldest_title && r.oldest_days >= 7 && <div className="muted" style={{ fontSize: 11 }}>{r.oldest_title}</div>}</>
            : <span className="muted">—</span>}</td>
          <td className="num">{r.published}</td>
          <td className="muted">{when(r.last_login) || 'Never'}</td><td><Tag s={r.status} /></td>
          <td className="acts"><button className="btn ghost sm" onClick={() => act(async () => setMade(await api(`/api/reviewers/${r.id}/reset-password`, { method: 'POST' })), 'Password reset')}>Reset password</button>
            <button className="btn ghost sm" onClick={() => act(() => api('/api/reviewers/' + r.id, { method: 'PATCH', body: { status: r.status === 'active' ? 'suspended' : 'active' } }), 'Updated')}>{r.status === 'active' ? 'Suspend' : 'Reactivate'}</button>
            {r.in_review > 0 && <button className="btn ghost sm" onClick={() => { setHand(r); setTo('') }}>Hand over</button>}
            <button className="btn ghost sm" onClick={() => {
              if (r.in_review) return toast(`${r.name} still has ${r.in_review} book${r.in_review > 1 ? 's' : ''} to review. Hand them over first.`, true)
              if (confirm(`Remove ${r.name}? Books they published keep their name.`))
                act(() => api('/api/reviewers/' + r.id, { method: 'DELETE' }), 'Reviewer removed')
            }}>Remove</button></td></tr>)}</tbody></table>
        {data && !data.length && <div className="empty">No reviewers yet</div>}</div>
      {add && <Modal title="Add reviewer" onClose={() => setAdd(false)} footer={<><button className="btn" onClick={() => setAdd(false)}>Cancel</button><button className="btn primary" onClick={create}>Create reviewer</button></>}>
        {err && <div className="err">{err}</div>}<Field label="Full name"><input className="input" {...bind('name')} /></Field><Field label="Email"><input className="input" type="email" {...bind('email')} /></Field></Modal>}
      {hand && <Modal title={`Hand over ${hand.in_review} book${hand.in_review > 1 ? 's' : ''}`} onClose={() => setHand(null)}
        footer={<><button className="btn" onClick={() => setHand(null)}>Cancel</button>
          <button className="btn primary" disabled={!to} onClick={() => { setHand(null); act(() => api(`/api/reviewers/${hand.id}/handover`, { method: 'POST', body: { to_reviewer_id: Number(to) } }), 'Books handed over') }}>Hand over</button></>}>
        <p style={{ marginTop: 0 }}>Pages already approved are kept, so the next reviewer carries on rather than starting again.</p>
        <Field label="Give them to"><select className="input" value={to} onChange={e => setTo(e.target.value)}>
          <option value="">Choose a reviewer</option>
          {data?.filter(x => x.id !== hand.id && x.status === 'active').map(x =>
            <option key={x.id} value={x.id}>{x.name} — {x.in_review} already</option>)}
        </select></Field></Modal>}
      {made && <Modal title="Sign in details" onClose={() => setMade(null)} footer={<button className="btn primary" onClick={() => setMade(null)}>Done</button>}>
        <p style={{ margin: 0 }}>Shown once. They sign in on the Reviewer login page.</p><div className="secret">{made.email}<br />{made.temp_password}</div></Modal>}
    </Page>
  )
}

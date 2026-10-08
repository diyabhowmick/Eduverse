import { useState } from 'react'
import { api, when } from '../api'
import { useLoad, Page, Modal, Field, Tag, useToast, useForm, Icon, Confirm } from '../ui'

/* Two admin roles live on this screen.

   A school admin runs one school: its students, classes and books.
   A platform admin runs the book factory for every school, and is never shown
   what any school pays. They belong to no school, which is why the School
   field disappears when that role is chosen. */
const ROLE = {
  admin: { label: 'School Admin', portal: 'School Admin', where: '/login/admin', what: "Runs one school — students, classes, assigning books." },
  platform_admin: { label: 'Platform Admin', portal: 'Platform Admin', where: '/login/platform', what: 'Runs book production — processing, reviewers, the AI keys and what they spend. Sees no school prices.' },
}

function AdminForm({ admin, schools, onClose, onSaved }) {
  const [v, , bind] = useForm(admin || { name: '', email: '', phone: '', role: schools.length ? 'admin' : 'platform_admin', school_id: schools[0]?.id || '' })
  const [err, setErr] = useState(''); const [created, setCreated] = useState(null)
  const role = v.role || 'admin'
  const platform = role === 'platform_admin'
  async function save() {
    setErr('')
    try {
      if (admin) {
        const body = { name: v.name, phone: v.phone }
        if (admin.role === 'admin') body.school_id = +v.school_id
        await api('/api/admins/' + admin.id, { method: 'PATCH', body }); onSaved('Admin updated')
      } else {
        const r = await api('/api/admins', { method: 'POST', body: { ...v, role, school_id: platform ? null : +v.school_id } })
        setCreated(r)
      }
    } catch (e) { setErr(e.message) }
  }
  if (created) return (
    <Modal title={ROLE[created.role]?.label + ' created'} onClose={() => onSaved('Admin created')} footer={<button className="btn primary" onClick={() => onSaved('Admin created')}>Done</button>}>
      <p style={{ margin: 0 }}>Share these sign in details with {created.name}. The password is shown once.</p>
      <div className="secret">{created.email}<br />{created.temp_password}</div>
      <div className="note">They sign in on the {ROLE[created.role]?.portal} login page
        ({ROLE[created.role]?.where}) and can change the password there.</div>
    </Modal>)
  return (
    <Modal title={admin ? 'Edit admin' : 'Add an admin'} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>{admin ? 'Save changes' : 'Create admin'}</button></>}>
      {err && <div className="err">{err}</div>}
      {!admin && <Field label="Role" hint={ROLE[role].what}>
        <select className="input" {...bind('role')}>
          <option value="admin" disabled={!schools.length}>School Admin{schools.length ? '' : ' — add a school first'}</option>
          <option value="platform_admin">Platform Admin</option>
        </select></Field>}
      <div className="grid2"><Field label="Full name"><input className="input" {...bind('name')} /></Field><Field label="Phone"><input className="input" {...bind('phone')} /></Field></div>
      <Field label="Email" hint={admin ? 'Email cannot be changed' : 'Used to sign in'}><input className="input" type="email" {...bind('email')} disabled={!!admin} /></Field>
      {(admin ? admin.role === 'admin' : !platform) &&
        <Field label="School"><select className="input" {...bind('school_id')}>{schools.map(s => <option key={s.id} value={s.id}>{s.name}, {s.city}</option>)}</select></Field>}
      {platform && <div className="note">A platform admin belongs to no school. They run the
        factory, which is the same for every school, and they are never shown what a school pays.</div>}
    </Modal>)
}

export default function Admins() {
  const [q, setQ] = useState('')
  const { data, reload } = useLoad('/api/admins?q=' + encodeURIComponent(q), [q])
  const { data: schools } = useLoad('/api/schools')
  const [edit, setEdit] = useState(null); const [confirm, setConfirm] = useState(null); const [pw, setPw] = useState(null)
  const toast = useToast()
  const act = async (fn, msg) => { try { await fn(); toast(msg); reload() } catch (e) { toast(e.message, true) } }
  return (
    <Page title="Admins" sub="School admins run one school. Platform admins run book production for all of them."
      actions={<button className="btn primary" onClick={() => setEdit({})} disabled={!schools}><Icon n="plus" s={16} />Add admin</button>}>
      <div className="toolbar"><input className="input" placeholder="Search name or email" value={q} onChange={e => setQ(e.target.value)} /></div>
      <div className="card">
        <table className="t"><thead><tr><th>Name</th><th>Role</th><th>School</th><th>Status</th><th>Last sign in</th><th>Added</th><th /></tr></thead>
          <tbody>{data?.map(a => (
            <tr key={a.id}>
              <td><b>{a.name}</b><div className="muted">{a.email}</div></td>
              <td>{a.role === 'platform_admin' ? <Tag s="info">Platform Admin</Tag> : 'School Admin'}</td>
              <td>{a.school}</td><td><Tag s={a.status} /></td>
              <td className="muted">{when(a.last_login) || 'Never'}</td><td className="muted">{when(a.created_at)}</td>
              <td className="acts">
                <button className="btn ghost sm" onClick={() => setEdit(a)}>Edit</button>
                <button className="btn ghost sm" onClick={() => act(async () => setPw(await api(`/api/admins/${a.id}/reset-password`, { method: 'POST' })), 'Password reset')}>Reset password</button>
                <button className="btn ghost sm" onClick={() => act(() => api('/api/admins/' + a.id, { method: 'PATCH', body: { status: a.status === 'active' ? 'suspended' : 'active' } }), a.status === 'active' ? 'Admin suspended' : 'Admin reactivated')}>{a.status === 'active' ? 'Suspend' : 'Reactivate'}</button>
                <button className="btn ghost sm" style={{ color: 'var(--red)' }} onClick={() => setConfirm(a)}>Remove</button>
              </td>
            </tr>))}</tbody></table>
        {data && !data.length && <div className="empty">No admins yet. A platform admin can be added straight away; a school admin needs a school first.</div>}
      </div>
      {edit && schools && <AdminForm admin={edit.id ? edit : null} schools={schools} onClose={() => setEdit(null)} onSaved={m => { setEdit(null); toast(m); reload() }} />}
      {confirm && <Confirm text={`Remove ${confirm.name}? They lose access immediately.`} yes="Remove admin" onClose={() => setConfirm(null)} onYes={() => { act(() => api('/api/admins/' + confirm.id, { method: 'DELETE' }), 'Admin removed'); setConfirm(null) }} />}
      {pw && <Modal title="New password" onClose={() => setPw(null)} footer={<button className="btn primary" onClick={() => setPw(null)}>Done</button>}><p style={{ margin: 0 }}>Shown once. Share it securely.</p><div className="secret">{pw.temp_password}</div></Modal>}
    </Page>
  )
}

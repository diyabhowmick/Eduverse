import { useRef, useState } from 'react'
import { api, when } from '../../api'
import { useLoad, Page, Modal, Field, Tag, useToast, useForm, Icon, Confirm } from '../../ui'

function download(name, text) { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' })); a.download = name; a.click() }

function StudentForm({ s, classes, onClose, onSaved }) {
  const [v, , bind] = useForm(s || { name: '', roll_no: '', email: '', phone: '', class_id: '' })
  const [err, setErr] = useState(''); const [made, setMade] = useState(null)
  async function save() {
    const body = { name: v.name, roll_no: v.roll_no, phone: v.phone, class_id: v.class_id ? +v.class_id : null }
    try {
      if (s) { await api('/api/school/students/' + s.id, { method: 'PATCH', body }); onSaved('Student updated') }
      else setMade(await api('/api/school/students', { method: 'POST', body: { ...body, email: v.email } }))
    } catch (e) { setErr(e.message) }
  }
  if (made) return <Modal title="Student added" onClose={() => onSaved('Student added')} footer={<button className="btn primary" onClick={() => onSaved('Student added')}>Done</button>}>
    <p style={{ margin: 0 }}>Give these sign in details to {made.name}. The password is shown once.</p><div className="secret">{made.email}<br />{made.temp_password}</div></Modal>
  return (
    <Modal title={s ? 'Edit student' : 'Add student'} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>{s ? 'Save changes' : 'Add student'}</button></>}>
      {err && <div className="err">{err}</div>}
      <Field label="Full name"><input className="input" {...bind('name')} /></Field>
      <div className="grid2">
        <Field label="Roll number"><input className="input" {...bind('roll_no')} /></Field>
        <Field label="Class"><select className="input" {...bind('class_id')}><option value="">No class yet</option>{classes.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select></Field>
        {!s && <Field label="Email" hint="Leave empty to create a login ID"><input className="input" type="email" {...bind('email')} /></Field>}
        <Field label="Parent phone"><input className="input" {...bind('phone')} /></Field>
      </div>
    </Modal>)
}

function BulkUpload({ onClose, onDone }) {
  const [file, setFile] = useState(null); const [preview, setPreview] = useState(null); const [result, setResult] = useState(null)
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false); const ref = useRef()
  async function send(commit) {
    const f = new FormData(); f.append('file', file); f.append('commit', commit); setBusy(true); setErr('')
    try { const r = await api('/api/school/students/upload', { method: 'POST', form: f }); commit ? setResult(r) : setPreview(r) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  async function template() { const r = await fetch('/api/school/students/template', { headers: { Authorization: 'Bearer ' + localStorage.getItem('ev_token') } }); download('students_template.csv', await r.text()) }
  if (result) return <Modal title="Students added" onClose={onDone} footer={<><button className="btn" onClick={onDone}>Close</button><button className="btn primary" onClick={() => download('student_logins.csv', result.credentials_csv)}><Icon n="download" s={16} />Download logins</button></>}>
    <p style={{ margin: 0 }}><b>{result.summary.added}</b> students added{result.summary.new_classes.length ? `, new classes ${result.summary.new_classes.join(', ')}` : ''}.</p>
    <div className="note">Download the logins file now. Passwords are not shown again; you can reset any student's password later.</div></Modal>
  const s = preview?.summary
  return (
    <Modal title="Upload students" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button>
      {preview ? <button className="btn primary" disabled={busy || !s.ready || s.ready > s.seats_free} onClick={() => send(true)}>Add {s.ready} students</button>
        : <button className="btn primary" disabled={!file || busy} onClick={() => send(false)}>{busy ? 'Checking' : 'Check file'}</button>}</>}>
      <div className="steps">{!preview ? <b>1. Choose file</b> : <span>1. Choose file</span>}{preview ? <b>2. Check rows</b> : <span>2. Check rows</span>}<span>3. Add students</span></div>
      {err && <div className="err">{err}</div>}
      {!preview && <>
        <div className="drop" onClick={() => ref.current.click()}><Icon n="upload" s={22} /><div style={{ marginTop: 6 }}>{file ? <b>{file.name}</b> : 'Choose a CSV or Excel file'}</div>
          <input ref={ref} hidden type="file" accept=".csv,.xlsx" onChange={e => setFile(e.target.files[0])} /></div>
        <div className="note">Columns: name, roll_no, grade, section, email, phone. Only name is required. Missing classes are created for you. <button className="btn ghost sm" onClick={template}>Download template</button></div>
      </>}
      {preview && <>
        <div className="note"><b>{s.ready}</b> ready, <b>{s.with_problems}</b> with problems, <b>{s.seats_free}</b> seats free{s.new_classes.length ? `. New classes: ${s.new_classes.join(', ')}` : ''}.</div>
        {s.ready > s.seats_free && <div className="err">Not enough seats. Request more seats before adding these students.</div>}
        <div className="check-list" style={{ maxHeight: 260 }}><table className="t"><thead><tr><th>Row</th><th>Name</th><th>Class</th><th>Problem</th></tr></thead>
          <tbody>{preview.rows.map(r => <tr key={r.row} className={r.problems.length ? 'row-bad' : ''}><td className="muted">{r.row}</td><td>{r.name}</td><td>{r.grade}{r.section}</td><td className="muted">{r.problems.join(', ') || 'Ready'}</td></tr>)}</tbody></table></div>
        <div className="muted" style={{ fontSize: 12 }}>Rows with problems are skipped. Fix them in the file and upload again.</div>
      </>}
    </Modal>)
}

export default function Students() {
  const [cls, setCls] = useState(''); const [q, setQ] = useState(''); const [st, setSt] = useState('')
  const classes = useLoad('/api/school/classes')
  const { data, reload } = useLoad(`/api/school/students?${cls !== '' ? 'class_id=' + cls + '&' : ''}q=${encodeURIComponent(q)}&status=${st}`, [cls, q, st])
  const [edit, setEdit] = useState(null); const [bulk, setBulk] = useState(false); const [del, setDel] = useState(null); const [pw, setPw] = useState(null)
  const [sel, setSel] = useState([]); const [moveTo, setMoveTo] = useState('')
  const toast = useToast()
  const act = async (fn, m) => { try { await fn(); toast(m); reload(); classes.reload() } catch (e) { toast(e.message, true) } }
  const all = data?.length && sel.length === data.length
  const bulkAct = (action, extra = {}) => act(() => api('/api/school/students/bulk-action', { method: 'POST', body: { ids: sel, action, ...extra } }).then(() => setSel([])), 'Students updated')
  return (
    <Page title="Students" sub="Everyone enrolled in your school"
      actions={<><button className="btn" onClick={() => setBulk(true)}><Icon n="upload" s={16} />Upload students</button><button className="btn primary" onClick={() => setEdit({})}><Icon n="plus" s={16} />Add student</button></>}>
      <div className="toolbar">
        <input className="input" placeholder="Search name, roll number or email" value={q} onChange={e => setQ(e.target.value)} />
        <select className="input" style={{ maxWidth: 170 }} value={cls} onChange={e => setCls(e.target.value)}><option value="">All classes</option><option value="0">Without a class</option>{classes.data?.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select>
        <select className="input" style={{ maxWidth: 150 }} value={st} onChange={e => setSt(e.target.value)}><option value="">Any status</option><option value="active">Active</option><option value="suspended">Suspended</option></select>
        <span className="muted" style={{ marginLeft: 'auto' }}>{data?.length ?? ''} students</span>
      </div>
      {sel.length > 0 && <div className="selbar"><b>{sel.length} selected</b>
        <button className="btn sm" onClick={() => bulkAct('activate')}>Activate</button><button className="btn sm" onClick={() => bulkAct('suspend')}>Suspend</button>
        <select value={moveTo} onChange={e => setMoveTo(e.target.value)}><option value="">Move to class</option>{classes.data?.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select>
        <button className="btn sm" disabled={!moveTo} onClick={() => bulkAct('move', { class_id: +moveTo })}>Move</button>
        <button className="btn sm" style={{ marginLeft: 'auto' }} onClick={() => setSel([])}>Clear</button></div>}
      <div className="card">
        <table className="t"><thead><tr><th style={{ width: 36 }}><input type="checkbox" checked={!!all} onChange={() => setSel(all ? [] : data.map(s => s.id))} aria-label="Select all" style={{ accentColor: 'var(--red)' }} /></th>
          <th>Student</th><th>Roll no</th><th>Class</th><th>Reading progress</th><th>Last read</th><th>Status</th><th /></tr></thead>
          <tbody>{data?.slice(0, 300).map(s => (
            <tr key={s.id}><td><input type="checkbox" checked={sel.includes(s.id)} onChange={() => setSel(x => x.includes(s.id) ? x.filter(i => i !== s.id) : [...x, s.id])} aria-label={'Select ' + s.name} style={{ accentColor: 'var(--red)' }} /></td>
              <td><b>{s.name}</b><div className="muted">{s.email}</div></td><td>{s.roll_no}</td><td>{s.class || <span className="tag warn">No class</span>}</td>
              <td style={{ minWidth: 130 }}><div className="bar-track"><i style={{ width: s.progress + '%' }} /></div><div className="muted">{s.progress}% of assigned books</div></td>
              <td className="muted">{when(s.last_read) || 'Not yet'}</td><td><Tag s={s.status} /></td>
              <td className="acts"><button className="btn ghost sm" onClick={() => setEdit(s)}>Edit</button>
                <button className="btn ghost sm" onClick={() => act(async () => setPw(await api(`/api/school/students/${s.id}/reset-password`, { method: 'POST' })), 'Password reset')}>Reset password</button>
                <button className="btn ghost sm" onClick={() => act(() => api('/api/school/students/' + s.id, { method: 'PATCH', body: { status: s.status === 'active' ? 'suspended' : 'active' } }), s.status === 'active' ? 'Student suspended' : 'Student activated')}>{s.status === 'active' ? 'Suspend' : 'Activate'}</button>
                <button className="btn ghost sm" style={{ color: 'var(--red)' }} onClick={() => setDel(s)}>Remove</button></td></tr>))}</tbody></table>
        {data && data.length > 300 && <div className="empty">Showing 300 of {data.length}. Filter by class or search to narrow down.</div>}
        {data && !data.length && <div className="empty">No students match. Add one, or upload your class lists.</div>}
      </div>
      {edit && classes.data && <StudentForm s={edit.id ? edit : null} classes={classes.data} onClose={() => setEdit(null)} onSaved={m => { setEdit(null); toast(m); reload(); classes.reload() }} />}
      {bulk && <BulkUpload onClose={() => setBulk(false)} onDone={() => { setBulk(false); reload(); classes.reload() }} />}
      {del && <Confirm text={`Remove ${del.name}? Their reading progress is deleted and the seat is freed.`} yes="Remove student" onClose={() => setDel(null)} onYes={() => { act(() => api('/api/school/students/' + del.id, { method: 'DELETE' }), 'Student removed'); setDel(null) }} />}
      {pw && <Modal title="New password" onClose={() => setPw(null)} footer={<button className="btn primary" onClick={() => setPw(null)}>Done</button>}><p style={{ margin: 0 }}>Shown once.</p><div className="secret">{pw.email}<br />{pw.temp_password}</div></Modal>}
    </Page>
  )
}

import { useState } from 'react'
import { api } from '../../api'
import { useLoad, Page, Modal, Field, useToast, useForm, Icon, Confirm } from '../../ui'

function ClassForm({ c, onClose, onSaved }) {
  const [v, , bind] = useForm(c || { grade: '', section: '', class_teacher: '' }); const [err, setErr] = useState('')
  async function save() { try { await api(c ? '/api/school/classes/' + c.id : '/api/school/classes', { method: c ? 'PUT' : 'POST', body: v }); onSaved(c ? 'Class updated' : 'Class added') } catch (e) { setErr(e.message) } }
  return <Modal title={c ? 'Edit class' : 'Add class'} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save</button></>}>
    {err && <div className="err">{err}</div>}
    <div className="grid2"><Field label="Class"><input className="input" placeholder="8" {...bind('grade')} /></Field><Field label="Section"><input className="input" placeholder="A" {...bind('section')} /></Field></div>
    <Field label="Class teacher"><input className="input" {...bind('class_teacher')} /></Field></Modal>
}

export function AssignBooks({ c, onClose, onSaved }) {
  const { data: cat } = useLoad('/api/school/catalogue'); const { data: ov } = useLoad('/api/school/overview')
  const [ids, setIds] = useState(c.books.map(b => b.id)); const [all, setAll] = useState(false); const [err, setErr] = useState('')
  const limit = ov?.school.max_books || 0
  const live = cat?.filter(b => b.status === 'live' && (all || b.grade === c.grade)) || []
  async function save() { try { await api(`/api/school/classes/${c.id}/books`, { method: 'PUT', body: { book_ids: ids } }); onSaved('Books assigned') } catch (e) { setErr(e.message) } }
  return <Modal title={'Books for ' + c.label} onClose={onClose} footer={<><span className="muted" style={{ marginRight: 'auto' }}>{ids.length}{limit ? ' of ' + limit : ''} selected</span><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save books</button></>}>
    {err && <div className="err">{err}</div>}
    <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 }}><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)} style={{ accentColor: 'var(--red)' }} />Show books for other classes too</label>
    <div className="check-list">{live.map(b => <label key={b.id}><input type="checkbox" checked={ids.includes(b.id)} disabled={!ids.includes(b.id) && limit && ids.length >= limit}
      onChange={() => setIds(x => x.includes(b.id) ? x.filter(i => i !== b.id) : [...x, b.id])} /><span><b>{b.title}</b><div className="muted" style={{ fontSize: 12 }}>{b.board}, {b.medium}{b.your_board ? '' : ', different board'}</div></span></label>)}
      {cat && !live.length && <div className="empty">No live books for Class {c.grade} yet</div>}</div>
    {limit > 0 && <div className="muted" style={{ fontSize: 12 }}>Your plan allows {limit} books per class.</div>}
  </Modal>
}

export default function Classes() {
  const { data, reload } = useLoad('/api/school/classes')
  const [edit, setEdit] = useState(null); const [assign, setAssign] = useState(null); const [del, setDel] = useState(null)
  const toast = useToast()
  const done = m => { setEdit(null); setAssign(null); toast(m); reload() }
  return (
    <Page title="Classes" sub="Sections, class teachers and the books each class reads" actions={<button className="btn primary" onClick={() => setEdit({})}><Icon n="plus" s={16} />Add class</button>}>
      <div className="classes-grid">{data?.map(c => (
        <div className="class-card" key={c.id}>
          <h4>{c.label}</h4>
          <div className="meta">{c.students} students{c.class_teacher ? `, ${c.class_teacher}` : ''}</div>
          <div className="chips">{c.books.length ? c.books.map(b => <span className="chip" key={b.id}>{b.subject}</span>) : <span className="tag warn">No books yet</span>}</div>
          <div className="foot"><button className="btn sm" onClick={() => setAssign(c)}>Assign books</button><button className="btn ghost sm" onClick={() => setEdit(c)}>Edit</button>
            <button className="btn ghost sm" style={{ color: 'var(--red)', marginLeft: 'auto' }} onClick={() => setDel(c)}>Delete</button></div>
        </div>))}</div>
      {data && !data.length && <div className="card empty">No classes yet. Add one, or upload students and classes are created for you.</div>}
      {edit && <ClassForm c={edit.id ? edit : null} onClose={() => setEdit(null)} onSaved={done} />}
      {assign && <AssignBooks c={assign} onClose={() => setAssign(null)} onSaved={done} />}
      {del && <Confirm text={`Delete ${del.label}? Only empty classes can be deleted.`} yes="Delete class" onClose={() => setDel(null)} onYes={async () => { try { await api('/api/school/classes/' + del.id, { method: 'DELETE' }); done('Class deleted') } catch (e) { toast(e.message, true) } setDel(null) }} />}
    </Page>
  )
}

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, inr, day } from '../api'
import { useLoad, Page, Modal, Field, Tag, useToast, useForm, Icon } from '../ui'

const STAGES = [['', 'All'], ['live', 'Live'], ['in_review', 'In review'], ['rejected', 'Sent back'], ['processing', 'Processing'], ['upcoming', 'Upcoming'], ['retired', 'Retired']]

function BookForm({ book, onClose, onSaved }) {
  const [v, , bind] = useForm(book || { title: '', subject: '', board: 'Tamil Nadu State Board', grade: '', medium: 'English', edition: '', price: 0, status: 'upcoming' })
  const [err, setErr] = useState('')
  async function save() {
    const body = { ...v, price: +v.price }
    try { await api(book ? '/api/books/' + book.id : '/api/books', { method: book ? 'PATCH' : 'POST', body }); onSaved(book ? 'Book updated' : 'Added as upcoming') } catch (e) { setErr(e.message) }
  }
  return (
    <Modal title={book ? 'Edit book details' : 'Add upcoming book'} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save</button></>}>
      {err && <div className="err">{err}</div>}
      {!book && <div className="note">Students see upcoming books in the store. To digitise a book, upload it in Processing.</div>}
      <Field label="Title"><input className="input" {...bind('title')} /></Field>
      <div className="grid2">
        <Field label="Subject"><input className="input" {...bind('subject')} /></Field>
        <Field label="Class"><input className="input" {...bind('grade')} /></Field>
        <Field label="Board"><input className="input" {...bind('board')} /></Field>
        <Field label="Medium"><input className="input" {...bind('medium')} /></Field>
        <Field label="Edition"><input className="input" {...bind('edition')} /></Field>
        <Field label="Student price (₹)"><input className="input" type="number" min="0" {...bind('price')} /></Field>
      </div>
    </Modal>)
}

export default function Catalogue() {
  const [stage, setStage] = useState('')
  const { data, reload } = useLoad('/api/books?status=' + stage, [stage])
  const { data: reviewers } = useLoad('/api/reviewers')
  const rname = id => reviewers?.find(r => r.id === id)?.name
  const assign = async (b, rid) => { try { await api('/api/reviewers/books/' + b.id, { method: 'PUT', body: { reviewer_id: rid ? +rid : null } }); toast('Reviewer updated'); reload() } catch (e) { toast(e.message, true) } }
  const [edit, setEdit] = useState(null)
  const toast = useToast()
  const move = async (b, action, msg) => { try { await api(`/api/books/${b.id}/${action}`, { method: 'POST' }); toast(msg); reload() } catch (e) { toast(e.message, true) } }
  return (
    <Page title="Book catalogue" sub="A book is published when a reviewer approves every page"
      actions={<><button className="btn" onClick={() => setEdit({})}><Icon n="plus" s={16} />Add upcoming book</button><Link className="btn primary" to="/sa/processing?add=1"><Icon n="upload" s={16} />Add document</Link></>}>
      <div className="toolbar"><div className="seg">{STAGES.map(([k, l]) => <button key={k} className={stage === k ? 'on' : ''} onClick={() => setStage(k)}>{l}</button>)}</div></div>
      <div className="card">
        <table className="t"><thead><tr><th>Book</th><th>Board</th><th>Class</th><th className="num">Pages</th><th className="num">Price</th><th>Stage</th><th /></tr></thead>
          <tbody>{data?.map(b => (
            <tr key={b.id}>
              <td><b>{b.title}</b><div className="muted">{b.subject}, {b.medium}{b.edition ? ', ' + b.edition : ''}</div></td>
              <td>{b.board}</td><td>{b.grade}</td><td className="num">{b.pages || ''}</td><td className="num">{inr(b.price)}</td>
              <td><Tag s={b.status} />{b.live_at && b.status === 'live' && <div className="muted">since {day(b.live_at)}{b.reviewed_by ? ', by ' + b.reviewed_by : ''}</div>}
                {b.status === 'rejected' && b.review_note && <div className="muted" style={{ maxWidth: 260 }}>{b.review_note}</div>}
                {['in_review', 'processing'].includes(b.status) && reviewers && <select className="input" style={{ marginTop: 4, padding: '3px 6px', fontSize: 12, maxWidth: 190 }} value={b.assigned_reviewer_id || ''} onChange={e => assign(b, e.target.value)}>
                  <option value="">Any reviewer</option>{reviewers.filter(r => r.status === 'active').map(r => <option key={r.id} value={r.id}>Reviewer: {r.name}</option>)}</select>}</td>
              <td className="acts">
                {b.status === 'approved' && <button className="btn primary sm" onClick={() => move(b, 'go_live', 'Book is live')}>Go live</button>}
                {b.status === 'live' && <button className="btn ghost sm" title="Send it back to the reviewer. Approved pages are kept." onClick={() => { if (confirm('Send this book back to the reviewer? Students will not see it until it is approved again. Approved pages are kept, so only what changed is checked.')) move(b, 'pull_back', 'Sent back to the reviewer') }}>Pull back</button>}
                {b.status === 'live' && <button className="btn ghost sm" onClick={() => move(b, 'retire', 'Book retired')}>Retire</button>}
                {b.status === 'retired' && <button className="btn ghost sm" onClick={() => move(b, 'restore', 'Book is live again')}>Restore</button>}
                <button className="btn ghost sm" onClick={() => setEdit(b)}>Edit</button>
              </td>
            </tr>))}</tbody></table>
        {data && !data.length && <div className="empty">No books in this stage</div>}
      </div>
      {edit && <BookForm book={edit.id ? edit : null} onClose={() => setEdit(null)} onSaved={m => { setEdit(null); toast(m); reload() }} />}
    </Page>
  )
}

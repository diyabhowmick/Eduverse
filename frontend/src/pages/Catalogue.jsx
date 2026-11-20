import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, inr, day } from '../api'
import { useLoad, Page, Modal, Field, Tag, useToast, useForm, Icon, ask } from '../ui'

const STAGES = [['', 'All'], ['live', 'Live'], ['in_review', 'In review'], ['rejected', 'Sent back'], ['processing', 'Processing'], ['upcoming', 'Upcoming'], ['retired', 'Retired']]

function BookForm({ book, onClose, onSaved }) {
  const [v, setV, bind] = useForm(book || { title: '', subject: '', board: '', grade: '', medium: 'English', edition: '', price: 0, status: 'upcoming',
    track: 'textbook', level: 'school', exam: '', university: '', course: '', semester: '', linked_book_ids: [] })
  const [err, setErr] = useState('')
  const { data: tx } = useLoad('/api/taxonomy')
  const { data: texts } = useLoad('/api/books?track=textbook')
  const exam = v.track === 'exam'
  async function save() {
    const body = { ...v, price: +v.price, linked_book_ids: (v.linked_book_ids || []).map(Number) }
    delete body.id; delete body.created_at; delete body.live_at; delete body.pages; delete body.assigned_reviewer_id; delete body.review_note; delete body.reviewed_by; if (book) delete body.status
    try { await api(book ? '/api/books/' + book.id : '/api/books', { method: book ? 'PATCH' : 'POST', body }); onSaved(book ? 'Book updated' : 'Added as upcoming') } catch (e) { setErr(e.message) }
  }
  return (
    <Modal title={book ? (exam ? 'Edit exam pack' : 'Edit book details') : 'Add to the catalogue'} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save</button></>}>
      {err && <div className="err">{err}</div>}
      {!book && <div className="seg" style={{ marginBottom: 12 }}>
        <button className={!exam ? 'on' : ''} onClick={() => setV(x => ({ ...x, track: 'textbook', level: x.level === 'competitive' ? 'school' : x.level }))}>Textbook</button>
        <button className={exam ? 'on' : ''} onClick={() => setV(x => ({ ...x, track: 'exam' }))}>Exam pack</button></div>}
      {!book && <div className="note">{exam ? 'An exam pack holds past papers. Add the papers on its page; it goes live once a paper is approved.' : 'Students see upcoming books in the store. To digitise a book, upload it in Processing.'}</div>}
      <datalist id="dl-boards">{tx?.boards.map(b => <option key={b} value={b} />)}</datalist>
      <datalist id="dl-exams">{(tx?.exams[v.level] || []).map(b => <option key={b} value={b} />)}</datalist>
      <Field label="Title"><input className="input" {...bind('title')} /></Field>
      <div className="grid2">
        <Field label="Level"><select className="input" {...bind('level')}>{Object.entries(tx?.levels || { school: 'School' }).filter(([k]) => exam || k !== 'competitive').map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
        <Field label="Subject"><input className="input" {...bind('subject')} /></Field>
        {exam && <Field label="Exam"><input className="input" list="dl-exams" placeholder="NEET UG, Class 10 Board" {...bind('exam')} /></Field>}
        {v.level === 'school' && <><Field label="Board"><input className="input" list="dl-boards" {...bind('board')} /></Field><Field label="Class"><input className="input" {...bind('grade')} /></Field></>}
        {v.level === 'degree' && <><Field label="University"><input className="input" {...bind('university')} /></Field><Field label="Course"><input className="input" placeholder="B.Sc Physics" {...bind('course')} /></Field>
          <Field label="Semester"><input className="input" {...bind('semester')} /></Field></>}
        {v.level === 'competitive' && <Field label="Class (optional)"><input className="input" {...bind('grade')} /></Field>}
        {!exam && <Field label="Medium"><input className="input" {...bind('medium')} /></Field>}
        {!exam && <Field label="Edition"><input className="input" {...bind('edition')} /></Field>}
        <Field label="Individual price (₹)" hint="What a student pays in the store. Organisations pay per seat on their plan."><input className="input" type="number" min="0" {...bind('price')} /></Field>
      </div>
      {exam && <Field label="Textbooks for chapter tagging" hint="Past questions are tagged to chapters of these books, and students can jump to the chapter">
        <select className="input" multiple size={5} value={(v.linked_book_ids || []).map(String)} onChange={e => setV(x => ({ ...x, linked_book_ids: [...e.target.selectedOptions].map(o => +o.value) }))}>
          {texts?.map(b => <option key={b.id} value={b.id}>{b.title}, {b.board || b.university} {b.grade}</option>)}</select></Field>}
    </Modal>)
}

export default function Catalogue() {
  const [stage, setStage] = useState(''); const [track, setTrack] = useState('')
  const { data, reload } = useLoad(`/api/books?status=${stage}&track=${track}`, [stage, track])
  const { data: reviewers } = useLoad('/api/reviewers')
  const rname = id => reviewers?.find(r => r.id === id)?.name
  const assign = async (b, rid) => { try { await api('/api/reviewers/books/' + b.id, { method: 'PUT', body: { reviewer_id: rid ? +rid : null } }); toast('Reviewer updated'); reload() } catch (e) { toast(e.message, true) } }
  const [edit, setEdit] = useState(null)
  const toast = useToast()
  const move = async (b, action, msg) => { try { await api(`/api/books/${b.id}/${action}`, { method: 'POST' }); toast(msg); reload() } catch (e) { toast(e.message, true) } }
  return (
    <Page title="Catalogue" sub="Textbooks are published when a reviewer approves every page. Exam packs go live once a past paper is approved."
      actions={<><div className="seg">{[['', 'All'], ['textbook', 'Textbooks'], ['exam', 'Exam packs']].map(([k, l]) => <button key={k} className={track === k ? 'on' : ''} onClick={() => setTrack(k)}>{l}</button>)}</div>
        <button className="btn" onClick={() => setEdit({})}><Icon n="plus" s={16} />Add upcoming</button><Link className="btn primary" to="/sa/add"><Icon n="upload" s={16} />Add content</Link></>}>
      <div className="toolbar"><div className="seg">{STAGES.map(([k, l]) => <button key={k} className={stage === k ? 'on' : ''} onClick={() => setStage(k)}>{l}</button>)}</div></div>
      <div className="card">
        <table className="t"><thead><tr><th>Book</th><th>Shelf</th><th>Class</th><th className="num">Pages</th><th className="num">Price</th><th>Stage</th><th /></tr></thead>
          <tbody>{data?.map(b => (
            <tr key={b.id}>
              <td><b>{b.title}</b><div className="muted">{b.track === 'exam' ? <span className="tag" style={{ marginRight: 6 }}>Exam pack</span> : null}{[b.subject, b.track !== 'exam' && b.medium, b.edition].filter(Boolean).join(', ')}</div></td>
              <td>{b.track === 'exam' ? b.exam : ''}{b.track === 'exam' && (b.board || b.university) ? <div className="muted">{b.board || b.university}</div> : b.level === 'degree' ? <>{b.university}<div className="muted">{b.course}{b.semester ? ', Sem ' + b.semester : ''}</div></> : b.board}</td><td>{b.grade}</td><td className="num">{b.pages || ''}</td><td className="num">{inr(b.price)}</td>
              <td><Tag s={b.status} />{b.live_at && b.status === 'live' && <div className="muted">since {day(b.live_at)}{b.reviewed_by ? ', by ' + b.reviewed_by : ''}</div>}
                {b.status === 'rejected' && b.review_note && <div className="muted" style={{ maxWidth: 260 }}>{b.review_note}</div>}
                {['in_review', 'processing'].includes(b.status) && reviewers && <select className="input" style={{ marginTop: 4, padding: '3px 6px', fontSize: 12, maxWidth: 190 }} value={b.assigned_reviewer_id || ''} onChange={e => assign(b, e.target.value)}>
                  <option value="">Any reviewer</option>{reviewers.filter(r => r.status === 'active').map(r => <option key={r.id} value={r.id}>Reviewer: {r.name}</option>)}</select>}</td>
              <td className="acts">
                {b.track === 'exam' && <Link className="btn sm" to={'/sa/exams/' + b.id}>Question papers</Link>}
                {(b.status === 'approved' || (b.track === 'exam' && !['live', 'retired'].includes(b.status))) && <button className="btn primary sm" onClick={() => move(b, 'go_live', 'Now live')}>Go live</button>}
                {b.status === 'live' && <button className="btn ghost sm" title="Send it back to the reviewer. Approved pages are kept." onClick={() => ask('Send this book back to the reviewer? Students will not see it until it is approved again. Approved pages are kept, so only what changed is checked.', { yes: 'Pull back' }).then(ok => ok && move(b, 'pull_back', 'Sent back to the reviewer'))}>Pull back</button>}
                {b.status === 'live' && <button className="btn ghost sm" onClick={() => move(b, 'retire', 'Book retired')}>Retire</button>}
                {b.status === 'retired' && <button className="btn ghost sm" onClick={() => move(b, 'restore', 'Book is live again')}>Restore</button>}
                <button className="btn ghost sm" onClick={() => setEdit(b)}>Edit</button>
              </td>
            </tr>))}</tbody></table>
        {data && !data.length && <div className="empty">Nothing in this stage</div>}
      </div>
      {edit && <BookForm book={edit.id ? edit : null} onClose={() => setEdit(null)} onSaved={m => { setEdit(null); toast(m); reload() }} />}
    </Page>
  )
}

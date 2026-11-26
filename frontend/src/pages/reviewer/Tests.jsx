// Chapter tests: write questions from a book, check each one, approve what students may see.
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../api'
import { useLoad, Page, Tag, Modal, Field, useToast, plural, BookImg } from '../../ui'
import '../../tests.css'

const LEVEL = { easy: 'Easy', medium: 'Medium', hard: 'Hard' }
const KIND = { mcq: 'Choose one', fill: 'Fill in', figure: 'Figure' }

export function TestBooks() {
  const { data } = useLoad('/api/review/tests')
  return (
    <Page title="Chapter tests" sub="Questions written from each book. Students only see the ones you approve.">
      <div className="card"><table className="t"><thead><tr><th>Book</th><th>Approved</th><th>Waiting for you</th><th /></tr></thead>
        <tbody>{data?.map(b => <tr key={b.id}><td><b>{b.title}</b><div className="muted">{[b.board, b.grade && 'Class ' + b.grade, b.subject].filter(Boolean).join(', ')}</div></td>
          <td>{b.approved}</td><td>{b.draft ? <Tag s="processing">{plural(b.draft, 'question')}</Tag> : <span className="muted">None</span>}</td>
          <td className="acts"><Link className="btn sm" to={'/review/tests/' + b.id}>{b.approved + b.draft ? 'Open' : 'Write questions'}</Link></td></tr>)}</tbody></table>
        {data && !data.length && <div className="empty">No books with content yet</div>}</div>
    </Page>
  )
}

function Editor({ q, chapter, bid, onClose, onSaved }) {
  const isNew = !q
  const [f, setF] = useState(() => q ? { text: q.text, options: q.options.length ? q.options : [], answer: q.answer, explanation: q.explanation, level: q.level, qtype: q.qtype }
    : { text: '', options: ['a', 'b', 'c', 'd'].map(k => ({ key: k, text: '' })), answer: 'a', explanation: '', level: 'medium', qtype: 'mcq' })
  const [err, setErr] = useState('')
  const choose = f.qtype !== 'fill'
  async function save() {
    try {
      const body = { ...f, options: choose ? f.options.filter(o => o.text.trim()) : [] }
      if (isNew) await api(`/api/review/tests/${bid}/questions`, { method: 'POST', body: { ...body, chapter } })
      else await api(`/api/review/tests/q/${q.id}`, { method: 'PUT', body })
      onSaved()
    } catch (e) { setErr(e.message) }
  }
  return <Modal title={isNew ? 'Write a question' : 'Edit question'} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save</button></>}>
    {err && <div className="err">{err}</div>}
    {isNew && <Field label="Kind"><div className="chips">{[['mcq', 'Choose one'], ['fill', 'Fill in']].map(([k, l]) =>
      <button key={k} type="button" className={'chip' + (f.qtype === k ? ' on' : '')} onClick={() => setF({ ...f, qtype: k, answer: k === 'fill' ? '' : 'a' })}>{l}</button>)}</div></Field>}
    <Field label="Question"><textarea className="input" rows={3} value={f.text} onChange={e => setF({ ...f, text: e.target.value })} /></Field>
    {choose ? <Field label="Options" hint="Tick the right one">{f.options.map((o, i) => <div key={o.key} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
      <input type="radio" name="ans" checked={f.answer === o.key} onChange={() => setF({ ...f, answer: o.key })} aria-label={'Option ' + o.key + ' is right'} />
      <input className="input" value={o.text} onChange={e => setF({ ...f, options: f.options.map((x, j) => j === i ? { ...x, text: e.target.value } : x) })} /></div>)}</Field>
      : <Field label="Answer" hint="Several accepted answers? Separate them with |"><input className="input" value={f.answer} onChange={e => setF({ ...f, answer: e.target.value })} /></Field>}
    <Field label="Why it is right" hint="Eddie uses this when he teaches a student who got it wrong"><textarea className="input" rows={2} value={f.explanation} onChange={e => setF({ ...f, explanation: e.target.value })} /></Field>
    <Field label="Level"><div className="chips">{Object.entries(LEVEL).map(([k, l]) => <button key={k} type="button" className={'chip' + (f.level === k ? ' on' : '')} onClick={() => setF({ ...f, level: k })}>{l}</button>)}</div></Field>
  </Modal>
}

function QCard({ q, n, bid, onChange, onEdit }) {
  const toast = useToast()
  async function act(a) { try { await api(`/api/review/tests/q/${q.id}/${a}`, { method: 'POST' }); onChange() } catch (e) { toast(e.message) } }
  return <div className={'tq ' + q.status}>
    <div className="tq-h"><b>Q{n}</b><span className="tag">{KIND[q.qtype]}</span><span className="tag">{LEVEL[q.level]}</span>
      {q.origin === 'ai' && <span className="tag">Written by AI</span>}{q.origin === 'human' && <span className="tag">Written by a reviewer</span>}
      {q.section_title && <span className="muted" style={{ fontSize: 12 }}>{q.section_title}</span>}
      <span style={{ marginLeft: 'auto' }}>{q.status === 'approved' ? <Tag s="live">Approved</Tag> : <Tag s="processing">Waiting</Tag>}</span></div>
    {q.figure?.image && <BookImg className="tq-fig" src={`/api/content/${bid}/${q.figure.image}`} alt={q.figure.caption || ''} />}
    <div className="tq-t">{q.text}</div>
    {q.options.length > 0 ? <ol className="tq-o">{q.options.map(o => <li key={o.key} className={o.key === q.answer ? 'right' : ''}><span>{o.key}</span>{o.text}</li>)}</ol>
      : <div className="tq-a">Answer: <b>{q.answer.split('|').join(' or ')}</b></div>}
    {q.source && <div className="tq-src"><b>From the book:</b> {q.source}</div>}
    <div className="tq-acts">
      {q.status !== 'approved' ? <button className="btn primary sm" onClick={() => act('approve')}>Approve</button> : <button className="btn sm" onClick={() => act('undo')}>Unapprove</button>}
      <button className="btn sm" onClick={onEdit}>Edit</button>
      <button className="btn ghost sm" onClick={() => act('reject')}>Remove</button>
    </div>
  </div>
}

export default function BookTests() {
  const { id } = useParams(); const toast = useToast()
  const { data, reload } = useLoad('/api/review/tests/' + id, [id])
  const [busy, setBusy] = useState(null)
  const [edit, setEdit] = useState(null)   // { q, chapter }
  if (!data) return <Page title="Chapter tests"><div className="empty">Loading</div></Page>
  async function gen(chapter) {
    setBusy(chapter ?? 'all')
    try { const r = await api(`/api/review/tests/${id}/generate`, { method: 'POST', body: chapter == null ? {} : { chapter } }); toast(r.made ? `${plural(r.made, 'new question')} to check` : 'No new questions found'); if (r.note) toast(r.note); reload() }
    catch (e) { toast(e.message) } finally { setBusy(null) }
  }
  async function approveAll(ch) { try { const r = await api(`/api/review/tests/${id}/chapters/${ch}/approve-all`, { method: 'POST' }); toast(`${plural(r.approved, 'question')} approved`); reload() } catch (e) { toast(e.message) } }
  const total = data.chapters.reduce((a, c) => a + c.questions.length, 0)
  return (
    <Page title={'Chapter tests: ' + data.title} sub={data.ai ? 'Questions are written by AI from the book, and each must quote the book. Check every one before approving.' : 'Questions are written from the book\'s highlighted words and figures. Check, edit or add your own.'}
      actions={<><Link className="btn" to="/review/tests">All books</Link><button className="btn primary" disabled={busy != null} onClick={() => gen(null)}>{busy === 'all' ? 'Writing…' : total ? 'Write more for every unit' : 'Write questions for every unit'}</button></>}>
      <div className="stack">{data.chapters.map(c => {
        const wait = c.questions.filter(q => q.status === 'draft').length, ok = c.questions.length - wait
        return <div className="card" key={c.number}>
          <div className="card-h"><h3>{c.number ? `Unit ${c.number}: ` : ''}{c.title}</h3><span className="sub">{ok} approved{wait ? `, ${wait} waiting` : ''}</span>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {wait > 0 && <button className="btn sm" onClick={() => approveAll(c.number)}>Approve all {wait}</button>}
              <button className="btn sm" onClick={() => setEdit({ q: null, chapter: c.number })}>Write one</button>
              <button className="btn sm" disabled={busy != null} onClick={() => gen(c.number)}>{busy === c.number ? 'Writing…' : 'Write more'}</button></div></div>
          <div className="card-b">{c.questions.length ? <div className="tq-list">{c.questions.map((q, i) => <QCard key={q.id} q={q} n={i + 1} bid={id} onChange={reload} onEdit={() => setEdit({ q, chapter: c.number })} />)}</div>
            : <div className="empty" style={{ padding: 12 }}>No questions yet</div>}</div>
        </div>
      })}</div>
      {edit && <Editor q={edit.q} chapter={edit.chapter} bid={id} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); toast('Saved'); reload() }} />}
    </Page>
  )
}

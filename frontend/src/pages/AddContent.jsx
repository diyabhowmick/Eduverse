import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useLoad, Page, Field, Dropzone, Icon, useToast } from '../ui'

const TYPES = [
  ['book', 'book', 'Book', 'A printed textbook as a PDF or Word file. Scanned is fine. It is converted, then goes to review.'],
  ['document', 'audit', 'Document', 'Notes, guides and study material. Same steps as a book, and it shows as study material in the store.'],
  ['exam', 'job', 'Exam test set', 'A question paper, with its answer key if you have one. Checked by you, then published to the marketplace.'],
]
const STEPS = { book: ['Upload', 'Convert', 'Review', 'Live in store'], document: ['Upload', 'Convert', 'Review', 'Live in store'], exam: ['Upload', 'Read and answer', 'You check', 'Live in marketplace'] }
const LEVELS = { school: 'School', degree: 'Degree college', competitive: 'Competitive exam' }

function Where({ v, set, tx, exam }) {
  const sel = (k, opts, ph) => <select className="input" value={v[k]} onChange={e => set(k, e.target.value)}><option value="">{ph}</option>{opts.map(o => Array.isArray(o) ? <option key={o[0]} value={o[0]}>{o[1]}</option> : <option key={o}>{o}</option>)}</select>
  const text = (k, ph) => <input className="input" placeholder={ph} value={v[k]} onChange={e => set(k, e.target.value)} />
  return <>
    <Field label={exam ? 'Exam type' : 'Curriculum'}><div className="seg" role="radiogroup">{(exam ? ['competitive', 'school', 'degree'] : ['school', 'degree']).map(l =>
      <button key={l} type="button" className={v.level === l ? 'on' : ''} onClick={() => set('level', l)} role="radio" aria-checked={v.level === l}>{LEVELS[l]}</button>)}</div></Field>
    <div className="grid2">
      {exam && <Field label="Exam" hint="Pick from the list or type a new one"><input className="input" list="dl-exam" placeholder="JEE Main" value={v.exam} onChange={e => set('exam', e.target.value)} /><datalist id="dl-exam">{(tx?.exams[v.level] || []).map(x => <option key={x} value={x} />)}</datalist></Field>}
      {v.level === 'school' && <><Field label="Board">{sel('board', tx?.boards || [], 'Pick a board')}</Field><Field label="Class">{sel('grade', (tx?.grades || []).map(g => [g, 'Class ' + g]), 'Pick a class')}</Field></>}
      {v.level === 'degree' && <><Field label="University">{text('university', 'Anna University')}</Field><Field label="Course">{text('course', 'B.Sc Physics')}</Field><Field label="Semester">{text('semester', '3')}</Field></>}
      <Field label="Subject" hint={exam ? 'Leave empty for a full paper' : ''}>{text('subject', exam ? 'All subjects' : 'Physics')}</Field>
    </div></>
}

export default function AddContent() {
  const [params] = useSearchParams(); const nav = useNavigate(); const toast = useToast()
  const [type, setType] = useState(TYPES.some(t => t[0] === params.get('type')) ? params.get('type') : '')
  const { data: tx } = useLoad('/api/taxonomy'); const { data: reviewers } = useLoad('/api/reviewers')
  const { data: ai } = useLoad(type === 'exam' ? '/api/settings/openai/status' : null, [type])
  const [v, setV] = useState({ title: '', level: 'school', board: '', grade: '', university: '', course: '', semester: '', subject: '', medium: 'English', price: 0, reviewer_id: '', kind: 'auto',
    exam: '', year: new Date().getFullYear(), session: '', text: '' })
  const [file, setFile] = useState(null); const [key, setKey] = useState(null); const [cover, setCover] = useState(null)
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  const set = (k, x) => setV(s => ({ ...s, [k]: x }))
  const exam = type === 'exam'

  function choose(t) { setType(t); setErr(''); setV(s => ({ ...s, level: t === 'exam' ? 'competitive' : 'school' })) }

  function problem() {
    if (exam) {
      if (!v.exam.trim()) return 'Choose which exam this is for'
      if (!v.year) return 'Enter the year of the paper'
      if (!file && !v.text.trim()) return 'Upload the question paper or paste it'
    } else {
      if (!file) return 'Choose a PDF or Word file'
      if (!v.title.trim()) return 'Give it a title'
    }
    if (v.level === 'school' && !exam && !v.board) return 'Pick a board'
    if (v.level === 'degree' && !v.university.trim()) return 'Enter the university'
    if (+v.price < 0) return 'The price cannot be negative'
    return ''
  }

  async function save() {
    const p = problem(); if (p) return setErr(p)
    setErr(''); setBusy(true)
    const f = new FormData()
    const fields = exam ? ['level', 'exam', 'board', 'grade', 'university', 'course', 'semester', 'subject', 'price', 'year', 'session', 'title', 'text']
      : ['title', 'level', 'board', 'grade', 'university', 'course', 'semester', 'subject', 'medium', 'price', 'reviewer_id', 'kind']
    fields.forEach(k => v[k] !== '' && f.append(k, v[k]))
    if (file) f.append('file', file)
    if (cover) f.append('cover', cover)
    try {
      if (exam) {
        if (key) f.append('key_file', key)
        const r = await api('/api/exams/test-sets', { method: 'POST', form: f })
        toast(r.warning || `${r.found} questions found${r.key_matched ? `, ${r.key_matched} answers from the key` : ''}`, !!r.warning)
        nav(`/sa/exams/${r.book_id}?paper=${r.id}`)
      } else {
        f.append('content_type', type)
        await api('/api/jobs', { method: 'POST', form: f })
        toast(type === 'book' ? 'Book added. Converting now.' : 'Document added. Converting now.')
        nav('/sa/processing')
      }
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  if (!type) return (
    <Page title="Add content" sub="What are you adding?">
      <div className="choice-grid">{TYPES.map(([k, i, l, d]) => <button key={k} type="button" className="choice" onClick={() => choose(k)}>
        <span className="choice-icon"><Icon n={i} s={24} /></span><b>{l}</b><span>{d}</span></button>)}</div>
    </Page>)

  const label = TYPES.find(t => t[0] === type)[2]
  return (
    <Page title={'Add ' + label.toLowerCase()} sub={exam ? 'It stays private until you check it and press Publish.' : 'It stays private until a reviewer approves it.'}
      actions={<button className="btn" onClick={() => setType('')}>Change type</button>}>
      <ol className="stepper">{STEPS[type].map((s, i) => <li key={s} className={i === 0 ? 'on' : ''}><i>{i + 1}</i>{s}</li>)}</ol>
      <div className="add-form card"><div className="card-b stack">
        {err && <div className="err" role="alert">{err}</div>}
        <Dropzone file={file} onFile={setFile} accept={exam ? '.pdf,.docx,.txt' : '.pdf,.doc,.docx'} label={exam ? 'Drop the question paper here, or click to choose' : `Drop the ${label.toLowerCase()} here, or click to choose`} hint={exam ? 'PDF, Word or plain text' : 'PDF or Word'} />
        {exam && <>
          <Field label="Answer key (optional)" hint="Answers from a key are used as they are. AI only fills what is missing."><Dropzone small file={key} onFile={setKey} accept=".pdf,.docx,.txt" label="Add the answer key" /></Field>
          {ai && !ai.has_key && <div className="note">Papers with maths need AI to be read properly. <Link to="/sa/ai" style={{ color: 'var(--red)', fontWeight: 650 }}>Add your OpenAI key</Link> to use Read with AI and Generate answers.</div>}
        </>}
        {!exam && <Field label="Title"><input className="input" value={v.title} onChange={e => set('title', e.target.value)} /></Field>}
        <Where v={v} set={set} tx={tx} exam={exam} />
        {exam && <div className="grid3">
          <Field label="Year"><input className="input" type="number" value={v.year} onChange={e => set('year', e.target.value)} /></Field>
          <Field label="Session or shift"><input className="input" placeholder="2 April, Shift 1" value={v.session} onChange={e => set('session', e.target.value)} /></Field>
          <Field label="Title (optional)"><input className="input" value={v.title} onChange={e => set('title', e.target.value)} /></Field></div>}
        <div className="grid2">
          <Field label="Price (₹)" hint={exam ? 'For the whole pack of this exam. Leave 0 to keep the current price.' : 'What an individual student pays. 0 is free.'}><input className="input" type="number" min="0" value={v.price} onChange={e => set('price', e.target.value)} /></Field>
          <Field label="Cover (optional)" hint="PNG, JPG or WEBP, under 5 MB"><Dropzone small file={cover} onFile={setCover} accept=".png,.jpg,.jpeg,.webp" label="Add a cover picture" /></Field>
        </div>
        {!exam && <Field label="Send to reviewer" hint="Only this reviewer sees it. Leave on Any to let any reviewer pick it up."><select className="input" value={v.reviewer_id} onChange={e => set('reviewer_id', e.target.value)}><option value="">Any reviewer</option>{reviewers?.filter(r => r.status === 'active').map(r => <option key={r.id} value={r.id}>{r.name}, {r.in_review} with them</option>)}</select></Field>}
        <details className="more"><summary>More options</summary><div className="stack" style={{ marginTop: 10 }}>
          {exam && <Field label="Or paste the paper" hint="Numbered questions, then options, then Answer: lines"><textarea className="input" rows={7} value={v.text} onChange={e => set('text', e.target.value)} /></Field>}
          {!exam && <><Field label="Medium"><input className="input" value={v.medium} onChange={e => set('medium', e.target.value)} /></Field>
            <Field label="File type" hint="Leave on Detect unless the file was already converted by the book reader"><div className="seg" role="radiogroup">{[['auto', 'Detect'], ['book', 'Needs reading'], ['flow', 'Already converted']].map(([k, l]) => <button key={k} type="button" className={v.kind === k ? 'on' : ''} onClick={() => set('kind', k)} role="radio" aria-checked={v.kind === k}>{l}</button>)}</div></Field></>}
        </div></details>
        <div className="add-actions"><button className="btn primary" onClick={save} disabled={busy}><Icon n="upload" s={16} />{busy ? (exam ? 'Reading the paper' : 'Uploading') : (exam ? 'Add test set' : 'Add and start converting')}</button></div>
      </div></div>
    </Page>)
}

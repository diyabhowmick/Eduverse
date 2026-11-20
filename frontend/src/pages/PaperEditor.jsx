import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useLoad, Tag, useToast, Modal, Field, MathText, AuthImg, ask } from '../ui'

const SOURCE = { paper: ['Printed on the paper', 'ok'], key: ['From the answer key', 'ok'], human: ['Set by a person', 'ok'], ai: ['AI answer', 'info'] }
const TYPES = [['mcq', 'One correct option'], ['multi', 'More than one correct'], ['numeric', 'Typed number'], ['written', 'Written']]

// One question paper, question by question. Used by the super admin (build and submit) and the reviewer (check and approve).
// Drag on the original page to mark the figure for a question.
function CropPage({ src, page, onBox }) {
  const area = useRef(); const [drag, setDrag] = useState(null)
  const at = e => { const r = area.current.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))] }
  const rect = drag && [Math.min(drag[0], drag[2]), Math.min(drag[1], drag[3]), Math.max(drag[0], drag[2]), Math.max(drag[1], drag[3])]
  return <div ref={area} className="crop-area" onMouseDown={e => { e.preventDefault(); const [x, y] = at(e); setDrag([x, y, x, y]) }}
    onMouseMove={e => drag && setDrag(d => [d[0], d[1], ...at(e)])}
    onMouseUp={() => { if (rect && rect[2] - rect[0] > .02 && rect[3] - rect[1] > .01) onBox(page, rect); setDrag(null) }}>
    <AuthImg src={src} alt={'Page ' + page} />
    {rect && <i style={{ left: rect[0] * 100 + '%', top: rect[1] * 100 + '%', width: (rect[2] - rect[0]) * 100 + '%', height: (rect[3] - rect[1]) * 100 + '%' }} />}
  </div>
}

const STYLE_NAME = { exam: 'Exam answer', concept_clarity: 'Explain simply', curiosity: 'Why it matters', research: 'Go deeper' }

// Every saved explanation students have been shown for this question. Exam explanations only become
// final when a reviewer pins one, because a well liked wrong solution would do real harm.
function Explanations({ q, onClose }) {
  const { data, reload } = useLoad('/api/learn/admin/explanations?question_id=' + q.id); const toast = useToast()
  const [edit, setEdit] = useState(null)
  const act = async (e, a) => { try { await api(`/api/learn/admin/explanations/${e.id}/${a}`, { method: 'POST' }); toast({ pin: 'Pinned as final', retire: 'Retired', restore: 'Back in use' }[a]); reload() } catch (x) { toast(x.message, true) } }
  const save = async () => { try { await api('/api/learn/admin/explanations/' + edit.id, { method: 'PUT', body: { text: edit.text } }); toast('Saved'); setEdit(null); reload() } catch (x) { toast(x.message, true) } }
  return <Modal title={'Explanations for Q' + q.number} onClose={onClose}>
    {data && !data.length && <div className="empty">No student has asked about this question yet, and none were written ahead.</div>}
    {data?.map(e => <div key={e.id} className="card" style={{ marginBottom: 10 }}><div className="card-b" style={{ display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <span className="tag">{e.level === 1 ? (STYLE_NAME[e.style] || e.style) : 'Level ' + e.level + ': ' + e.term}</span>
        <Tag s={{ final: 'approved', candidate: 'pending', flagged: 'rejected', retired: 'retired' }[e.status]}>{{ final: 'Final', candidate: 'Being compared', flagged: 'Reported', retired: 'Retired' }[e.status]}</Tag>
        <span className="muted" style={{ fontSize: 12 }}>shown {e.shown}, helpful {e.helpful}, not helpful {e.unhelpful}, asked to redo {e.retries}{e.reports ? `, ${e.reports} reports` : ''}{e.source === 'prepared' ? ', written ahead' : e.source === 'edited' ? ', edited' : ''}</span></div>
      {edit?.id === e.id ? <><textarea className="input" rows={8} value={edit.text} onChange={x => setEdit({ ...edit, text: x.target.value })} />
        <div style={{ display: 'flex', gap: 6 }}><button className="btn primary sm" onClick={save}>Save</button><button className="btn sm" onClick={() => setEdit(null)}>Cancel</button></div></>
        : <div style={{ maxHeight: 220, overflow: 'auto' }}><MathText text={e.text} /></div>}
      {edit?.id !== e.id && <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {e.status !== 'final' && e.status !== 'retired' && <button className="btn primary sm" onClick={() => act(e, 'pin')}>Pin as final</button>}
        <button className="btn sm" onClick={() => setEdit({ id: e.id, text: e.text })}>Edit</button>
        {e.status !== 'retired' ? <button className="btn ghost sm" onClick={() => act(e, 'retire')}>Retire</button> : <button className="btn ghost sm" onClick={() => act(e, 'restore')}>Restore</button>}
        {e.status === 'flagged' && <button className="btn ghost sm" onClick={() => act(e, 'restore')}>Restore</button>}</div>}
    </div></div>)}
  </Modal>
}

function QEdit({ q, chapters, onSave, onDelete, locked, onPage, onCrop, onNoFigure, onExplanations }) {
  const [v, setV] = useState({ ...q, options: q.options || [] }); const [open, setOpen] = useState(false)
  const set = k => e => setV(x => ({ ...x, [k]: e.target.value }))
  const opt = (i, t) => setV(x => ({ ...x, options: x.options.map((o, j) => j === i ? { ...o, text: t } : o) }))
  const src = SOURCE[q.answer_source]
  if (!open) return <div className={'card' + (q.confidence === 'low' ? ' flagged' : '')} style={{ marginBottom: 8 }}><div className="card-b" style={{ display: 'flex', gap: 10 }}>
    <b style={{ minWidth: 34 }}>{q.number ? 'Q' + q.number : 'Q'}</b>
    <div style={{ flex: 1, minWidth: 0 }}><div>{q.text ? <MathText text={q.text} /> : <span className="muted">No question text</span>}</div>
      {q.has_figure && <AuthImg stamp={q.figure_stamp} src={`/api/exams/questions/${q.id}/figure`} style={{ margin: '8px 0', maxHeight: 220 }} />}
      {q.options?.length > 0 && <div style={{ fontSize: 13, display: 'grid', gap: 2, marginTop: 4 }}>{q.options.map(o => <div key={o.key}>({o.key}) <MathText text={o.text} /></div>)}</div>}
      <div style={{ fontSize: 13, marginTop: 6 }}>{q.answer ? <span>Answer: <b><MathText text={q.answer} /></b></span> : <span className="tag warn">No answer</span>}
        {src && <span className={'tag ' + src[1]} style={{ marginLeft: 6 }}>{src[0]}</span>}
        {q.answer_source === 'ai' && q.confidence && <span className={'tag ' + (q.confidence === 'low' ? 'bad' : q.confidence === 'medium' ? 'warn' : 'ok')} style={{ marginLeft: 6 }}>{q.confidence} confidence</span>}
        {q.solution && <details style={{ marginTop: 4 }}><summary className="muted">Solution</summary><MathText text={q.solution} /></details>}{q.marks ? <span className="muted">, {q.marks} marks</span> : ''}
        {' '}{q.chapter ? <span className="tag">{q.chapter}</span> : <span className="tag warn">No chapter</span>}{q.section && <span className="muted"> {q.section}</span>}</div></div>
    <div style={{ display: 'grid', gap: 4, alignContent: 'start' }}>{!locked && <button className="btn ghost sm" onClick={() => setOpen(true)}>Edit</button>}
      {q.page > 0 && <button className="btn ghost sm" onClick={() => onPage(q.page)}>Page {q.page}</button>}
      {!locked && onCrop && <button className="btn ghost sm" onClick={() => onCrop(q)}>{q.has_figure ? 'Redo figure' : 'Add figure'}</button>}
      {!locked && q.has_figure && <button className="btn ghost sm" onClick={onNoFigure}>No figure</button>}
      {onExplanations && <button className="btn ghost sm" onClick={() => onExplanations(q)}>Explanations</button>}</div></div></div>
  return <div className="card" style={{ marginBottom: 8 }}><div className="card-b" style={{ display: 'grid', gap: 8 }}>
    <div className="grid3"><Field label="Number"><input className="input" value={v.number} onChange={set('number')} /></Field><Field label="Section"><input className="input" value={v.section} onChange={set('section')} /></Field>
      <Field label="Question type"><select className="input" value={v.qtype} onChange={set('qtype')}>{TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field></div>
    <Field label="Question"><textarea className="input" rows={3} value={v.text} onChange={set('text')} /></Field>
    {v.options.map((o, i) => <div key={i} style={{ display: 'flex', gap: 6 }}><span style={{ width: 24, paddingTop: 8 }}>({o.key})</span><input className="input" value={o.text} onChange={e => opt(i, e.target.value)} />
      <button className="btn ghost sm" onClick={() => setV(x => ({ ...x, options: x.options.filter((_, j) => j !== i) }))}>Remove</button></div>)}
    <button className="btn ghost sm" style={{ justifySelf: 'start' }} onClick={() => setV(x => ({ ...x, options: [...x.options, { key: 'abcdefgh'[x.options.length], text: '' }] }))}>Add option</button>
    <div className="grid2"><Field label={v.qtype === 'multi' ? 'Answers (letters, separated by commas)' : v.options.length ? 'Answer (option letter)' : 'Answer'}><input className="input" value={v.answer} onChange={set('answer')} /></Field>
      <Field label="Marks"><input className="input" type="number" min="0" step="0.5" value={v.marks} onChange={set('marks')} /></Field></div>
    <Field label="Solution"><textarea className="input" rows={3} value={v.solution} onChange={set('solution')} /></Field>
    <Field label="Chapter" hint={chapters.length ? 'From the textbooks linked to this exam pack' : 'Link textbooks to the exam pack to pick from their chapters'}>
      {chapters.length ? <select className="input" value={v.chapter} onChange={set('chapter')}><option value="">Not tagged</option>{chapters.map(c => <option key={c.title + c.number}>{c.title}</option>)}</select>
        : <input className="input" value={v.chapter} onChange={set('chapter')} />}</Field>
    <div style={{ display: 'flex', gap: 8 }}><button className="btn primary sm" onClick={async () => { if (await onSave({ ...v, marks: +v.marks || 0 })) setOpen(false) }}>Save</button>
      <button className="btn sm" onClick={() => { setV({ ...q, options: q.options || [] }); setOpen(false) }}>Cancel</button>
      <button className="btn ghost sm" style={{ marginLeft: 'auto' }} onClick={() => ask('Delete this question?', { yes: 'Delete' }).then(ok => ok && onDelete())}>Delete</button></div>
  </div></div>
}

export default function PaperEditor({ pid, role, onBack }) {
  const { data: p, reload } = useLoad('/api/exams/papers/' + pid, [pid]); const toast = useToast()
  const [back, setBack] = useState(false); const [note, setNote] = useState(''); const [page, setPage] = useState(0); const [crop, setCrop] = useState(null); const [stamp, setStamp] = useState(0); const [exq, setExq] = useState(null)
  const working = ['queued', 'running'].includes(p?.ai?.status)
  useEffect(() => { if (!working) return; const t = setInterval(reload, 3000); return () => clearInterval(t) }, [working, reload])
  const call = async (fn, msg) => { try { const r = await fn(); msg && toast(msg); await reload(); return r || true } catch (e) { toast(e.message, true); return false } }
  const act = (a, msg, body) => call(() => api(`/api/exams/papers/${pid}/${a}`, { method: 'POST', body: body || {} }), msg)
  if (!p) return <div className="empty">Loading</div>
  const locked = p.status === 'approved' && role !== 'super_admin'
  const untagged = p.questions.filter(q => !q.chapter).length, noAns = p.questions.filter(q => !q.answer).length
  const unsure = p.questions.filter(q => q.answer_source === 'ai' && q.confidence === 'low').length
  const open = role === 'super_admin' && p.status !== 'approved'
  const publish = () => ask(`Publish this paper to the marketplace?${noAns ? ` ${noAns} questions have no answer.` : ''}${unsure ? ` ${unsure} AI answers are low confidence.` : ''}`, { yes: 'Publish' }).then(ok => ok && act('publish', 'Published. It is now in the marketplace.'))
  return <div>
    <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
      <button className="btn sm" onClick={onBack}>Back</button>
      <h3 style={{ margin: 0 }}>{p.pack}: {p.title}</h3><Tag s={p.status} />
      <span className="muted" style={{ fontSize: 13 }}>{p.questions.length} questions{noAns ? `, ${noAns} without an answer` : ''}{unsure ? `, ${unsure} low confidence` : ''}{untagged ? `, ${untagged} without a chapter` : ''}</span>
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
        {p.is_pdf && <button className="btn ghost sm" onClick={() => setPage(page ? 0 : 1)}>{page ? 'Hide original' : 'Show original'}</button>}
        {open && p.is_pdf && <button className="btn sm" disabled={working} onClick={async () => (!p.questions.length || await ask('Read the paper again with AI? This replaces the questions below, including your edits, when it finishes.')) && act('read_ai', 'Reading the paper')}>Read with AI</button>}
        {open && noAns > 0 && <button className="btn sm" disabled={working} onClick={() => act('answer_ai', 'Writing answers')}>Generate answers</button>}
        {role === 'super_admin' && p.status !== 'approved' && <button className="btn ghost sm" onClick={async () => { const r = await act('retag'); r && toast(`${r.tagged} of ${r.of} questions tagged to a chapter`) }}>Tag chapters</button>}
        {role === 'super_admin' && ['draft', 'rejected'].includes(p.status) && <button className="btn ghost sm" onClick={() => act('submit', 'Sent to the reviewer')}>Send to a reviewer</button>}
        {open && <button className="btn primary sm" disabled={working} onClick={publish}>Publish to marketplace</button>}
        {p.status === 'in_review' && <><button className="btn sm" onClick={() => { setNote(''); setBack(true) }}>Send back</button>{role !== 'super_admin' && <button className="btn primary sm" onClick={() => act('approve', 'Paper approved')}>Approve paper</button>}</>}
        {role === 'super_admin' && p.status === 'approved' && <button className="btn ghost sm" onClick={() => act('reopen', 'Reopened for editing')}>Reopen</button>}
      </div></div>
    {p.status === 'rejected' && p.review_note && <div className="note" style={{ marginBottom: 10 }}>Sent back by {p.reviewed_by}: {p.review_note}</div>}
    {working && <div className="note" style={{ marginBottom: 10 }}><b>{p.ai.stage}</b>{p.ai.total ? `: ${p.ai.done} of ${p.ai.total}` : ''}<span className="dots" /><div className="bar-track" style={{ marginTop: 6 }}><i style={{ width: (p.ai.total ? p.ai.done / p.ai.total * 100 : 0) + '%' }} /></div></div>}
    {!working && p.ai?.error && <div className="err" style={{ marginBottom: 10 }}>{p.ai.error}</div>}
    {open && !working && !p.ai?.status && p.is_pdf && p.questions.length > 0 && <div className="note" style={{ marginBottom: 10 }}>These questions came from the PDF's text, which loses maths and diagrams. If any look incomplete, press <b>Read with AI</b>.</div>}
    <div className={page ? 'paper-split' : ''}>
      <div>
        {p.questions.map(q => <QEdit key={q.id + ':' + JSON.stringify(q)} q={{ ...q, figure_stamp: stamp }} chapters={p.chapters} locked={locked} onPage={setPage} onExplanations={p.status === 'approved' || p.status === 'in_review' ? setExq : null}
          onCrop={p.is_pdf ? x => { setCrop(x); setPage(x.page || page || 1) } : null}
          onNoFigure={() => call(() => api(`/api/exams/questions/${q.id}/figure`, { method: 'POST', body: { box: null } }), 'Figure removed')}
          onSave={b => call(() => api('/api/exams/questions/' + q.id, { method: 'PUT', body: b }), 'Question saved')}
          onDelete={() => call(() => api('/api/exams/questions/' + q.id, { method: 'DELETE' }), 'Question deleted')} />)}
        {!locked && <button className="btn sm" onClick={() => call(() => api(`/api/exams/papers/${pid}/questions`, { method: 'POST', body: { number: String(p.questions.length + 1), text: '', qtype: 'mcq' } }), 'Question added')}>Add question</button>}
      </div>
      {page > 0 && <aside className="paper-original card"><div className="toolbar" style={{ padding: '8px 10px', margin: 0, gap: 6 }}>
        <button className="btn ghost sm" disabled={page < 2} onClick={() => setPage(page - 1)}>Previous</button><b>Page {page}</b>
        <button className="btn ghost sm" onClick={() => setPage(page + 1)}>Next</button></div>
        {crop && <div className="note" style={{ margin: '0 10px 8px' }}>Drag around the figure for <b>Q{crop.number}</b>, including any picture options. <button className="btn ghost sm" onClick={() => setCrop(null)}>Cancel</button></div>}
        {crop ? <CropPage src={`/api/exams/papers/${pid}/pages/${page}`} page={page} onBox={async (pg, box) => { if (await call(() => api(`/api/exams/questions/${crop.id}/figure`, { method: 'POST', body: { page: pg, box } }), 'Figure saved')) { setCrop(null); setStamp(s => s + 1) } }} />
          : <AuthImg src={`/api/exams/papers/${pid}/pages/${page}`} alt={'Page ' + page + ' of the original paper'} />}</aside>}
    </div>
    {exq && <Explanations q={exq} onClose={() => setExq(null)} />}
    {back && <Modal title="Send this paper back" onClose={() => setBack(false)} footer={<><button className="btn" onClick={() => setBack(false)}>Cancel</button><button className="btn primary" onClick={async () => { if (await act('send_back', 'Sent back', { note })) setBack(false) }}>Send back</button></>}>
      <Field label="What needs fixing"><textarea className="input" rows={4} value={note} onChange={e => setNote(e.target.value)} /></Field></Modal>}
  </div>
}

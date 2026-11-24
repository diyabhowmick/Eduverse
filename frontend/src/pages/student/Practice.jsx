import { NotSure } from './common'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'
import { useLoad, MathText, AuthImg, Icon, useToast } from '../../ui'
import ExplainPanel from '../../ExplainPanel'

const SHOW = [['all', 'All'], ['new', 'Not tried'], ['wrong', 'Mistakes'], ['saved', 'Saved']]
export const TYPE = { mcq: 'One correct option', multi: 'One or more correct', numeric: 'Type a number', written: 'Written answer' }

// The answer area shared by practice and tests: big options to tap, or a box for a number.
export function Options({ q, value, onChange, result, disabled }) {
  const answers = String(q.answer || '').split(',').map(x => x.trim()).filter(Boolean)
  const chosen = String(value || '').split(',').filter(Boolean)
  if (q.qtype === 'numeric') return <div style={{ margin: '16px 0' }}>
    <input className="input numans" inputMode="decimal" placeholder="Type your answer" aria-label="Your answer" disabled={disabled} value={value || ''} onChange={e => onChange(e.target.value)} />
    {result && q.answer && <div className="muted" style={{ marginTop: 8 }}>Correct answer: <b><MathText text={q.answer} /></b></div>}</div>
  if (!q.options?.length) return null
  return <div className="opts" role={q.qtype === 'multi' ? 'group' : 'radiogroup'}>{q.options.map(o => {
    const on = chosen.includes(o.key)
    const cls = result ? (answers.includes(o.key) ? ' right' : on ? ' wrong' : '') : on ? ' on' : ''
    return <button key={o.key} type="button" className={'opt' + cls} disabled={disabled} role={q.qtype === 'multi' ? 'checkbox' : 'radio'} aria-checked={on}
      onClick={() => onChange(q.qtype === 'multi' ? (on ? chosen.filter(x => x !== o.key) : [...chosen, o.key]).sort().join(',') : (on ? '' : o.key))}>
      <span className="k">{o.key}</span><span style={{ flex: 1, minWidth: 0 }}><MathText text={o.text} />
        {o.has_figure && <AuthImg src={`/api/exams/questions/${q.id}/options/${o.key}/figure`} alt={'Option ' + o.key} style={{ display: 'block', maxHeight: 180, marginTop: o.text ? 6 : 0 }} />}</span></button>
  })}</div>
}

export default function Practice({ id, styles, initial = {} }) {
  const [f, setF] = useState({ show: initial.show || 'all', subject: '', chapter: initial.chapter || '', year: 0 })
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString()
  const { data, reload, setData } = useLoad(`/api/student/exams/${id}/practice?${qs}`, [qs])
  const [i, setI] = useState(0); const [given, setGiven] = useState(''); const [unsure, setUnsure] = useState(false); const [res, setRes] = useState(null); const [explain, setExplain] = useState(false)
  const toast = useToast()
  useEffect(() => { setI(0) }, [qs])
  const q = data?.questions[i]
  useEffect(() => { setGiven(''); setRes(null); setExplain(false); setUnsure(false); window.scrollTo({ top: 0, behavior: 'smooth' }) }, [q?.id])
  const set = (k, v) => setF(x => ({ ...x, [k]: v }))
  const checkable = q && (q.options?.length || q.qtype === 'numeric')

  async function check() {
    if (!given.trim()) return
    try {
      const r = await api(`/api/student/exams/${id}/practice/${q.id}/answer`, { method: 'POST', body: { given, not_sure: unsure } })
      setRes(r); setData(d => ({ ...d, questions: d.questions.map(x => x.id === q.id ? { ...x, answer: r.answer, solution: r.solution, state: r.state } : x) }))
    } catch (e) { toast(e.message, true) }
  }
  async function reveal() { setRes({ correct: null, answer: q.answer, solution: q.solution }) }
  async function star() {
    try { const r = await api(`/api/student/exams/${id}/practice/${q.id}/bookmark`, { method: 'POST' }); setData(d => ({ ...d, questions: d.questions.map(x => x.id === q.id ? { ...x, state: { ...x.state, bookmarked: r.bookmarked } } : x) })); toast(r.bookmarked ? 'Saved for revision' : 'Removed from saved') }
    catch (e) { toast(e.message, true) }
  }
  const next = () => i < data.questions.length - 1 ? setI(i + 1) : toast('That was the last question in this list')
  // Keyboard on laptops: A-D or 1-4 to pick, Enter to check then go on, arrows to move.
  useEffect(() => {
    const k = e => {
      if (!q || ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return
      const idx = 'abcd'.indexOf(e.key.toLowerCase()) >= 0 ? 'abcd'.indexOf(e.key.toLowerCase()) : '1234'.indexOf(e.key)
      if (idx >= 0 && q.options?.[idx] && !res) setGiven(q.options[idx].key)
      else if (e.key === 'Enter') res ? next() : check()
      else if (e.key === 'ArrowRight') next()
      else if (e.key === 'ArrowLeft' && i > 0) setI(i - 1)
    }
    addEventListener('keydown', k); return () => removeEventListener('keydown', k)
  })

  const counts = data?.counts || {}
  return <div>
    <div className="filters">
      <div className="chips">{SHOW.map(([k, l]) => <button key={k} type="button" className={'chip' + (f.show === k ? ' on' : '')} onClick={() => set('show', k)}>{l}<em>{counts[k] ?? ''}</em></button>)}</div>
      {data && <div className="row2">
        {data.subjects.length > 1 && <div className="chips">{['', ...data.subjects].map(s => <button key={s} type="button" className={'chip' + (f.subject === s ? ' on' : '')} onClick={() => set('subject', s)}>{s || 'All subjects'}</button>)}</div>}
        {data.chapters.length > 0 && <select className="input" aria-label="Chapter" value={f.chapter} onChange={e => set('chapter', e.target.value)}><option value="">Every chapter</option>{data.chapters.map(c => <option key={c}>{c}</option>)}</select>}
        {data.years.length > 1 && <select className="input" aria-label="Year" value={f.year} onChange={e => set('year', +e.target.value)}><option value={0}>Every year</option>{data.years.map(y => <option key={y} value={y}>{y}</option>)}</select>}
      </div>}
    </div>
    {data && !data.questions.length && <div className="card empty">{{ wrong: 'No mistakes here. Questions you get wrong in practice or tests collect here for another try.', saved: 'Nothing saved yet. Tap the star on any question to keep it for revision.', new: 'You have tried every question in this list. Well done.' }[f.show] || 'No questions match these filters.'}</div>}
    {q && <div className="qwrap card"><div className="card-b">
      <div className="qhead"><span className="n">Question {i + 1} <span className="muted" style={{ fontWeight: 500 }}>of {data.questions.length}</span></span>
        <span className="t">{TYPE[q.qtype] || 'Question'}</span><span className="t">{q.year}{q.session ? ' · ' + q.session : ''}</span>
        {q.state.status && <span className={'tag ' + (q.state.status === 'correct' ? 'ok' : 'bad')}>{q.state.status === 'correct' ? 'You got this right before' : 'You got this wrong before'}</span>}
        <button type="button" className={'btn ghost sm star' + (q.state.bookmarked ? ' on' : '')} style={{ marginLeft: 'auto' }} onClick={star} aria-pressed={q.state.bookmarked} aria-label="Save for revision"><Icon n="star" s={18} />{q.state.bookmarked ? 'Saved' : 'Save'}</button></div>
      <div className="qtext"><MathText text={q.text} /></div>
      {q.has_figure && <div style={{ margin: '12px 0' }}><AuthImg src={`/api/exams/questions/${q.id}/figure`} alt="Figure for this question" style={{ maxHeight: 300 }} /></div>}
      <Options q={{ ...q, answer: res?.answer ?? q.answer }} value={given} onChange={setGiven} result={!!res} disabled={!!res} />
      {res && res.correct !== null && <div className={'verdict ' + (res.correct ? 'ok' : 'bad')}><Icon n={res.correct ? 'check' : 'x'} />{res.correct ? 'Correct' : 'Not quite. The right answer is marked in green.'}</div>}
      {res && (res.solution || res.answer) && <div className="solution">{!q.options?.length && q.qtype !== 'numeric' && res.answer && <div><b>Answer:</b> <MathText text={res.answer} /></div>}
        {res.solution ? <MathText text={res.solution} /> : <span className="muted">No worked solution for this one.</span>}</div>}
      {res && (explain ? <div className="explain-box"><ExplainPanel styles={styles} request={{ scope: 'question', question_id: q.id }} /></div>
        : <button type="button" className="btn" style={{ marginTop: 12 }} onClick={() => setExplain(true)}>Explain with AI</button>)}
      <div className="qnav">
        <button type="button" className="btn lg inline" disabled={i === 0} onClick={() => setI(i - 1)} aria-label="Previous question"><Icon n="left" s={18} /></button>
        <span className="grow" />
        {!res && !checkable && <button type="button" className="btn lg" onClick={reveal}>Show answer</button>}
        {!res && checkable && <NotSure on={unsure} onChange={setUnsure} />}
        {!res && checkable && <button type="button" className="btn primary lg" disabled={!given.trim()} onClick={check}>Check answer</button>}
        {res && <button type="button" className="btn primary lg" onClick={next}>Next question<Icon n="right" s={18} /></button>}
      </div>
    </div></div>}
  </div>
}

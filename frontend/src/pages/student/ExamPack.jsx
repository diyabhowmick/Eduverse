import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, day } from '../../api'
import { useLoad, Page, useToast, MathText, AuthImg, Icon, plural } from '../../ui'
import ExplainPanel from '../../ExplainPanel'
import Practice from './Practice'
import Tests from './TestRunner'

const TABS = [['practice', 'Practice'], ['tests', 'Tests'], ['papers', 'Past papers'], ['topics', 'By chapter'], ['weight', 'Weightage'], ['recap', 'Quick recap']]
const WINDOWS = [[10, 'Last 10 years'], [20, 'Last 20 years'], [0, 'Every year']]

function ExplainBox({ pack, q }) {
  const { data: home } = useLoad('/api/student/home')
  const [open, setOpen] = useState(false)
  if (!open) return <button type="button" className="btn sm" style={{ marginTop: 10 }} onClick={() => setOpen(true)}>Explain with AI</button>
  return <div className="explain-box"><ExplainPanel styles={home?.rules?.allowed_depths} request={{ scope: 'question', question_id: q.id }} /></div>
}

export function QuestionCard({ q, reveal: start = false, pick, picked, result, pack }) {
  const [reveal, setReveal] = useState(start)
  const show = reveal || result
  const answers = String(q.answer || '').split(',').map(x => x.trim())
  const chosen = String(picked || '').split(',')
  const numeric = q.qtype === 'numeric'
  return (
    <div className="card" style={{ marginBottom: 10 }}><div className="card-b">
      <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
        <b style={{ minWidth: 28 }}>{q.number ? 'Q' + q.number : ''}</b>
        <div style={{ flex: 1, minWidth: 0 }}><MathText text={q.text} /></div>
        <span className="muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{[q.year && q.year + (q.session ? ' ' + q.session : ''), q.marks ? q.marks + ' marks' : ''].filter(Boolean).join(', ')}</span>
      </div>
      {q.has_figure && <div style={{ margin: '10px 0 0 38px' }}><AuthImg src={`/api/exams/questions/${q.id}/figure`} alt="Figure for this question" style={{ maxHeight: 280 }} /></div>}
      {q.qtype === 'multi' && pick && <div className="muted" style={{ margin: '8px 0 0 38px', fontSize: 13 }}>More than one option can be correct</div>}
      {numeric && pick && <div style={{ margin: '10px 0 0 38px', maxWidth: 220 }}><input className="input" inputMode="decimal" placeholder="Type your answer" aria-label="Your answer" value={picked || ''} onChange={e => pick(e.target.value)} /></div>}
      {numeric && result && <div className="muted" style={{ margin: '8px 0 0 38px', fontSize: 14 }}>Your answer: {q.given || 'not answered'}</div>}
      {q.options?.length > 0 && <div style={{ display: 'grid', gap: 6, margin: '10px 0 0 38px' }}>{q.options.map(o => {
        const on = chosen.includes(o.key), right = show && answers.includes(o.key), wrong = result && on && !right
        return <button key={o.key} type="button" className="btn ghost sm" disabled={!pick || !!result} onClick={() => pick?.(o.key)}
          style={{ justifyContent: 'flex-start', textAlign: 'left', border: '1px solid ' + (right ? 'var(--ok, #1a7f37)' : wrong ? 'var(--red)' : on ? 'var(--ink)' : 'var(--line-2)'), fontWeight: on ? 700 : 400 }}>
          ({o.key})&nbsp;<MathText text={o.text} /></button>
      })}</div>}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '10px 0 0 38px', flexWrap: 'wrap' }}>
        {q.chapter && (q.chapter_ref?.book_id ? <Link className="tag" to={'/student/read/' + q.chapter_ref.book_id}>{q.chapter}</Link> : <span className="tag">{q.chapter}</span>)}
        {!result && !pick && (q.answer || q.solution) && <button className="btn ghost sm" onClick={() => setReveal(r => !r)}>{reveal ? 'Hide answer' : 'Show answer'}</button>}
        {result && q.self_check && <span className="tag">Check this one yourself</span>}
        {result && q.correct === true && <span className="tag ok">Correct</span>}
        {result && q.correct === false && <span className="tag bad">Wrong</span>}
      </div>
      {show && (q.answer || q.solution) && <div className="note" style={{ margin: '10px 0 0 38px', whiteSpace: 'pre-wrap' }}>
        {q.answer && <div><b>Answer:</b> {q.options?.length ? answers.map(a => <span key={a}>({a}) <MathText text={q.options.find(o => o.key === a)?.text || ''} /> </span>) : <MathText text={q.answer} />}</div>}
        {q.solution && <div style={{ marginTop: 4 }}><MathText text={q.solution} /></div>}
        {q.answer_source === 'ai' && <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>This answer was written by AI and checked by EduVerse. It is not the official key.</div>}
        {pack && <ExplainBox pack={pack} q={q} />}</div>}
    </div></div>)
}

function Papers({ id, home, onTest }) {
  const [open, setOpen] = useState(null)
  const { data } = useLoad(open ? `/api/student/exams/${id}/papers/${open}` : null, [open])
  if (open) return <div><button className="btn sm" onClick={() => setOpen(null)} style={{ marginBottom: 12 }}><Icon n="left" s={16} />All papers</button>
    <h3>{data?.title}</h3>{data?.questions.map(q => <QuestionCard key={q.id} q={q} pack={id} />)}</div>
  return <div className="suggest">{home.papers.map(p => <div key={p.id} className="card" style={{ padding: 16, display: 'grid', gap: 10 }}>
    <div><b style={{ fontSize: 16 }}>{p.title}</b><div className="muted" style={{ fontSize: 13 }}>{p.year} · {plural(p.questions, 'question')}</div></div>
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}><button className="btn primary" style={{ flex: 1 }} onClick={onTest}><Icon n="play" s={15} />Take as a test</button>
      <button className="btn" style={{ flex: 1 }} onClick={() => setOpen(p.id)}>Read with answers</button></div></div>)}
    {!home.papers.length && <div className="card empty">No papers in this window yet</div>}</div>
}

function Topics({ id, years }) {
  const { data } = useLoad(`/api/student/exams/${id}/topics?years=${years}`, [years])
  const [open, setOpen] = useState(null)
  return <div>{data?.map(g => <div key={g.chapter} className="card" style={{ marginBottom: 10 }}>
    <button className="btn ghost" style={{ width: '100%', justifyContent: 'space-between' }} onClick={() => setOpen(open === g.chapter ? null : g.chapter)}>
      <b>{g.chapter}</b><span className="muted">{g.questions.length} questions</span></button>
    {open === g.chapter && <div className="card-b">{g.questions.map(q => <QuestionCard key={q.id} q={q} pack={id} />)}</div>}</div>)}
    {data && !data.length && <div className="card empty">No questions yet</div>}</div>
}

function Weight({ home }) {
  const max = Math.max(1, ...home.weightage.map(w => w.questions))
  return <div className="card"><div className="card-b">
    <p className="muted" style={{ marginTop: 0 }}>How often each chapter was asked in {WINDOWS.find(w => w[0] === home.years)?.[1].toLowerCase()}. Spend your time where the marks are.</p>
    {home.weightage.map(w => <div key={w.chapter} style={{ display: 'grid', gridTemplateColumns: 'minmax(140px,260px) 1fr 90px', gap: 10, alignItems: 'center', marginBottom: 8 }}>
      <span>{w.chapter}</span><div className="bar-track"><i style={{ width: (w.questions / max * 100) + '%' }} /></div>
      <span className="muted" style={{ fontSize: 13 }}>{w.share}%{w.marks ? `, ${w.marks} marks` : ''}</span></div>)}
    {!home.weightage.length && <div className="empty">No questions yet</div>}</div></div>
}

function Recap({ id, home }) {
  const [ch, setCh] = useState(''); const [out, setOut] = useState(null); const [busy, setBusy] = useState(false); const toast = useToast()
  const go = async c => { setCh(c); setBusy(true); setOut(null); try { setOut(await api(`/api/student/exams/${id}/recap`, { method: 'POST', body: { chapter: c } })) } catch (e) { toast(e.message, true) } finally { setBusy(false) } }
  return <div className="row" style={{ alignItems: 'flex-start' }}>
    <div className="card" style={{ flex: '0 0 260px' }}><div className="card-b" style={{ display: 'grid', gap: 6 }}>
      <div className="muted" style={{ fontSize: 13 }}>Pick a chapter. The recap is written from what this exam keeps asking.</div>
      {home.weightage.map(w => <button key={w.chapter} className={'btn sm ' + (ch === w.chapter ? 'primary' : 'ghost')} style={{ justifyContent: 'space-between' }} onClick={() => go(w.chapter)}>
        <span>{w.chapter}</span><span>{w.share}%</span></button>)}</div></div>
    <div className="card" style={{ flex: 1 }}><div className="card-b" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
      {busy ? 'Writing your recap' : out ? <><h3 style={{ marginTop: 0 }}>{out.chapter}</h3>{out.text}<div className="muted" style={{ fontSize: 12, marginTop: 10 }}>Based on {out.based_on} past questions</div></> : <span className="muted">No chapter picked yet</span>}</div></div>
  </div>
}

export default function ExamPack() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'practice'
  const go = (t, extra = {}) => setParams({ tab: t, ...extra }, { replace: false })
  const [years, setYears] = useState(10)
  const { data: home, error } = useLoad(`/api/student/exams/${id}?years=${years}`, [years])
  const { data: me } = useLoad('/api/student/home')
  if (error) return <Page title="Exam pack"><div className="card empty">{error}</div></Page>
  if (!home) return <Page title="Exam pack"><div className="empty">Loading</div></Page>
  const p = home.pack
  const styles = me?.rules?.allowed_depths
  const windowed = ['papers', 'topics', 'weight'].includes(tab)
  return (
    <Page title={p.title} sub={[p.exam !== p.title && p.exam, p.board, p.grade && 'Class ' + p.grade, p.subject].filter(Boolean).concat(`${plural(home.questions, 'question')} from ${plural(home.papers.length, 'paper')}`).join(' · ')}>
      <div className="tabs" role="tablist">{TABS.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => go(k)}>{l}</button>)}</div>
      {windowed && <div className="chips" style={{ marginBottom: 14 }}>{WINDOWS.map(([k, l]) => <button key={k} type="button" className={'chip' + (years === k ? ' on' : '')} onClick={() => setYears(k)}>{l}</button>)}</div>}
      {windowed && home.linked_books.length > 0 && <div className="muted" style={{ fontSize: 13, marginBottom: 10 }}>Questions link to chapters in {home.linked_books.map(b => b.title).join(', ')}</div>}
      {tab === 'practice' && <Practice key={(params.get('chapter') || '') + (params.get('show') || '')} id={id} styles={styles} initial={{ chapter: params.get('chapter') || '', show: params.get('show') || '' }} />}
      {tab === 'tests' && <Tests id={id} home={home} styles={styles} onPractise={() => go('practice', { show: 'wrong' })} />}
      {tab === 'papers' && <Papers id={id} home={home} onTest={() => go('tests')} />}
      {tab === 'topics' && <Topics id={id} years={years} />}
      {tab === 'weight' && <Weight home={home} />}
      {tab === 'recap' && <Recap id={id} home={home} />}
    </Page>
  )
}

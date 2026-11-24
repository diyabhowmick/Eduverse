import { NotSure } from './common'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { api, day } from '../../api'
import { useLoad, MathText, AuthImg, Icon, Sheet, Ring, useToast, plural, QuestionText } from '../../ui'
import { Options, TYPE } from './Practice'
import { QuestionCard } from './ExamPack'

const KEY = aid => 'ev_test_' + aid
const mmss = s => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0') }
const long = s => { const h = Math.floor(s / 3600), m = Math.round(s % 3600 / 60); return h ? `${h} h ${m} min` : `${m} min` }
const isExam = name => /jee|neet|bitsat|cuet|eamcet|cet|tnea/i.test(name || '')

function savedFor(bid) {
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i)
    if (k?.startsWith('ev_test_')) { try { const t = JSON.parse(localStorage.getItem(k)); if (t && !t.done && String(t.bid) === String(bid)) return t } catch { /* ignore */ } }
  }
  return null
}

// ---------------- choosing a test ----------------
function Setup({ id, home, onStart }) {
  const exam = isExam(home.pack.exam)
  const [c, setC] = useState({ count: 20, chapter: '', minutes: 30, scheme: exam ? 'exam' : 'simple' })
  const [busy, setBusy] = useState(false); const toast = useToast()
  const saved = savedFor(id)
  const marking = c.scheme === 'exam' ? { correct: 4, wrong: 1 } : { correct: 1, wrong: 0 }
  async function start(body) {
    setBusy(true)
    try { onStart(await api(`/api/student/exams/${id}/mock`, { method: 'POST', body })) } catch (e) { toast(e.message, true) } finally { setBusy(false) }
  }
  return <div className="stack" style={{ maxWidth: 900 }}>
    {saved && <div className="hero" style={{ cursor: 'default' }}><div className="hero-body"><div className="k">Test in progress</div><h2>{saved.title}</h2>
      <div className="muted">{Object.keys(saved.answers || {}).length} of {saved.questions.length} answered{saved.deadline ? `, ${mmss((saved.deadline - Date.now()) / 1000)} left` : ''}.</div></div>
      <button className="btn primary lg inline" onClick={() => onStart(null, saved)}><Icon n="play" s={16} />Resume test</button></div>}
    <div className="card"><div className="card-h"><h3>Full papers</h3><span className="sub">The real paper, in order, against the clock</span></div>
      <div className="card-b stack">{home.papers.map(p => {
        const mins = exam ? Math.round(p.questions * 2.4) : p.questions * 2
        return <div key={p.id} style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 200 }}><b>{p.title}</b><div className="muted" style={{ fontSize: 13 }}>{plural(p.questions, 'question')} · {long(mins * 60)}{exam ? ' · +4 right, −1 wrong' : ''}</div></div>
          <button className="btn primary lg inline" disabled={busy} onClick={() => start({ paper_id: p.id, minutes: mins, correct: exam ? 4 : 0, wrong: exam ? 1 : 0 })}><Icon n="play" s={16} />Start paper</button></div>
      })}{!home.papers.length && <div className="empty">No papers yet</div>}</div></div>
    <div className="card"><div className="card-h"><h3>Custom test</h3><span className="sub">Mixed questions, your choice of size and time</span></div>
      <div className="card-b stack">
        <div><div className="muted" style={{ fontSize: 13, marginBottom: 6 }}>Questions</div><div className="chips">{[10, 20, 30, 50].map(n => <button key={n} type="button" className={'chip' + (c.count === n ? ' on' : '')} onClick={() => setC({ ...c, count: n })}>{n}</button>)}</div></div>
        <div><div className="muted" style={{ fontSize: 13, marginBottom: 6 }}>Time</div><div className="chips">{[[0, 'No limit'], [15, '15 min'], [30, '30 min'], [60, '1 hour'], [90, '1.5 hours']].map(([m, l]) => <button key={m} type="button" className={'chip' + (c.minutes === m ? ' on' : '')} onClick={() => setC({ ...c, minutes: m })}>{l}</button>)}</div></div>
        <div><div className="muted" style={{ fontSize: 13, marginBottom: 6 }}>Marking</div><div className="chips">
          <button type="button" className={'chip' + (c.scheme === 'exam' ? ' on' : '')} onClick={() => setC({ ...c, scheme: 'exam' })}>Exam style: +4 right, −1 wrong</button>
          <button type="button" className={'chip' + (c.scheme === 'simple' ? ' on' : '')} onClick={() => setC({ ...c, scheme: 'simple' })}>1 mark each, nothing taken off</button></div></div>
        {home.weightage.length > 1 && <select className="input" style={{ maxWidth: 360 }} aria-label="Chapter" value={c.chapter} onChange={e => setC({ ...c, chapter: e.target.value })}>
          <option value="">Whole syllabus</option>{home.weightage.filter(w => w.chapter !== 'Not tagged').map(w => <option key={w.chapter}>{w.chapter}</option>)}</select>}
        <button className="btn primary lg" style={{ justifySelf: 'start' }} disabled={busy} onClick={() => start({ count: c.count, years: 0, chapter: c.chapter || null, minutes: c.minutes, ...marking })}><Icon n="play" s={16} />Start test</button>
      </div></div>
    {home.attempts.length > 0 && <div className="card"><div className="card-h"><h3>Recent tests</h3></div>
      <table className="t"><tbody>{home.attempts.map(a => <tr key={a.id}><td><b>{a.title || 'Test'}</b><div className="muted" style={{ fontSize: 12 }}>{day(a.when)} · {plural(a.questions, 'question')}{a.time_taken ? ' · ' + long(a.time_taken) : ''}</div></td>
        <td className="num"><b>{a.score}</b> <span className="muted">/ {a.total}</span></td><td className="num">{a.total ? Math.round(Math.max(0, a.score) / a.total * 100) + '%' : ''}</td></tr>)}</tbody></table></div>}
  </div>
}

// ---------------- taking it ----------------
function Runner({ test, onDone, onExit }) {
  const [t, setT] = useState(test)
  const [now, setNow] = useState(Date.now()); const [pal, setPal] = useState(false); const [sum, setSum] = useState(false); const [busy, setBusy] = useState(false)
  const entered = useRef(Date.now()); const toast = useToast()
  const q = t.questions[t.idx]
  useEffect(() => { document.body.dataset.immersive = '1'; return () => { delete document.body.dataset.immersive } }, [])
  useEffect(() => { localStorage.setItem(KEY(t.aid), JSON.stringify(t)) }, [t])
  useEffect(() => { const x = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(x) }, [])
  const left = t.deadline ? (t.deadline - now) / 1000 : null
  useEffect(() => { if (left != null && left <= 0 && !busy) submit(true) }, [left != null && left <= 0])
  // Leaving the page by accident would lose nothing (answers are saved), but warn anyway.
  useEffect(() => { const w = e => { e.preventDefault(); e.returnValue = '' }; addEventListener('beforeunload', w); return () => removeEventListener('beforeunload', w) }, [])

  function spent(state) {
    const s = Math.round((Date.now() - entered.current) / 1000); entered.current = Date.now()
    return { ...state.times, [q.id]: (state.times[q.id] || 0) + s }
  }
  const go = i => setT(s => ({ ...s, times: spent(s), idx: i, visited: [...new Set([...s.visited, s.questions[i].id])] }))
  const answer = v => setT(s => { const a = { ...s.answers }; if (v) a[q.id] = v; else delete a[q.id]; return { ...s, answers: a } })
  const mark = () => setT(s => ({ ...s, marked: s.marked.includes(q.id) ? s.marked.filter(x => x !== q.id) : [...s.marked, q.id] }))
  const nextIdx = Math.min(t.idx + 1, t.questions.length - 1)
  const status = x => { const a = !!t.answers[x.id], m = t.marked.includes(x.id); return a && m ? 'am' : m ? 'mk' : a ? 'an' : t.visited.includes(x.id) ? 'na' : 'nv' }
  const subjects = useMemo(() => [...new Set(t.questions.map(x => x.subject))], [t.questions])
  const counts = useMemo(() => { const c = { an: 0, na: 0, nv: 0, mk: 0, am: 0 }; t.questions.forEach(x => c[status(x)]++); return c }, [t])

  async function submit(auto) {
    setBusy(true)
    const times = spent(t)
    try {
      const r = await api(`/api/student/exams/mock/${t.aid}/submit`, { method: 'POST', body: { answers: t.answers, unsure: t.unsure || [], times, time_taken: Math.round((Date.now() - t.started) / 1000) } })
      localStorage.removeItem(KEY(t.aid))
      if (auto) toast('Time is up. Your test was submitted.')
      onDone({ ...r, marked: t.marked })
    } catch (e) { toast(e.message, true); setBusy(false) }
  }
  useEffect(() => {
    const k = e => {
      if (['INPUT', 'TEXTAREA'].includes(e.target.tagName) || sum || pal) return
      const i = 'abcd'.indexOf(e.key.toLowerCase()) >= 0 ? 'abcd'.indexOf(e.key.toLowerCase()) : '1234'.indexOf(e.key)
      if (i >= 0 && q.options?.[i] && q.qtype !== 'multi') answer(t.answers[q.id] === q.options[i].key ? '' : q.options[i].key)
      else if (e.key === 'ArrowRight') go(nextIdx)
      else if (e.key === 'ArrowLeft' && t.idx > 0) go(t.idx - 1)
    }
    addEventListener('keydown', k); return () => removeEventListener('keydown', k)
  })

  const palette = <>
    <div className="legend"><span><i className="an" />Answered {counts.an}</span><span><i className="na" />Not answered {counts.na}</span><span><i />Not visited {counts.nv}</span>
      <span><i className="mk" />Marked {counts.mk}</span><span style={{ gridColumn: '1/-1' }}><i className="am" />Answered and marked {counts.am} (counted)</span></div>
    {subjects.map(s => <div key={s}>{subjects.length > 1 && <div className="subj-h">{s}</div>}
      <div className="palette">{t.questions.map((x, i) => x.subject === s && <button key={x.id} type="button" className={status(x) + (i === t.idx ? ' cur' : '')}
        aria-label={`Question ${i + 1}, ${{ an: 'answered', na: 'not answered', nv: 'not visited', mk: 'marked for review', am: 'answered and marked' }[status(x)]}`}
        onClick={() => { go(i); setPal(false) }}>{i + 1}</button>)}</div></div>)}
  </>
  // Its own layer over the whole screen, so nothing in the page layout can sit on top of the answer buttons.
  return createPortal(<div className="test-layer"><div className="test">
    <div className="test-top">
      <button className="btn ghost sm" onClick={onExit} aria-label="Leave the test (your answers are kept)"><Icon n="left" s={18} /></button>
      <span className="title">{t.title}</span>
      {left != null ? <span className={'timer' + (left < 300 ? ' low' : '')} aria-live="off"><Icon n="clock" s={16} />{mmss(left)}</span> : <span className="timer"><Icon n="clock" s={16} />{mmss((now - t.started) / 1000)}</span>}
      <button className="btn sm pal-btn" onClick={() => setPal(true)}><Icon n="grid" s={16} />{t.idx + 1}/{t.questions.length}</button>
      <button className="btn sm" onClick={() => setSum(true)}>Submit</button>
    </div>
    <div className="test-main">
      {subjects.length > 1 && <div className="chips" style={{ marginBottom: 14 }}>{subjects.map(s => { const first = t.questions.findIndex(x => x.subject === s)
        return <button key={s} type="button" className={'chip' + (q.subject === s ? ' on' : '')} onClick={() => go(first)}>{s}<em>{t.questions.filter(x => x.subject === s && t.answers[x.id]).length}/{t.questions.filter(x => x.subject === s).length}</em></button> })}</div>}
      <div className="qhead"><span className="n">Question {t.idx + 1}</span><span className="t">{TYPE[q.qtype] || 'Question'}</span>
        {t.correct > 0 && <span className="t">+{t.correct}{t.wrong ? ` / −${t.wrong}` : ''}</span>}
        {t.marked.includes(q.id) && <span className="tag" style={{ background: '#EEE7FB', color: '#6B46C1' }}>Marked for review</span>}</div>
      <div className="qtext"><QuestionText q={q} maxHeight={320} /></div>
      <Options q={q} value={t.answers[q.id]} onChange={answer} />
      {!q.options?.length && q.qtype !== 'numeric' && <div className="note">Written question: work it out on paper. It is not marked automatically; the solution is shown after you submit.</div>}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <NotSure on={(t.unsure || []).includes(q.id)} onChange={v => setT(s => ({ ...s, unsure: v ? [...(s.unsure || []), q.id] : (s.unsure || []).filter(x => x !== q.id) }))} />
        {t.answers[q.id] && <button type="button" className="btn ghost sm" onClick={() => answer('')}>Clear answer</button>}</div>
    </div>
    <aside className="test-side">{palette}</aside>
    <div className="test-bar">
      <button type="button" className="btn lg inline" disabled={t.idx === 0} onClick={() => go(t.idx - 1)}><Icon n="left" s={18} />Previous</button>
      <button type="button" className="btn lg inline" onClick={() => { mark(); go(nextIdx) }}><Icon n="flag" s={16} />{t.marked.includes(q.id) ? 'Unmark' : 'Mark'} &amp; next</button>
      <span className="grow" />
      <button type="button" className="btn primary lg inline save" onClick={() => t.idx === t.questions.length - 1 ? setSum(true) : go(nextIdx)}>{t.idx === t.questions.length - 1 ? 'Finish' : 'Save & next'}<Icon n="right" s={18} /></button>
    </div>
    {pal && <Sheet title="Questions" onClose={() => setPal(false)}>{palette}</Sheet>}
    {sum && <Sheet title="Submit your test?" onClose={() => setSum(false)} footer={<><button className="btn lg" style={{ flex: 1 }} onClick={() => setSum(false)}>Back to test</button>
      <button className="btn primary lg" style={{ flex: 1 }} disabled={busy} onClick={() => submit(false)}>{busy ? 'Submitting' : 'Submit'}</button></>}>
      <div className="statline"><span className="ok">{counts.an + counts.am} answered</span><span className="bad">{counts.na + counts.nv} not answered</span><span>{counts.mk + counts.am} marked for review</span></div>
      {left != null && <p className="muted">{mmss(left)} left on the clock.</p>}
      {counts.mk > 0 && <p style={{ marginBottom: 0 }}>{plural(counts.mk, 'question is', 'questions are')} marked but not answered, so they will score nothing.</p>}
    </Sheet>}
  </div></div>, document.body)
}

// ---------------- results ----------------
function Results({ r, id, styles, onAgain, onPractise }) {
  const [show, setShow] = useState('all')
  const auto = r.results.filter(x => !x.self_check)
  const pct = r.total ? Math.max(0, Math.round(r.score / r.total * 100)) : 0
  const acc = r.right + r.wrong ? Math.round(r.right / (r.right + r.wrong) * 100) : 0
  const bySubject = {}, byChapter = {}
  auto.forEach(x => {
    const s = bySubject[x.subject] ||= { right: 0, wrong: 0, blank: 0 }
    s[x.correct ? 'right' : x.given ? 'wrong' : 'blank']++
    if (!x.correct && x.chapter) byChapter[x.chapter] = (byChapter[x.chapter] || 0) + 1
  })
  const slow = [...r.results].filter(x => x.time).sort((a, b) => b.time - a.time).slice(0, 3)
  const avg = r.results.length ? Math.round(r.results.reduce((a, x) => a + (x.time || 0), 0) / r.results.length) : 0
  const list = r.results.map((x, i) => ({ ...x, n: i + 1 })).filter(x => show === 'all' || (show === 'wrong' && x.correct === false && x.given) || (show === 'blank' && !x.given) || (show === 'marked' && r.marked?.includes(x.id)))
  return <div className="stack" style={{ maxWidth: 960 }}>
    <div className="score-hero"><Ring value={pct} max={100} size={104} stroke={10}><span style={{ fontSize: 22 }}>{pct}%</span></Ring>
      <div style={{ flex: 1, minWidth: 220 }}><div className="muted" style={{ fontSize: 13 }}>{r.title}</div><div className="big">{r.score} <small>/ {r.total}</small></div>
        <div className="statline"><span className="ok">{r.right} right</span><span className="bad">{r.wrong} wrong{r.mark_wrong ? ` (−${r.wrong * r.mark_wrong})` : ''}</span><span>{r.blank} skipped</span>
          <span>Accuracy {acc}%</span>{r.time_taken > 0 && <span>{long(r.time_taken)}{r.minutes ? ` of ${long(r.minutes * 60)}` : ''}</span>}</div></div>
      <div style={{ display: 'grid', gap: 8, minWidth: 200 }}>{r.wrong > 0 && <button className="btn primary lg" onClick={onPractise}>Practise my mistakes</button>}<button className="btn lg" onClick={onAgain}>New test</button></div></div>
    <div className="row">
      {Object.keys(bySubject).length > 0 && <div className="card"><div className="card-h"><h3>By subject</h3></div>
        <table className="t"><thead><tr><th>Subject</th><th className="num">Right</th><th className="num">Wrong</th><th className="num">Skipped</th></tr></thead>
          <tbody>{Object.entries(bySubject).map(([s, v]) => <tr key={s}><td><b>{s}</b></td><td className="num" style={{ color: 'var(--ok)' }}>{v.right}</td><td className="num" style={{ color: 'var(--red)' }}>{v.wrong}</td><td className="num">{v.blank}</td></tr>)}</tbody></table></div>}
      <div className="card"><div className="card-h"><h3>Revise next</h3><span className="sub">Chapters where you lost marks</span></div><div className="card-b stack">
        {Object.entries(byChapter).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([c, n]) => <div key={c} style={{ display: 'flex', alignItems: 'center', gap: 10 }}><span style={{ flex: 1 }}>{c}</span><span className="muted">{plural(n, 'question')}</span>
          <Link className="btn sm" to={`/student/exam/${id}?tab=practice&chapter=${encodeURIComponent(c)}`}>Practise</Link></div>)}
        {!Object.keys(byChapter).length && <div className="muted">{r.wrong + r.blank ? 'Questions are not tagged to chapters yet.' : 'Nothing to revise. Excellent work.'}</div>}
        {avg > 0 && <div className="muted" style={{ fontSize: 13 }}>About {mmss(avg)} a question{slow.length ? `. Slowest: ${slow.map(x => 'Q' + (r.results.indexOf(x) + 1) + ' (' + mmss(x.time) + ')').join(', ')}` : ''}.</div>}
      </div></div>
    </div>
    <div><div className="section-h"><h3>Review answers</h3></div>
      <div className="chips" style={{ marginBottom: 12 }}>{[['all', 'All'], ['wrong', 'Wrong'], ['blank', 'Skipped'], ['marked', 'Marked']].map(([k, l]) => <button key={k} type="button" className={'chip' + (show === k ? ' on' : '')} onClick={() => setShow(k)}>{l}</button>)}</div>
      {list.map(x => <QuestionCard key={x.id} q={{ ...x, number: String(x.n) }} picked={x.given} result={x} pack={id} styles={styles} />)}
      {!list.length && <div className="card empty">Nothing here</div>}</div>
  </div>
}

export default function Tests({ id, home, styles, onPractise }) {
  const [run, setRun] = useState(null); const [res, setRes] = useState(null)
  function start(m, saved) {
    if (saved) return setRun(saved)
    const s = { aid: m.id, bid: id, title: m.title, questions: m.questions, correct: m.correct, wrong: m.wrong, idx: 0, answers: {}, marked: [], visited: [m.questions[0].id], times: {},
      started: Date.now(), deadline: m.minutes ? Date.now() + m.minutes * 60000 : null }
    localStorage.setItem(KEY(m.id), JSON.stringify(s)); setRun(s)
  }
  if (run) return <Runner test={run} onExit={() => setRun(null)} onDone={r => { setRun(null); setRes(r); window.scrollTo(0, 0) }} />
  if (res) return <Results r={res} id={id} styles={styles} onAgain={() => setRes(null)} onPractise={onPractise} />
  return <Setup id={id} home={home} onStart={start} />
}

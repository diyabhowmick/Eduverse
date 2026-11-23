// A chapter test: Eddie gets the student ready, then one question at a time, then the result.
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import { Icon, plural } from '../../ui'
import { EddieBot } from '../../Eddie'
import { speak, hush } from '../../voice'
import { sound } from '../../sound'
import '../../buddy.css'
import '../../tests.css'

const mmss = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export default function ChapterTest() {
  const { bid, ch } = useParams(); const [sp] = useSearchParams(); const nav = useNavigate()
  const [t, setT] = useState(null); const [err, setErr] = useState('')
  const [i, setI] = useState(0); const [ans, setAns] = useState({}); const [go, setGo] = useState(false)
  const [secs, setSecs] = useState(0); const [busy, setBusy] = useState(false); const [talking, setTalking] = useState(false)
  const started = useRef(false)
  const level = sp.get('level') || 'quick', retry = sp.get('retry')

  useEffect(() => {
    if (started.current) return; started.current = true
    const go = ch === 'daily' ? api(`/api/student/books/${bid}/daily/start`, { method: 'POST' })
      : api(`/api/student/books/${bid}/tests/${ch}/start`, { method: 'POST', body: retry ? { ids: retry.split(',').map(Number) } : { level } })
    go.then(setT).catch(e => { const m = /^done:(\d+)/.exec(e.message); if (m) nav('/student/result/' + m[1], { replace: true }); else setErr(e.message) })
  }, [bid, ch, level, retry])
  useEffect(() => { if (t?.level === 'daily' && !go && sound.on && navigator.userActivation?.hasBeenActive) { const x = setTimeout(() => speak(document.querySelector('.ct-say')?.innerText || '', { onStart: () => setTalking(true), onEnd: () => setTalking(false) }), 500); return () => clearTimeout(x) } }, [t]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!go) return; const x = setInterval(() => setSecs(s => s + 1), 1000); return () => clearInterval(x) }, [go])
  useEffect(() => () => hush(), [])
  // In the Daily 5 Eddie reads each question out; in any test the student can ask him to.
  const readQ = qq => { if (!qq || !sound.on) return; hush(); speak(qq.text.replace(/_{3,}/g, 'blank').replace(/[.?!]*$/, m => m || '.') + (qq.options?.length ? ' ' + qq.options.map(o => `${o.key.toUpperCase()}: ${o.text.replace(/[.?!]+$/, '')}.`).join(' ') : ''), { onStart: () => setTalking(true), onEnd: () => setTalking(false) }) }
  useEffect(() => { if (go && t?.level === 'daily') { const x = setTimeout(() => readQ(t.questions[i]), i === 0 ? 2600 : 300); return () => clearTimeout(x) } }, [i, go]) // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <div className="page"><div className="card empty">{err} <Link to={'/student/read/' + bid}>Back to the book</Link></div></div>
  if (!t) return <div className="page"><div className="empty">Getting your test ready</div></div>
  const n = t.questions.length, q = t.questions[i]
  const daily = t.level === 'daily'
  const where = t.chapter > 0 ? `Unit ${t.chapter}, ${t.chapter_title}` : daily ? t.book_title : t.chapter_title
  const mixText = m => [m.mistake && `${m.mistake === 1 ? 'one' : m.mistake} you missed before`, m.reading && `${m.reading === 1 ? 'one' : m.reading} on what you read`, m.new && `${m.new === 1 ? 'one' : m.new} new`].filter(Boolean)
  const intro = daily ? `Your Daily 5! I picked ${mixText(t.mix).join(', ').replace(/, ([^,]*)$/, ' and $1')}. Five quick questions, then you're done for today.`
    : t.level === 'retry' ? `Let's try the ${n === 1 ? 'one' : n} you missed again. You know more now!`
    : `${plural(n, 'question')} on ${t.chapter_title}. No rush. Read each one carefully, and if you are not sure, make your best guess.`

  function begin() {
    if (daily) hush()
    setGo(true)
    if (sound.on && !daily) speak(`Ready? ${intro} Let's go!`, { onStart: () => setTalking(true), onEnd: () => setTalking(false) })
  }
  async function finish() {
    setBusy(true); hush()
    try { const r = await api(`/api/student/tests/${t.id}/submit`, { method: 'POST', body: { answers: ans, seconds: secs } }); nav('/student/result/' + r.id, { replace: true }) }
    catch (e) { setErr(e.message); setBusy(false) }
  }
  const answered = Object.values(ans).filter(v => String(v).trim()).length

  if (!go) return (
    <div className="page"><div className="ct-intro card">
      <div className="ct-eddie"><EddieBot size={96} jet={false} mood="happy" talking={talking} /></div>
      <div className="k">{daily ? "Eddie's Daily 5" : t.level === 'retry' ? 'Try again' : t.level === 'quick' ? 'Quick check' : 'Chapter test'}</div>
      <h1>{daily ? `Good ${new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 17 ? 'afternoon' : 'evening'}! Ready for today's five?` : where}</h1>
      <p className="ct-say">{intro}</p>
      <div className="ct-facts"><span><Icon n="check" s={16} />{plural(n, 'question')}</span><span><Icon n="clock" s={16} />No time limit</span><span><Icon n="book" s={16} />{t.book_title}</span></div>
      <button className="btn primary lg" onClick={begin}>Start</button>
      {!daily && <Link className="btn ghost" to={'/student/read/' + bid + '?ch=' + t.chapter}>Read the unit first</Link>}
    </div></div>
  )

  const set = v => setAns(a => ({ ...a, [q.id]: v }))
  return (
    <div className="page ct">
      <div className="ct-top">
        <div><div className="k">{daily ? "Eddie's Daily 5" : t.level === 'retry' ? 'Try again' : t.level === 'quick' ? 'Quick check' : 'Chapter test'}</div><b>{where}</b></div>
        <div className="ct-meta"><span><Icon n="clock" s={15} />{mmss(secs)}</span><span>{answered} of {n} answered</span>
          <span className={'ct-mini' + (talking ? ' talking' : '')} title="Eddie is with you"><EddieBot size={30} jet={false} talking={talking} /></span></div>
      </div>
      <div className="ct-bar"><i style={{ width: ((i + 1) / n * 100) + '%' }} /></div>
      <div className="ct-q card">
        <div className="ct-qn">{q.why && <em className={'why ' + q.why}>{{ mistake: 'From your revision list', reading: 'From your reading', new: 'New' }[q.why]}</em>}Question {i + 1} of {n}{q.section_title && <span> · {q.section_title}</span>}
          <button type="button" className="ct-read" onClick={() => readQ(q)} title="Read it to me" aria-label="Read the question to me"><svg viewBox="0 0 24 24"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4zM15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" /></svg></button></div>
        {q.figure?.image && <figure className="ct-fig"><img src={`/api/content/${bid}/${q.figure.image}`} alt={q.figure.caption || ''} />
          {(q.figure.number || q.figure.caption) && <figcaption>{q.figure.number && <b>Figure {q.figure.number} </b>}{q.figure.caption}</figcaption>}</figure>}
        <div className="ct-text">{q.text}</div>
        {q.options.length ? <div className="ct-opts">{q.options.map(o =>
          <button key={o.key} type="button" className={'ct-opt' + (ans[q.id] === o.key ? ' on' : '')} onClick={() => set(o.key)} aria-pressed={ans[q.id] === o.key}>
            <span className="ct-key">{o.key.toUpperCase()}</span><span>{o.text}</span></button>)}</div>
          : <input className="input ct-fill" placeholder="Type your answer" value={ans[q.id] || ''} onChange={e => set(e.target.value)} onKeyDown={e => e.key === 'Enter' && i < n - 1 && setI(i + 1)} autoFocus />}
      </div>
      <div className="ct-nav">
        <button className="btn" disabled={i === 0} onClick={() => setI(i - 1)}><Icon n="left" s={16} />Back</button>
        <div className="ct-dots">{t.questions.map((x, k) => <button key={x.id} type="button" className={(k === i ? 'cur ' : '') + (String(ans[x.id] || '').trim() ? 'done' : '')} onClick={() => setI(k)} aria-label={'Question ' + (k + 1)}>{k + 1}</button>)}</div>
        {i < n - 1 ? <button className="btn primary" onClick={() => setI(i + 1)}>Next<Icon n="right" s={16} /></button>
          : <button className="btn primary" disabled={busy} onClick={finish}>{busy ? 'Checking…' : answered < n ? `Finish (${n - answered} blank)` : 'Finish'}</button>}
      </div>
    </div>
  )
}

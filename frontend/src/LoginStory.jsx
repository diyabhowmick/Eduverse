import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { MathText, Ring, Icon } from './ui'
import './story.css'

export { Brandmark } from './Brandmark'
import { Brandmark } from './Brandmark'

const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches
const SPARK = <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l1.9 5.6 5.6 1.9-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.9zM19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z" /></svg>
const FLOAT = [['$E = mc^2$', 4, 8, 1.1], ['$PV = nRT$', 86, 74, 1], ['$\\lambda = \\frac{h}{p}$', 2, 70, 1.15], ['$\\sin^2\\theta + \\cos^2\\theta = 1$', 56, 2, .85], ['$F = ma$', 70, 90, 1]]

// ---------------- scene 1 and 2: the book ----------------
// The cover opens only the first time someone ever sees it; after that the book is already open.
let bookOpened = typeof localStorage !== 'undefined' && localStorage.getItem('ev_book_opened') === '1'

function Book({ deeper }) {
  const [opened] = useState(() => deeper || bookOpened)
  useEffect(() => { bookOpened = true; try { localStorage.setItem('ev_book_opened', '1') } catch { /* private mode */ } }, [])
  return <div className={'book-scene' + (opened ? ' opened' : '') + (deeper ? ' deeper' : '')}>
    {FLOAT.map(([f, x, y, z], n) => <span key={n} className="bk-float" style={{ left: x + '%', top: y + '%', fontSize: z + 'em', animationDelay: -n * 3.1 + 's' }}><MathText text={f} /></span>)}
    <div className="book">
      <div className="bk-stack" />
      <div className="bk-right"><div className="bk-sheet r"><div className="bk-copy first">
        <div className="bk-fig-box"><svg viewBox="0 0 120 60"><rect x="8" y="22" width="34" height="24" rx="3" /><path d="M48 34h52m-8-6 8 6-8 6" /><text x="62" y="24">v</text><path d="M4 50h112" className="ground" /></svg></div>
        <i className="bk-lines" /><i className="bk-lines short" /></div></div></div>
      <div className="bk-cover"><div className="bk-face front"><div className="bk-sheet r"><i className="bk-lines" /><i className="bk-lines short" /><i className="bk-lines" /></div></div>
        <div className="bk-face back"><div className="bk-sheet l"><div className="bk-copy first">
          <small>Chapter 5 · Laws of Motion</small><h4>Momentum</h4>
          <p>The <mark>momentum<em className="tap" /></mark> of a body is the product of its mass and its velocity:</p>
          <div className="bk-formula"><MathText text="$p = mv$" /></div>
          <p>A loaded truck and a cricket ball moving at the same speed carry very different momentum.</p>
        </div></div></div></div>
    </div>
    <div className={'ex-card first' + (deeper ? ' hold' : '')}>
      <div className="ex-top"><span className="ex-pill">{SPARK}Explain simply</span><span>Physics</span></div>
      <b>Momentum</b>
      <div className="ex-body"><div className="ex-think"><i /><i /><i /></div>
        <div className="ex-text">Momentum tells you how hard it is to stop something moving. It depends on mass and <span className="pick">velocity<em className="sel-bubble">Explain this</em></span>, written <MathText text="$p = mv$" />.</div></div>
      <div className="ex-foot">AI explanation · tap any word in your book</div>
    </div>
    {deeper && <div className="ex-card l2">
      <div className="ex-crumb">Momentum <span>›</span> <b>velocity</b></div>
      <div className="ex-body"><div className="ex-think"><i /><i /></div>
        <div className="ex-text">Velocity is speed in a stated direction. Going <MathText text="$5$" /> m/s north and <MathText text="$5$" /> m/s south is the same speed but two different velocities.</div></div>
    </div>}
    <div className="bk-shadow" />
  </div>
}

// ---------------- scene 3: practise ----------------
function Practise() {
  return <div className="sc sc-q gcard">
    <div className="gq-top"><span className="gq-tag">JEE Main · 2 April 2026, Shift 1</span><span>Question 9</span></div>
    <div className="gq-text">The midpoints of the sides of triangle <MathText text="$ABC$" /> are <MathText text="$(\tfrac52, 7), (\tfrac52, 3)$" /> and <MathText text="$(4, 5)$" />. If its incentre is <MathText text="$(h, k)$" />, then <MathText text="$3h + k$" /> is</div>
    <div className="gq-opts">{['11', '12', '13', '14'].map((o, i) => <div key={o} className={'gq-opt' + (i === 2 ? ' pick' : '')}><span>{'ABCD'[i]}</span>{o}{i === 2 && <em className="gq-plus">+4</em>}</div>)}</div>
    <div className="gq-sol"><b>Solution.</b> The vertices are <MathText text="$(4,9), (1,5), (4,1)$" />, with sides <MathText text="$5, 8, 5$" />. The incentre is <MathText text="$(\tfrac83, 5)$" />, so <MathText text="$3h + k = 13$" />.</div>
  </div>
}

// ---------------- scene 4: test ----------------
const PATTERN = 'aaanaaamaaaxaanaaaaxaaamaaanaa'
function Test() {
  const still = reduced()
  const [n, setN] = useState(still ? 30 : 0); const [sec, setSec] = useState(10798); const [done, setDone] = useState(still)
  useEffect(() => {
    if (still) return
    const a = setInterval(() => setN(x => Math.min(30, x + 1)), 85)
    const b = setInterval(() => setSec(s => s - 1), 1000)
    const c = setTimeout(() => setDone(true), 3400)
    return () => { clearInterval(a); clearInterval(b); clearTimeout(c) }
  }, [])
  const hms = `${Math.floor(sec / 3600)}:${String(Math.floor(sec % 3600 / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`
  return <div className="sc sc-test gcard">
    <div className="gt-top"><b>JEE Main · Full paper</b><span className="gt-timer"><Icon n="clock" s={14} />{hms}</span></div>
    <div className="gt-body">
      <div className="gt-q"><span className="gt-n">Question 21</span><i /><i /><i className="s" /><div className="gt-opts"><i /><i className="on" /><i /><i /></div></div>
      <div className="gt-pal">{[...PATTERN].map((c, i) => <span key={i} className={i < n ? { a: 'an', n: 'na', m: 'mk', x: 'am' }[c] : ''}>{i + 1}</span>)}</div>
    </div>
    <div className={'gt-score' + (done ? ' in' : '')}><Ring value={done ? 72 : 0} max={100} size={92} stroke={9}><span style={{ fontSize: 18 }}>72%</span></Ring>
      <div><div className="gt-big">216 <small>/ 300</small></div><div className="gt-sub">Physics 76 · Chemistry 68 · Maths 72</div><div className="gt-note">Sample result</div></div></div>
  </div>
}

// ---------------- scene 5: track ----------------
function Track() {
  const still = reduced()
  const [v, setV] = useState(still ? 20 : 0)
  useEffect(() => { if (still) return; const t = setTimeout(() => setV(20), 350); return () => clearTimeout(t) }, [])
  return <div className="sc sc-track">
    <div className="gcard tk-goal"><Ring value={v} max={20} size={86} stroke={9}><span style={{ fontSize: 15 }}>{v ? '20' : '0'}<small style={{ display: 'block', fontSize: 10, fontWeight: 500 }}>of 20 min</small></span></Ring>
      <div><b>Today's goal</b><span className="tk-done">Done</span></div></div>
    <div className="gcard tk-streak"><Icon n="fire" s={26} /><div><b>12-day streak</b><span>Keep it going</span></div>
      <div className="tk-week">{[30, 45, 20, 50, 40, 60, 35].map((h, i) => <i key={i} style={{ '--h': h + '%', animationDelay: i * 70 + 'ms' }} />)}</div></div>
    <div className="gcard tk-next"><span className="tk-k">Practise next</span><b>Thermodynamics</b><span className="tk-pct">48% right in 25 tries</span><span className="tk-btn">Practise</span></div>
  </div>
}

// ---------------- teachers and school admins: classes ----------------
const PUPILS = [['Aarav', 82, ''], ['Diya', 67, ''], ['Ishaan', 74, ''], ['Meera', 31, 'Behind · 9 days'], ['Rohan', 58, '']]
function Classes() {
  const [go, setGo] = useState(reduced())
  useEffect(() => { const t = setTimeout(() => setGo(true), 200); return () => clearTimeout(t) }, [])
  return <div className="sc sc-class gcard">
    <div className="gq-top"><b style={{ color: '#fff', fontSize: 15 }}>Class 11 A · Physics</b><span>38 students · 31 read this week</span></div>
    {PUPILS.map(([name, p, tag]) => <div key={name} className={'cl-row' + (tag ? ' behind' : '')}><span className="cl-name">{name}</span>
      <span className="cl-bar"><i style={{ width: go ? p + '%' : 0 }} /></span><span className="cl-p">{p}%</span>
      {tag ? <span className="cl-tag">{tag}<em className="cl-nudge">Nudge</em></span> : <span />}</div>)}
    <div className="cl-toast">Reminder sent to Meera</div>
  </div>
}

// ---------------- reviewers: page by page ----------------
function Review() {
  const [n, setN] = useState(reduced() ? 15 : 14)
  useEffect(() => { if (reduced()) return; const t = setTimeout(() => setN(15), 3550); return () => clearTimeout(t) }, [])
  return <div className="sc sc-review">
    <div className="gcard rv-orig"><span className="rv-k">Original · page 14</span><i /><i /><i className="s" /><div className="rv-fig" /><i /><i className="s" /></div>
    <div className="gcard rv-digi"><span className="rv-k">Digital page</span><b>5.2 Newton's second law</b><i /><i className="s" /><div className="rv-eq"><MathText text="$F = \frac{dp}{dt} = ma$" /></div><i />
      <ul className="rv-checks"><li>Text matches the original</li><li>Equation checked</li><li>Figure in place</li></ul>
      <div className="rv-act"><span className="rv-count"><b>{n}</b> of 40 pages approved</span><span className="rv-btn">Approve page</span></div></div>
  </div>
}

const SCENES = {
  read: { label: 'Read', cap: 'Your textbook, made digital. Tap any word for an explanation at your level.', ms: 7600, C: () => <Book /> },
  deeper: { label: 'Go deeper', cap: 'Still unsure? Select words inside the explanation to go one level deeper.', ms: 7000, C: () => <Book deeper /> },
  practise: { label: 'Practise', cap: 'Past exam questions, checked as you answer, with worked solutions.', ms: 7000, C: Practise },
  test: { label: 'Test', cap: 'Timed tests that feel like the real exam, with exam marking and a question palette.', ms: 7400, C: Test },
  track: { label: 'Track', cap: 'Daily goals, streaks and the chapters to practise next.', ms: 6400, C: Track },
  classes: { label: 'Classes', cap: 'Every class at a glance, and who needs a nudge.', ms: 6800, C: Classes },
  review: { label: 'Review', cap: 'Each page is checked against the original before any student sees it.', ms: 6800, C: Review },
}
const ORDER = { student: ['read', 'deeper', 'practise', 'test', 'track'], teacher: ['read', 'practise', 'track', 'classes'],
  admin: ['read', 'practise', 'track', 'classes'], reviewer: ['review', 'read', 'deeper'] }

// The story of what EduVerse does, told in a few short scenes on one canvas that scales to any space.
export default function LoginStory({ portal = 'student', compact, tour, onIndex }) {
  const list = ORDER[portal] || ORDER.student
  const [i, setI] = useState(0); const [paused, setPaused] = useState(reduced); const [k, setK] = useState(.8)
  const stage = useRef(); const firstCover = useRef(!bookOpened)
  useLayoutEffect(() => {
    const el = stage.current; if (!el) return
    const fit = () => setK(Math.min(tour ? 1.7 : 1.15, el.clientWidth / 640, el.clientHeight / 360))
    fit(); const ro = new ResizeObserver(fit); ro.observe(el); return () => ro.disconnect()
  }, [])
  const ms = SCENES[list[i]].ms + (i === 0 && firstCover.current && list[0] === 'read' ? 1100 : 0)
  useEffect(() => {
    onIndex?.(i)
    if (paused) return
    const t = setTimeout(() => { firstCover.current = false; setI(x => (x + 1) % list.length) }, ms)
    return () => clearTimeout(t)
  }, [i, paused])
  const S = SCENES[list[i]]
  return <div className={'story' + (compact ? ' compact' : '') + (tour ? ' in-tour' : '') + (paused ? ' paused' : '')}>
    <div className="story-stage" ref={stage} aria-hidden="true">
      <div className="story-canvas" style={{ transform: `translate(-50%, -50%) scale(${k})` }}><div key={list[i] + i} className="story-scene"><S.C /></div></div></div>
    {!tour && <p className="story-cap" aria-live="polite">{S.cap}</p>}
    <div className="story-nav">
      {list.map((s, n) => <button key={s} type="button" className={n === i ? 'on' : ''} aria-current={n === i} onClick={() => { firstCover.current = false; setI(n) }}>
        {SCENES[s].label}<i key={n === i ? 'run' + i : 'idle'} style={{ animationDuration: ms + 'ms' }} /></button>)}
      <button type="button" className="story-pause" onClick={() => setPaused(p => !p)} aria-label={paused ? 'Play the story' : 'Pause the story'}>
        {paused ? <Icon n="play" s={14} /> : <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4h4v16H7zM13 4h4v16h-4z" fill="currentColor" /></svg>}</button>
    </div>
    <ul className="sr-only">{list.map(s => <li key={s}>{SCENES[s].label}: {SCENES[s].cap}</li>)}</ul>
  </div>
}

// The lower half of the sign in panel.
export function LoginCopy({ eyebrow, head, sub }) {
  return <div className="login-copy">
    {eyebrow && <div className="lc-eyebrow"><i />{eyebrow}</div>}
    <h2>{head}</h2>
    <p>{sub}</p>
    <div className="lc-foot"><span className="lc-tag">Textbooks<i />Exam packs<i />AI explanations</span><span>EduVerse by zPROx.AI</span></div>
  </div>
}

// Full screen, for people who arrive without knowing what EduVerse is.
export function Tour({ onClose }) {
  const [i, setI] = useState(0)
  const list = ORDER.student
  useEffect(() => { const k = e => e.key === 'Escape' && onClose(); addEventListener('keydown', k); return () => removeEventListener('keydown', k) }, [])
  const S = SCENES[list[i]]
  return createPortal(<div className="tour" role="dialog" aria-modal="true" aria-label="How EduVerse works">
    <div className="tour-top"><Brandmark small /><button className="btn ghost tour-x" onClick={onClose} aria-label="Close"><Icon n="x" /></button></div>
    <div className="tour-cap"><span className="tour-k">{i + 1} of {list.length} · {S.label}</span><h2>{S.cap}</h2></div>
    <LoginStory portal="student" tour onIndex={setI} />
    <div className="tour-cta"><Link className="btn primary lg inline" to="/signup">Create a free account</Link><button className="btn lg inline tour-sec" onClick={onClose}>Back to sign in</button></div>
  </div>, document.body)
}

import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { MathText } from './ui'

export const STYLE = { exam: 'Exam answer', concept_clarity: 'Explain simply', curiosity: 'Why it matters', research: 'Go deeper' }

// One explanation thread: the word or question first, then phrases the student selects inside it.
// Levels 1 and 2 come from saved explanations shared by every student; level 3 and typed questions are
// written for this student alone and use a credit. A saved answer still shows a short "thinking" moment,
// kept under a second so it never slows anyone down.
export default function ExplainPanel({ request, styles = Object.keys(STYLE) }) {
  const [style, setStyle] = useState(styles.includes('concept_clarity') ? 'concept_clarity' : styles[0])
  const [trail, setTrail] = useState([]); const [busy, setBusy] = useState(false); const [err, setErr] = useState('')
  const [pick, setPick] = useState(null); const [doubt, setDoubt] = useState(''); const [report, setReport] = useState(null)
  const box = useRef()
  const top = trail[trail.length - 1]

  async function ask(body, how) {
    setBusy(true); setErr(''); setPick(null); const t0 = Date.now()
    try {
      const r = await api('/api/learn/explain', { method: 'POST', body })
      const wait = 650 - (Date.now() - t0); if (wait > 0) await new Promise(f => setTimeout(f, wait))
      setTrail(t => how === 'reset' ? [r] : how === 'replace' ? [...t.slice(0, -1), r] : [...t, r])
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const start = s => { setStyle(s); ask({ ...request, style: s }, 'reset') }
  useEffect(() => { start(style) }, [])

  function differently() {
    const parent = trail[trail.length - 2]
    ask(top.level === 1 ? { ...request, style, different_from: top.id } : { parent_id: parent.id, term: top.term, different_from: top.id }, 'replace')
  }
  async function vote(value, note = '') {
    try {
      const r = await api(`/api/learn/explanations/${top.id}/vote`, { method: 'POST', body: { value: value === top.vote ? 'clear' : value, note } })
      if (value === 'report') { setReport(null); setTrail(t => t.map(x => x.id === top.id ? { ...x, reported: true } : x)) }
      else setTrail(t => t.map(x => x.id === top.id ? { ...x, vote: r.vote } : x))
    } catch (e) { setErr(e.message) }
  }
  function onSelect() {
    setTimeout(() => {
      const s = getSelection(); const t = s.toString().trim()
      if (!top?.id || !t || t.length < 2 || t.length > 80 || !box.current?.contains(s.anchorNode)) return setPick(null)
      const r = s.getRangeAt(0).getBoundingClientRect()
      setPick({ t, x: r.left, y: r.bottom + 6 })
    }, 0)
  }

  return <div className="xp">
    {trail.length > 1 && <nav className="xp-trail" aria-label="Explanation path">{trail.map((x, i) => <span key={i}>
      {i > 0 && <i>›</i>}<button type="button" className={i === trail.length - 1 ? 'on' : ''} disabled={i === trail.length - 1 || busy} onClick={() => setTrail(t => t.slice(0, i + 1))}>{x.term || 'Explanation'}</button></span>)}</nav>}
    {trail.length <= 1 && styles.length > 1 && <div className="seg xp-styles">{styles.map(s => <button key={s} type="button" disabled={busy} className={s === style ? 'on' : ''} onClick={() => s !== style && start(s)}>{STYLE[s] || s}</button>)}</div>}
    {busy && <div className="xp-think" aria-label="Writing the explanation"><i /><i /><i /></div>}
    {err && !busy && <div className="err" role="alert">{err}</div>}
    {top && !busy && <>
      {top.note && <div className="muted xp-note" style={{ marginBottom: 6 }}>{top.note}</div>}
      <div className="xp-text" ref={box} onMouseUp={onSelect}><MathText text={top.text} /></div>
      {top.id ? <>
        <div className="xp-acts">
          <button type="button" className={'btn ghost sm' + (top.vote === 'up' ? ' on' : '')} aria-pressed={top.vote === 'up'} onClick={() => vote('up')}>Helpful</button>
          <button type="button" className={'btn ghost sm' + (top.vote === 'down' ? ' on' : '')} aria-pressed={top.vote === 'down'} onClick={() => vote('down')}>Not helpful</button>
          <button type="button" className="btn ghost sm" onClick={differently}>Explain differently</button>
          {!top.reported ? <button type="button" className="btn ghost sm xp-report" onClick={() => setReport('')}>Report a mistake</button> : <span className="muted xp-note">Thanks, a reviewer will check it</span>}
        </div>
        {report !== null && <form className="xp-form" onSubmit={e => { e.preventDefault(); vote('report', report) }}>
          <input className="input" autoFocus placeholder="What is wrong? (optional)" value={report} onChange={e => setReport(e.target.value)} />
          <button className="btn sm">Send</button><button type="button" className="btn ghost sm" onClick={() => setReport(null)}>Cancel</button></form>}
        <div className="muted xp-note">Select any words above to have them explained{top.free_deeper ? '' : ' (uses 1 AI credit)'}.</div>
        <form className="xp-form" onSubmit={e => { e.preventDefault(); if (doubt.trim()) { ask({ parent_id: top.id, doubt }, 'push'); setDoubt('') } }}>
          <input className="input" placeholder="Ask your own question (uses 1 AI credit)" aria-label="Ask your own question" value={doubt} onChange={e => setDoubt(e.target.value)} />
          <button className="btn sm" disabled={busy || !doubt.trim()}>Ask</button></form>
      </> : <div className="muted xp-note">Written just for you. Go back to keep exploring the saved explanations.</div>}
      {top.credits_left != null && <div className="muted xp-note">{top.credits_left} AI credits left today. Saved explanations are always free.</div>}
    </>}
    {pick && <button type="button" className="selbtn" style={{ left: pick.x, top: pick.y }} onMouseDown={e => { e.preventDefault(); ask({ parent_id: top.id, term: pick.t }, 'push'); getSelection().removeAllRanges() }}>
      Explain this{top.free_deeper ? '' : ' · 1 credit'}</button>}
  </div>
}

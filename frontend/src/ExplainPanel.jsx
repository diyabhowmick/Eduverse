import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { MathText, Icon } from './ui'
import { EddieBot } from './Eddie'

export const STYLE = { exam: 'Exam answer', concept_clarity: 'Explain simply', curiosity: 'Why it matters', research: 'Go deeper' }

const esc = t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const calm = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

// Text with its prepared level 2 words underlined. Maths stays whole so it never renders half written.
function LinkText({ text, links = [], onLink }) {
  const terms = [...new Set(links.map(l => l.term).filter(Boolean))].sort((a, b) => b.length - a.length)
  const re = terms.length ? new RegExp('(' + terms.map(esc).join('|') + ')', 'gi') : null
  const parts = String(text ?? '').split(/(\$[^$\n]+\$)/)
  return <span style={{ whiteSpace: 'pre-wrap' }}>{parts.map((p, i) => {
    if (p.length > 2 && p.startsWith('$') && p.endsWith('$')) return <MathText key={i} text={p} />
    if (!re || !onLink) return <span key={i}>{p}</span>
    return <span key={i}>{p.split(re).map((x, j) => j % 2
      ? <button key={j} type="button" className="xp-link" onClick={() => onLink(terms.find(t => t.toLowerCase() === x.toLowerCase()) || x)}>{x}</button>
      : x)}</span>
  })}</span>
}

// Saved answers come back at once; they are revealed a few words at a time so reading feels the same as a live answer.
function StreamText({ text, links, onLink, done, onDone }) {
  const tokens = useMemo(() => String(text ?? '').split(/(\$[^$\n]+\$|\s+)/).filter(Boolean), [text])
  const [n, setN] = useState(done || calm() ? tokens.length : 0)
  useEffect(() => {
    if (n >= tokens.length) { onDone?.(); return }
    const t = setTimeout(() => setN(k => Math.min(tokens.length, k + 2 + (Math.random() < 0.3 ? 2 : 0))), 32)
    return () => clearTimeout(t)
  }, [n, tokens.length])
  const full = n >= tokens.length
  return <LinkText text={full ? text : tokens.slice(0, n).join('')} links={full ? links : []} onLink={onLink} />
}

// One explanation thread: the word or question first, then the underlined words inside it, or any words the student selects.
// Levels 1 and 2 are written ahead and shared by every student. Anything nobody prepared is written once and then
// saved for the next student. A typed question is matched to saved answers first; the model only bridges into one,
// or answers in full when nothing saved fits. Saved answers show a short "thinking" moment and stream in.
const seen = k => { try { return localStorage.getItem('ev_hint_' + k) === '1' } catch { return true } }
const markSeen = k => { try { localStorage.setItem('ev_hint_' + k, '1') } catch { /* private mode */ } }

// One chat bubble from Eddie. Saved replies stream in like live ones.
function Reply({ m, onOpen, onDone }) {
  if (m.err) return <div className="xc-msg xc-bot err-b"><MathText text={m.err} /></div>
  const r = m.r
  return <div className="xc-msg xc-bot">
    {r.kind === 'saved' && <div className="xc-tag">Already explained: <b>{r.term}</b></div>}
    {r.kind === 'match' && <div className="xc-tag">Answered from saved replies</div>}
    <StreamText text={r.text} done={m.done} onDone={onDone} />
    {r.see && !r.see.same && m.done && <div className="xp-see"><div className="xc-tag">From the saved explanation of <b>{r.see.term}</b></div><MathText text={r.see.text} /></div>}
    {r.see?.same && m.done && <div className="xc-tag">Read the explanation above again with this in mind.</div>}
    {r.kind === 'saved' && r.id && m.done && <button type="button" className="btn ghost sm" onClick={() => onOpen(r)}>Open it here <Icon n="right" s={14} /></button>}
  </div>
}

// layout: 'side' is the resizable panel beside the book; 'wide' is the large view, which
// reads at a larger size.
export default function ExplainPanel({ request, styles = Object.keys(STYLE), onSaved, layout = 'side' }) {
  const [style, setStyle] = useState(styles.includes('concept_clarity') ? 'concept_clarity' : styles[0])
  const [trail, setTrail] = useState([]); const [busy, setBusy] = useState(false); const [err, setErr] = useState('')
  const [pick, setPick] = useState(null); const [doubt, setDoubt] = useState(''); const [report, setReport] = useState(null)
  const [chats, setChats] = useState({}); const [typing, setTyping] = useState(false)
  const [hint, setHint] = useState(!seen('links')); const [kept, setKept] = useState({})
  const box = useRef(); const chatEnd = useRef()
  const top = trail[trail.length - 1]
  const thread = (top && chats[top.id]) || []

  async function ask(body, how) {
    setBusy(true); setErr(''); setPick(null); const t0 = Date.now()
    try {
      const r = await api('/api/learn/explain', { method: 'POST', body })
      const wait = 650 - (Date.now() - t0); if (wait > 0) await new Promise(f => setTimeout(f, wait))
      setTrail(t => how === 'reset' ? [r] : how === 'replace' ? [...t.slice(0, -1), r] : [...t, r])
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const start = s => { setStyle(s); setChats({}); ask({ ...request, style: s }, 'reset') }
  useEffect(() => { start(style) }, [])
  useEffect(() => { chatEnd.current?.scrollIntoView({ block: 'nearest', behavior: calm() ? 'auto' : 'smooth' }) }, [thread.length, typing])

  // A typed question stays under the explanation it was asked about, as a short chat with Eddie.
  async function send(e) {
    e.preventDefault(); const q = doubt.trim(); if (!q || !top?.id || typing) return
    const id = top.id; setDoubt(''); setTyping(true)
    const add = m => setChats(c => ({ ...c, [id]: [...(c[id] || []), m] }))
    add({ me: q }); const t0 = Date.now()
    try {
      const r = await api('/api/learn/explain', { method: 'POST', body: { parent_id: id, doubt: q } })
      const wait = 700 - (Date.now() - t0); if (wait > 0) await new Promise(f => setTimeout(f, wait))
      add({ r })
    } catch (x) { add({ err: x.message }) } finally { setTyping(false) }
  }
  const replyDone = i => setChats(c => ({ ...c, [top.id]: c[top.id].map((m, j) => j === i ? { ...m, done: true } : m) }))

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
  async function keep() {
    const on = kept[top.id]
    try {
      if (on) await api('/api/student/study/saved/by-explanation/' + top.id, { method: 'DELETE' })
      else await api('/api/student/study/saved', { method: 'POST', body: { explanation_id: top.id, book_id: request.book_id || null, chapter: request.chapter ?? null, path: trail.map(x => x.term).filter(Boolean) } })
      setKept(k => ({ ...k, [top.id]: !on })); onSaved?.()
    } catch (e) { setErr(e.message) }
  }
  const deeper = t => { if (hint) { setHint(false); markSeen('links') } ask({ parent_id: top.id, term: t }, 'push') }

  // No source quote here: every screen that passes a `definition` already shows the book's
  // own words above this panel, and repeating them was the first thing that looked wrong.
  return <div className={'xp' + (layout === 'wide' ? ' xp-wide' : '')}>
    {trail.length > 1 && <nav className="xp-chips" aria-label="Explanation path">{trail.map((x, i) => <span key={i} className="xp-chip-w">
      {i > 0 && <Icon n="right" s={12} />}
      <button type="button" className={'xp-chip' + (i === trail.length - 1 ? ' on' : '')} disabled={i === trail.length - 1 || busy} onClick={() => setTrail(t => t.slice(0, i + 1))}>
        <i>{x.level || i + 1}</i>{x.term || 'Explanation'}</button></span>)}</nav>}
    {trail.length <= 1 && styles.length > 1 && <div className="seg xp-styles">{styles.map(s => <button key={s} type="button" disabled={busy} className={s === style ? 'on' : ''} onClick={() => s !== style && start(s)}>{STYLE[s] || s}</button>)}</div>}
    {busy && <div className="xp-think" aria-label="Writing the explanation"><i /><i /><i /></div>}
    {err && !busy && <div className="err" role="alert">{err}</div>}
    {top && !busy && <div className="xp-body" key={trail.length + ':' + top.id}>
      {top.note && <div className="muted xp-note" style={{ marginBottom: 6 }}>{top.note}</div>}
      {top.bridge && <div className="xp-bridge"><MathText text={top.bridge} /></div>}
      <div className="xp-text" ref={box} onMouseUp={onSelect}>
        <StreamText text={top.text} links={top.links} done={top._done} onLink={deeper}
          onDone={() => !top._done && setTrail(tr => tr.map((x, i) => i === tr.length - 1 ? { ...x, _done: true } : x))} />
      </div>
      {hint && top._done && top.links?.length > 0 && <div className="xp-hint" role="status"><span>Tap an <u>underlined word</u> to go one level deeper.</span>
        <button type="button" className="linkbtn" onClick={() => { setHint(false); markSeen('links') }}>Got it</button></div>}
      {top.id ? <>
        <div className="xp-acts">
          <button type="button" className={'btn ghost sm' + (top.vote === 'up' ? ' on' : '')} aria-pressed={top.vote === 'up'} onClick={() => vote('up')}><Icon n="check" s={14} />Helpful</button>
          <button type="button" className={'btn ghost sm' + (top.vote === 'down' ? ' on' : '')} aria-pressed={top.vote === 'down'} onClick={() => vote('down')}>Not helpful</button>
          <button type="button" className="btn ghost sm" onClick={differently}>Explain differently</button>
          {request.scope === 'book' && <button type="button" className={'btn ghost sm xp-keep' + (kept[top.id] ? ' on' : '')} aria-pressed={!!kept[top.id]} onClick={keep}><Icon n="star" s={14} />{kept[top.id] ? 'Saved' : 'Save'}</button>}
          {!top.reported ? <button type="button" className="btn ghost sm xp-report" onClick={() => setReport('')}>Report a mistake</button> : <span className="muted xp-note">Thanks, a reviewer will check it</span>}
        </div>
        {report !== null && <form className="xp-form" onSubmit={e => { e.preventDefault(); vote('report', report) }}>
          <input className="input" autoFocus placeholder="What is wrong? (optional)" value={report} onChange={e => setReport(e.target.value)} />
          <button className="btn sm">Send</button><button type="button" className="btn ghost sm" onClick={() => setReport(null)}>Cancel</button></form>}

        <div className="xc" aria-label="Ask Eddie about this">
          {thread.length > 0 && <div className="xc-list">{thread.map((m, i) => m.me != null
            ? <div key={i} className="xc-msg me">{m.me}</div>
            : <div key={i} className="xc-row"><span className="xc-av"><EddieBot size={26} jet={false} /></span><Reply m={m} onDone={() => replyDone(i)} onOpen={r => setTrail(t => [...t, r])} /></div>)}
            {typing && <div className="xc-row"><span className="xc-av"><EddieBot size={26} jet={false} /></span><div className="xc-msg xc-bot"><span className="xc-dots"><i /><i /><i /></span></div></div>}
            <div ref={chatEnd} /></div>}
          <form className="xc-in" onSubmit={send}>
            <span className="xc-av"><EddieBot size={24} jet={false} /></span>
            <input placeholder={thread.length ? 'Ask something else' : 'Not clear? Ask Eddie, or say what you think'} aria-label="Ask Eddie" value={doubt} onChange={e => setDoubt(e.target.value)} />
            <button className="xc-send" disabled={typing || !doubt.trim()} aria-label="Send"><Icon n="right" s={16} /></button>
          </form>
        </div>
      </> : <div className="muted xp-note">{top.note ? '' : 'Written for your question.'} Go back to keep exploring.</div>}
      {top.credits_left != null && <div className="muted xp-note xp-credits">{top.credits_left} AI credits left today. Saved explanations are always free.</div>}
    </div>}
    {pick && <button type="button" className="selbtn" style={{ left: pick.x, top: pick.y }} onMouseDown={e => { e.preventDefault(); deeper(pick.t); getSelection().removeAllRanges() }}>
      Explain this{top.free_deeper ? '' : ' · may use 1 credit'}</button>}
  </div>
}

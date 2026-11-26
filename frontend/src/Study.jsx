import { useEffect, useRef, useState } from 'react'
import { api, auth } from './api'
import { Icon, MathText } from './ui'
import './study.css'

export const COLORS = [['yellow', 'Important to remember'], ['red', 'Exam point'], ['green', 'Understood'], ['blue', 'Ask about it']]
export const when = d => { if (!d) return ''; const t = new Date(d + (String(d).endsWith('Z') ? '' : 'Z')); const days = Math.floor((Date.now() - t) / 86400000)
  return days < 1 ? t.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' }) : days < 2 ? 'Yesterday' : days < 7 ? t.toLocaleDateString('en-IN', { weekday: 'short' }) : t.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) }
const mmss = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

// Records up to three minutes from the microphone. The browser picks the format it supports (webm, ogg or mp4).
export function useRecorder(max = 180) {
  const [state, setState] = useState('idle'); const [secs, setSecs] = useState(0); const [blob, setBlob] = useState(null); const [err, setErr] = useState('')
  const rec = useRef(); const chunks = useRef([]); const timer = useRef(); const levels = useRef([]); const [bars, setBars] = useState([])
  async function start() {
    setErr(''); setBlob(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const type = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'].find(t => window.MediaRecorder?.isTypeSupported?.(t)) || ''
      const r = new MediaRecorder(stream, type ? { mimeType: type } : undefined)
      chunks.current = []; levels.current = []
      r.ondataavailable = e => e.data.size && chunks.current.push(e.data)
      r.onstop = () => { stream.getTracks().forEach(t => t.stop()); setBlob(new Blob(chunks.current, { type: r.mimeType || 'audio/webm' })); setState('done') }
      // a live level meter, so the learner can see it is hearing them
      try {
        const ctx = new AudioContext(); const an = ctx.createAnalyser(); an.fftSize = 256; ctx.createMediaStreamSource(stream).connect(an)
        const buf = new Uint8Array(an.frequencyBinCount)
        const tick = () => { if (r.state !== 'recording') { ctx.close(); return } an.getByteFrequencyData(buf); const v = buf.reduce((a, b) => a + b, 0) / buf.length / 255
          levels.current = [...levels.current.slice(-39), Math.min(1, v * 2.4 + .08)]; setBars(levels.current); requestAnimationFrame(tick) }
        requestAnimationFrame(tick)
      } catch { /* no meter */ }
      r.start(250); rec.current = r; setState('recording'); setSecs(0)
      const t0 = Date.now(); timer.current = setInterval(() => { const s = (Date.now() - t0) / 1000; setSecs(s); if (s >= max) stop() }, 200)
    } catch { setErr('Allow the microphone to record a voice note.') }
  }
  function stop() { clearInterval(timer.current); if (rec.current?.state === 'recording') rec.current.stop() }
  function reset() { setBlob(null); setState('idle'); setSecs(0); setBars([]) }
  useEffect(() => () => { clearInterval(timer.current); if (rec.current?.state === 'recording') rec.current.stop() }, [])
  return { state, secs, blob, err, bars, start, stop, reset }
}

export function Wave({ bars = [], progress = 0, n = 36 }) {
  const list = bars.length ? bars : Array.from({ length: n }, (_, i) => .25 + .6 * Math.abs(Math.sin(i * 1.7) * Math.cos(i * .6)))
  return <div className="sv-wave" aria-hidden="true">{list.map((h, i) => <i key={i} className={i / list.length < progress ? 'p' : ''} style={{ height: Math.round(h * 100) + '%' }} />)}</div>
}

// Plays a private voice note: fetched with the sign-in token, then played from memory.
export function Player({ id, secs }) {
  const [url, setUrl] = useState(''); const [playing, setPlaying] = useState(false); const [p, setP] = useState(0); const a = useRef()
  useEffect(() => () => url && URL.revokeObjectURL(url), [url])
  async function toggle() {
    if (!url) {
      const r = await fetch(`/api/student/study/notes/${id}/audio`, { headers: { Authorization: 'Bearer ' + auth.token } }); if (!r.ok) return
      const u = URL.createObjectURL(await r.blob()); setUrl(u); setTimeout(() => a.current?.play(), 0); return
    }
    a.current.paused ? a.current.play() : a.current.pause()
  }
  return <div className="sv-player">
    <button type="button" className="sv-play" onClick={toggle} aria-label={playing ? 'Pause' : 'Play'}>{playing ? <span className="sv-pause" /> : <span className="sv-tri" />}</button>
    <Wave progress={p} /><span className="sv-dur">{mmss(secs || 0)}</span>
    {url && <audio ref={a} src={url} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => { setPlaying(false); setP(0) }}
      onTimeUpdate={e => setP(e.target.currentTime / (e.target.duration && isFinite(e.target.duration) ? e.target.duration : (secs || 1)))} />}
  </div>
}

export function Tags({ tags }) { return tags?.length ? <div className="sv-tags">{tags.map(t => <span key={t}>#{t}</span>)}</div> : null }

export function NoteCard({ n, onOpen, onDelete, onCard, onSaved, compact }) {
  const label = { note: 'Note', highlight: 'Highlight', voice: 'Voice note' }[n.kind]
  const [edit, setEdit] = useState(null); const [busy, setBusy] = useState(false); const [err, setErr] = useState('')
  async function save() {
    setBusy(true); setErr('')
    try {
      const saved = await api('/api/student/study/notes/' + n.id, { method: 'PUT', body: { body: edit.body, tags: edit.tags.split(/[\s,]+/).map(x => x.replace(/^#/, '')).filter(Boolean) } })
      setEdit(null); onSaved && onSaved(saved)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  if (edit) return <div className={'sv-card' + (compact ? ' compact' : '')}>
    <div className="sv-where"><b className={'k-' + n.kind}>Edit {label.toLowerCase()}</b></div>
    {n.quote && <div className="sv-quote"><span className={'hl hl-' + n.color}>{n.quote}</span></div>}
    <textarea className="input" rows="4" value={edit.body} onChange={e => setEdit({ ...edit, body: e.target.value })} aria-label="Note" />
    <input className="input" style={{ marginTop: 6 }} value={edit.tags} onChange={e => setEdit({ ...edit, tags: e.target.value })} placeholder="Tags, for example #exam #formula" aria-label="Tags" />
    {err && <div className="err">{err}</div>}
    <div className="sv-foot"><button type="button" className="btn sm" onClick={() => setEdit(null)}>Cancel</button>
      <button type="button" className="btn primary sm" disabled={busy} onClick={save}>{busy ? 'Saving' : 'Save'}</button></div>
  </div>
  return <div className={'sv-card' + (compact ? ' compact' : '')}>
    <div className="sv-where"><b className={'k-' + n.kind}>{label}</b><span>{[n.book, n.chapter != null && `Unit ${n.chapter}`, n.section].filter(Boolean).join(' · ')}</span></div>
    {n.quote && <div className="sv-quote"><span className={'hl hl-' + n.color}>{n.quote}</span></div>}
    {n.kind === 'voice' && <Player id={n.id} secs={n.audio_secs} />}
    {n.transcript && <div className="sv-trans">"{n.transcript}"</div>}
    {n.body && <div className="sv-body"><MathText text={n.body} /></div>}
    <Tags tags={n.tags} />
    <div className="sv-foot"><span>{when(n.created_at)}</span>
      {onSaved && <button type="button" className="linkbtn" onClick={() => setEdit({ body: n.body || '', tags: (n.tags || []).map(x => '#' + x).join(' ') })}>Edit</button>}
      {onCard && <button type="button" className="linkbtn" onClick={() => onCard(n)}>Make a card</button>}
      {onDelete && <button type="button" className="linkbtn" onClick={() => onDelete(n)}>Delete</button>}
      {onOpen && n.book_id && <button type="button" className="sv-go" onClick={() => onOpen(n)}>Go to page</button>}</div>
  </div>
}

// Writing a note, choosing a highlight colour, or recording a voice note, for one spot in a book.
export function Composer({ at, onSaved, onCancel, autoFocus = true }) {
  const [body, setBody] = useState(''); const [tags, setTags] = useState(''); const [color, setColor] = useState('yellow'); const [busy, setBusy] = useState(false); const [err, setErr] = useState('')
  const r = useRecorder()
  const tagList = tags.split(/[\s,]+/).filter(Boolean)
  async function save(kind = 'note') {
    setBusy(true); setErr('')
    try {
      if (r.blob) {
        const f = new FormData(); f.append('audio', r.blob, 'voice.' + (r.blob.type.includes('mp4') ? 'm4a' : r.blob.type.includes('ogg') ? 'ogg' : 'webm'))
        f.append('seconds', String(Math.round(r.secs))); Object.entries({ ...at, body }).forEach(([k, v]) => v != null && v !== '' && f.append(k, String(v)))
        onSaved(await api('/api/student/study/notes/voice', { method: 'POST', form: f })); r.reset()
      } else {
        onSaved(await api('/api/student/study/notes', { method: 'POST', body: { ...at, kind, body, color, tags: tagList } }))
      }
      setBody(''); setTags('')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return <div className="sv-compose">
    {at.quote && <div className="sv-quote"><span className={'hl hl-' + color}>{at.quote}</span></div>}
    {r.state === 'idle' ? <textarea autoFocus={autoFocus} placeholder="Write a note..." value={body} onChange={e => setBody(e.target.value)} rows={3} />
      : <div className="sv-rec"><span className={'sv-dot' + (r.state === 'recording' ? ' on' : '')} /><Wave bars={r.bars} n={40} /><span className="sv-dur">{mmss(r.secs)} / 3:00</span>
        {r.state === 'recording' ? <button type="button" className="btn sm" onClick={r.stop}>Stop</button> : <button type="button" className="btn ghost sm" onClick={r.reset}>Discard</button>}</div>}
    {err || r.err ? <div className="err">{err || r.err}</div> : null}
    <div className="sv-row">
      <div className="sv-sw" role="radiogroup" aria-label="Colour">{COLORS.map(([c, l]) => <button key={c} type="button" title={l} aria-label={l} aria-checked={color === c} role="radio" className={'hl-' + c + (color === c ? ' on' : '')} onClick={() => setColor(c)} />)}</div>
      <input className="sv-tagin" placeholder="#tags" value={tags} onChange={e => setTags(e.target.value)} />
      <span className="grow" />
      {onCancel && <button type="button" className="btn ghost sm" onClick={onCancel}>Cancel</button>}
      {r.state === 'idle' && <button type="button" className="btn sm sv-mic" onClick={r.start} aria-label="Record a voice note"><Icon n="mic" s={15} /></button>}
      {at.quote && !body && r.state === 'idle' && <button type="button" className="btn sm" disabled={busy} onClick={() => save('highlight')}>Highlight</button>}
      <button type="button" className="btn primary sm" disabled={busy || r.state === 'recording' || (!body.trim() && !r.blob)} onClick={() => save('note')}>{busy ? 'Saving' : r.blob ? 'Save voice note' : 'Save note'}</button>
    </div>
  </div>
}

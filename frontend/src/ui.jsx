import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { splitMath, parseArray, cellPlain } from './mathParse'
import { api, auth } from './api'

const P = {
  home: 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
  admins: 'M16 11a4 4 0 1 0-8 0M4 20c0-3.3 3.6-6 8-6s8 2.7 8 6M12 3a4 4 0 1 1 0 8',
  school: 'M3 9l9-5 9 5-9 5zM6 11v5c0 1.5 2.7 3 6 3s6-1.5 6-3v-5',
  price: 'M3 12l9-9h8v8l-9 9zM15.5 8.5h.01',
  book: 'M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 21V5M8 7h7',
  job: 'M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01',
  ai: 'M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M6 18l2-2M16 8l2-2M9 9h6v6H9z',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z',
  audit: 'M9 4h6l1 2h3v15H5V6h3zM9 11h6M9 15h6',
  plus: 'M12 5v14M5 12h14', x: 'M6 6l12 12M18 6L6 18', menu: 'M4 6h16M4 12h16M4 18h16',
  sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z', out: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
  upload: 'M12 16V4M7 9l5-5 5 5M4 20h16',
  inbox: 'M4 13l2-8h12l2 8v6H4zM4 13h5l1 2h4l1-2h5',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
  download: 'M12 4v12M7 11l5 5 5-5M4 20h16',
  scan: 'M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4M7 12h10',
  image: 'M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15.5 9.5h.01',
  star: 'M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
  flag: 'M5 21V4M5 4h11l-2 4 2 4H5',
  play: 'M7 4l13 8-13 8z',
  grid: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
  left: 'M15 5l-7 7 7 7', right: 'M9 5l7 7-7 7',
  check: 'M4 12l5 5L20 6',
  target: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12h.01',
  text: 'M4 7V5h16v2M9 19h6M12 5v14',
  mic: 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3',
  note: 'M5 4h10l4 4v12H5zM15 4v4h4M8 12h8M8 16h5',
  repeat: 'M4 12a8 8 0 0 1 14-5l2 2M20 4v5h-5M20 12a8 8 0 0 1-14 5l-2-2M4 20v-5h5',
  bookmark: 'M6 4h12v17l-6-4-6 4z',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  fire: 'M12 21c4 0 7-3 7-7 0-5-5-6-4-11-4 2-6 5-6 8-1-1-2-2-2-4-2 2-2 4-2 7 0 4 3 7 7 7z',
}
export const Icon = ({ n, s = 18 }) => (
  <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={P[n]} /></svg>
)

// Text with maths between $ signs, as the AI paper reader writes it. $$...$$ is a block of its own, and a
// $$\begin{array}...\end{array}$$ table is drawn as a real table so long cells wrap (see mathParse.js).
const tex = (s, display) => ({ __html: katex.renderToString(s, { throwOnError: false, displayMode: display }) })
const Cell = ({ c }) => { const p = cellPlain(c); return p != null ? p : <span dangerouslySetInnerHTML={tex(c)} /> }
function MathBlock({ value }) {
  const t = parseArray(value)
  if (!t) return <div className="mt-display" dangerouslySetInnerHTML={tex(value, true)} />
  return <div className="mt-table"><table><tbody>{t.rows.map((r, i) => <tr key={i}>{r.map((c, j) => t.header && i === 0
    ? <th key={j}><Cell c={c} /></th> : <td key={j}><Cell c={c} /></td>)}</tr>)}</tbody></table></div>
}
export function MathText({ text, style }) {
  const parts = useMemo(() => splitMath(text), [text])
  return <span style={{ whiteSpace: 'pre-wrap', ...style }}>{parts.map((p, i) => p.kind === 'display' ? <MathBlock key={i} value={p.value} />
    : p.kind === 'inline' ? <span key={i} dangerouslySetInnerHTML={tex(p.value)} />
    // a block already breaks the line, so the line breaks around it in the text would show as blank lines
    : <span key={i}>{p.value.replace(parts[i - 1]?.kind === 'display' ? /^[ \t]*\n/ : /(?!)/, '').replace(parts[i + 1]?.kind === 'display' ? /\n[ \t]*$/ : /(?!)/, '')}</span>)}</span>
}

// A picture behind sign in. A plain img tag cannot send the sign in token.
export function AuthImg({ src, alt = '', style, stamp }) {
  const [url, setUrl] = useState(''); const [failed, setFailed] = useState(false)
  useEffect(() => {
    let live = true, made = ''
    setUrl(''); setFailed(false)
    fetch(src, { cache: 'no-store', headers: { Authorization: 'Bearer ' + auth.token } }).then(r => { if (!r.ok) throw new Error(); return r.blob() })
      .then(b => { if (live) { made = URL.createObjectURL(b); setUrl(made) } }).catch(() => live && setFailed(true))
    return () => { live = false; if (made) URL.revokeObjectURL(made) }
  }, [src, stamp])
  if (failed) return <div className="muted" style={{ padding: 12 }}>Picture not available</div>
  return url ? <img src={url} alt={alt} style={{ maxWidth: '100%', display: 'block', ...style }} /> : <div className="muted" style={{ padding: 12 }}>Loading picture</div>
}

export function Dropzone({ file, onFile, accept, label, hint, small }) {
  const input = useRef(); const [over, setOver] = useState(false)
  return <div className={'dropzone' + (small ? ' small' : '') + (over ? ' over' : '') + (file ? ' has' : '')} role="button" tabIndex={0}
    onClick={() => input.current.click()} onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), input.current.click())}
    onDragOver={e => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
    onDrop={e => { e.preventDefault(); setOver(false); e.dataTransfer.files[0] && onFile(e.dataTransfer.files[0]) }}>
    <Icon n="upload" s={small ? 16 : 26} />
    <div><b>{file ? file.name : label}</b>{!small && <div className="muted">{file ? (file.size / 1048576).toFixed(1) + ' MB. Click to change.' : hint}</div>}</div>
    {file && <button type="button" className="btn ghost sm" style={{ marginLeft: 'auto' }} onClick={e => { e.stopPropagation(); input.current.value = ''; onFile(null) }}>Remove</button>}
    <input ref={input} type="file" accept={accept} hidden onChange={e => e.target.files[0] && onFile(e.target.files[0])} />
  </div>
}

// A panel that slides up from the bottom on phones and sits in the middle on larger screens.
export function Sheet({ title, onClose, children, footer }) {
  useEffect(() => {
    const k = e => e.key === 'Escape' && onClose()
    addEventListener('keydown', k); const prev = document.body.style.overflow; document.body.style.overflow = 'hidden'
    return () => { removeEventListener('keydown', k); document.body.style.overflow = prev }
  }, [])
  return createPortal(<div className="sheet-wrap" onMouseDown={e => e.target === e.currentTarget && onClose()}>
    <div className="sheet" role="dialog" aria-modal="true" aria-label={title}><div className="grab" />
      {title && <div className="sheet-h"><h2>{title}</h2><button className="btn ghost" style={{ marginLeft: 'auto' }} onClick={onClose} aria-label="Close"><Icon n="x" /></button></div>}
      {children}{footer && <div className="sheet-f">{footer}</div>}</div></div>, document.body)
}

// ask('Delete this?') -> Promise<boolean>, shown as a proper dialog instead of the browser's own pop-up.
let askHandler = null
export const ask = (text, opts = {}) => askHandler ? askHandler(text, opts) : Promise.resolve(window.confirm(text))
export function ConfirmHost() {
  const [q, setQ] = useState(null)
  useEffect(() => { askHandler = (text, opts) => new Promise(res => setQ({ text, opts, res })); return () => { askHandler = null } }, [])
  if (!q) return null
  const done = v => { q.res(v); setQ(null) }
  return <Modal title={q.opts.title || 'Please confirm'} onClose={() => done(false)} footer={<><button className="btn" onClick={() => done(false)}>{q.opts.no || 'Cancel'}</button>
    <button className="btn primary" autoFocus onClick={() => done(true)}>{q.opts.yes || 'Confirm'}</button></>}><p style={{ margin: 0, lineHeight: 1.6 }}>{q.text}</p></Modal>
}

export function Ring({ value, max, size = 72, stroke = 7, children }) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, f = Math.min(1, max ? value / max : 0)
  return <div className="ring" style={{ width: size, height: size }}><svg width={size} height={size} aria-hidden="true">
    <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--line)" strokeWidth={stroke} fill="none" />
    <circle cx={size / 2} cy={size / 2} r={r} stroke={f >= 1 ? 'var(--ok)' : 'var(--red)'} strokeWidth={stroke} fill="none" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - f)} style={{ transition: 'stroke-dashoffset .6s' }} /></svg>
    <div className="ring-in">{children}</div></div>
}

export function useNarrow(px = 900) {
  const q = `(max-width:${px}px)`
  const [n, setN] = useState(() => matchMedia(q).matches)
  useEffect(() => { const m = matchMedia(q); const f = () => setN(m.matches); m.addEventListener('change', f); return () => m.removeEventListener('change', f) }, [q])
  return n
}

export const plural = (n, one, many = one + 's') => `${n} ${n === 1 ? one : many}`

const ToastCtx = createContext(() => {})
export function ToastHost({ children }) {
  const [items, set] = useState([])
  const push = useCallback((msg, bad) => {
    const id = Math.random(); set(x => [...x, { id, msg, bad }])
    setTimeout(() => set(x => x.filter(t => t.id !== id)), 3800)
  }, [])
  return <ToastCtx.Provider value={push}>{children}<div className="toasts" role="status">{items.map(t => <div key={t.id} className={'toast' + (t.bad ? ' bad' : '')}>{t.msg}</div>)}</div></ToastCtx.Provider>
}
export const useToast = () => useContext(ToastCtx)

export function useLoad(path, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const reload = useCallback(() => path ? api(path).then(setData).catch(e => setError(e.message)) : Promise.resolve(), [path])
  useEffect(() => { reload() }, [reload, ...deps])
  return { data, error, reload, setData }
}

export function Modal({ title, onClose, children, footer }) {
  useEffect(() => { const k = e => e.key === 'Escape' && onClose(); addEventListener('keydown', k); return () => removeEventListener('keydown', k) }, [onClose])
  return (
    <div className="overlay" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-h"><h2>{title}</h2><button className="btn ghost" style={{ marginLeft: 'auto' }} onClick={onClose} aria-label="Close"><Icon n="x" /></button></div>
        <div className="modal-b">{children}</div>
        {footer && <div className="modal-f">{footer}</div>}
      </div>
    </div>
  )
}

export const Field = ({ label, hint, children }) => (
  <div className="field"><label>{label}</label>{children}{hint && <span className="hint">{hint}</span>}</div>
)

export const Switch = ({ checked, onChange, label }) => (
  <label className="switch" title={label}><input type="checkbox" checked={!!checked} onChange={e => onChange(e.target.checked)} aria-label={label} /><i /></label>
)

const TONES = { active: 'ok', live: 'ok', done: 'ok', approved: 'info', in_review: 'warn', running: 'info', processing: 'info',
  queued: '', upcoming: '', rejected: 'bad', pending: '', suspended: 'bad', failed: 'bad', retired: '', cancelled: '', inactive: '' }
const LABELS = { in_review: 'In review', rejected: 'Sent back', live: 'Published' }
// `s` is normally a status ("live", "failed") and the tone is looked up. A
// tone passed straight in ("bad") used to fall through to no colour at all,
// which quietly greyed out every flag count on the issues screen.
const TONE_NAMES = new Set(['ok', 'warn', 'bad', 'info'])
export const Tag = ({ s, children }) => <span className={'tag ' + (TONE_NAMES.has(s) ? s : TONES[s] ?? '')}>{children || LABELS[s] || (s ? s[0].toUpperCase() + s.slice(1) : '')}</span>

export function Page({ title, sub, actions, children }) {
  return <div className="page"><div className="page-head"><div><h1>{title}</h1>{sub && <p>{sub}</p>}</div><div className="actions">{actions}</div></div>{children}</div>
}

export function useForm(init) {
  const [v, setV] = useState(init)
  const bind = k => ({ value: v[k] ?? '', onChange: e => setV(x => ({ ...x, [k]: e.target.value })) })
  return [v, setV, bind]
}

export function LineChart({ data, keys, height = 220 }) {
  if (!data?.length) return <div className="empty">No activity yet</div>
  const W = 760, H = height, pl = 44, pr = 12, pt = 12, pb = 26
  const max = Math.max(1, ...data.flatMap(d => keys.map(k => d[k.key])))
  const nice = Math.pow(10, Math.floor(Math.log10(max))); const top = Math.ceil(max / nice) * nice
  const x = i => pl + (i * (W - pl - pr)) / Math.max(1, data.length - 1)
  const y = v => pt + (1 - v / top) * (H - pt - pb)
  const ticks = [0, .25, .5, .75, 1].map(f => f * top)
  return (
    <div className="chart"><svg viewBox={`0 0 ${W} ${H}`} role="img">
      {ticks.map(t => <g key={t}><line className="gridline" x1={pl} x2={W - pr} y1={y(t)} y2={y(t)} /><text className="axis" x={pl - 6} y={y(t) + 4} textAnchor="end">{t >= 1000 ? (t / 1000) + 'k' : t}</text></g>)}
      {data.map((d, i) => i % Math.ceil(data.length / 8) === 0 && <text key={i} className="axis" x={x(i)} y={H - 6} textAnchor="middle">{new Date(d.day).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</text>)}
      {keys.map(k => <polyline key={k.key} fill="none" stroke={k.color} strokeWidth="2.2" strokeLinejoin="round" points={data.map((d, i) => `${x(i)},${y(d[k.key])}`).join(' ')} />)}
    </svg></div>
  )
}

export function HBars({ rows, label, value, fmt = v => v }) {
  const max = Math.max(1, ...rows.map(r => r[value]))
  return <div>{rows.map((r, i) => <div className="hbar" key={i}><span>{r[label]}</span><div className="bar-track"><i style={{ width: (r[value] / max * 100) + '%' }} /></div><span className="num">{fmt(r[value])}</span></div>)}</div>
}

export function Confirm({ text, onYes, onClose, yes = 'Confirm', danger }) {
  return <Modal title="Please confirm" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className={'btn ' + (danger ? 'primary' : 'primary')} onClick={onYes}>{yes}</button></>}><p style={{ margin: 0 }}>{text}</p></Modal>
}

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api'

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
  key: 'M15 7a4 4 0 1 1-3.3 6.3L10 15H8v2H6v2H3v-3l7.7-7.7A4 4 0 0 1 15 7zM16.5 9.5h.01',
  pulse: 'M3 12h3l2.5-7 3.5 14 3-7h6',
}
export const Icon = ({ n, s = 18 }) => (
  <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={P[n]} /></svg>
)

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
  const reload = useCallback(() => api(path).then(setData).catch(e => setError(e.message)), [path])
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
  queued: '', upcoming: '', rejected: 'bad', pending: '', suspended: 'bad', failed: 'bad', retired: '', cancelled: '', inactive: '',
  // a tone can also be passed straight through, which several screens already do
  ok: 'ok', warn: 'warn', bad: 'bad', info: 'info' }
const LABELS = { in_review: 'In review', rejected: 'Sent back', live: 'Published' }
export const Tag = ({ s, children }) => <span className={'tag ' + (TONES[s] ?? '')}>{children || LABELS[s] || (s ? s[0].toUpperCase() + s.slice(1) : '')}</span>

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

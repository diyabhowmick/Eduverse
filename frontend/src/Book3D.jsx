import { useEffect, useRef, useState } from 'react'

// A textbook as a real 3D object in CSS: cover, spine, page edges with thickness and a back cover.
// It leans towards the pointer with light moving across the cover, and can swing open on its hinge.
// Phones with little memory, and anyone who turned motion off, get a flat cover with no 3D.

const TINTS = [
  [/chem/i, '#22B8CF', 'hex'], [/phys/i, '#3B82F6', 'wave'], [/bio|botany|zoology/i, '#2BB673', 'cell'],
  [/science|evs/i, '#2BB673', 'atom'], [/math|algebra|geometry|statistic/i, '#3B82F6', 'grid'],
  [/social|history|geograph|civic|econom|politic/i, '#F59E0B', 'map'],
  [/english|tamil|hindi|kannada|telugu|malayalam|sanskrit|french|language|literature/i, '#A855F7', 'type'],
  [/computer|coding|informatic/i, '#22B8CF', 'code'],
]
export const tintOf = b => { const s = (b.subject || '') + ' ' + (b.title || ''); const t = TINTS.find(([re]) => re.test(s)); return t ? { c: t[1], p: t[2] } : { c: '#E0212F', p: 'arc' } }

export const flat = () => {
  try {
    return matchMedia('(prefers-reduced-motion: reduce)').matches || (navigator.deviceMemory && navigator.deviceMemory <= 2)
  } catch { return false }
}

// Subject patterns, drawn in thin lines in the subject's colour.
function Pattern({ p, c }) {
  const s = { stroke: c, fill: 'none', strokeWidth: 1.2, opacity: .55 }
  const shapes = {
    atom: <g {...s}><ellipse cx="70" cy="70" rx="46" ry="16" /><ellipse cx="70" cy="70" rx="46" ry="16" transform="rotate(60 70 70)" /><ellipse cx="70" cy="70" rx="46" ry="16" transform="rotate(120 70 70)" /><circle cx="70" cy="70" r="5" fill={c} /></g>,
    grid: <g {...s}>{[0, 1, 2, 3, 4, 5, 6].map(i => <line key={'h' + i} x1="0" x2="140" y1={i * 22 + 4} y2={i * 22 + 4} />)}{[0, 1, 2, 3, 4, 5, 6].map(i => <line key={'v' + i} y1="0" y2="140" x1={i * 22 + 4} x2={i * 22 + 4} />)}<path d="M4 124 Q 50 120 70 70 T 136 10" strokeWidth="2" opacity=".9" /></g>,
    map: <g {...s}>{[18, 30, 42, 54].map(r => <path key={r} d={`M${70 - r} 70 q ${r / 2} ${-r} ${r} ${-r / 3} t ${r} ${r / 2} t ${-r / 2} ${r} t ${-r * 1.4} ${-r / 6}z`} />)}</g>,
    type: <g fill={c} opacity=".35" fontFamily="Georgia,serif">{['A', 'அ', 'क', 'Ω', 'ಅ', 'a'].map((t, i) => <text key={i} x={12 + (i % 3) * 44} y={44 + Math.floor(i / 3) * 56} fontSize="34">{t}</text>)}</g>,
    hex: <g {...s}>{[[40, 40], [70, 57], [100, 40], [70, 92], [40, 109], [100, 109]].map(([x, y], i) => <polygon key={i} points={[0, 1, 2, 3, 4, 5].map(k => [x + 17 * Math.cos(Math.PI / 3 * k), y + 17 * Math.sin(Math.PI / 3 * k)].join(',')).join(' ')} />)}</g>,
    wave: <g {...s}>{[30, 50, 70, 90, 110].map((y, i) => <path key={y} d={`M0 ${y} q 17 ${-14 + i * 2} 35 0 t 35 0 t 35 0 t 35 0`} />)}</g>,
    cell: <g {...s}><circle cx="70" cy="70" r="44" /><circle cx="78" cy="62" r="14" fill={c} fillOpacity=".25" /><circle cx="48" cy="88" r="5" /><circle cx="96" cy="94" r="7" /><circle cx="52" cy="52" r="4" /></g>,
    code: <g fill={c} opacity=".45" fontFamily="monospace" fontSize="15"><text x="10" y="40">{'{ }'}</text><text x="60" y="76">{'</>'}</text><text x="18" y="112">{'01'}</text><text x="92" y="122">{'=>'}</text></g>,
    arc: <g {...s}>{[20, 34, 48, 62].map(r => <circle key={r} cx="120" cy="20" r={r} />)}</g>,
  }
  return <svg className="b3-pat" viewBox="0 0 140 140" preserveAspectRatio="xMidYMid slice" aria-hidden="true">{shapes[p] || shapes.arc}</svg>
}

export function CoverArt({ b }) {
  const exam = b.track === 'exam'
  const { c, p } = tintOf(b)
  if (b.cover) return <img className="b3-img" src={b.cover} alt="" />
  const band = exam ? 'Exam pack' : b.level === 'degree' ? (b.university || 'Degree') : (b.board || '')
  const big = exam ? (b.exam || '') : b.level === 'degree' ? (b.semester ? 'S' + b.semester : '') : (b.grade || '')
  return <div className="b3-art" style={{ '--tint': c }}>
    <Pattern p={p} c={c} />
    <div className="b3-band">{band}</div>
    <div className="b3-big">{big && <span className={String(big).length > 3 ? 'long' : ''}>{big}</span>}{!exam && b.level !== 'degree' && big && <small>Class</small>}</div>
    <div className="b3-subj">{b.subject || b.title}</div>
    <div className="b3-foot">{b.medium && b.medium !== 'English' ? b.medium + ' medium' : b.edition || 'EduVerse'}</div>
  </div>
}

export default function Book3D({ b, size = 'md', pose = 'cover', open = false, flipped = false, spin = false, ribbon, back, className = '', onClick }) {
  const el = useRef(); const [isFlat] = useState(flat)
  const raf = useRef(0)
  function move(e) {
    if (isFlat || !el.current) return
    const r = el.current.getBoundingClientRect()
    const x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5
    cancelAnimationFrame(raf.current)
    raf.current = requestAnimationFrame(() => {
      el.current?.style.setProperty('--ty', (x * 26).toFixed(2) + 'deg'); el.current?.style.setProperty('--tx', (-y * 16).toFixed(2) + 'deg')
      el.current?.style.setProperty('--sx', ((x + .5) * 100).toFixed(1) + '%'); el.current?.style.setProperty('--sy', ((y + .5) * 100).toFixed(1) + '%')
    })
  }
  function leave() { if (!el.current) return; ['--ty', '--tx'].forEach(k => el.current.style.setProperty(k, '0deg')) }
  useEffect(() => () => cancelAnimationFrame(raf.current), [])
  const exam = b.track === 'exam'
  const cls = ['b3', 'b3-' + size, 'b3-' + pose, open && 'is-open', flipped && 'is-flipped', spin && 'is-spin', isFlat && 'b3-flat', exam && 'b3-exam', b.status === 'upcoming' && 'is-soon', className].filter(Boolean).join(' ')
  return <div ref={el} className={cls} onPointerMove={move} onPointerLeave={leave} onClick={onClick} style={{ '--tint': tintOf(b).c }}>
    <div className="b3-obj">
      <div className="b3-face b3-back">{back || <div className="b3-backart"><b>{b.title}</b><span>EduVerse</span></div>}</div>
      <div className="b3-face b3-pages-r" /><div className="b3-face b3-pages-t" /><div className="b3-face b3-pages-b" />
      <div className="b3-face b3-spine"><span>{b.subject || b.title}</span><i>{exam ? b.exam : b.grade}</i></div>
      <div className="b3-face b3-inner"><div className="b3-title-page"><small>{b.board || b.exam}</small><b>{b.title}</b><span>EduVerse</span></div></div>
      <div className="b3-leaf l1" /><div className="b3-leaf l2" /><div className="b3-leaf l3" />
      <div className="b3-front"><div className="b3-cv"><CoverArt b={b} /><div className="b3-sheen" />
        {b.status === 'upcoming' && <div className="b3-soon">Coming soon</div>}</div><div className="b3-cv-in" /></div>
    </div>
    {ribbon != null && ribbon > 0 && <div className="b3-ribbon" style={{ '--p': Math.min(100, ribbon) }}><span>{ribbon}%</span></div>}
    <div className="b3-shadow" />
  </div>
}

// An exam pack as a stack of past papers with year tabs. Hover fans the papers out.
export function PaperStack({ b, years = [], onClick }) {
  const ys = (years.length ? years : ['', '', '', '']).slice(0, 4)
  return <div className="pst" onClick={onClick} role={onClick ? 'button' : undefined} tabIndex={onClick ? 0 : undefined}
    onKeyDown={e => onClick && (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onClick())}>
    {ys.map((y, i) => <div key={i} className="pst-sheet" style={{ '--i': i }}>{y && <span className="pst-tab">{y}</span>}<i /><i /><i /><i /></div>)}
    <div className="pst-top"><div className="pst-k">Past papers</div><div className="pst-ex">{b.exam || b.title}</div><div className="pst-t">{b.title}</div>
      {b.status === 'upcoming' && <span className="tag" style={{ marginTop: 6 }}>Coming soon</span>}</div>
  </div>
}

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { flushSync, createPortal } from 'react-dom'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, inr } from '../../api'
import { useLoad, Icon, useToast } from '../../ui'
import Book3D, { PaperStack, tintOf, flat } from '../../Book3D'
import { openPath } from './common'
import '../../books3d.css'

// The store in three steps: pick a universe (a board, an exam or a university), pick a class on its shelf,
// then pick up a book and look at it from every side before opening it.
const SEG_COLORS = ['#E0212F', '#3B82F6', '#2BB673', '#F59E0B', '#A855F7', '#22B8CF']
const vt = f => (document.startViewTransition && !flat()) ? document.startViewTransition(() => flushSync(f)) : f()
const range = gs => gs.length ? (gs.length === 1 ? 'Class ' + gs[0] : `Class ${gs[0]} to ${gs[gs.length - 1]}`) : ''
const slug = s => String(s).replace(/[^a-z0-9]+/gi, '-').toLowerCase()
const HERO = [{ subject: 'Mathematics', grade: '10', board: 'CBSE' }, { subject: 'Science', grade: '8', board: 'Tamil Nadu' }, { subject: 'English', grade: '12', board: 'ICSE' }]

function Scrubber({ items, value, onChange, label = x => x }) {
  const box = useRef(); const [pill, setPill] = useState(null)
  useLayoutEffect(() => {
    const el = box.current?.querySelector('button.on'); if (!el) return setPill(null)
    setPill({ left: el.offsetLeft, width: el.offsetWidth }); el.scrollIntoView({ block: 'nearest', inline: 'center', behavior: flat() ? 'auto' : 'smooth' })
  }, [value, items.join()])
  return <div className="sx-scrub" ref={box} role="tablist">
    {pill && <i className="sx-pill" style={pill} />}
    {items.map(x => <button key={x} role="tab" aria-selected={x === value} className={x === value ? 'on' : ''} onClick={() => onChange(x)}>{label(x)}</button>)}
  </div>
}

function Landing({ seg, mine, go }) {
  const boards = [...seg.boards].sort((a, b) => (b.board === mine) - (a.board === mine))
  return <>
    <div className="sx-hero"><div className="sx-stars" />
      <div style={{ position: 'relative' }}><div className="bx-k" style={{ color: '#ff6b75' }}>EduVerse store</div>
        <h1>Choose your universe</h1><p>Every board, every class, every exam. Pick where you study and your shelf is ready.</p></div>
      <div className="sx-hero-books" aria-hidden="true">{HERO.map((b, i) => <Book3D key={i} b={b} size="md" />)}</div>
    </div>
    {boards.length > 0 && <><div className="sx-group"><h2>School boards</h2><span className="muted">{boards.length} boards</span></div>
      <div className="sx-grid">{boards.map((s, i) => <button key={s.board} className={'sx-card' + (s.board === mine ? ' mine' : '')} style={{ '--sx-c': SEG_COLORS[i % SEG_COLORS.length], viewTransitionName: 'seg-' + slug(s.board) }}
        onClick={() => go({ board: s.board })}>
        <div className="sx-fan" aria-hidden="true">{(s.subjects.length ? s.subjects : ['Science', 'Maths', 'English']).slice(0, 3).map((sub, j) => <Book3D key={j} size="sm" b={{ subject: sub, grade: s.grades[s.grades.length - 1 - j] || s.grades[0], board: s.board }} />)}</div>
        <div style={{ minWidth: 0 }}>{s.board === mine && <span className="sx-mine">Your board</span>}<div className="sx-name">{s.board}</div>
          <div className="sx-meta">{s.books} {s.books === 1 ? 'book' : 'books'}{s.grades.length ? ' · ' + range(s.grades) : ''}{s.upcoming ? ` · ${s.upcoming} coming soon` : ''}</div>
          <div className="sx-chips">{s.subjects.slice(0, 4).map(x => <span key={x}>{x}</span>)}</div></div>
        <span className="sx-go"><Icon n="right" s={16} /></span></button>)}</div></>}
    {seg.exams.length > 0 && <><div className="sx-group"><h2>Exam preparation</h2><span className="muted">Past papers, recaps and mock tests</span></div>
      <div className="sx-grid">{seg.exams.map((s, i) => <button key={s.exam} className="sx-card" style={{ '--sx-c': SEG_COLORS[(i + 2) % SEG_COLORS.length], viewTransitionName: 'seg-x-' + slug(s.exam) }} onClick={() => go({ exam: s.exam })}>
        <PaperStack b={{ exam: s.exam, title: s.exam }} years={['', '', '']} />
        <div><div className="sx-name">{s.exam}</div><div className="sx-meta">{s.packs} {s.packs === 1 ? 'pack' : 'packs'} · {s.level === 'competitive' ? 'Competitive exam' : s.level === 'degree' ? 'Degree exam' : 'Board exam'}</div></div>
        <span className="sx-go"><Icon n="right" s={16} /></span></button>)}</div></>}
    {seg.universities.length > 0 && <><div className="sx-group"><h2>Degree college</h2></div>
      <div className="sx-grid">{seg.universities.map((s, i) => <button key={s.university} className="sx-card" style={{ '--sx-c': SEG_COLORS[(i + 4) % SEG_COLORS.length], viewTransitionName: 'seg-u-' + slug(s.university) }} onClick={() => go({ uni: s.university })}>
        <div className="sx-fan" aria-hidden="true">{[0, 1, 2].map(j => <Book3D key={j} size="sm" b={{ subject: ['Physics', 'Chemistry', 'Mathematics'][j], level: 'degree', university: s.university, semester: String(j + 1) }} />)}</div>
        <div><div className="sx-name">{s.university}</div><div className="sx-meta">{s.books} {s.books === 1 ? 'book' : 'books'}</div></div>
        <span className="sx-go"><Icon n="right" s={16} /></span></button>)}</div></>}
    {!seg.boards.length && !seg.exams.length && !seg.universities.length && <div className="card empty">The store is being stocked. Check back soon.</div>}
  </>
}

function Item({ b, n, onOpen }) {
  const exam = b.track === 'exam'
  return <div className="sx-item" style={{ '--n': n }}>
    {exam ? <PaperStack b={b} onClick={() => onOpen(b)} /> : <Book3D b={b} size="md" ribbon={b.owned ? b.progress : null} onClick={() => onOpen(b)} />}
    <div className="sx-ledge" aria-hidden="true" />
    <div className="sx-cap"><b>{exam ? b.title : b.subject || b.title}</b>
      <span className="muted">{exam ? b.exam : [b.grade && 'Class ' + b.grade, b.medium !== 'English' && b.medium].filter(Boolean).join(' · ')}</span>
      {b.status === 'upcoming' ? <span className="muted">Coming soon</span> : b.owned ? <span className="tag ok" style={{ justifySelf: 'center' }}>In My books</span> : <span className="sx-price">{inr(b.price)}</span>}</div>
  </div>
}

function Segment({ q, seg, go, onOpen }) {
  const board = q.get('board'), exam = q.get('exam'), uni = q.get('uni')
  const meta = board ? seg.boards.find(s => s.board === board) : null
  const grades = meta?.grades || []
  const [dir, setDir] = useState(40)
  const grade = q.get('grade') || (grades.includes(q.get('mine')) ? q.get('mine') : grades[0] || '')
  const qs = new URLSearchParams(exam ? { track: 'exam', exam } : uni ? { track: 'textbook', level: 'degree', university: uni } : { track: 'textbook', level: 'school', board }).toString()
  const { data } = useLoad('/api/student/store?' + qs, [qs])
  const books = (data?.books || []).filter(b => !board || !grade || b.grade === grade)
  const title = board || exam || uni
  function pickGrade(g) { setDir(grades.indexOf(g) > grades.indexOf(grade) ? 60 : -60); go({ board, grade: g }, true) }
  return <>
    <div className="sx-head">
      <button className="sx-back" aria-label="All universes" onClick={() => go({})}><Icon n="left" s={18} /></button>
      <div style={{ viewTransitionName: 'seg-' + (board ? '' : exam ? 'x-' : 'u-') + slug(title) }}><div className="bx-k">{board ? 'School board' : exam ? 'Exam preparation' : 'Degree college'}</div><h1>{title}</h1></div>
    </div>
    {board && grades.length > 1 && <Scrubber items={grades} value={grade} onChange={pickGrade} label={g => 'Class ' + g} />}
    {exam && seg.exams.length > 1 && <div className="sx-exams">{seg.exams.map(s => <button key={s.exam} className={s.exam === exam ? 'on' : ''} onClick={() => go({ exam: s.exam }, true)}>{s.exam}</button>)}</div>}
    <div className="sx-shelf" key={grade + exam + uni} style={{ '--from': dir + 'px' }}>
      {data && !books.length ? <div className="card empty">Nothing on this shelf yet. Try another {board ? 'class' : 'one'}.</div>
        : <div className="sx-row">{books.map((b, i) => <Item key={b.id} b={b} n={i} onOpen={onOpen} />)}</div>}
    </div>
  </>
}

function Detail({ id, onClose, onChanged }) {
  const { data: b, reload } = useLoad('/api/student/store/books/' + id); const nav = useNavigate(); const toast = useToast()
  const [flip, setFlip] = useState(false); const [opening, setOpening] = useState(false); const [flash, setFlash] = useState(false); const [buying, setBuying] = useState(false)
  useEffect(() => { const k = e => e.key === 'Escape' && onClose(); addEventListener('keydown', k); const o = document.body.style.overflow; document.body.style.overflow = 'hidden'
    return () => { removeEventListener('keydown', k); document.body.style.overflow = o } }, [])
  const exam = b?.track === 'exam'
  function open() {
    if (flat() || exam) return nav(openPath(b))
    setFlip(false); setOpening(true)
    setTimeout(() => setFlash(true), 950); setTimeout(() => nav(openPath(b)), 1400)
  }
  async function buy() {
    setBuying(true)
    try { await api('/api/student/purchase', { method: 'POST', body: { book_id: b.id } }); toast('Added to My books'); await reload(); onChanged() } catch (e) { toast(e.message, true) } finally { setBuying(false) }
  }
  const back = b && <div className="bx-backlist"><b>{exam ? 'Papers inside' : 'Chapters'}</b>
    {exam ? (b.years || []).slice(0, 14).map(y => <span key={y}><i>·</i>{y}</span>) : (b.chapters || []).slice(0, 16).map((c, i) => <span key={i}><i>{c.number || '·'}</i>{c.title}</span>)}</div>
  return createPortal(<div className="bx-wrap" onMouseDown={e => e.target === e.currentTarget && onClose()}>
    <div className="bx" role="dialog" aria-modal="true" aria-label={b?.title || 'Book'}>
      <button className="bx-close" aria-label="Close" onClick={onClose}><Icon n="x" s={18} /></button>
      <div className={'bx-stage' + (opening ? ' opening' : '')} style={{ '--tint': b ? tintOf(b).c : undefined }}><div className="sx-stars" />
        {b && (exam ? <div style={{ transform: 'scale(1.35)' }}><PaperStack b={b} years={b.years || []} /></div>
          : <Book3D b={b} size={innerWidth < 760 ? 'lg' : 'xl'} spin flipped={flip} open={opening} back={back} ribbon={b.owned ? b.progress : null} onClick={() => !opening && setFlip(f => !f)} />)}
        {b && !exam && !opening && <button className="bx-turn" onClick={() => setFlip(f => !f)}>{flip ? 'Turn to the front' : exam ? 'See the papers' : 'Turn it over'}</button>}
      </div>
      <div className="bx-info">
        {!b ? <div className="muted">Opening</div> : <>
          <div className="bx-k">{exam ? 'Exam pack' : [b.board || b.university, b.grade && 'Class ' + b.grade].filter(Boolean).join(' · ')}</div>
          <h2>{b.title}</h2>
          <div className="bx-facts">{[exam ? b.exam : b.subject, b.pages ? b.pages + ' pages' : '', exam ? (b.papers ? b.papers + (b.papers === 1 ? ' paper' : ' papers') : '') : (b.chapters?.length ? b.chapters.length + (b.chapters.length === 1 ? ' chapter' : ' chapters') : ''),
            b.medium && b.medium !== 'English' ? b.medium + ' medium' : '', b.edition].filter(Boolean).map(x => <span key={x}>{x}</span>)}</div>
          {exam ? (b.years?.length > 0 && <div className="bx-list">{b.years.map((y, i) => <div key={y} style={{ '--n': i }}><i>{y}</i>Question paper with worked answers</div>)}</div>)
            : (b.chapters?.length > 0 && <div className="bx-list">{b.chapters.map((c, i) => <div key={i} style={{ '--n': i }}><i>{c.number || ''}</i>{c.title}</div>)}</div>)}
          <div className="bx-cta">
            {b.status === 'upcoming' ? <button className="btn lg" disabled>Coming soon</button>
              : b.owned ? (b.readable ? <button className="btn primary lg" onClick={open} disabled={opening}>{opening ? 'Opening' : exam ? 'Start practising' : 'Open the book'}</button> : <span className="tag warn">Being prepared</span>)
                : <><div className="bx-price">{inr(b.price)}</div><button className="btn primary lg" onClick={buy} disabled={buying}>{buying ? 'Adding' : 'Get it'}</button></>}
          </div>
          {!b.owned && b.status !== 'upcoming' && <div className="muted" style={{ fontSize: 12 }}>Payments are not connected yet. Getting it adds it to My books as a demo; no money is taken.</div>}
        </>}
      </div>
    </div>
    {flash && <div className="bx-flash" />}
  </div>, document.body)
}

export default function Store() {
  const { data: home } = useLoad('/api/student/home')
  const seg = useLoad('/api/student/store/segments')
  const [q, setQ] = useSearchParams(); const [pick, setPick] = useState(null)
  const mine = home?.me?.board || ''
  const inSeg = q.get('board') || q.get('exam') || q.get('uni')
  const go = (p, replace = false) => vt(() => setQ(Object.fromEntries(Object.entries({ ...p, mine: home?.me?.grade || '' }).filter(([, v]) => v)), { replace }))
  useEffect(() => { if (!inSeg) scrollTo?.(0, 0) }, [inSeg])
  const page = !seg.data ? <div className="empty">Opening the store</div>
    : inSeg ? <Segment q={q} seg={seg.data} go={go} onOpen={b => setPick(b.id)} /> : <Landing seg={seg.data} mine={mine} go={go} />
  return <div className="page">
    {page}
    {pick && <Detail id={pick} onClose={() => setPick(null)} onChanged={() => seg.reload()} />}
  </div>
}

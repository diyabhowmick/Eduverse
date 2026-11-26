import '../../study.css'
import { Link } from 'react-router-dom'
import { Ring } from '../../ui'
import Book3D, { PaperStack } from '../../Book3D'
import '../../books3d.css'

export const openPath = b => (b.track === 'exam' ? '/student/exam/' : '/student/read/') + b.id
const levelLine = b => b.level === 'degree' ? [b.university, b.course, b.semester && 'Sem ' + b.semester].filter(Boolean).join(', ')
  : b.level === 'competitive' ? 'Competitive exam' : b.board

export function Cover({ b, size = 'md' }) {
  const exam = b.track === 'exam'
  if (b.cover) return <div className={'cover-card ' + size} style={{ padding: 0, overflow: 'hidden' }}><img src={b.cover} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /></div>
  return <div className={'cover-card ' + size} style={exam ? { background: 'linear-gradient(160deg,#1b1d22,#E0212F)' } : undefined}>
    <small>{exam ? 'Exam pack' : b.content_type === 'document' ? 'Study material' : levelLine(b)}</small>
    <div><div className="cls">{exam ? b.exam : (b.level === 'degree' ? (b.semester ? 'S' + b.semester : '') : b.grade)}</div>{(b.subject || b.title) !== (exam ? b.exam : '') && <div className="subj">{b.subject || b.title}</div>}</div>
    <small>{exam ? levelLine(b) : b.medium !== 'English' ? b.medium + ' medium' : b.edition}</small></div>
}

export function BookTile({ b, action }) {
  const exam = b.track === 'exam'
  const go = b.readable && b.owned
  const inner = <>
    {exam ? <PaperStack b={b} /> : <Book3D b={b} size="md" ribbon={go ? b.progress : null} />}
    <div className="sx-cap"><b>{exam ? b.title : b.subject || b.title}</b>
      <span className="muted">{exam ? b.exam : b.grade ? 'Class ' + b.grade + (b.medium && b.medium !== 'English' ? ' · ' + b.medium : '') : levelLine(b)}</span>
      {go && !exam && <span className="muted">{b.progress ? b.progress + '% read' : 'Not started'}</span>}
      {b.owned && !b.readable && <span className="tag warn" style={{ justifySelf: 'center' }}>Being prepared</span>}
      {action}</div></>
  return go ? <Link className="t3" to={openPath(b)}>{inner}</Link> : <div className="t3">{inner}</div>
}

// "Continue reading": books already started, most read first, as a row that scrolls sideways on phones.
export function ContinueRow({ books }) {
  const list = books.filter(b => b.track !== 'exam' && b.readable && b.owned && b.progress > 0 && b.progress < 100).sort((a, b) => b.progress - a.progress).slice(0, 8)
  if (!list.length) return null
  return <div><div className="section-h"><h3>Continue reading</h3></div>
    <div className="cont-row">{list.map(b => <Link key={b.id} className="cont-card" to={openPath(b)}>
      <Book3D b={b} size="sm" />
      <div className="cont-b"><b>{b.title}</b><div className="muted">{b.progress}% read</div><span className="cont-go">Continue</span></div>
      <Ring value={b.progress} max={100} size={44} stroke={5}><span>{b.progress}%</span></Ring></Link>)}</div></div>
}

// "Not sure": flags an answer the learner guessed, so it comes back in Revise even when it was right.
export function NotSure({ on, onChange }) {
  return <button type="button" className={'notsure' + (on ? ' on' : '')} aria-pressed={!!on} onClick={() => onChange(!on)}>
    <span className="ns-box">{on ? '?' : ''}</span>Not sure</button>
}

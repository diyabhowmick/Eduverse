import { Link } from 'react-router-dom'

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
  const inner = <>
    <Cover b={b} />
    <div className="tile-b"><b>{b.title}</b>{(exam ? (b.exam !== b.title && b.exam) : levelLine(b)) && <div className="muted">{exam ? b.exam : levelLine(b)}</div>}
      {b.readable && b.owned && !exam && <><div className="bar-track" style={{ marginTop: 8 }}><i style={{ width: b.progress + '%' }} /></div><div className="muted" style={{ fontSize: 12 }}>{b.progress}% read</div></>}
      {b.owned && !b.readable && <span className="tag warn" style={{ marginTop: 8 }}>Being prepared</span>}
      {action}</div></>
  return b.readable && b.owned ? <Link className="tile" to={openPath(b)}>{inner}</Link> : <div className="tile">{inner}</div>
}

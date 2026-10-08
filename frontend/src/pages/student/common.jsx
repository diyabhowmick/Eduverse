import { Link } from 'react-router-dom'

export function Cover({ b, size = 'md' }) {
  return <div className={'cover-card ' + size}><small>{b.board}</small><div><div className="cls">{b.grade}</div><div className="subj">{b.subject || b.title}</div></div><small>{b.medium !== 'English' ? b.medium + ' medium' : b.edition}</small></div>
}

export function BookTile({ b, action }) {
  const inner = <>
    <Cover b={b} />
    <div className="tile-b"><b>{b.title}</b><div className="muted">{b.board}</div>
      {b.readable && b.owned && <><div className="bar-track" style={{ marginTop: 8 }}><i style={{ width: b.progress + '%' }} /></div><div className="muted" style={{ fontSize: 12 }}>{b.progress}% read</div></>}
      {b.owned && !b.readable && <span className="tag warn" style={{ marginTop: 8 }}>Being prepared</span>}
      {action}</div></>
  return b.readable && b.owned ? <Link className="tile" to={'/student/read/' + b.id}>{inner}</Link> : <div className="tile">{inner}</div>
}

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useLoad, Page, Tag } from '../../ui'

export default function Books() {
  const { data } = useLoad('/api/school/catalogue'); const { data: ov } = useLoad('/api/school/overview')
  const [show, setShow] = useState('live')
  const rows = data?.filter(b => b.status === show) || []
  return (
    <Page title="Books" sub={ov ? `Books you can assign on the ${ov.school.plan} plan${ov.school.max_books ? `, up to ${ov.school.max_books} per class` : ''}` : ''}
      actions={<Link className="btn" to="/admin/requests">Ask for a book</Link>}>
      <div className="toolbar"><div className="seg"><button className={show === 'live' ? 'on' : ''} onClick={() => setShow('live')}>Available now</button><button className={show === 'upcoming' ? 'on' : ''} onClick={() => setShow('upcoming')}>Coming soon</button></div></div>
      <div className="card"><table className="t"><thead><tr><th>Book</th><th>Board</th><th>Class</th><th className="num">Pages</th><th>Assigned to</th></tr></thead>
        <tbody>{rows.map(b => <tr key={b.id}><td><b>{b.title}</b><div className="muted">{b.subject}, {b.medium}</div></td>
          <td>{b.board}{!b.your_board && <div className="muted">Not your board</div>}</td><td>{b.grade}</td><td className="num">{b.pages || ''}</td>
          <td>{b.status === 'upcoming' ? <Tag s="upcoming">Coming soon</Tag> : b.classes.length ? <div className="chips">{b.classes.map(c => <span key={c} className="chip">{c}</span>)}</div> : <span className="muted">Not assigned. Use Classes to assign.</span>}</td></tr>)}</tbody></table>
        {data && !rows.length && <div className="empty">Nothing here yet</div>}</div>
    </Page>
  )
}

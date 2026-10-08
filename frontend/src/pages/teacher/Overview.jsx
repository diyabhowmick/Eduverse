import { Link } from 'react-router-dom'
import { num, when } from '../../api'
import { useLoad, Page, Tag } from '../../ui'

export default function Overview() {
  const { data: d, error } = useLoad('/api/teacher/overview')
  if (error) return <Page title="Home"><div className="empty">{error}</div></Page>
  if (!d) return <Page title="Home"><div className="empty">Loading</div></Page>
  const cs = d.classes || []
  return (
    <Page title={`Good day, ${(d.teacher || '').split(' ')[0]}`}
      sub={cs.length
        ? `${num(d.students)} students across ${cs.length} class${cs.length > 1 ? 'es' : ''}. ${d.behind} have not read this week.`
        : 'No classes have been given to you yet. Your school admin assigns them.'}>
      <div className="stack">
        <div className="metrics">
          <div className="metric"><div className="v">{cs.length}</div><div className="l">Your classes</div></div>
          <div className="metric"><div className="v">{num(d.students)}</div><div className="l">Students</div></div>
          <div className="metric"><div className="v">{d.avg_progress}%</div><div className="l">Average book progress</div></div>
          <div className="metric"><div className="v">{d.behind}</div><div className="l">Not read this week</div></div>
        </div>
        <div className="card">
          <div className="card-h"><h3>Your classes</h3></div>
          <table className="t">
            <thead><tr><th>Class</th><th className="num">Students</th><th>Books</th>
              <th className="num">Average</th><th>Read this week</th><th /></tr></thead>
            <tbody>{cs.map(c => <tr key={c.id}>
              <td><b>Class {c.name}</b></td>
              <td className="num">{c.students}</td>
              <td className="muted">{c.books.map(b => b.title).join(', ') || 'none yet'}</td>
              <td className="num">{c.avg_progress}%</td>
              <td>{c.behind ? <Tag s="suspended">{c.behind} behind</Tag>
                : <Tag s="active">all caught up</Tag>}</td>
              <td className="acts"><Link className="btn ghost sm" to={`/teacher/classes/${c.id}`}>Open</Link></td>
            </tr>)}</tbody>
          </table>
          {!cs.length && <div className="empty">Nothing yet</div>}
        </div>
      </div>
    </Page>
  )
}

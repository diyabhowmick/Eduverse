import { Link } from 'react-router-dom'
import { useLoad, Page, Tag } from '../../ui'

export default function Classes() {
  const { data, error } = useLoad('/api/teacher/classes')
  return (
    <Page title="My classes" sub="Only the classes you have been given">
      {error && <div className="empty">{error}</div>}
      <div className="card"><table className="t">
        <thead><tr><th>Class</th><th className="num">Students</th><th>Books</th>
          <th className="num">Average</th><th className="num">Read this week</th>
          <th className="num">Hours read</th><th /></tr></thead>
        <tbody>{data?.map(c => <tr key={c.id}>
          <td><b>Class {c.name}</b></td>
          <td className="num">{c.students}</td>
          <td className="muted">{c.books.map(b => b.title).join(', ') || '—'}</td>
          <td className="num">{c.avg_progress}%</td>
          <td className="num">{c.active_week} of {c.students}</td>
          <td className="num">{c.hours}</td>
          <td className="acts"><Link className="btn ghost sm" to={`/teacher/classes/${c.id}`}>Open</Link></td>
        </tr>)}</tbody></table>
        {data && !data.length && <div className="empty">No classes have been given to you yet</div>}
      </div>
    </Page>
  )
}

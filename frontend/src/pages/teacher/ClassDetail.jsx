import { Link, useParams } from 'react-router-dom'
import { api, when } from '../../api'
import { useLoad, Page, Tag, useToast } from '../../ui'

export default function ClassDetail() {
  const { cid } = useParams()
  const { data, error, reload } = useLoad(`/api/teacher/classes/${cid}`)
  const toast = useToast()
  if (error) return <Page title="Class"><div className="empty">{error}</div></Page>
  if (!data) return <Page title="Class"><div className="empty">Loading</div></Page>
  const c = data.class

  async function nudge(s) {
    try {
      await api(`/api/teacher/students/${s.id}/nudge`, { method: 'POST' })
      toast(`${s.name} has been nudged`); reload()
    } catch (e) { toast(e.message, true) }
  }

  return (
    <Page title={`Class ${c.name}`}
      sub={`${c.students} students · ${c.books.map(b => b.title).join(', ') || 'no book assigned yet'}`}
      actions={<Link className="btn" to="/teacher/classes">All classes</Link>}>
      <div className="stack">
        <div className="metrics">
          <div className="metric"><div className="v">{c.avg_progress}%</div><div className="l">Average book progress</div></div>
          <div className="metric"><div className="v">{c.active_week}</div><div className="l">Read this week</div></div>
          <div className="metric"><div className="v">{c.behind}</div><div className="l">Not read this week</div></div>
          <div className="metric"><div className="v">{c.hours}</div><div className="l">Hours read</div></div>
        </div>
        {data.by_book?.length > 0 && <div className="card">
          <div className="card-h"><h3>Books</h3></div>
          <table className="t">
            <thead><tr><th>Book</th><th className="num">Class average</th><th className="num">Not started</th></tr></thead>
            <tbody>{data.by_book.map(b => <tr key={b.id}><td><b>{b.title}</b></td><td className="num">{b.avg}%</td>
              <td className="num">{b.not_started ? `${b.not_started} of ${data.students.length}` : 'Everyone has started'}</td></tr>)}</tbody>
          </table>
        </div>}
        <div className="card">
          <div className="card-h"><h3>Students</h3></div>
          <table className="t">
            <thead><tr><th>Student</th><th>Roll no</th><th className="num">All books</th>
              {(data.by_book || []).map(b => <th key={b.id} className="num" title={b.title}>{b.title.length > 18 ? b.title.slice(0, 17) + '…' : b.title}</th>)}
              <th>Last read</th><th /></tr></thead>
            <tbody>{data.students.map(s => <tr key={s.id}>
              <td><b>{s.name}</b></td>
              <td className="muted">{s.roll_no || '—'}</td>
              <td className="num">{s.progress}%</td>
              {(data.by_book || []).map(b => <td key={b.id} className="num">{s.by_book?.[b.id] ?? 0}%</td>)}
              <td className="muted">{s.last_read ? when(s.last_read) : 'Never'}</td>
              <td className="acts">
                {s.behind && <>
                  <Tag s="suspended">Behind</Tag>
                  <button className="btn ghost sm" onClick={() => nudge(s)}>Nudge</button>
                </>}
              </td>
            </tr>)}</tbody>
          </table>
          {!data.students.length && <div className="empty">No students in this class yet</div>}
        </div>
        <p className="muted" style={{ fontSize: 12.5 }}>
          Adding, removing or suspending a student is done by your school admin.
        </p>
      </div>
    </Page>
  )
}

import { Link } from 'react-router-dom'
import { useLoad, LineChart, Page } from '../../ui'
import { compact, num, when, actionLabel } from '../../api'

export default function Overview() {
  const { data: d } = useLoad('/api/school/overview')
  const { data: a } = useLoad('/api/school/analytics?days=30')
  if (!d) return <Page title="Overview" />
  const free = d.seats - d.seats_used; const t = d.attention
  return (
    <Page title="Overview" sub={`${d.school.board}, ${d.school.medium} medium${d.school.academic_year ? ', ' + d.school.academic_year : ''}`}>
      <p className="headline"><em>{num(d.active_students)}</em> students across <em>{d.classes}</em> classes are reading <em>{d.books}</em> books. <em>{num(free)}</em> of your {num(d.seats)} seats are free.</p>
      <div className="stack">
        <div className="card"><div className="card-b">
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}><b>Seats on the {d.school.plan} plan</b><span className="muted">{num(d.seats_used)} used of {num(d.seats)}</span></div>
          <div className="seatbar"><i style={{ width: Math.min(100, d.seats_used / Math.max(1, d.seats) * 100) + '%' }} /></div>
          {free < d.seats * 0.1 && <div style={{ marginTop: 10 }}><Link className="btn sm" to="/admin/requests">Request more seats</Link></div>}
        </div></div>
        <div className="metrics">
          <div className="metric"><div className="v">{num(d.week_active)}</div><div className="l">Most active students in a day, last 7 days</div></div>
          <div className="metric"><div className="v">{compact(d.week_minutes / 60)} h</div><div className="l">Reading time, last 7 days</div></div>
          <div className="metric"><div className="v">{compact(d.week_explanations)}</div><div className="l">Explanations asked, last 7 days</div></div>
          <div className="metric"><div className="v">{d.school.max_books || 'All'}</div><div className="l">Books allowed per class</div></div>
        </div>
        <div className="card"><div className="card-h"><h3>Needs your attention</h3></div>
          <div className="attention">
            <Link to="/admin/students"><div className={'v' + (t.unassigned_students ? ' hot' : '')}>{t.unassigned_students}</div><div className="l">Students without a class</div></Link>
            <Link to="/admin/classes"><div className={'v' + (t.classes_without_books ? ' hot' : '')}>{t.classes_without_books}</div><div className="l">Classes without books</div></Link>
            <Link to="/admin/analytics"><div className="v">{num(t.idle_students)}</div><div className="l">Students who did not read this week</div></Link>
            <Link to="/admin/requests"><div className="v">{t.open_requests}</div><div className="l">Requests waiting on EduVerse</div></Link>
          </div></div>
        <div className="row">
          <div className="card" style={{ flex: 1.6 }}><div className="card-h"><h3>Daily active students</h3><span className="sub">last 30 days</span></div>
            <div className="card-b">{a && <LineChart data={a.daily} keys={[{ key: 'active', color: 'var(--red)' }]} />}</div></div>
          <div className="card"><div className="card-h"><h3>Recent changes</h3></div>
            {d.recent.length ? <ul className="feed">{d.recent.map((r, i) => <li key={i}><time>{when(r.at)}</time><span><b>{actionLabel(r.action)}</b> <span style={{ color: 'var(--ink-3)' }}>{r.detail?.name || (r.detail?.added ? r.detail.added + ' students' : '')}</span></span></li>)}</ul>
              : <div className="empty">Changes you make show up here</div>}</div>
        </div>
      </div>
    </Page>
  )
}

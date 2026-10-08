import { Link } from 'react-router-dom'
import { useLoad, LineChart, Page } from '../ui'
import { compact, num, when, actionLabel } from '../api'

export default function Dashboard() {
  const { data: d } = useLoad('/api/dashboard')
  const { data: a } = useLoad('/api/analytics?days=30')
  if (!d) return <Page title="Overview" />
  const live = d.books.live || 0
  const n = d.needs_attention
  return (
    <Page title="Overview" sub="Platform status today">
      <p className="headline"><em>{d.active_schools}</em> schools are live with <em>{num(d.seats)}</em> paid seats and <em>{live}</em> books in the catalogue, worth <em>₹{compact(d.arr)}</em> a year.</p>
      <div className="stack">
        <div className="metrics">
          <div className="metric"><div className="v">{num(d.students)}</div><div className="l">Students enrolled</div></div>
          <div className="metric"><div className="v">{num(d.admins)}</div><div className="l">School admins</div></div>
          <div className="metric"><div className="v">{compact(d.week_minutes / 60)} h</div><div className="l">Reading time, last 7 days</div></div>
          <div className="metric"><div className="v">{compact(d.week_explanations)}</div><div className="l">Explanations, last 7 days</div></div>
        </div>
        <div className="card">
          <div className="card-h"><h3>Needs your attention</h3></div>
          <div className="attention" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
            <Link to="/sa/catalogue"><div className={'v' + (n.sent_back ? ' hot' : '')}>{n.sent_back}</div><div className="l">Books sent back by reviewers</div></Link>
            <Link to="/sa/processing"><div className={'v' + (n.failed_jobs ? ' hot' : '')}>{n.failed_jobs}</div><div className="l">Failed processing jobs</div></Link>
            <Link to="/sa/catalogue"><div className="v">{n.in_review}</div><div className="l">Books with reviewers</div></Link>
            <Link to="/sa/requests"><div className={'v' + (n.open_requests ? ' hot' : '')}>{n.open_requests}</div><div className="l">School requests waiting</div></Link>
            <Link to="/sa/schools"><div className="v">{n.suspended_schools}</div><div className="l">Suspended schools</div></Link>
          </div>
        </div>
        <div className="row">
          <div className="card" style={{ flex: 1.6 }}>
            <div className="card-h"><h3>Daily active students</h3><span className="sub">last 30 days</span></div>
            <div className="card-b">{a && <LineChart data={a.daily} keys={[{ key: 'active', color: 'var(--red)' }]} />}</div>
          </div>
          <div className="card">
            <div className="card-h"><h3>Recent activity</h3><Link className="right btn ghost sm" to="/sa/audit">Open audit log</Link></div>
            <ul className="feed">{d.recent.map((r, i) => <li key={i}><time>{when(r.at)}</time><span><b>{actionLabel(r.action)}</b> <span style={{ color: 'var(--ink-3)' }}>{r.detail?.name || r.detail?.title || r.detail?.email || r.detail?.file || r.target}</span></span></li>)}</ul>
          </div>
        </div>
      </div>
    </Page>
  )
}

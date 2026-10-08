import { useState } from 'react'
import { Link } from 'react-router-dom'
import { when, num } from '../../api'
import { useLoad, Page, Tag } from '../../ui'

/* Pipeline health.
   The factory's own screen. Processing already shows what is running right
   now; this answers the harder question — is the pipeline trustworthy, and
   where does it keep breaking. Failures are grouped, because the same problem
   twenty times is one problem, not twenty. */
export default function Health() {
  const [days, setDays] = useState(30)
  const { data: d } = useLoad('/api/factory/health?days=' + days, [days])
  if (!d) return <Page title="Pipeline health" />

  const j = d.jobs
  const ok = d.success_rate
  const tone = ok == null ? '' : ok >= 90 ? '' : ok >= 70 ? 'warn' : 'bad'
  const problems = d.poor_conversions.length + d.stuck_in_review.length + d.no_figures.length
  const SPLIT = {
    sections: 'Split by printed section numbers',
    headings: 'No section numbers — split by headings',
    pages: 'Neither found — page by page',
    'not converted': 'Not converted yet',
  }

  return (
    <Page title="Pipeline health" sub="Whether book production is trustworthy, and where it keeps breaking">
      <p className="headline">
        {ok == null
          ? <>Nothing has been processed in the last {days} days.</>
          : <><em>{ok}%</em> of the books started in the last {days} days came out the other end.
            {j.failed > 0 && <> {j.failed === 1 ? 'One failed' : j.failed + ' failed'}.</>}</>}
      </p>

      <div className="stack">
        <div className="metrics">
          <div className="metric"><div className="v">{j.done}</div><div className="l">Finished, of {j.total} started</div></div>
          <div className="metric"><div className="v">{j.failed + j.cancelled}</div><div className="l">{j.failed} failed, {j.cancelled} stopped by hand</div></div>
          <div className="metric"><div className="v">{d.min_per_page ?? '—'}</div><div className="l">Minutes a page, from upload to finished — queue waiting included, so it reads high when books are stacked up</div></div>
          <div className="metric"><div className="v">{j.running + j.queued}</div><div className="l">{j.running} running, {j.queued} waiting</div></div>
        </div>

        <div className="card">
          <div className="card-h"><h3>Why books fail</h3>
            <span className="sub">Grouped by reason</span>
            <span className="right">
              <select className="input" value={days} onChange={e => setDays(+e.target.value)}>
                <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
              </select></span>
          </div>
          <table className="t">
            <thead><tr><th>Reason</th><th className="num">Books</th></tr></thead>
            <tbody>{d.failures.map((f, i) => (
              <tr key={i}><td>{f.why}</td><td className="num">{f.n}</td></tr>))}</tbody>
          </table>
          {!d.failures.length && <div className="empty">No failures in the last {days} days.</div>}
        </div>

        {!!d.recent_failures.length && <div className="card">
          <div className="card-h"><h3>The last failures</h3><span className="sub">Newest first</span></div>
          <table className="t">
            <thead><tr><th>File</th><th>Got as far as</th><th>Reason</th><th>When</th></tr></thead>
            <tbody>{d.recent_failures.map(f => (
              <tr key={f.id}>
                <td><b>{f.filename}</b></td>
                <td className="muted">{f.pages_done}{f.pages ? ' of ' + f.pages : ''} pages</td>
                <td>{f.why}</td>
                <td className="muted">{when(f.at)}</td>
              </tr>))}</tbody>
          </table>
        </div>}

        <div className="card">
          <div className="card-h"><h3>How books came out</h3></div>
          <table className="t">
            <thead><tr><th>Result</th><th className="num">Books</th></tr></thead>
            <tbody>{Object.entries(d.split).map(([k, n]) => (
              <tr key={k}>
                <td>{SPLIT[k] || k} {k === 'pages' && <Tag s="warn">no chapter list</Tag>}</td>
                <td className="num">{num(n)}</td>
              </tr>))}</tbody>
          </table>
          <div className="note">
            A book is split into chapters by its printed section numbers where it has them, by its
            headings where it does not, and failing both, every page becomes its own unit. The last
            one still reads — the reviewer can work and a student can study — but it has no real
            chapter list, so it is worth looking at the original.
          </div>
        </div>

        {!!d.poor_conversions.length && <div className="card">
          <div className="card-h"><h3>Books with no chapter list</h3><Tag s="warn">{d.poor_conversions.length}</Tag></div>
          <table className="t">
            <thead><tr><th>Book</th><th className="num">Pages</th><th className="num">Headings found</th><th>Status</th><th /></tr></thead>
            <tbody>{d.poor_conversions.map(b => (
              <tr key={b.id}>
                <td><b>{b.title}</b></td><td className="num">{b.pages}</td><td className="num">{b.headings}</td>
                <td><Tag s={b.status} /></td>
                <td><Link className="btn ghost sm" to="/pa/catalogue">Open in catalogue</Link></td>
              </tr>))}</tbody>
          </table>
        </div>}

        {!!d.stuck_in_review.length && <div className="card">
          <div className="card-h"><h3>Sitting in review over two weeks</h3><Tag s="bad">{d.stuck_in_review.length}</Tag></div>
          <table className="t">
            <thead><tr><th>Book</th><th>Waiting</th><th>With</th><th /></tr></thead>
            <tbody>{d.stuck_in_review.map(b => (
              <tr key={b.id}>
                <td><b>{b.title}</b></td><td><Tag s="bad">{b.days} days</Tag></td><td>{b.reviewer}</td>
                <td><Link className="btn ghost sm" to="/pa/reviewers">Hand to someone else</Link></td>
              </tr>))}</tbody>
          </table>
        </div>}

        {!!d.no_figures.length && <div className="card">
          <div className="card-h"><h3>Long books with no figures at all</h3><Tag s="warn">{d.no_figures.length}</Tag></div>
          <table className="t">
            <thead><tr><th>Book</th><th className="num">Pages</th></tr></thead>
            <tbody>{d.no_figures.map(b => (
              <tr key={b.id}><td><b>{b.title}</b></td><td className="num">{b.pages}</td></tr>))}</tbody>
          </table>
          <div className="note">
            A textbook this long with zero figures usually means figure detection missed them, not
            that the book has none. Worth opening one page against the original.
          </div>
        </div>}

        {!problems && !d.failures.length && <div className="card">
          <div className="empty">Nothing to fix. Every book started in the last {days} days came out the other end with a chapter list.</div>
        </div>}
      </div>
    </Page>
  )
}

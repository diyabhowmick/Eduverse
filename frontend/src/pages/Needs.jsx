import { Link } from 'react-router-dom'
import { inr, day } from '../api'
import { useLoad, Page, Tag } from '../ui'

/* What needs you today — Super Admin's home.

   This replaced a screen of statistics. A count of schools is pleasant to look
   at and tells you nothing to do; every row here is a decision, and each one is
   money arriving or money leaving. An empty screen is a good day, which is why
   it says so instead of showing zeroes. */

const Block = ({ title, why, rows, children, tone }) => !rows.length ? null : (
  <div className="card">
    <div className="card-h"><h3>{title}</h3><Tag s={tone}>{rows.length}</Tag><span className="sub">{why}</span></div>
    {children}
  </div>
)

export default function Needs() {
  const { data: d } = useLoad('/api/money/needs-attention')
  if (!d) return <Page title="What needs you today" />

  const total = d.nearly_full.length + d.renewing.length + d.gone_quiet.length
    + d.never_onboarded.length + d.stuck_in_review.length + d.poor_conversions.length
  const money = [...d.renewing, ...d.gone_quiet].reduce((s, r) => s + r.value, 0)
  const sale = d.nearly_full.reduce((s, r) => s + r.value, 0)

  const who = r => (
    <td><b>{r.name}</b>{r.contact && <div className="muted" style={{ fontSize: 12 }}>{r.contact} · {r.phone || 'no phone on file'}</div>}</td>)

  return (
    <Page title="What needs you today"
      sub="Decisions, not statistics — every row is money arriving or leaving"
      actions={<Link className="btn ghost" to="/sa/numbers">See the numbers instead</Link>}>

      <p className="headline">
        {!total
          ? <>Nothing needs you. No renewal inside 45 days, no school gone quiet, nothing stuck in review.</>
          : <><em>{total}</em> {total === 1 ? 'thing needs' : 'things need'} a decision.
            {money > 0 && <> <em>{inr(money)}</em> of yearly value is in the balance.</>}</>}
      </p>

      <div className="stack">
        <Block title="Renewing inside 45 days" tone="warn" rows={d.renewing}
          why="Call before the date, not after it">
          <table className="t">
            <thead><tr><th>School</th><th className="num">Seats</th><th className="num">Value</th><th>Renews</th><th /></tr></thead>
            <tbody>{d.renewing.map(r => (
              <tr key={r.id}>{who(r)}
                <td className="num">{r.used} of {r.seats}</td>
                <td className="num">{inr(r.value)}</td>
                <td>{day(r.plan_end)}</td>
                <td><Tag s={r.days_to_renewal <= 30 ? 'bad' : 'warn'}>{r.days_to_renewal} days</Tag></td>
              </tr>))}</tbody>
          </table>
        </Block>

        <Block title="Nearly out of seats" tone="ok" rows={d.nearly_full}
          why={sale > 0 ? 'A sale, not a problem' : 'A sale'}>
          <table className="t">
            <thead><tr><th>School</th><th className="num">Seats used</th><th className="num">Free</th><th className="num">Current value</th></tr></thead>
            <tbody>{d.nearly_full.map(r => (
              <tr key={r.id}>{who(r)}
                <td className="num">{r.used} of {r.seats}</td>
                <td className="num">{r.free}</td>
                <td className="num">{inr(r.value)}</td>
              </tr>))}</tbody>
          </table>
          <div className="note">They are about to run out of seats. Offer more before a teacher
            finds out by failing to add a student.</div>
        </Block>

        <Block title="Gone quiet" tone="bad" rows={d.gone_quiet}
          why="Nobody has signed in for over two weeks">
          <table className="t">
            <thead><tr><th>School</th><th>Last sign in</th><th className="num">Seats</th><th className="num">At risk</th></tr></thead>
            <tbody>{d.gone_quiet.map(r => (
              <tr key={r.id}>{who(r)}
                <td><Tag s="bad">{r.quiet_days} days ago</Tag></td>
                <td className="num">{r.used} of {r.seats}</td>
                <td className="num">{inr(r.value)}</td>
              </tr>))}</tbody>
          </table>
          <div className="note">A paying school that has stopped signing in will not renew. This is
            the cheapest renewal to save, because it has not been lost yet.</div>
        </Block>

        <Block title="Paid for but never set up" tone="bad" rows={d.never_onboarded}
          why="Under a fifth of their seats are in use">
          <table className="t">
            <thead><tr><th>School</th><th className="num">Students added</th><th className="num">Seats paid for</th><th className="num">Value</th></tr></thead>
            <tbody>{d.never_onboarded.map(r => (
              <tr key={r.id}>{who(r)}
                <td className="num">{r.used}</td>
                <td className="num">{r.seats}</td>
                <td className="num">{inr(r.value)}</td>
              </tr>))}</tbody>
          </table>
          <div className="note">They have paid and nobody has used it. Somebody needs to walk their
            admin through adding students — this is the renewal most likely to be lost, and the
            easiest to fix.</div>
        </Block>

        <Block title="Stuck in review over two weeks" tone="warn" rows={d.stuck_in_review}
          why="A book nobody is reading is a book nobody paid for yet">
          <table className="t">
            <thead><tr><th>Book</th><th>Waiting</th><th /></tr></thead>
            <tbody>{d.stuck_in_review.map(b => (
              <tr key={b.id}>
                <td><b>{b.title}</b></td>
                <td><Tag s="bad">{b.days} days</Tag></td>
                <td><Link className="btn ghost sm" to="/sa/reviewers">Hand to someone else</Link></td>
              </tr>))}</tbody>
          </table>
        </Block>

        <Block title="Books that came out without a chapter list" tone="warn" rows={d.poor_conversions}
          why="Readable, but no real chapters">
          <table className="t">
            <thead><tr><th>Book</th><th>Split by</th><th className="num">Headings found</th><th /></tr></thead>
            <tbody>{d.poor_conversions.map(b => (
              <tr key={b.id}>
                <td><b>{b.title}</b></td>
                <td><Tag s="warn">page by page</Tag></td>
                <td className="num">{b.headings}</td>
                <td><Link className="btn ghost sm" to="/sa/health">Pipeline health</Link></td>
              </tr>))}</tbody>
          </table>
        </Block>

        {!total && <div className="card"><div className="empty">
          Nothing is waiting on you. The statistics are still on
          <Link to="/sa/numbers" style={{ margin: '0 4px' }}>the numbers screen</Link>
          if you want them.
        </div></div>}
      </div>
    </Page>
  )
}

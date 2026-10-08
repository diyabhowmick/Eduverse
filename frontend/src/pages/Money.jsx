import { Link } from 'react-router-dom'
import { useLoad, Page, Tag } from '../ui'
import { compact, num } from '../api'

/* Money and renewals.
   Nothing in the product answered "what do we earn, from whom, and what
   expires next month". A plan simply existed with no end date, which makes a
   renewal something you notice after it has passed. */
export default function Money() {
  const { data: d } = useLoad('/api/money/overview')
  if (!d) return <Page title="Money and renewals" />

  const soon = d.renewals.filter(r => r.days_to_renewal <= 45)
  const tone = n => n <= 30 ? 'bad' : n <= 45 ? 'warn' : ''

  return (
    <Page title="Money and renewals" sub="What comes in, from whom, and what is about to expire">
      <p className="headline">
        <em>{d.schools}</em> paying schools are worth <em>₹{compact(d.billed)}</em> a year.
        {soon.length > 0 && <> <em>₹{compact(d.renewing_45d)}</em> of that comes up for renewal in the next 45 days.</>}
      </p>
      <div className="stack">
        <div className="metrics">
          <div className="metric"><div className="v">₹{compact(d.billed)}</div><div className="l">Billed this year</div></div>
          <div className="metric"><div className="v">₹{compact(d.used)}</div><div className="l">Seats actually used</div></div>
          <div className="metric"><div className="v">₹{compact(d.idle)}</div><div className="l">Paid for and sitting idle</div></div>
          <div className="metric"><div className="v">₹{compact(d.at_risk)}</div><div className="l">At risk — quiet or barely used</div></div>
        </div>

        <div className="note">
          <b>What it costs to serve all of this: ${d.catalogue_cost_usd.toFixed(2)}.</b> That is the
          whole catalogue — {d.books} books, each processed once. A book is paid for once and read
          by every school on that syllabus, so this figure does not grow when a school reads more.
        </div>

        <div className="card">
          <div className="card-h"><h3>Renewals, soonest first</h3></div>
          <table className="t">
            <thead><tr>
              <th>School</th><th>Plan</th><th className="num">Seats</th>
              <th className="num">Value</th><th>Renews</th><th />
            </tr></thead>
            <tbody>{d.renewals.map(r => (
              <tr key={r.id}>
                <td><b>{r.name}</b>{r.contact && <div className="muted" style={{ fontSize: 12 }}>{r.contact} · {r.phone}</div>}</td>
                <td>{r.plan || '—'}</td>
                <td className="num">{r.used} of {r.seats}</td>
                <td className="num">₹{num(r.value)}</td>
                <td>{r.plan_end ? new Date(r.plan_end).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}</td>
                <td><Tag s={tone(r.days_to_renewal)}>{r.days_to_renewal} days</Tag></td>
              </tr>
            ))}</tbody>
          </table>
          {!d.renewals.length && <div className="empty">
            No school has a renewal date yet. Set one when you add or edit a school — without it,
            a plan can lapse without anybody noticing.
          </div>}
        </div>

        <div className="card">
          <div className="card-h"><h3>Where the money is not being used</h3></div>
          <table className="t">
            <thead><tr><th>School</th><th className="num">Seats used</th><th className="num">Idle value</th><th /></tr></thead>
            <tbody>{d.renewals.filter(r => r.free > 0).sort((a, b) => b.free - a.free).map(r => (
              <tr key={r.id}>
                <td><b>{r.name}</b></td>
                <td className="num">{r.used} of {r.seats}</td>
                <td className="num">₹{num(r.free * r.price_per_seat)}</td>
                <td>{r.never_onboarded
                  ? <Tag s="bad">never onboarded</Tag>
                  : r.nearly_full ? <Tag s="warn">nearly full — a sale</Tag> : null}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>

        <p className="muted" style={{ fontSize: 12.5 }}>
          Seats bought but unused is the clearest early warning there is. A school that bought 320
          seats and enrolled 12 students did not onboard, and will not renew unless somebody helps
          them. <Link to="/sa/schools">Open a school</Link> to see its full record.
        </p>
      </div>
    </Page>
  )
}

import { Link } from 'react-router-dom'
import { num } from '../../api'
import { useLoad, Page, Tag } from '../../ui'

/* Keys and spending.
   There are three API keys in this product and they are genuinely separate: a
   key typed into one screen does nothing for the other two. That has caught
   people out — a book comes back with blank figures and the key looks set,
   because it was set somewhere else. This screen puts all three in one place
   and says which job each one does. */
export default function Keys() {
  const { data: d } = useLoad('/api/factory/keys')
  if (!d) return <Page title="Keys and spending" />
  const s = d.spend

  return (
    <Page title="Keys and spending" sub="The three keys this product uses, and what they have cost">
      <p className="headline">
        {d.missing.length
          ? <><em>{d.missing.length === 1 ? 'One key is missing' : d.missing.length + ' keys are missing'}</em> — {d.missing.join(' and ')}. That part of the pipeline cannot run.</>
          : <>All three keys are set. The catalogue has cost <em>${s.all_time_usd.toFixed(2)}</em> so far.</>}
      </p>

      <div className="stack">
        <div className="card">
          <div className="card-h"><h3>The three keys</h3>
            <span className="sub">Each lives on its own screen, and each is a separate account</span></div>
          <table className="t">
            <thead><tr><th>Key</th><th>What it does</th><th>Provider and model</th><th>Set?</th><th /></tr></thead>
            <tbody>{d.slots.map(k => (
              <tr key={k.slot}>
                <td><b>{k.slot}</b></td>
                <td className="muted">{k.does}</td>
                <td>{k.provider}{k.model ? <div className="muted" style={{ fontSize: 12 }}>{k.model}</div> : null}</td>
                <td>{k.set ? <Tag s="ok">Set</Tag>
                  : k.needed ? <Tag s="bad">Missing</Tag>
                    : <Tag s="info">Not needed</Tag>}</td>
                <td><Link className="btn ghost sm" to={'/pa/' + k.path}>{k.screen}</Link></td>
              </tr>))}</tbody>
          </table>
          <div className="note">
            A key in one row does nothing for the other two. If figures come back blank while page
            text reads fine, it is the M2 key, not the M1 one.
          </div>
        </div>

        <div className="metrics">
          <div className="metric"><div className="v">${s.all_time_usd.toFixed(2)}</div><div className="l">Spent on the whole catalogue, all time</div></div>
          <div className="metric"><div className="v">${s.this_month_usd.toFixed(2)}</div><div className="l">This month, across {s.books_this_month} {s.books_this_month === 1 ? 'book' : 'books'}</div></div>
          <div className="metric"><div className="v">${s.avg_per_book_usd.toFixed(2)}</div><div className="l">Average, per book processed</div></div>
          <div className="metric"><div className="v">{num(d.monthly_token_budget)}</div><div className="l">Monthly token budget</div></div>
        </div>

        <div className="note">
          <b>This is a one-time cost per book, not a running one.</b> A book is processed once and
          read by every school on that syllabus, so this figure does not grow when a school reads
          more. The rate paid is ${d.rates.input_per_mtok} per million tokens in and
          ${d.rates.output_per_mtok} out.
        </div>

        <div className="card">
          <div className="card-h"><h3>The most expensive books</h3>
            <span className="sub">Scanned pages are the whole difference</span></div>
          <table className="t">
            <thead><tr><th>Book</th><th className="num">Pages</th><th className="num">Scanned pages</th><th className="num">Cost</th></tr></thead>
            <tbody>{s.most_expensive.map(b => (
              <tr key={b.id}>
                <td><b>{b.title}</b></td>
                <td className="num">{b.pages}</td>
                <td className="num">{b.scanned || '—'}</td>
                <td className="num">${b.cost_usd.toFixed(3)}</td>
              </tr>))}</tbody>
          </table>
          {!s.most_expensive.length && <div className="empty">
            No book has cost anything yet. A book only costs money for the pages that have to be
            read by the model — a page with real text in it is copied for free.
          </div>}
        </div>
      </div>
    </Page>
  )
}

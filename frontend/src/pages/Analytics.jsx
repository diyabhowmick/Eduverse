import { useState } from 'react'
import { compact, inr, num } from '../api'
import { useLoad, Page, LineChart, HBars } from '../ui'

export default function Analytics() {
  const [days, setDays] = useState(30)
  const { data } = useLoad('/api/analytics?days=' + days, [days])
  const revenue = data?.revenue.filter(r => r.annual_value > 0).sort((a, b) => b.annual_value - a.annual_value) || []
  return (
    <Page title="Analytics" sub="Usage, engagement and revenue across every school"
      actions={<div className="seg">{[7, 30, 90].map(d => <button key={d} className={days === d ? 'on' : ''} onClick={() => setDays(d)}>{d} days</button>)}</div>}>
      {data && <div className="stack">
        <div className="metrics">
          <div className="metric"><div className="v">{compact(data.totals.minutes / 60)} h</div><div className="l">Reading time</div></div>
          <div className="metric"><div className="v">{compact(data.totals.explanations)}</div><div className="l">Explanations</div></div>
          <div className="metric"><div className="v">{compact(data.totals.tokens)}</div><div className="l">LLM tokens</div></div>
          <div className="metric"><div className="v">₹{compact(revenue.reduce((a, r) => a + r.annual_value, 0))}</div><div className="l">Annual contract value</div></div>
        </div>
        <div className="card">
          <div className="card-h"><h3>Daily activity</h3><span className="sub"><b style={{ color: 'var(--red)' }}>Active students</b> and <b style={{ color: 'var(--ink-3)' }}>explanations / 5</b></span></div>
          <div className="card-b"><LineChart data={data.daily.map(d => ({ ...d, ex5: d.explanations / 5 }))} keys={[{ key: 'active', color: 'var(--red)' }, { key: 'ex5', color: 'var(--ink-3)' }]} /></div>
        </div>
        <div className="row">
          <div className="card"><div className="card-h"><h3>Books by reading time</h3><span className="sub">hours</span></div>
            <div className="card-b"><HBars rows={data.top_books} label="book" value="minutes" fmt={m => num(Math.round(m / 60))} /></div></div>
          <div className="card"><div className="card-h"><h3>Schools by reading time</h3><span className="sub">hours</span></div>
            <div className="card-b"><HBars rows={data.schools} label="school" value="minutes" fmt={m => num(Math.round(m / 60))} /></div></div>
        </div>
        <div className="card"><div className="card-h"><h3>Revenue by school</h3><span className="sub">yearly contract value after discounts</span></div>
          <table className="t"><thead><tr><th>School</th><th>Plan</th><th className="num">Seats</th><th className="num">Annual value</th></tr></thead>
            <tbody>{revenue.map(r => <tr key={r.school}><td>{r.school}</td><td>{r.plan}</td><td className="num">{num(r.seats)}</td><td className="num">{inr(r.annual_value)}</td></tr>)}</tbody></table></div>
      </div>}
    </Page>
  )
}

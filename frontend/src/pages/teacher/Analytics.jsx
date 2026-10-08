import { useState } from 'react'
import { compact, num, when } from '../../api'
import { useLoad, Page, LineChart } from '../../ui'

export default function Analytics() {
  const [days, setDays] = useState(30)
  const { data, error } = useLoad('/api/teacher/analytics?days=' + days, [days])
  const tot = data ? data.daily.reduce((a, d) => ({ m: a.m + d.minutes, e: a.e + d.explanations }), { m: 0, e: 0 }) : null
  return (
    <Page title="Analytics" sub="How your classes are reading"
      actions={<div className="seg">{[7, 30, 90].map(d =>
        <button key={d} className={days === d ? 'on' : ''} onClick={() => setDays(d)}>{d} days</button>)}</div>}>
      {error && <div className="empty">{error}</div>}
      {data && <div className="stack">
        <div className="metrics">
          <div className="metric"><div className="v">{compact(tot.m / 60)} h</div><div className="l">Reading time</div></div>
          <div className="metric"><div className="v">{compact(tot.e)}</div><div className="l">Explanations asked</div></div>
          <div className="metric"><div className="v">{data.classes.length}</div><div className="l">Your classes</div></div>
          <div className="metric"><div className="v">{num(data.classes.reduce((a, c) => a + c.active_week, 0))}</div>
            <div className="l">Students who read this week</div></div>
        </div>
        <div className="card"><div className="card-h"><h3>Daily active students</h3></div>
          <div className="card-b"><LineChart data={data.daily} keys={[{ key: 'active', color: 'var(--red)' }]} /></div></div>
        <div className="card"><div className="card-h"><h3>Class by class</h3></div>
          <table className="t">
            <thead><tr><th>Class</th><th className="num">Students</th><th className="num">Average progress</th>
              <th className="num">Read this week</th><th className="num">Hours read</th></tr></thead>
            <tbody>{data.classes.map(c => <tr key={c.id}>
              <td><b>Class {c.name}</b></td><td className="num">{c.students}</td>
              <td className="num">{c.avg_progress}%</td><td className="num">{c.active_week}</td>
              <td className="num">{c.hours}</td></tr>)}</tbody>
          </table>
        </div>
        <div className="grid2">
          <div className="card"><div className="card-h"><h3>Reading the most</h3></div>
            <table className="t"><tbody>{data.top.map(s => <tr key={s.id}>
              <td>{s.name}<div className="muted" style={{ fontSize: 11 }}>{s.class}</div></td>
              <td className="num">{s.progress}%</td></tr>)}</tbody></table>
            {!data.top.length && <div className="empty">Nothing yet</div>}</div>
          <div className="card"><div className="card-h"><h3>Needs a hand</h3></div>
            <table className="t"><tbody>{data.needs_help.map(s => <tr key={s.id}>
              <td>{s.name}<div className="muted" style={{ fontSize: 11 }}>
                {s.last_read ? 'last read ' + when(s.last_read) : 'never read'}</div></td>
              <td className="num">{s.progress}%</td></tr>)}</tbody></table>
            {!data.needs_help.length && <div className="empty">Everyone is keeping up</div>}</div>
        </div>
      </div>}
    </Page>
  )
}

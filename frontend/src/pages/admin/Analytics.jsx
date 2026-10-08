import { useState } from 'react'
import { compact, num, when } from '../../api'
import { useLoad, Page, LineChart, HBars } from '../../ui'

export default function Analytics() {
  const [days, setDays] = useState(30)
  const { data } = useLoad('/api/school/analytics?days=' + days, [days])
  const tot = data ? data.daily.reduce((a, d) => ({ m: a.m + d.minutes, e: a.e + d.explanations }), { m: 0, e: 0 }) : null
  return (
    <Page title="Analytics" sub="How your classes are reading" actions={<div className="seg">{[7, 30, 90].map(d => <button key={d} className={days === d ? 'on' : ''} onClick={() => setDays(d)}>{d} days</button>)}</div>}>
      {data && <div className="stack">
        <div className="metrics">
          <div className="metric"><div className="v">{compact(tot.m / 60)} h</div><div className="l">Reading time</div></div>
          <div className="metric"><div className="v">{compact(tot.e)}</div><div className="l">Explanations asked</div></div>
          <div className="metric"><div className="v">{data.classes.length ? Math.round(data.classes.reduce((a, c) => a + c.avg_progress * c.students, 0) / Math.max(1, data.classes.reduce((a, c) => a + c.students, 0))) : 0}%</div><div className="l">Average book progress</div></div>
          <div className="metric"><div className="v">{num(data.classes.reduce((a, c) => a + c.active_week, 0))}</div><div className="l">Students who read this week</div></div>
        </div>
        <div className="card"><div className="card-h"><h3>Daily active students</h3></div><div className="card-b"><LineChart data={data.daily} keys={[{ key: 'active', color: 'var(--red)' }]} /></div></div>
        <div className="card"><div className="card-h"><h3>Class by class</h3></div>
          <table className="t"><thead><tr><th>Class</th><th className="num">Students</th><th>Average progress</th><th className="num">Read this week</th><th className="num">Hours read</th></tr></thead>
            <tbody>{data.classes.map(c => <tr key={c.class}><td><b>{c.class}</b></td><td className="num">{c.students}</td>
              <td style={{ minWidth: 180 }}><div style={{ display: 'flex', gap: 10, alignItems: 'center' }}><div className="bar-track" style={{ flex: 1 }}><i style={{ width: c.avg_progress + '%' }} /></div><span className="muted">{c.avg_progress}%</span></div></td>
              <td className="num">{c.active_week} of {c.students}</td><td className="num">{num(c.hours)}</td></tr>)}</tbody></table></div>
        <div className="row">
          <div className="card"><div className="card-h"><h3>Furthest ahead</h3></div><table className="t"><tbody>{data.top.map(s => <tr key={s.id}><td><b>{s.name}</b><div className="muted">{s.class}</div></td><td className="num">{s.progress}%</td></tr>)}</tbody></table></div>
          <div className="card"><div className="card-h"><h3>May need help</h3><span className="sub">lowest progress, active students</span></div><table className="t"><tbody>{data.needs_help.map(s => <tr key={s.id}><td><b>{s.name}</b><div className="muted">{s.class}{s.last_read ? ', last read ' + when(s.last_read) : ', not started'}</div></td><td className="num">{s.progress}%</td></tr>)}</tbody></table></div>
          <div className="card"><div className="card-h"><h3>Books by reading time</h3><span className="sub">hours</span></div><div className="card-b"><HBars rows={data.books} label="book" value="minutes" fmt={m => num(Math.round(m / 60))} /></div></div>
        </div>
      </div>}
    </Page>
  )
}

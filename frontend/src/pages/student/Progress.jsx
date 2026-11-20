import { Link } from 'react-router-dom'
import { day } from '../../api'
import { useLoad, Page, Ring, Icon, plural } from '../../ui'

const hm = m => m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`
const band = a => a >= 75 ? '' : a >= 50 ? ' mid' : ' low'

export default function Progress() {
  const { data: d } = useLoad('/api/student/progress')
  if (!d) return <Page title="Progress"><div className="empty">Loading</div></Page>
  const month = d.days.reduce((a, x) => a + x.minutes, 0); const max = Math.max(10, ...d.days.map(x => x.minutes))
  const acc = d.practised ? Math.round(d.correct / d.practised * 100) : 0
  const weak = d.chapters.filter(c => c.tried >= 3 && c.chapter !== 'Not tagged').slice(0, 5)
  const strong = [...d.chapters].filter(c => c.tried >= 3 && c.chapter !== 'Not tagged').reverse().slice(0, 5)
  const empty = !month && !d.practised && !d.tests.length
  return (
    <Page title="Progress" sub="How much you study, how you are scoring, and what to work on next">
      <div className="stack">
        <div className="today">
          <div><span className="ic"><Icon n="fire" /></span><div><div className="v">{d.streak ? plural(d.streak, 'day') : 'No streak yet'}</div><div className="l">Study streak</div></div></div>
          <div><span className="ic"><Icon n="clock" /></span><div><div className="v">{hm(month)}</div><div className="l">Studied in the last 30 days</div></div></div>
          <div><Ring value={acc} max={100} size={52} stroke={6}><span style={{ fontSize: 12 }}>{acc}%</span></Ring><div><div className="v">{plural(d.practised, 'question')}</div><div className="l">Practised, {acc}% right</div></div></div>
        </div>
        {empty && <div className="card empty">Your progress shows here once you start reading or practising. <Link to="/student" style={{ color: 'var(--red)', fontWeight: 650 }}>Go to Home</Link></div>}
        {month > 0 && <div className="card"><div className="card-h"><h3>Last 30 days</h3><span className="sub">{hm(month)} in total</span></div>
          <div className="card-b"><div className="bars30" role="img" aria-label={`Minutes studied each day for the last 30 days, ${month} in total`}>{d.days.map(x => <i key={x.day} className={x.minutes ? '' : 'zero'} title={`${day(x.day)}: ${x.minutes} min`} style={{ height: (x.minutes / max * 100) + '%' }} />)}</div></div></div>}
        <div className="row">
          {d.subjects.length > 0 && <div className="card"><div className="card-h"><h3>By subject</h3></div><div className="card-b">
            {d.subjects.map(s => <div key={s.subject} className="acc"><span>{s.subject}</span><div className={'bar-track' + band(s.accuracy)}><i style={{ width: s.accuracy + '%' }} /></div><b className="num">{s.accuracy}%</b></div>)}</div></div>}
          {weak.length > 0 && <div className="card"><div className="card-h"><h3>Needs work</h3><span className="sub">Lowest scores, from 3 or more tries</span></div><div className="card-b">
            {weak.map(c => <div key={c.book_id + c.chapter} className="acc"><span>{c.chapter}</span><div className={'bar-track' + band(c.accuracy)}><i style={{ width: c.accuracy + '%' }} /></div>
              <Link className="btn sm" to={`/student/exam/${c.book_id}?tab=practice&chapter=${encodeURIComponent(c.chapter)}`}>Practise</Link></div>)}</div></div>}
        </div>
        {strong.length > 0 && strong[0].accuracy >= 75 && <div className="card"><div className="card-h"><h3>Your strongest chapters</h3></div><div className="card-b">
          {strong.filter(c => c.accuracy >= 75).map(c => <div key={c.book_id + c.chapter} className="acc"><span>{c.chapter}</span><div className="bar-track"><i style={{ width: c.accuracy + '%' }} /></div><b className="num">{c.accuracy}%</b></div>)}</div></div>}
        {d.tests.length > 0 && <div className="card"><div className="card-h"><h3>Tests</h3><span className="sub">Most recent first</span></div>
          <table className="t"><tbody>{d.tests.map(t => <tr key={t.id}><td><b>{t.title || 'Test'}</b><div className="muted" style={{ fontSize: 12 }}>{day(t.when)} · {plural(t.questions, 'question')}{t.time_taken ? ' · ' + hm(Math.round(t.time_taken / 60)) : ''}</div></td>
            <td className="num"><b>{t.score}</b> <span className="muted">/ {t.total}</span></td><td className="num" style={{ width: 70 }}>{t.pct != null ? t.pct + '%' : ''}</td></tr>)}</tbody></table></div>}
        {d.books.some(b => b.track !== 'exam' && b.readable) && <div className="card"><div className="card-h"><h3>Reading</h3></div><div className="card-b">
          {d.books.filter(b => b.track !== 'exam' && b.readable).map(b => <div key={b.id} className="acc"><Link to={'/student/read/' + b.id}>{b.title}</Link><div className="bar-track"><i style={{ width: b.progress + '%', background: 'var(--red)' }} /></div><b className="num">{b.progress}%</b></div>)}</div></div>}
      </div>
    </Page>
  )
}

import { Link } from 'react-router-dom'
import { useLoad, Page } from '../../ui'
import { BookTile, Cover } from './common'

export default function Home() {
  const { data: d } = useLoad('/api/student/home')
  if (!d) return <Page title="Home" />
  const c = d.continue; const max = Math.max(10, ...d.week.map(w => w.minutes))
  const weekMin = d.week.reduce((a, w) => a + w.minutes, 0); const weekEx = d.week.reduce((a, w) => a + w.explanations, 0)
  return (
    <Page title={`Hi ${d.me.name.split(' ')[0]}`} sub={`${d.me.class}, ${d.me.school}`}>
      <div className="stack">
        {d.rules.exam_mode && <div className="note" style={{ borderLeft: '3px solid var(--red)' }}><b>{d.rules.exam_mode}</b> is on for your class. Explanations are short and exam focused until it ends.</div>}
        {c ? <Link to={'/student/read/' + c.id} className="continue"><Cover b={c} size="sm" /><div><div className="muted">Continue reading</div><h2>{c.title}</h2>
          <div className="bar-track" style={{ maxWidth: 360 }}><i style={{ width: c.progress + '%' }} /></div><div className="muted" style={{ fontSize: 13 }}>{c.progress}% read</div></div><span className="btn primary" style={{ marginLeft: 'auto' }}>Open</span></Link>
          : d.books.some(b => b.readable) && <div className="note">Pick a book below to start reading.</div>}
        <div className="row">
          <div className="metrics" style={{ gridTemplateColumns: 'repeat(3,1fr)', flex: 1.2 }}>
            <div className="metric"><div className="v">{d.streak}</div><div className="l">Day streak</div></div>
            <div className="metric"><div className="v">{weekMin}</div><div className="l">Minutes this week</div></div>
            <div className="metric"><div className="v">{weekEx}</div><div className="l">Words explained this week</div></div>
          </div>
          <div className="card" style={{ flex: 1 }}><div className="card-b"><div className="weekbars">{d.week.map(w => <div key={w.day} title={`${w.minutes} min`}><i style={{ height: (w.minutes / max * 70 + 2) + 'px' }} /><span>{new Date(w.day).toLocaleDateString('en-IN', { weekday: 'short' })}</span></div>)}</div></div></div>
        </div>
        <div><div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}><h3 style={{ margin: 0 }}>My books</h3>{d.store_on && <Link className="btn sm" style={{ marginLeft: 'auto' }} to="/student/store">Find more books</Link>}</div>
          <div className="tiles">{d.books.map(b => <BookTile key={b.id} b={b} />)}</div>
          {!d.books.length && <div className="card empty">No books yet. Your school assigns books to your class, or get one from the store.</div>}</div>
        {d.upcoming.length > 0 && <div><h3>Coming soon for your class</h3><div className="tiles">{d.upcoming.map(b => <BookTile key={b.id} b={b} action={<span className="tag" style={{ marginTop: 8 }}>Coming soon</span>} />)}</div></div>}
      </div>
    </Page>
  )
}

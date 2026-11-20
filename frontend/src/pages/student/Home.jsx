import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api'
import { useLoad, Page, Ring, Icon, Sheet, Field, useToast, plural } from '../../ui'
import { BookTile, Cover } from './common'

const greet = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening' }
const daysTo = d => d ? Math.ceil((new Date(d + 'T00:00:00') - new Date(new Date().toDateString())) / 86400000) : null

// A test left running on this device, so Home can offer to resume it.
function openTest() {
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i)
    if (k?.startsWith('ev_test_')) { try { const t = JSON.parse(localStorage.getItem(k)); if (t && !t.done) return t } catch { /* ignore */ } }
  }
  return null
}

function GoalSheet({ d, onClose, onSaved }) {
  const [goal, setGoal] = useState(d.goal_minutes); const [date, setDate] = useState(d.exam_date); const [err, setErr] = useState('')
  async function save() {
    try { await api('/api/student/profile', { method: 'PUT', body: { goal_minutes: +goal, exam_date: date || '' } }); onSaved() } catch (e) { setErr(e.message) }
  }
  return <Sheet title="Your daily goal" onClose={onClose} footer={<button className="btn primary lg block" onClick={save}>Save</button>}>
    {err && <div className="err">{err}</div>}
    <Field label="Minutes of study a day"><div className="chips">{[10, 20, 30, 45, 60, 90].map(m => <button key={m} type="button" className={'chip' + (+goal === m ? ' on' : '')} onClick={() => setGoal(m)}>{m} min</button>)}</div></Field>
    <Field label="Exam date (optional)" hint="Home shows a countdown"><input className="input" type="date" value={date} onChange={e => setDate(e.target.value)} /></Field>
  </Sheet>
}

export default function Home() {
  const { data: d, reload } = useLoad('/api/student/home'); const toast = useToast()
  const [goalOpen, setGoalOpen] = useState(false)
  if (!d) return <Page title="Home"><div className="empty">Loading</div></Page>
  const first = d.me.name.split(' ')[0]
  const left = daysTo(d.exam_date)
  const running = openTest()
  const c = d.continue, x = d.last_exam
  const weekMin = d.week.reduce((a, w) => a + w.minutes, 0); const max = Math.max(10, ...d.week.map(w => w.minutes))
  return (
    <div className="page">
      <div className="hello">
        <div><h1>{greet()}, {first}</h1><div className="muted">{[d.me.class, d.me.school || d.me.board || d.me.profile?.exam].filter(Boolean).join(' · ') || 'Welcome to EduVerse'}</div></div>
        {left != null && left >= 0 ? <button type="button" className="countdown" onClick={() => setGoalOpen(true)}><Icon n="clock" s={16} /><b>{left}</b> {left === 1 ? 'day' : 'days'} to your exam</button>
          : <button type="button" className="countdown" onClick={() => setGoalOpen(true)}><Icon n="clock" s={16} />Set your exam date</button>}
      </div>
      <div className="stack">
        {d.rules.exam_mode && <div className="note" style={{ borderLeft: '3px solid var(--red)' }}><b>{d.rules.exam_mode}</b> is on for your class. Explanations are short and exam focused until it ends.</div>}

        {running ? <Link className="hero" to={`/student/exam/${running.bid}?tab=tests`}><div className="hero-body"><div className="k">Test in progress</div><h2>{running.title}</h2>
            <div className="muted">{Object.keys(running.answers || {}).length} of {running.questions.length} answered. Your answers are saved on this device.</div></div>
            <span className="btn primary lg inline"><Icon n="play" s={16} />Resume test</span></Link>
          : c ? <Link className="hero" to={'/student/read/' + c.id}><Cover b={c} size="sm" /><div className="hero-body"><div className="k">Continue reading</div><h2>{c.title}</h2>
            <div className="bar-track" style={{ maxWidth: 360 }}><i style={{ width: c.progress + '%' }} /></div><div className="muted" style={{ fontSize: 13, marginTop: 6 }}>{c.progress}% read</div></div>
            <span className="btn primary lg inline">Continue</span></Link>
          : x ? <Link className="hero" to={`/student/exam/${x.id}?tab=practice`}><div className="hero-body"><div className="k">Keep practising</div><h2>{x.title}</h2>
            <div className="muted">{x.practised ? `${plural(x.practised, 'question')} practised so far. Pick up where you left off.` : 'Start with a few questions. Every answer shows you the solution.'}</div></div>
            <span className="btn primary lg inline">{x.practised ? 'Continue' : 'Start practising'}</span></Link>
          : <Link className="hero" to={d.store_on ? '/student/store' : '/student/books'}><div className="hero-body"><div className="k">Start here</div><h2>Find your textbooks and exam packs</h2>
            <div className="muted">Pick your board and class, or the exam you are preparing for.</div></div><span className="btn primary lg inline">Browse</span></Link>}

        <div className="today">
          <div><Ring value={d.today_minutes} max={d.goal_minutes} size={56} stroke={6}><span style={{ fontSize: 12 }}>{Math.min(100, Math.round(d.today_minutes / d.goal_minutes * 100))}%</span></Ring>
            <div><div className="v">{d.today_minutes} <span style={{ fontSize: 14, color: 'var(--ink-3)' }}>of {d.goal_minutes} min</span></div><div className="l">Today's goal · <button type="button" className="linkbtn" onClick={() => setGoalOpen(true)}>Change</button></div></div></div>
          <div><span className="ic"><Icon n="fire" /></span><div><div className="v">{d.streak ? plural(d.streak, 'day') : 'Start today'}</div><div className="l">{d.streak ? 'Study streak. Keep it going.' : 'Study a little every day to build a streak'}</div></div></div>
          <div><span className="ic"><Icon n="check" /></span><div><div className="v">{d.today_questions}</div><div className="l">Questions practised today</div></div></div>
        </div>

        {d.practice.length > 0 && <div><div className="section-h"><h3>Practise next</h3><span className="muted" style={{ fontSize: 13 }}>Chapters where you are losing marks</span></div>
          <div className="suggest">{d.practice.map(s => <Link key={s.book_id + s.chapter} to={`/student/exam/${s.book_id}?tab=practice&chapter=${encodeURIComponent(s.chapter)}`}>
            <b>{s.chapter}</b><span className="muted" style={{ fontSize: 12.5 }}>{s.pack}</span><span className="pct">{s.accuracy}% right in {plural(s.tried, 'try', 'tries')}</span></Link>)}</div></div>}

        {weekMin > 0 && <div className="card"><div className="card-h"><h3>This week</h3><span className="sub">{weekMin} minutes</span></div><div className="card-b"><div className="weekbars">{d.week.map(w => <div key={w.day} title={`${w.minutes} min`}><i style={{ height: (w.minutes / max * 70 + 2) + 'px' }} /><span>{new Date(w.day).toLocaleDateString('en-IN', { weekday: 'short' })}</span></div>)}</div></div></div>}

        <div><div className="section-h"><h3>My books and exam packs</h3>{d.store_on && <Link className="btn sm" to="/student/store">Browse the store</Link>}</div>
          <div className="tiles">{d.books.map(b => <BookTile key={b.id} b={b} />)}</div>
          {!d.books.length && <div className="card empty">{d.me.individual ? 'Nothing yet. Pick your textbooks or an exam pack from the store.' : 'No books yet. Your school or college assigns books to your class, or get one from the store.'}</div>}</div>
        {d.upcoming.length > 0 && <div><div className="section-h"><h3>Coming soon for your class</h3></div><div className="tiles">{d.upcoming.map(b => <BookTile key={b.id} b={b} action={<span className="tag" style={{ marginTop: 8 }}>Coming soon</span>} />)}</div></div>}
      </div>
      {goalOpen && <GoalSheet d={d} onClose={() => setGoalOpen(false)} onSaved={() => { setGoalOpen(false); toast('Saved'); reload() }} />}
    </div>
  )
}

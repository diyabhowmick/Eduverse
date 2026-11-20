import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api, auth } from '../api'
import { useLoad, useNarrow } from '../ui'
import LoginStory, { LoginCopy, Brandmark } from '../LoginStory'

// Individual learners (B2C) create their own account. What they pick here opens the store on their shelf.
export default function Signup() {
  const { data: tx } = useLoad('/api/taxonomy')
  const [v, setV] = useState({ name: '', email: '', phone: '', password: '', track: 'textbook', level: 'school', board: '', grade: '', exam: '', university: '', course: '' })
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false); const nav = useNavigate(); const narrow = useNarrow(900)
  const set = k => e => setV(x => ({ ...x, [k]: e.target.value }))
  const levels = v.track === 'exam' ? ['school', 'degree', 'competitive'] : ['school', 'degree']
  async function submit(e) {
    e.preventDefault(); setErr(''); setBusy(true)
    try { const r = await api('/api/auth/signup', { method: 'POST', body: v }); auth.set(r.token, r.user); nav('/student/store') }
    catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  if (tx && !tx.public_signup) return <div className="login"><section className="login-form"><div><h1>Sign up is closed</h1><p className="muted">Ask your school or college for an account.</p><Link to="/login/student">Back to sign in</Link></div></section></div>
  const sel = (k, opts, ph) => <select className="input" value={v[k]} onChange={set(k)} required><option value="">{ph}</option>{opts.map(o => Array.isArray(o) ? <option key={o[0]} value={o[0]}>{o[1]}</option> : <option key={o}>{o}</option>)}</select>
  return (
    <div className="login">
      <section className="login-art">
        <Brandmark />
        {!narrow && <LoginStory portal="student" />}
        <LoginCopy eyebrow="For students" head={<>Your syllabus. <em>Your exam</em>.</>} sub="Textbooks for CBSE, ICSE and every state board. Past papers, quick recaps and mock tests for board exams, degree exams, JEE and NEET." />
      </section>
      <section className="login-form">
        {narrow && <div className="login-strip"><Brandmark small /><LoginStory portal="student" compact /></div>}
        <form onSubmit={submit}>
          <span className="portal"><i />Create your account</span>
          <h1>Sign up</h1>
          {err && <div className="err" role="alert">{err}</div>}
          <div className="field"><label>Full name</label><input className="input" value={v.name} onChange={set('name')} required /></div>
          <div className="field"><label>Email</label><input className="input" type="email" autoComplete="username" value={v.email} onChange={set('email')} required /></div>
          <div className="field"><label>Phone (optional)</label><input className="input" value={v.phone} onChange={set('phone')} /></div>
          <div className="field"><label>Password</label><input className="input" type="password" autoComplete="new-password" minLength={8} value={v.password} onChange={set('password')} required /></div>
          <div className="field"><label>I want to</label><div className="seg">
            <button type="button" className={v.track === 'textbook' ? 'on' : ''} onClick={() => setV(x => ({ ...x, track: 'textbook', level: x.level === 'competitive' ? 'school' : x.level }))}>Study my textbooks</button>
            <button type="button" className={v.track === 'exam' ? 'on' : ''} onClick={() => setV(x => ({ ...x, track: 'exam' }))}>Prepare for an exam</button></div></div>
          <div className="field"><label>Level</label>{sel('level', levels.map(l => [l, tx?.levels[l] || l]), 'Pick one')}</div>
          {v.level === 'school' && <div className="grid2">
            <div className="field"><label>Board</label>{sel('board', tx?.boards || [], 'Pick your board')}</div>
            <div className="field"><label>Class</label>{sel('grade', (tx?.grades || []).map(g => [g, 'Class ' + g]), 'Pick')}</div></div>}
          {v.level === 'degree' && <div className="grid2">
            <div className="field"><label>University</label><input className="input" value={v.university} onChange={set('university')} /></div>
            <div className="field"><label>Course</label><input className="input" placeholder="B.Sc Physics" value={v.course} onChange={set('course')} /></div></div>}
          {v.track === 'exam' && <div className="field"><label>Exam</label>{sel('exam', tx?.exams[v.level] || [], 'Pick your exam')}</div>}
          <button className="btn primary" disabled={busy} style={{ justifyContent: 'center', padding: '11px' }}>{busy ? 'Creating account' : 'Create account'}</button>
          <span style={{ fontSize: 14 }}>Already have an account? <Link to="/login/student" style={{ color: 'var(--red)', fontWeight: 650 }}>Sign in</Link></span>
        </form>
      </section>
    </div>
  )
}

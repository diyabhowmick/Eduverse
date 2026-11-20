import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api, auth } from '../api'
import { useNarrow } from '../ui'
import LoginStory, { LoginCopy, Brandmark, Tour } from '../LoginStory'

const PORTALS = {
  super_admin: { eyebrow: 'Platform admin', label: 'Super Admin login', home: '/sa', head: <>Run the whole platform from <em>one place</em>.</>, sub: 'Schools, pricing, books and the AI behind every explanation.' },
  student: { eyebrow: 'For students', label: 'Student login', home: '/student', head: <>Learn the book. <em>Crack the exam</em>.</>, sub: 'Digital textbooks for every board, and past papers, quick recaps and mock tests for board, degree and competitive exams.' },
  teacher: { eyebrow: 'For teachers', label: 'Teacher login', home: '/teacher', head: <>See how <em>your class</em> is reading.</>, sub: 'Your classes, who is keeping up, and who has quietly fallen behind.' },
  reviewer: { eyebrow: 'For reviewers', label: 'Reviewer login', home: '/review', head: <>Nothing reaches a student <em>until you approve it</em>.</>, sub: 'Check every converted page against the original, fix what is wrong, then publish.' },
  admin: { eyebrow: 'For schools and colleges', label: 'Organisation Admin login', home: '/admin', head: <>Your students' books and exam packs, <em>in order</em>.</>, sub: 'For schools, colleges and coaching centres. Add students, set up classes, assign books and follow progress.' },
}

export default function Login({ portal }) {
  const P = PORTALS[portal]
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('')
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  const nav = useNavigate(); const narrow = useNarrow(900); const [tour, setTour] = useState(false)
  const story = portal === 'super_admin' ? 'student' : portal
  async function submit(e) {
    e.preventDefault(); setErr(''); setBusy(true)
    try { const r = await api('/api/auth/login', { method: 'POST', body: { email, password, portal } }); auth.set(r.token, r.user); nav(P.home) }
    catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  return (
    <div className="login">
      <section className="login-art">
        <Brandmark />
        {!narrow && <LoginStory portal={story} />}
        <LoginCopy eyebrow={P.eyebrow} head={P.head} sub={P.sub} />
      </section>
      <section className="login-form">
        {narrow && <div className="login-strip"><Brandmark small /><LoginStory portal={story} compact /></div>}
        <form onSubmit={submit}>
          <span className="portal"><i />{P.label}</span>
          <h1>Sign in</h1>
          {err && <div className="err" role="alert">{err}</div>}
          <div className="field"><label htmlFor="em">Email</label><input id="em" className="input" type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required /></div>
          <div className="field"><label htmlFor="pw">Password</label><input id="pw" className="input" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></div>
          <button className="btn primary" disabled={busy} style={{ justifyContent: 'center', padding: '11px' }}>{busy ? 'Signing in' : 'Sign in'}</button>
          {portal === 'student' && <span style={{ fontSize: 14 }}>New here? <Link to="/signup" style={{ color: 'var(--red)', fontWeight: 650 }}>Create a free account</Link>
            {' '}or <button type="button" className="linkbtn" style={{ fontSize: 14 }} onClick={() => setTour(true)}>see how EduVerse works</button></span>}
          <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>{portal === 'student' ? 'Forgot your password? If your school or college gave you this account, ask them to reset it. Otherwise contact EduVerse support.' : portal !== 'super_admin' ? 'Forgot your password? Ask EduVerse support to reset it.' : 'School admins, reviewers and students sign in on their own login page.'}</span>
        </form>
      </section>
      {tour && <Tour onClose={() => setTour(false)} />}
    </div>
  )
}

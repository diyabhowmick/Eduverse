import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, auth } from '../api'

const PORTALS = {
  super_admin: { label: 'Super Admin login', home: '/sa', head: <>Run the whole platform from <em>one place</em>.</>, sub: 'Schools, pricing, books and the AI behind every explanation.' },
  student: { label: 'Student login', home: '/student', head: <>Tap any word. <em>Get it explained</em>.</>, sub: 'Your textbooks, with every important idea explained at the depth you need.' },
  teacher: { label: 'Teacher login', home: '/teacher', head: <>See how <em>your class</em> is reading.</>, sub: 'Your classes, who is keeping up, and who has quietly fallen behind.' },
  reviewer: { label: 'Reviewer login', home: '/review', head: <>Nothing reaches a student <em>until you approve it</em>.</>, sub: 'Check every page M1 extracted against the original, fix what is wrong, then publish.' },
  admin: { label: 'School Admin login', home: '/admin', head: <>Your school's digital textbooks, <em>in order</em>.</>, sub: 'Add students, set up classes, assign books and follow how every class is reading.' },
  platform_admin: { label: 'Platform Admin login', home: '/pa', head: <>Run the <em>book factory</em>.</>, sub: 'Books in, books out. Processing, reviewers, the keys and what they spend. No school prices here.' },
}

export default function Login({ portal }) {
  const P = PORTALS[portal]
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('')
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  const nav = useNavigate()
  async function submit(e) {
    e.preventDefault(); setErr(''); setBusy(true)
    try { const r = await api('/api/auth/login', { method: 'POST', body: { email, password, portal } }); auth.set(r.token, r.user); nav(P.home) }
    catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  return (
    <div className="login">
      <section className="login-art">
        <img className="login-logo" src="/brand/zprox_logo_dark.png" alt="zPROx.AI" />
        <div><div style={{ color: '#B9B9B9', fontSize: 15, marginBottom: 14 }}>EduVerse</div><h2>{P.head}</h2><p>{P.sub}</p></div>
        <div style={{ fontSize: 13, color: '#B9B9B9' }}>Automate everything effortlessly</div>
        <svg className="pages" width="420" height="420" viewBox="0 0 200 200" fill="none" stroke="#E0212F" strokeWidth="3"><path d="M20 40h70a20 20 0 0 1 20 20v120a15 15 0 0 0-15-15H20zM180 40h-70a20 20 0 0 0-20 20v120a15 15 0 0 1 15-15h75z" /><path d="M35 70h40M35 90h40M35 110h30M125 70h40M125 90h40M125 110h30" /></svg>
      </section>
      <section className="login-form">
        <form onSubmit={submit}>
          <span className="portal"><i />{P.label}</span>
          <h1>Sign in</h1>
          {err && <div className="err" role="alert">{err}</div>}
          <div className="field"><label htmlFor="em">Email</label><input id="em" className="input" type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required /></div>
          <div className="field"><label htmlFor="pw">Password</label><input id="pw" className="input" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></div>
          <button className="btn primary" disabled={busy} style={{ justifyContent: 'center', padding: '11px' }}>{busy ? 'Signing in' : 'Sign in'}</button>
          <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>{portal === 'student' ? 'Forgot your password? Ask your school office to reset it.' : portal !== 'super_admin' ? 'Forgot your password? Ask EduVerse support to reset it.' : 'Platform admins, school admins, reviewers, teachers and students each sign in on their own login page.'}</span>
        </form>
      </section>
    </div>
  )
}

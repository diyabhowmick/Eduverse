import { lazy, Suspense, useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api, auth } from '../api'
import { useNarrow } from '../ui'
import { Brandmark } from '../Brandmark'
import { shouldPlayIntro, markIntroSeen, slowNet } from '../introGate'
// The art loads after the form, so on a slow network the student can sign in straight away.
const LoginStory = lazy(() => import('../LoginStory'))
const Tour = lazy(() => import('../LoginStory').then(m => ({ default: m.Tour })))
const Intro = lazy(() => import('../Intro'))
const HERO_DUR = 12
import FoldLogo from '../FoldLogo'
import Eddie from '../Eddie'
import Launch from '../Launch'
import SoundToggle from '../SoundToggle'
import { eddie } from '../eddieBus'
import { play, buzz } from '../sound'
import '../login-premium.css'

const PORTALS = {
  super_admin: { eyebrow: 'Platform admin', label: 'Super Admin login', home: '/sa', head: <>Run the whole platform from <em>one place</em>.</>, sub: 'Schools, pricing, books and the AI behind every explanation.' },
  student: { eyebrow: 'For students', label: 'Student login', home: '/student', head: <>Learn the book. <em>Crack the exam</em>.</>, sub: 'Digital textbooks for every board, and past papers, quick recaps and mock tests for board, degree and competitive exams.' },
  teacher: { eyebrow: 'For teachers', label: 'Teacher login', home: '/teacher', head: <>See how <em>your class</em> is reading.</>, sub: 'Your classes, who is keeping up, and who has quietly fallen behind.' },
  reviewer: { eyebrow: 'For reviewers', label: 'Reviewer login', home: '/review', head: <>Nothing reaches a student <em>until you approve it</em>.</>, sub: 'Check every converted page against the original, fix what is wrong, then publish.' },
  admin: { eyebrow: 'For schools and colleges', label: 'Organisation Admin login', home: '/admin', head: <>Your students' books and exam packs, <em>in order</em>.</>, sub: 'For schools, colleges and coaching centres. Add students, set up classes, assign books and follow progress.' },
}

// Hero logo size: fills the art panel on desktop, sized to the strip on phones, never crowds the copy
function heroSize() {
  const w = innerWidth, h = innerHeight
  if (w <= 900) return Math.round(Math.min(w - 140, 240))
  const art = w * 1.1 / 2.1 - 96
  return Math.round(Math.max(250, Math.min(art, 430, (h - 470) * 1.574)))
}

const dayPart = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening' }
const MAIL = <svg className="in-ic" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="3" /><path d="M4 7l8 6 8-6" /></svg>
const LOCK = <svg className="in-ic" viewBox="0 0 24 24" aria-hidden="true"><rect x="4.5" y="10.5" width="15" height="10" rx="2.5" /><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" /></svg>

const lastKey = p => 'ev_last_' + p
// Remembered on this device only, so a returning student is greeted by name and their email is filled in.
export const rememberLogin = (portal, user) => { try { localStorage.setItem(lastKey(portal), JSON.stringify({ name: (user.name || '').split(' ')[0], nick: user.nickname || '', email: user.email })) } catch { /* private mode */ } }
const lastLogin = p => { try { return JSON.parse(localStorage.getItem(lastKey(p)) || 'null') } catch { return null } }

export default function Login({ portal }) {
  const onBurst = () => eddie.emit('burst')
  const [last, setLast] = useState(() => lastLogin(portal))
  const P = PORTALS[portal]
  const [email, setEmail] = useState(() => lastLogin(portal)?.email || ''); const [password, setPassword] = useState('')
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  const nav = useNavigate(); const narrow = useNarrow(900); const [tour, setTour] = useState(false)
  const [intro, setIntro] = useState(shouldPlayIntro); const [shown, setShown] = useState(!intro)
  const [showPw, setShowPw] = useState(false)
  const [caps, setCaps] = useState(false)
  const story = portal === 'super_admin' ? 'student' : portal
  const [heroOff] = useState(() => (intro ? HERO_DUR * .64 : 0)); const [heroCls] = useState(() => (intro ? 'fold-in' : ''))
  const [played] = useState(intro)
  const [heroW, setHeroW] = useState(heroSize)
  useEffect(() => { const r = () => setHeroW(heroSize()); addEventListener('resize', r); return () => removeEventListener('resize', r) }, [])
  const [launch, setLaunch] = useState(null)
  // Eddie follows what you type, hides his eyes for the password
  function caret(el) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el)
    const c = caret.c || (caret.c = document.createElement('canvas').getContext('2d')); c.font = cs.font
    const w = c.measureText(el.value || '').width
    eddie.emit('focus', { x: r.left + parseFloat(cs.paddingLeft) + Math.min(w, r.width - 24), y: r.top + r.height / 2 })
  }
  useEffect(() => { eddie.emit('pw', { focus: document.activeElement?.id === 'pw', show: showPw }) }, [showPw])
  // Hand over to the app under a dark veil that lifts once the next page is up
  function enter(home) {
    const v = document.createElement('div'); v.className = 'launch-veil'; document.body.appendChild(v)
    nav(home)
    requestAnimationFrame(() => requestAnimationFrame(() => {
      v.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 650, easing: 'cubic-bezier(.4,0,.2,1)', fill: 'forwards' })
      setTimeout(() => v.remove(), 700)
    }))
  }
  function launchIn(home) {
    if (scrollY > 8) { scrollTo({ top: 0, behavior: 'smooth' }); setTimeout(() => launchIn(home), 480); return }
    const slot = [...document.querySelectorAll('.fold-slot')].find(el => el.offsetParent !== null)
    if (!slot || matchMedia('(prefers-reduced-motion: reduce)').matches) { nav(home); return }
    const rect = slot.getBoundingClientRect()
    setLaunch({ rect, phase: 'in', home })
    setTimeout(() => document.querySelector('.launch .fold')?.classList.add('lid-pop'), 700)
    setTimeout(() => play('pop', .7), 760)
    let fired = false
    const zoom = () => { if (fired) return; fired = true; setLaunch(l => l && { ...l, phase: 'zoom' }) }
    eddie.emit('launch', { done: zoom }); setTimeout(zoom, 1800)
  }
  async function submit(e) {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      const r = await api('/api/auth/login', { method: 'POST', body: { email, password, portal } }); auth.set(r.token, r.user); rememberLogin(portal, r.user)
      eddie.emit('mood', { type: 'happy' }); play('chime'); buzz(20)
      setTimeout(() => launchIn(P.home), 450)
    }
    catch (x) { setErr(x.message); setBusy(false); eddie.emit('mood', { type: 'sad' }); play('error'); buzz([30, 40, 30]) }
  }
  return (
    <div className={'login lux ' + (shown ? 'is-in' : 'is-pre') + (launch ? ' is-launching' : '')}>
      <section className="login-art"><div className="stars" aria-hidden="true"><i /><i /><i /></div>
        <Brandmark />
        {!narrow && <div className="fold-slot" style={{ width: heroW, height: heroW / 1.574 }}><FoldLogo width={heroW} dur={HERO_DUR} offset={heroOff} tilt theme={portal} hold={!shown} onBurst={onBurst} className={shown ? heroCls : 'fold-wait'} /></div>}
        {!narrow && <Suspense fallback={null}><LoginStory portal={story} /></Suspense>}
      </section>
      <section className="login-form">
        {narrow && <div className="login-strip"><div className="fold-slot" style={{ width: heroW, height: heroW / 1.574 }}><FoldLogo width={heroW} dur={HERO_DUR} offset={heroOff} theme={portal} hold={!shown} onBurst={onBurst} className={shown ? heroCls : 'fold-wait'} /></div><Suspense fallback={null}><LoginStory portal={story} compact /></Suspense></div>}
        <form onSubmit={submit}>
          {shown && <Eddie perch portal={portal} returning={last ? (last.nick || last.name) : ''} entrance={played} delay={intro ? 1350 : 700} onTour={portal === 'student' ? () => setTour(true) : null} />}
          <span className="portal"><i />{P.label}</span>
          <div className="lux-head"><h1>{last ? `Welcome back, ${last.nick || last.name}` : 'Sign in'}</h1><p>{last ? <>{dayPart()}. Not you? <button type="button" className="linkbtn" onClick={() => { try { localStorage.removeItem(lastKey(portal)) } catch { /* ok */ } setLast(null); setEmail('') }}>Use another account</button></> : `${dayPart()}, welcome back to EduVerse.`}</p></div>
          {err && <div className="err" role="alert">{err}</div>}
          <div className="field"><label htmlFor="em">Email</label><div className="in-wrap">{MAIL}<input id="em" className="input" type="email" autoComplete="username" value={email} onChange={e => { setEmail(e.target.value); caret(e.target) }} onFocus={e => caret(e.target)} onBlur={() => eddie.emit('focus', null)} required /></div></div>
          <div className="field"><label htmlFor="pw">Password</label>
            <div className="pw-wrap in-wrap">{LOCK}<input id="pw" className="input" type={showPw ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} onKeyUp={e => setCaps(e.getModifierState?.('CapsLock'))} onFocus={() => eddie.emit('pw', { focus: true, show: showPw })} onBlur={e => { if (!e.relatedTarget?.classList.contains('pw-eye')) eddie.emit('pw', { focus: false, show: showPw }) }} required />
              <button type="button" className="pw-eye" onMouseDown={e => e.preventDefault()} onClick={() => setShowPw(v => !v)} aria-label={showPw ? 'Hide password' : 'Show password'} aria-pressed={showPw}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" />{showPw && <path d="M4 4l16 16" />}</svg>
              </button></div>
            {caps && <span className="caps-warn" role="status">Caps Lock is on</span>}</div>
          <button className={'btn primary lux-cta' + (busy ? ' busy' : '')} disabled={busy}>{busy ? <><i className="spin" />Signing in</> : <>Sign in<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" /></svg></>}</button>
          {portal === 'student' && <span style={{ fontSize: 14 }}>New here? <Link to="/signup" style={{ color: 'var(--red)', fontWeight: 650 }}>Create a free account</Link>
            {' '}or <button type="button" className="linkbtn" style={{ fontSize: 14 }} onClick={() => setTour(true)}>see how EduVerse works</button></span>}
          <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>{portal === 'student' ? 'Forgot your password? If your school or college gave you this account, ask them to reset it. Otherwise contact EduVerse support.' : portal !== 'super_admin' ? 'Forgot your password? Ask EduVerse support to reset it.' : 'School admins, reviewers and students sign in on their own login page.'}</span>
        </form>
      </section>
      {tour && <Suspense fallback={null}><Tour onClose={() => setTour(false)} /></Suspense>}
      <SoundToggle />
      {launch && <Launch rect={launch.rect} phase={launch.phase} portal={portal} onDone={() => enter(launch.home)} />}
      {intro && <Suspense fallback={null}><Intro theme={portal} onReveal={() => { setShown(true); markIntroSeen() }} onDone={() => { setIntro(false); markIntroSeen() }} /></Suspense>}
      {!intro && !played && !slowNet() && <button type="button" className="replay-intro" onClick={() => { location.search = '?intro' }}>Replay intro</button>}
    </div>
  )
}

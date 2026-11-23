import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import './eddie.css'
import { eddie } from './eddieBus'
import { play, buzz } from './sound'
import { speak, hush, mayTalkNow, canTalk, playClip } from './voice'

// Eddie, the EduVerse helper bot. To use the final artwork, set EDDIE_IMG to its path
// (e.g. '/brand/eddie.png', transparent PNG or SVG) and the drawn Eddie below is replaced.
const EDDIE_IMG = null

const FORGOT = {
  student: 'If your school or college gave you this account, ask them to reset your password. Otherwise contact EduVerse support and we will help you back in.',
  super_admin: 'Super Admin passwords are reset by EduVerse support only.',
}
const NEW = {
  student: 'new',
  teacher: 'Teacher accounts are created by your school. Ask your school admin for an invite.',
  reviewer: 'Reviewer accounts are created by the EduVerse team. Ask your coordinator for access.',
  admin: 'Organisation accounts are set up by EduVerse. Contact EduVerse support to get your school or college started.',
  super_admin: 'School admins, reviewers, teachers and students each sign in on their own login page.',
}

const EYES = {
  idle: 'M33 42q5-6 10 0M57 42q5-6 10 0',
  happy: 'M32 43q6-9 12 0M56 43q6-9 12 0',
  sad: 'M33 40q5 4 10 2M57 42q5 2 10-2',
  look: 'M35 40.5h6M59 40.5h6',
}

// Who Eddie is on each login page, and what he says when he lands.
const ROLE = { student: 'your EduVerse guide', teacher: 'your EduVerse guide', reviewer: 'mission control', admin: 'your EduVerse guide', super_admin: 'your co-pilot' }
const HELLO = {
  student: "Hey, I'm Eddie! ... Welcome to EduVerse. Education's Universe. ... I'll be your guide on this space tour of learning. Sign in, and let's blast off!",
  teacher: "Hello, I'm Eddie! ... Welcome to EduVerse. Education's Universe. ... I'll guide you through your class's journey. Sign in, and let's take a look.",
  reviewer: "Hi, I'm Eddie! ... Welcome back to mission control. Sign in, and let's get these pages ready for launch.",
  admin: "Hello, I'm Eddie! ... Welcome to EduVerse. Education's Universe. ... Sign in, and I'll help you keep your school on course.",
  super_admin: "Welcome back, captain! I'm Eddie. All of EduVerse is ready for you. Sign in to take the controls.",
}
// What the bubble shows while he says the longer line above (kept short so it fits beside him).
const SHOW = {
  student: "Hey, I'm Eddie! Welcome to EduVerse, Education's Universe. Ready for your space tour of learning?",
  teacher: "Hello, I'm Eddie! Welcome to EduVerse, Education's Universe. Let's look at your class's journey.",
  reviewer: "Hi, I'm Eddie! Welcome back to mission control. Let's get these pages ready for launch.",
  admin: "Hello, I'm Eddie! Welcome to EduVerse, Education's Universe. Let's keep your school on course.",
  super_admin: "Welcome back, captain! I'm Eddie. All of EduVerse is ready for you.",
}
const GREET = {
  student: 'Need a hand signing in?', teacher: 'Ready to check on your class?', reviewer: 'Pages waiting for your review?',
  admin: 'Need help getting into your school?', super_admin: 'Welcome back, captain.',
}
// Ask Eddie: answers come only from what EduVerse already says on these pages. Unknown -> support.
const SUPPORT = 'I am not sure about that one yet. EduVerse support can help you with it.'
const FAQ = [
  { k: ['forgot', 'reset', 'password', 'locked', 'cant login', "can't login", 'cannot login'], a: p => FORGOT[p] || 'Ask EduVerse support to reset your password.' },
  { k: ['new', 'sign up', 'signup', 'register', 'create', 'account', 'join'], a: p => NEW[p] === 'new' ? 'NEW' : NEW[p] },
  { k: ['school', 'college', 'invite', 'class code', 'coaching'], a: p => p === 'student' ? 'If your school or college uses EduVerse, they add you and give you your login. You can also create a free account yourself.' : NEW[p] || SUPPORT },
  { k: ['what is', 'eduverse', 'about', 'how does', 'how it works'], a: () => 'EduVerse turns your textbook into a digital book. Tap any word for an explanation at your level, then practise, test yourself and track your progress.' },
  { k: ['exam', 'paper', 'mock', 'test', 'recap', 'competitive', 'board exam'], a: () => 'Exam packs bring past papers, quick recaps and mock tests for board, degree and competitive exams.' },
  { k: ['board', 'cbse', 'icse', 'state board', 'syllabus', 'textbook', 'book'], a: () => 'EduVerse has digital textbooks for every board. Once you sign in, your books are under My books.' },
  { k: ['explain', 'meaning', 'ai', 'word'], a: () => 'Inside a book, tap any word or line and EduVerse explains it simply. Not clear yet? Go one level deeper.' },
  { k: ['teacher', 'class', 'students progress', 'behind'], a: p => p === 'teacher' ? 'After you sign in you will see your classes, who is keeping up and who has fallen behind.' : 'Teachers sign in on the teacher login page. Their school creates their account.' },
  { k: ['review', 'approve', 'publish', 'reviewer'], a: () => 'Reviewers check every converted page against the original, fix what is wrong and then publish. Nothing reaches a student until it is approved.' },
  { k: ['support', 'help', 'contact', 'human', 'call'], a: () => 'EduVerse support can help with anything about your account. If your school gave you this login, your school admin can help too.' },
  { k: ['hi', 'hello', 'hey', 'who are you', 'eddie'], a: () => "Hi! I'm Eddie, the EduVerse helper. Ask me about signing in, your account or how EduVerse works." },
]
function answerFor(q, portal) {
  const t = ' ' + q.toLowerCase().replace(/[^a-z0-9' ]/g, ' ') + ' '
  let best = null, score = 0
  for (const f of FAQ) { const sc = f.k.reduce((n, k) => n + (t.includes(k.length < 4 ? ' ' + k + ' ' : k) ? k.length : 0), 0); if (sc > score) { score = sc; best = f } }
  return best ? best.a(portal) : SUPPORT
}

export function EddieBot({ size = 76, look = { x: 0, y: 0 }, waving, flying, jet = true, mood = '', talking, baby }) {
  const u = useId().replace(/:/g, '')
  if (EDDIE_IMG) return <img src={EDDIE_IMG} alt="" width={size} height={size} style={{ objectFit: 'contain' }} />
  const ex = look.x * 3.2, ey = look.y * 2.4, U = id => `url(#${u}${id})`
  return <svg className={'eddie-svg' + (baby ? ' baby' : '') + (waving ? ' waving' : '') + (flying ? ' flying' : '') + (mood ? ' mood-' + mood : '') + (talking ? ' talking' : '')} width={size} height={size * 1.12} viewBox="0 0 100 112" aria-hidden="true" style={{ overflow: 'visible' }}>
    <defs>
      <radialGradient id={u + 'shell'} cx="35%" cy="28%" r="80%"><stop offset="0" stopColor="#FF5A64" /><stop offset=".45" stopColor="#E0212F" /><stop offset="1" stopColor="#9C0E18" /></radialGradient>
      <radialGradient id={u + 'body'} cx="38%" cy="25%" r="85%"><stop offset="0" stopColor="#F23A46" /><stop offset=".6" stopColor="#D01A27" /><stop offset="1" stopColor="#8E0C15" /></radialGradient>
      <linearGradient id={u + 'visor'} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#2A2D35" /><stop offset=".55" stopColor="#0B0C10" /><stop offset="1" stopColor="#050608" /></linearGradient>
      <radialGradient id={u + 'bulb'}><stop offset="0" stopColor="#FFFFFF" /><stop offset=".5" stopColor="#FFC2C6" /><stop offset="1" stopColor="#FF4552" /></radialGradient>
      <linearGradient id={u + 'pack'} x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#3A3E48" /><stop offset=".45" stopColor="#5B606C" /><stop offset="1" stopColor="#22252C" /></linearGradient>
      <linearGradient id={u + 'flame'} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#FFFFFF" /><stop offset=".25" stopColor="#FFE7A3" /><stop offset=".6" stopColor="#FF8A3D" /><stop offset="1" stopColor="#E0212F" stopOpacity="0" /></linearGradient>
      <radialGradient id={u + 'thrust'}><stop offset="0" stopColor="#FFB36B" stopOpacity=".75" /><stop offset="1" stopColor="#E0212F" stopOpacity="0" /></radialGradient>
      <filter id={u + 'glow'} x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.6" /></filter>
    </defs>
    <ellipse className="ed-shadow" cx="50" cy="107" rx="24" ry="3.6" fill="#000" opacity=".28" />
    <g className="ed-float">
      {jet && <g className="ed-jet">
        <g className="ed-flames">
          <ellipse className="ed-thrust" cx="50" cy="110" rx="34" ry="18" fill={U('thrust')} />
          <path className="ed-flame l" d="M27.5 94q5 0 5 4.5l-5 24-5-24q0-4.5 5-4.5z" fill={U('flame')} />
          <path className="ed-flame r" d="M72.5 94q5 0 5 4.5l-5 24-5-24q0-4.5 5-4.5z" fill={U('flame')} />
        </g>
        <rect x="21" y="60" width="13" height="32" rx="6.5" fill={U('pack')} />
        <rect x="66" y="60" width="13" height="32" rx="6.5" fill={U('pack')} />
        <rect x="21" y="70" width="13" height="4" fill="#E0212F" /><rect x="66" y="70" width="13" height="4" fill="#E0212F" />
        <path d="M23.5 91h8l-1.2 4h-5.6zM68.5 91h8l-1.2 4h-5.6z" fill="#1A1C22" />
        <path d="M24 64q2-2.5 4-2.5M69 64q2-2.5 4-2.5" stroke="rgba(255,255,255,.35)" strokeWidth="1.4" strokeLinecap="round" fill="none" />
      </g>}
      <g className="ed-arm-l"><ellipse cx="22" cy="80" rx="7" ry="10" fill={U('body')} transform="rotate(20 22 80)" /></g>
      <g className="ed-arm-r"><ellipse cx="78" cy="80" rx="7" ry="10" fill={U('body')} transform="rotate(-20 78 80)" /></g>
      <path d="M28 74c0-9 10-14 22-14s22 5 22 14v12c0 9-9 15-22 15s-22-6-22-15z" fill={U('body')} />
      <path d="M33 72c3-5 9-7 14-7" stroke="rgba(255,255,255,.35)" strokeWidth="2.4" strokeLinecap="round" fill="none" />
      <g transform="translate(43.5 76) scale(.13)">
        <polygon points="50,4 92,28 50,52 8,28" fill="#fff" opacity=".95" />
        <polygon points="8,28 50,52 50,100 8,76" fill="#fff" opacity=".75" />
        <polygon points="50,52 92,28 92,76 50,100" fill="#fff" opacity=".55" />
      </g>
      <path d={baby ? 'M50 14V9' : 'M50 14V5'} stroke="#9C0E18" strokeWidth="3" strokeLinecap="round" />
      <circle className="ed-bulb-glow" cx="50" cy={baby ? 8 : 5} r="5" fill="#FF4552" filter={U('glow')} />
      <circle className="ed-bulb" cx="50" cy={baby ? 8 : 5} r={baby ? 4.2 : 3.4} fill={U('bulb')} />
      <rect x="14" y="13" width="72" height="54" rx="26" fill={U('shell')} />
      <path d="M24 24c6-6 14-8 22-8" stroke="rgba(255,255,255,.45)" strokeWidth="3" strokeLinecap="round" fill="none" />
      <rect x="21" y="22" width="58" height="36" rx="17" fill={U('visor')} />
      <path d="M27 30c4-4 10-5 16-5" stroke="rgba(255,255,255,.18)" strokeWidth="2.6" strokeLinecap="round" fill="none" />
      <g className="ed-eyes" transform={`translate(${ex} ${ey})`}>
        <g filter={U('glow')} opacity=".9"><path d={EYES[mood] || EYES.idle} stroke="#FF6A74" strokeWidth="4" strokeLinecap="round" fill="none" /></g>
        <path d={EYES[mood] || EYES.idle} stroke="#FFE3E5" strokeWidth="2.4" strokeLinecap="round" fill="none" />
      </g>
      <ellipse cx="50" cy="51" rx="3" ry="1.2" fill="#FF6A74" opacity=".5" className="ed-mouth" />
      {baby && <><ellipse cx="29" cy="50" rx="4.2" ry="2.6" fill="#FF7A8A" opacity=".55" /><ellipse cx="71" cy="50" rx="4.2" ry="2.6" fill="#FF7A8A" opacity=".55" /></>}
      <g className="ed-hand l"><ellipse cx="38" cy="43" rx="10" ry="8.5" fill={U('body')} /><path d="M31 39q4-3 9-2" stroke="rgba(255,255,255,.4)" strokeWidth="1.6" strokeLinecap="round" fill="none" /></g>
      <g className="ed-hand r"><ellipse cx="62" cy="43" rx="10" ry="8.5" fill={U('body')} /><path d="M55 39q4-3 9-2" stroke="rgba(255,255,255,.4)" strokeWidth="1.6" strokeLinecap="round" fill="none" /></g>
    </g>
  </svg>
}

// entrance: Eddie pops the lid of the folded logo cube, jumps out, lands and walks to his corner.
export default function Eddie({ portal, delay = 800, onTour, inline, entrance, perch, returning = '' }) {
  const size = perch ? (matchMedia('(max-width:900px)').matches ? 52 : 60) : inline ? 44 : 64
  const [open, setOpen] = useState(false), [peek, setPeek] = useState(false)
  const [answer, setAnswer] = useState(null)
  const [look, setLook] = useState({ x: 0, y: 0 })
  const [arrived, setArrived] = useState(!entrance)
  const [actor, setActor] = useState(null)
  const [mood, setMood] = useState(''), [pw, setPw] = useState({ focus: false, show: false })
  const [cheer, setCheer] = useState(false), [msg, setMsg] = useState('')
  const [launch, setLaunch] = useState(null), [gone, setGone] = useState(false)
  const [chat, setChat] = useState([]), [q, setQ] = useState(''), [typing, setTyping] = useState(false)
  const btn = useRef(null), actorEl = useRef(null), ringEl = useRef(null), focusPt = useRef(null), chatEnd = useRef(null)
  const arrivedRef = useRef(arrived); arrivedRef.current = arrived

  // Login form -> Eddie
  useEffect(() => {
    const look = pt => { const r = btn.current?.getBoundingClientRect(); if (!r) return
      const dx = pt.x - (r.left + r.width / 2), dy = pt.y - (r.top + r.height / 2), d = Math.hypot(dx, dy) || 1
      setLook({ x: +(dx / Math.max(d, 120)).toFixed(2), y: +(dy / Math.max(d, 120)).toFixed(2) }) }
    const offs = [
      eddie.on('focus', pt => { focusPt.current = pt; if (pt) look(pt) }),
      eddie.on('pw', v => setPw(v)),
      eddie.on('mood', ({ type }) => {
        setMood(type); clearTimeout(offs.t); offs.t = setTimeout(() => setMood(''), type === 'sad' ? 1600 : 2400)
        if (type === 'sad') {   // a failed sign-in: he says so kindly and offers help
          setPeek(true); setMsg("Hmm, that didn't work. Check your email and password, or tap me for help.")
          clearTimeout(offs.m); offs.m = setTimeout(() => setMsg(''), 7000)
          playClip('/voice/eddie_oops.mp3')
        }
        if (type === 'happy') { setMsg(''); playClip('/voice/eddie_yay.mp3') }
      }),
      // the box on the left just closed and things burst out: he watches, cheers and waves
      eddie.on('burst', () => {
        if (!arrivedRef.current || focusPt.current || !btn.current) return
        const slot = [...document.querySelectorAll('.fold-slot')].find(el => el.offsetParent !== null)
        if (slot) { const r = slot.getBoundingClientRect(); look({ x: r.left + r.width / 2, y: r.top + r.height * .35 }) }
        setCheer(true); clearTimeout(offs.c); offs.c = setTimeout(() => { setCheer(false); if (!focusPt.current) setLook({ x: 0, y: 0 }) }, 1900)
      }),
      eddie.on('launch', ({ done }) => {
        if (!arrivedRef.current || !btn.current) { done?.(); return }
        setOpen(false); setPeek(false)
        const slot = [...document.querySelectorAll('.fold-slot')].find(el => el.offsetParent !== null)
        if (!slot) { done?.(); return }
        setLaunch({ sr: slot.getBoundingClientRect(), b: btn.current.getBoundingClientRect(), done })
      }),
    ]
    return () => { offs.forEach(f => f()); clearTimeout(offs.t); clearTimeout(offs.c); clearTimeout(offs.m) }
  }, [])

  useEffect(() => {
    if (!entrance) return
    const t = setTimeout(() => {
      const slot = [...document.querySelectorAll('.fold-slot')].find(el => el.offsetParent !== null)
      const b = btn.current?.getBoundingClientRect()
      if (!slot || !b) { setArrived(true); return }
      const fold = slot.querySelector('.fold')
      fold?.classList.add('lid-pop'); setTimeout(() => fold?.classList.remove('lid-pop'), 1500); play('pop')
      setActor({ sr: slot.getBoundingClientRect(), b })
    }, delay)
    return () => clearTimeout(t)
  }, [])

  // Jetpack flight in five calm phases:
  //   1 lift-off   rises slowly out of the cube, flames swelling
  //   2 balance    hovers above the cube, wobbling less and less until steady
  //   3 glide      one smooth curve across, leaning into it and easing off
  //   4 balance    hovers over his spot, settling again
  //   5 landing    a slow vertical descent, thrust braking, a soft touch-down
  // One motion path carries the position; separate layers carry lean, hover and thrust.
  useLayoutEffect(() => {
    if (!actor || !actorEl.current) return
    const { sr, b } = actor, S = b.width, H = b.height
    const sx = sr.left + sr.width * .5, startY = sr.top + sr.height * .2
    const ex = b.left + S / 2, ey = b.top + H
    const top = H + 8, dir = ex >= sx ? 1 : -1
    const liftY = Math.max(top, startY - Math.max(110, H * 1.8))
    const hoverY = Math.max(top, ey - Math.max(70, H * 1.1))
    const c1x = sx + dir * Math.min(140, Math.abs(ex - sx) * .3), c1y = Math.max(top, liftY - 60)
    const c2x = ex - dir * Math.min(160, Math.abs(ex - sx) * .3), c2y = Math.max(top, hoverY - 40)
    // segment lengths so each phase gets its share of the path
    const cub = (t, a, b, c, d) => (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * d
    let curve = 0, px = sx, py = liftY
    for (let i = 1; i <= 40; i++) { const t = i / 40, x = cub(t, sx, c1x, c2x, ex), y = cub(t, liftY, c1y, c2y, hoverY); curve += Math.hypot(x - px, y - py); px = x; py = y }
    const L1 = startY - liftY, L3 = ey - hoverY, Ltot = L1 + curve + L3
    const d1 = L1 / Ltot * 100, d2 = (L1 + curve) / Ltot * 100
    const X = actorEl.current, B = X.firstChild, W = B.firstChild
    X.style.offsetPath = `path('M${sx},${startY} L${sx},${liftY} C${c1x},${c1y} ${c2x},${c2y} ${ex},${hoverY} L${ex},${ey}')`
    const tRise = 1500, tBal1 = 1000, tGlide = Math.max(2200, Math.min(3200, curve * 2.6)), tBal2 = 800, tLand = 1300, tSettle = 600
    const T1 = tRise, T2 = T1 + tBal1, T3 = T2 + tGlide, T4 = T3 + tBal2, T5 = T4 + tLand, total = T5 + tSettle
    const o = ms => Math.min(1, ms / total)
    X.animate([
      { offset: 0, offsetDistance: '0%', easing: 'cubic-bezier(.25,0,.35,1)' },
      { offset: o(T1), offsetDistance: d1 + '%' },
      { offset: o(T2), offsetDistance: d1 + '%', easing: 'cubic-bezier(.45,0,.25,1)' },
      { offset: o(T3), offsetDistance: d2 + '%' },
      { offset: o(T4), offsetDistance: d2 + '%', easing: 'cubic-bezier(.3,0,.25,1)' },
      { offset: o(T5), offsetDistance: '100%' },
      { offset: 1, offsetDistance: '100%' },
    ], { duration: total, fill: 'forwards' })
    // lean and balance: damped swings while hovering, a lean into the glide, upright for the landing
    const r = deg => `rotate(${deg}deg)`
    const swing = (t0, dur, amp, n) => Array.from({ length: n }, (_, i) => ({ offset: o(t0 + dur * (i + 1) / (n + 1)), transform: `scale(1) ${r((i % 2 ? -1 : 1) * amp * (1 - i / n))}`, easing: 'ease-in-out' }))
    B.animate([
      { offset: 0, transform: 'scale(.3) rotate(0deg)', opacity: 0, easing: 'cubic-bezier(.2,.8,.3,1)' },
      { offset: o(tRise * .45), transform: 'scale(.85) rotate(0deg)', opacity: 1, easing: 'ease-out' },
      { offset: o(T1), transform: 'scale(1) rotate(0deg)', opacity: 1, easing: 'ease-in-out' },
      ...swing(T1, tBal1, 7, 4),
      { offset: o(T2), transform: 'scale(1) rotate(0deg)', opacity: 1, easing: 'ease-in-out' },
      { offset: o(T2 + tGlide * .35), transform: `scale(1) ${r(dir * 10)}`, opacity: 1, easing: 'ease-in-out' },
      { offset: o(T2 + tGlide * .8), transform: `scale(1) ${r(-dir * 5)}`, opacity: 1, easing: 'ease-in-out' },
      { offset: o(T3), transform: 'scale(1) rotate(0deg)', opacity: 1, easing: 'ease-in-out' },
      ...swing(T3, tBal2, 4, 3),
      { offset: o(T4), transform: 'scale(1) rotate(0deg)', opacity: 1, easing: 'ease-in' },
      { offset: o(T5) - .001, transform: 'scale(.97,1.04) rotate(0deg)', opacity: 1 },
      { offset: o(T5), transform: 'scale(1.1,.9) rotate(0deg)', opacity: 1, easing: 'cubic-bezier(.3,1.6,.5,1)' },
      { offset: 1, transform: 'scale(1) rotate(0deg)', opacity: 1 },
    ], { duration: total, fill: 'forwards' })
    // hover bob, gentle and continuous until touch-down
    const bob = W.animate([{ transform: 'translateY(0)' }, { transform: 'translateY(-3px)' }, { transform: 'translateY(0)' }], { duration: 1100, iterations: Infinity, easing: 'ease-in-out' })
    // thrust: swells to lift, idles to hover, pushes to glide, idles, brakes hard on the way down, then off
    B.querySelector('.ed-flames')?.animate([
      { offset: 0, opacity: 0, transform: 'scaleY(.3)' }, { offset: o(250), opacity: 1, transform: 'scaleY(1.45)' },
      { offset: o(T1), opacity: 1, transform: 'scaleY(1.1)' }, { offset: o(T1 + 300), opacity: .9, transform: 'scaleY(.85)' },
      { offset: o(T2), opacity: .95, transform: 'scaleY(1.15)' }, { offset: o(T3 - 300), opacity: .9, transform: 'scaleY(.9)' },
      { offset: o(T3), opacity: .9, transform: 'scaleY(.85)' }, { offset: o(T4), opacity: 1, transform: 'scaleY(1.2)' },
      { offset: o(T5 - 200), opacity: 1, transform: 'scaleY(1.35)' }, { offset: o(T5 + 150), opacity: 0, transform: 'scaleY(.2)' },
      { offset: 1, opacity: 0, transform: 'scaleY(.2)' },
    ], { duration: total, fill: 'forwards' })
    ringEl.current?.animate([{ transform: 'scale(.2)', opacity: .8 }, { transform: 'scale(1.8)', opacity: 0 }], { duration: 900, easing: 'cubic-bezier(.2,.8,.3,1)', fill: 'forwards' })
    const puff = (x, y, k = 1, dx = 0) => {
      const d = document.createElement('i'); d.className = 'ed-puff'; d.style.left = x + 'px'; d.style.top = y + 'px'; document.body.appendChild(d)
      d.animate([{ transform: 'translate(-50%,-50%) scale(.35)', opacity: .5 * k }, { transform: `translate(calc(-50% + ${dx}px),calc(-50% + ${16 * k}px)) scale(${1.6 + k})`, opacity: 0 }],
        { duration: 1000 + 300 * k, easing: 'cubic-bezier(.2,.7,.3,1)', fill: 'forwards' }).onfinish = () => d.remove()
    }
    let n = 0
    const iv = setInterval(() => { const q = X.getBoundingClientRect(); n++; puff(q.left + q.width * (.3 + (n % 2) * .4), q.bottom + 4, .75, (n % 2 ? -1 : 1) * 4) }, 85)
    const timers = [setTimeout(() => clearInterval(iv), T5 - 100),
      setTimeout(() => { play('land'); buzz(12); for (const k of [-1, 1]) puff(ex + k * S * .3, ey - 4, 1.1, k * 26) }, T5),
      setTimeout(() => { bob.cancel(); setArrived(true); setActor(null) }, total + 40)]
    return () => { clearInterval(iv); timers.forEach(clearTimeout) }
  }, [actor])

  // Launch: Eddie flies back into the cube (Login then spins and zooms the cube)
  useLayoutEffect(() => {
    if (!launch || !actorEl.current) return
    const { sr, b, done } = launch, S = b.width, H = b.height
    const sx = b.left + S / 2, sy = b.top + H
    const ex = sr.left + sr.width * .5, ey = sr.top + sr.height * .12 + sr.height * .08
    const c1x = sx - (sx - ex) * .25, c1y = sy + 120, c2x = ex + (sx > ex ? 60 : -60), c2y = ey - 160
    const X = actorEl.current, B = X.firstChild
    X.style.offsetPath = `path('M${sx},${sy} C${c1x},${c1y} ${c2x},${Math.max(H + 10, c2y)} ${ex},${Math.max(H + 10, ey - 70)} L${ex},${ey}')`
    const total = 1250, dir = ex < sx ? -1 : 1
    X.animate([{ offsetDistance: '0%', easing: 'cubic-bezier(.5,0,.3,1)' }, { offset: .78, offsetDistance: '86%', easing: 'cubic-bezier(.5,0,.8,.5)' }, { offsetDistance: '100%' }], { duration: total, fill: 'forwards' })
    B.animate([
      { offset: 0, transform: 'scale(1) rotate(0deg)', opacity: 1 },
      { offset: .1, transform: 'scale(1.05,.92) rotate(0deg)', opacity: 1 },
      { offset: .26, transform: `scale(1.08) rotate(${dir * 360}deg)`, opacity: 1 },
      { offset: .4, transform: `scale(1) rotate(${dir * 370}deg)`, opacity: 1 },
      { offset: .78, transform: `scale(.85) rotate(${dir * 360}deg)`, opacity: 1 },
      { offset: 1, transform: `scale(.2) rotate(${dir * 360}deg)`, opacity: 0 },
    ], { duration: total, fill: 'forwards', easing: 'ease-in-out' })
    B.querySelector('.ed-flames')?.animate([{ opacity: 0 }, { opacity: 1, offset: .12 }, { opacity: 1, offset: .8 }, { opacity: 0 }], { duration: total, fill: 'forwards' })
    const t = setTimeout(() => { setGone(true); setLaunch(null); done?.() }, total)
    return () => clearTimeout(t)
  }, [launch])

  // Greeting: typed into the bubble as he says it. Browsers allow speech only after a
  // first touch, so if the page is still untouched the bubble offers "Hear Eddie" and
  // his greeting plays on the person's first tap or key press instead.
  const hello = returning ? `Welcome back, ${returning}! Good to see you again. Sign in, and let's continue your journey.` : HELLO[portal] || HELLO.student
  const show = returning ? `Welcome back, ${returning}! Good to see you again. Ready to continue your journey?` : SHOW[portal] || SHOW.student
  const clip = returning ? '/voice/eddie_welcome_back.mp3' : `/voice/eddie_${portal in HELLO ? portal : 'student'}.mp3`
  // On short screens there is little room above his perch: keep the whole bubble on screen.
  const bubbleEl = useRef(null)
  useLayoutEffect(() => {
    const el = bubbleEl.current; if (!el) return
    el.style.translate = ''
    const top = el.getBoundingClientRect().top
    if (top < 8) el.style.translate = `0 ${Math.ceil(8 - top)}px`
  })
  const [typed, setTyped] = useState(''), [talking, setTalking] = useState(false)
  const typer = useRef(0), spoken = useRef(false)
  const typeOut = () => { clearInterval(typer.current); let i = 0
    typer.current = setInterval(() => { i++; setTyped(show.slice(0, i)); if (i >= show.length) clearInterval(typer.current) }, 38) }
  const say = (again = false) => {
    if (spoken.current && !again) return
    spoken.current = true
    const done = () => { setTalking(false); clearInterval(typer.current); setTyped(show) }
    const start = () => { setTalking(true); clearInterval(typer.current); setTyped('') }
    // the recorded greeting, with the words typed in step with it
    return playClip(clip, { onStart: start, onEnd: done,
      onProgress: f => setTyped(show.slice(0, Math.ceil(show.length * Math.min(1, f * 1.08)))) })
      || speak(hello, { onStart: () => setTalking(true), onEnd: () => setTalking(false) })
  }
  useEffect(() => {
    if ((inline && !perch) || !arrived) return
    const t = setTimeout(() => { setPeek(true); typeOut(); if (mayTalkNow()) say() }, entrance ? 250 : delay)
    const first = () => say()   // first tap or key press on the page: now the browser lets him speak
    addEventListener('pointerdown', first, { once: true, capture: true }); addEventListener('keydown', first, { once: true, capture: true })
    const phone = matchMedia('(max-width:900px)').matches
    const t2 = phone ? setTimeout(() => setPeek(false), (entrance ? 250 : delay) + 9000) : 0
    return () => { clearTimeout(t); clearTimeout(t2); clearInterval(typer.current); removeEventListener('pointerdown', first, true); removeEventListener('keydown', first, true) }
  }, [arrived])
  useEffect(() => () => hush(), [])
  useEffect(() => {
    let raf = 0, ev = null
    const run = () => { raf = 0; const r = btn.current?.getBoundingClientRect(); if (!r || !ev || focusPt.current) return
      const dx = ev.clientX - (r.left + r.width / 2), dy = ev.clientY - (r.top + r.height / 2), d = Math.hypot(dx, dy) || 1
      setLook({ x: +(dx / Math.max(d, 160)).toFixed(2), y: +(dy / Math.max(d, 160)).toFixed(2) }) }
    const m = e => { ev = e; if (!raf) raf = requestAnimationFrame(run) }
    addEventListener('pointermove', m); return () => { removeEventListener('pointermove', m); cancelAnimationFrame(raf) }
  }, [])

  const forgot = FORGOT[portal] || 'Ask EduVerse support to reset your password.'
  const isNew = NEW[portal]
  return <div className={'eddie' + (open ? ' open' : '') + (peek && !open ? ' peeking' : '') + (inline ? ' inline' : '') + (perch ? ' perch' : '') + (arrived ? (entrance ? ' arrived' : '') : ' waiting') + (launch || gone ? ' launching' : '')}>
    {launch && createPortal(<div ref={actorEl} className="ed-actor launch" style={{ width: launch.b.width, height: launch.b.height }}><div className="ed-actor-b" style={{ opacity: 1 }}><EddieBot size={size} look={{ x: -.6, y: .5 }} flying mood="happy" /></div></div>, document.body)}
    {actor && createPortal(<>
      <div ref={ringEl} className="ed-ring" style={{ left: actor.sr.left + actor.sr.width / 2 - 40, top: actor.sr.top + actor.sr.height * .12 - 40 }} />
      <div ref={actorEl} className="ed-actor" style={{ width: actor.b.width, height: actor.b.height }}><div className="ed-actor-b"><div className="ed-actor-w"><EddieBot size={size} look={{ x: .5, y: .2 }} flying /></div></div></div>
    </>, document.body)}
    {(open || peek) && <div ref={bubbleEl} className={'ed-bubble' + (peek && !open ? ' peek' : '')} role="dialog" aria-label="Eddie, your EduVerse helper" onClick={() => { if (!open) { setOpen(true); setPeek(false) } }}>
      {open && <button type="button" className="ed-x" aria-label="Close" onClick={e => { e.stopPropagation(); setOpen(false) }}>
        <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18" /></svg></button>}
      <div className="ed-hi"><b>Eddie</b><span className="ed-role">{ROLE[portal] || ROLE.student}</span><span className={'ed-dot' + (talking ? ' talking' : '')} /></div>
      {!open ? <><p className="ed-say">{msg || typed || '\u00a0'}<i className={'ed-caret' + (msg || typed.length >= show.length ? ' done' : '')} /></p>
        {canTalk() && <button type="button" className="ed-hear" onClick={e => { e.stopPropagation(); say(true) }}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" /><path d="M15.5 9a4 4 0 0 1 0 6" /></svg>{talking ? 'Eddie is talking' : 'Hear Eddie'}</button>}</>
      : !answer ? <>
        <p>{GREET[portal] || GREET.student} Pick one, or ask me anything below.</p>
        <div className="ed-chips">
          <button type="button" onClick={() => setAnswer('forgot')}>I forgot my password</button>
          <button type="button" onClick={() => setAnswer('new')}>I'm new here</button>
          {onTour && <button type="button" onClick={() => { setOpen(false); onTour() }}>Show me how EduVerse works</button>}
        </div>
      </> : <div className="ed-answer">
        {answer === 'forgot' && <p>{forgot}</p>}
        {answer === 'new' && (isNew === 'new'
          ? <p>Welcome! You can start for free. <Link to="/signup">Create your account</Link> in under a minute.</p>
          : <p>{isNew}</p>)}
        <button type="button" className="ed-back" onClick={() => setAnswer(null)}>
          <svg viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6" /></svg>Something else</button>
      </div>}
      {open && <div className="ed-chat">
        {chat.length > 0 && <div className="ed-log">
          {chat.map((m, i) => <div key={i} className={'ed-msg ' + m.who}>{m.a === 'NEW' ? <>You can start for free. <Link to="/signup">Create your account</Link> in under a minute.</> : m.t}</div>)}
          {typing && <div className="ed-msg bot ed-typing"><i /><i /><i /></div>}
          <span ref={chatEnd} />
        </div>}
        <form className="ed-ask" onSubmit={e => { e.preventDefault(); const t = q.trim(); if (!t || typing) return
          setChat(c => [...c, { who: 'me', t }]); setQ(''); setTyping(true); play('tap', .6)
          setTimeout(() => { const a = answerFor(t, portal); setChat(c => [...c, { who: 'bot', t: a === 'NEW' ? '' : a, a }]); setTyping(false); setMood('happy'); setTimeout(() => setMood(''), 900)
            requestAnimationFrame(() => { const l = chatEnd.current?.parentElement; if (l) l.scrollTo({ top: l.scrollHeight, behavior: 'smooth' }) }) }, 650) }}>
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Ask Eddie a question" aria-label="Ask Eddie a question" maxLength={160} />
          <button type="submit" aria-label="Send" disabled={!q.trim()}><svg viewBox="0 0 24 24"><path d="M5 12h14m-6-6 6 6-6 6" /></svg></button>
        </form>
      </div>}
    </div>}
    <button ref={btn} type="button" className="ed-btn" aria-label={open ? 'Hide Eddie' : 'Ask Eddie for help'} aria-expanded={open}
      onClick={() => { setPeek(false); setOpen(o => !o); setAnswer(null) }}>
      <EddieBot talking={talking} size={size} look={pw.focus && !pw.show ? { x: 0, y: 0 } : look} waving={(open && !mood) || cheer} mood={mood || (cheer ? 'happy' : pw.focus ? (pw.show ? 'peek' : 'shy') : '')} />
    </button>
  </div>
}

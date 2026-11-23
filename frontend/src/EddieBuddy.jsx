// Eddie on the student home: says hello, reads out today's plan, listens to a question and talks back.
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from './api'
import { EddieBot } from './Eddie'
import { speak, hush, mayTalkNow, serverVoice } from './voice'
import { sound, play } from './sound'
import { callName } from './callname'
import './buddy.css'

const SR = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null
const greet = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening' }
const PLAN_Q = /(pending|plan|today|to ?do|what (should|shall|do|can) i (study|do|learn)|where (do|should) i start)/i
const HI_Q = /^(hi|hello|hey|hai|good (morning|afternoon|evening))\b/i
const STOP_Q = /^(stop|quiet|be quiet|shh+|enough)\b/i

export function planFor(d, running) {
  const items = [], c = d.continue, x = d.last_exam
  if (running) items.push({ id: 'test', to: `/student/exam/${running.bid}?tab=tests`, t: `Finish your test: ${running.title}`,
    s: `${Object.keys(running.answers || {}).length} of ${running.questions.length} answered`, say: `finish your ${running.title} test` })
  const dy = d.daily
  if (dy && !dy.done && dy.count) {
    const bits = [dy.mistakes && `${dy.mistakes} to revise`, dy.reading && `${dy.reading} from your reading`].filter(Boolean)
    items.push({ id: 'daily', to: `/student/test/${dy.book_id}/daily`, t: "Eddie's Daily 5", s: bits.length ? bits.join(', ') : `${dy.count} quick questions`,
      say: dy.mistakes ? `do your Daily 5. I put in ${dy.mistakes === 1 ? 'one question' : dy.mistakes + ' questions'} you missed before` : 'do your Daily 5, five quick questions I picked for you' })
  } else if (dy?.done) items.push({ id: 'daily', done: true, to: `/student/result/${dy.attempt_id}`, t: 'Daily 5 done', s: `${dy.score} of ${dy.total} right` })
  const lt = d.last_test
  if (lt?.untaught) items.push({ id: 'mistakes', to: `/student/result/${lt.id}?teach=1`, t: `Go through ${lt.untaught === 1 ? 'your mistake' : lt.untaught + ' mistakes'} with Eddie`,
    s: `Last test: ${lt.score} of ${lt.total}`, say: `go through your last test ${lt.untaught === 1 ? 'mistake' : 'mistakes'} with me` })
  const tn = d.test_next
  if (tn && !tn.done_today) items.push({ id: 'qc', to: `/student/test/${tn.book_id}/${tn.chapter}?level=quick`, t: `Quick check: ${tn.chapter_title || 'Unit ' + tn.chapter}`,
    s: `${Math.min(5, tn.count)} questions from ${tn.book_title}`, say: `take a ${Math.min(5, tn.count)} question quick check on ${tn.chapter_title || 'unit ' + tn.chapter}` })
  else if (tn?.done_today) items.push({ id: 'qc', done: true, t: 'Quick check done', s: tn.book_title })
  if (c) items.push({ id: 'read', to: '/student/read/' + c.id, t: `Continue ${c.title}`, s: `${c.progress}% read`,
    say: c.progress ? `continue ${c.title}, you are ${c.progress} percent through` : `open ${c.title} and read the first chapter` })
  const rem = Math.max(0, d.goal_minutes - d.today_minutes)
  items.push(rem ? { id: 'goal', to: c ? '/student/read/' + c.id : '/student/books', t: `Study ${rem} more minutes`, s: `${d.today_minutes} of ${d.goal_minutes} min done today`, say: `study ${rem} more minutes to reach today's goal` }
    : { id: 'goal', done: true, t: 'Daily goal reached', s: `${d.today_minutes} min today` })
  const p = d.practice?.[0]
  if (p) items.push({ id: 'prac', to: `/student/exam/${p.book_id}?tab=practice&chapter=${encodeURIComponent(p.chapter)}`, t: `Practise ${p.chapter}`, s: `${p.accuracy}% right so far`, say: `practise ${p.chapter}, that is where you are losing marks` })
  else if (x) items.push(d.today_questions ? { id: 'prac', done: true, t: `${d.today_questions} questions practised`, s: x.title }
    : { id: 'prac', to: `/student/exam/${x.id}?tab=practice`, t: `Practise a few questions`, s: x.title, say: `practise a few ${x.title} questions` })
  if (!d.exam_date) items.push({ id: 'exam', act: 'goal', t: 'Set your exam date', s: 'So I can plan your days', say: 'set your exam date so I can plan your days for you' })
  return items
}

function helloText(d, first, plan) {
  const todo = plan.filter(i => !i.done)
  let s = `${greet()}, ${first}! Eddie here, your guide through the EduVerse.`
  if (d.streak > 1) s += ` You're on a ${d.streak} day streak, nice!`
  if (!todo.length) return s + ` You're all caught up for today. Ask me anything you're curious about.`
  const weak = d.memory?.weak?.find(w => w.open)
  if (weak && d.daily?.mistakes) s += ` Last time, ${weak.title} tripped you up a little, so I put it in your Daily 5.`
  s += ` You have ${todo.length === 1 ? 'one thing' : todo.length + ' things'} for today. First, ${todo[0].say}.`
  if (todo[1]) s += ` Then ${todo[1].say}.`
  return s + ` Tap the mic and ask me anything.`
}

function planText(plan) {
  const todo = plan.filter(i => !i.done)
  if (!todo.length) return `Nothing pending! You've done everything for today. Want to learn something new? Ask me a doubt.`
  return `Here's your plan. ` + todo.map((i, n) => `${['First', 'Next', 'Then', 'After that', 'And'][n] || 'And'}, ${i.say}.`).join(' ') + ` You've got this.`
}

// The talking part of Eddie, shared by the Home card and the reader: speech out, mic in, chat with the AI.
export function useEddieChat({ getContext, local, first, send }) {
  const [say, setSay] = useState('')            // what Eddie is saying right now
  const [shown, setShown] = useState(0)         // how much of it is typed out
  const [talking, setTalking] = useState(false)
  const [mood, setMood] = useState('happy')
  const [thread, setThread] = useState([])      // [{who, text}]
  const [q, setQ] = useState('')
  const [listening, setListening] = useState(false)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [soundOn, setSoundOn] = useState(sound.on)
  const rec = useRef(null), typer = useRef(null), threadEl = useRef(null)

  useEffect(() => sound.sub(setSoundOn), [])
  useEffect(() => () => { hush(); clearInterval(typer.current); try { rec.current?.abort() } catch { /* gone */ } }, [])
  useEffect(() => { threadEl.current?.scrollTo({ top: 1e6 }) }, [thread, busy])

  function typeOut(text) { setSay(text); setShown(0); clearInterval(typer.current); typer.current = setInterval(() => setShown(n => n >= text.length ? (clearInterval(typer.current), n) : n + 2), 22) }

  // Eddie says something: the words type out, in step with his voice when sound is on.
  function talk(text, { mood: m = 'happy', log = true } = {}) {
    clearInterval(typer.current); hush()
    setSay(text); setShown(0); setMood(m)
    if (log) setThread(t => [...t, { who: 'eddie', text }].slice(-12))
    let spoken = false
    const tick = () => { typer.current = setInterval(() => setShown(n => { if (n >= text.length) { clearInterval(typer.current); return n } return n + 2 }), spoken ? 55 : 22) }
    const ok = soundOn && speak(text, {
      onStart: () => { spoken = true; setTalking(true); clearInterval(typer.current); tick() },
      onWord: i => setShown(n => Math.max(n, i)),
      onEnd: () => { setTalking(false); setShown(text.length); clearInterval(typer.current) },
    })
    if (!ok) tick()
    else setTimeout(() => { if (!spoken) tick() }, serverVoice() ? 5000 : 700)   // wait for his voice; some devices never fire onstart
  }

  async function ask(text) {
    const question = text.trim(); if (!question || busy) return
    setQ(''); setNote('')
    setThread(t => [...t, { who: 'me', text: question }].slice(-12))
    if (STOP_Q.test(question)) { hush(); setTalking(false); return talk('Okay, I will be quiet. Tap the mic when you need me.', { mood: 'idle' }) }
    if (!send && HI_Q.test(question) && question.split(/\s+/).length <= 3) return talk(`Hi ${first}! What shall we learn today?`)
    const mine = local?.(question); if (mine) return talk(mine)
    setBusy(true); setMood('look'); setSay(''); setShown(0)
    try {
      const r = send ? await send(question) : await api('/api/learn/buddy', { method: 'POST', body: { question, context: getContext(), history: thread.slice(-6) } })
      if (r.credits_left != null && r.credits_left <= 3) setNote(r.credits_left ? `${r.credits_left} questions left today` : 'That was your last question for today')
      talk(r.text)
    } catch (e) {
      talk(/credit/i.test(e.message) ? `We've used all of today's questions. Let's pick up again tomorrow!` : `Hmm, my brain is taking a short break. Try me again in a minute.`, { mood: 'sad' })
    } finally { setBusy(false) }
  }

  function listen() {
    if (listening) { try { rec.current?.stop() } catch { /* gone */ } return }
    hush(); setTalking(false); setNote('')
    if (!SR) { setNote('Voice works in Chrome and Edge. You can type to Eddie here.'); return }
    const r = new SR(); rec.current = r
    r.lang = 'en-IN'; r.interimResults = true; r.continuous = false; r.maxAlternatives = 1
    let finalText = ''
    r.onstart = () => { setListening(true); setMood('look'); setSay('I am listening…'); setShown(99); play('tap', .6) }
    r.onresult = e => {
      let interim = ''
      for (let i = e.resultIndex; i < e.results.length; i++) { const t = e.results[i][0].transcript; if (e.results[i].isFinal) finalText += t; else interim += t }
      setQ((finalText + interim).trim())
    }
    r.onerror = e => setNote(e.error === 'not-allowed' || e.error === 'service-not-allowed' ? 'Allow the microphone to talk to Eddie.' : e.error === 'no-speech' ? 'I did not catch that. Tap the mic and try again.' : '')
    r.onend = () => { setListening(false); setMood('happy'); if (finalText.trim()) ask(finalText); else setSay(s => s === 'I am listening…' ? 'Tap the mic and ask me anything.' : s) }
    try { r.start() } catch { setListening(false) }
  }

  function stop() { hush(); setTalking(false); setShown(say.length); clearInterval(typer.current) }
  const past = thread[thread.length - 1]?.who === 'eddie' ? thread.slice(0, -1) : thread
  const reset = () => setThread([])
  return { reset, say, shown, text: say.slice(0, shown), talking, mood, setMood, thread, past, q, setQ, listening, busy, note, soundOn, threadEl, talk, typeOut, ask, listen, stop }
}

// The ask bar both Eddies use.
export function AskBar({ c, placeholder }) {
  return <form className="bd-ask" onSubmit={e => { e.preventDefault(); c.ask(c.q) }}>
    <button type="button" className={'bd-mic' + (c.listening ? ' on' : '')} onClick={c.listen} aria-label={c.listening ? 'Stop listening' : 'Talk to Eddie'} title={c.listening ? 'Stop listening' : 'Talk to Eddie'}>
      <svg viewBox="0 0 24 24"><path d="M12 15a3 3 0 0 0 3-3V7a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3zM6.5 11.5a5.5 5.5 0 0 0 11 0M12 17v3" /></svg>
    </button>
    <input className="input" value={c.q} onChange={e => c.setQ(e.target.value)} placeholder={c.listening ? 'Listening…' : placeholder} disabled={c.busy} />
    <button className="btn primary" disabled={c.busy || !c.q.trim()}>Ask</button>
  </form>
}

export function Talk({ c }) {
  const has = c.past.length > 0
  // The answer bubble grows as it types, which squeezes the thread: keep the newest message in view.
  useEffect(() => {
    const el = c.threadEl.current; if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => { el.scrollTop = el.scrollHeight }); ro.observe(el); return () => ro.disconnect()
  }, [has]) // eslint-disable-line react-hooks/exhaustive-deps
  return <>
    {c.past.length > 0 && <div className="bd-thread" ref={c.threadEl}>
      {c.past.map((m, i) => <div key={i} className={'bd-m ' + (m.who === 'me' ? 'me' : 'bot')}>{m.text}</div>)}
    </div>}
    <div className="bd-bubble" aria-live="polite">
      {c.busy ? <span className="bd-dots"><i /><i /><i /></span> : <>{c.text}{c.shown < c.say.length && <i className="bd-caret" />}</>}
    </div>
  </>
}

export default function EddieBuddy({ d, running, onGoal, onNamed }) {
  const nav = useNavigate()
  const [nick, setNick] = useState(null)
  const first = nick || callName(d.me.name, d.me.profile || {})
  const plan = useMemo(() => planFor(d, running), [d, running])
  const context = useMemo(() => [`Name ${first}`, d.me.class, d.me.board || d.me.profile?.exam, d.books.length ? 'Books: ' + d.books.map(b => b.title).join(', ') : '',
    'Today: ' + plan.map(i => i.t + (i.done ? ' (done)' : '')).join('; '), d.exam_date ? `Exam on ${d.exam_date}` : '', d.memory?.for_eddie || ''].filter(Boolean).join('. '), [d, plan, first])
  const c = useEddieChat({ first, getContext: () => context, local: q => {
    const m = /^(?:please\s+)?(?:call me|my name is|you can call me)\s+(.{1,30}?)[.!]*$/i.exec(q.trim())
    if (m) {
      const n = m[1].trim()
      api('/api/student/profile', { method: 'PUT', body: { nickname: n } }).then(() => { setNick(n); callName('', { nickname: n }); onNamed?.() }).catch(() => {})
      return `Got it! From now on I'll call you ${n}. Nice to meet you properly, ${n}!`
    }
    return PLAN_Q.test(q) ? planText(plan) : null
  } })

  // Hello on arrival. He speaks it once a session if the page has already been touched (the sign-in click counts).
  useEffect(() => {
    const text = helloText(d, first, plan)
    const once = sessionStorage.getItem('ev_buddy_hi')
    if (!once && mayTalkNow()) { sessionStorage.setItem('ev_buddy_hi', '1'); setTimeout(() => c.talk(text, { log: false }), 600) }
    else c.typeOut(text)
    if (!once) sessionStorage.setItem('ev_buddy_hi', '1')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const open = i => i.act === 'goal' ? onGoal() : nav(i.to)
  return (
    <section className={'buddy' + (c.talking ? ' is-talking' : '') + (c.listening ? ' is-listening' : '')}>
      <div className="bd-bot">
        <div className="bd-halo" />
        <EddieBot size={96} jet={false} mood={c.mood} talking={c.talking} waving={!c.thread.length && c.talking} />
      </div>
      <div className="bd-main">
        <div className="bd-head">
          <div><b>Eddie</b><span>your EduVerse guide</span></div>
          <Tools c={c} replay={() => c.talk(c.say || helloText(d, first, plan), { log: false })} />
        </div>
        <Talk c={c} />
        <div className="bd-plan">
          <div className="bd-plan-h">Today's plan<span>{plan.filter(i => i.done).length} of {plan.length} done</span></div>
          {plan.map(i => i.done
            ? <div key={i.id} className="bd-item done"><span className="bd-tick" /><div><b>{i.t}</b><small>{i.s}</small></div></div>
            : <button key={i.id} type="button" className="bd-item" onClick={() => open(i)}><span className="bd-tick" /><div><b>{i.t}</b><small>{i.s}</small></div><span className="bd-go">›</span></button>)}
        </div>
        <AskBar c={c} placeholder='Ask Eddie a doubt, or "what should I study?"' />
        {c.note && <div className="bd-note">{c.note}</div>}
        {!c.thread.length && <div className="bd-chips">{['What should I study today?', 'Explain photosynthesis simply', 'Give me a quick quiz question'].map(s =>
          <button key={s} type="button" className="chip" onClick={() => c.ask(s)}>{s}</button>)}</div>}
      </div>
    </section>
  )
}

export function Tools({ c, replay }) {
  return <div className="bd-tools">
    <button type="button" className="bd-icon" title="Hear it again" aria-label="Hear it again" onClick={replay} disabled={!c.say}>
      <svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.5-5.8M4 4v4.5h4.5" /></svg></button>
    <button type="button" className={'bd-icon' + (c.soundOn ? '' : ' off')} title={c.soundOn ? "Eddie's voice is on" : "Eddie's voice is off"} aria-pressed={c.soundOn}
      onClick={() => { if (c.soundOn) c.stop(); sound.set(!c.soundOn) }}>
      {c.soundOn ? <svg viewBox="0 0 24 24"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4zM15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" /></svg>
        : <svg viewBox="0 0 24 24"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4zM16 9.5l5 5m0-5l-5 5" /></svg>}</button>
  </div>
}

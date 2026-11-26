// The result of a chapter test. Eddie sums it up out loud, then goes through each mistake like a teacher:
// he asks why the student chose that answer, listens, explains with the book's own words, and links back to the page.
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import { Ring, Icon, plural, BookImg } from '../../ui'
import { callName } from '../../callname'
import { EddieBot } from '../../Eddie'
import { useEddieChat, AskBar, Talk, Tools } from '../../EddieBuddy'
import { mayTalkNow } from '../../voice'
import '../../buddy.css'
import '../../tests.css'

const me = () => { try { return JSON.parse(localStorage.getItem('ev_user') || '{}') } catch { return {} } }
const mmss = s => `${Math.floor(s / 60)} min ${s % 60} s`

function summary(r, first) {
  const pct = Math.round(r.score / Math.max(1, r.total) * 100)
  const strong = r.by_section.filter(s => s.right === s.total && s.total).map(s => s.title)
  const weak = r.by_section.filter(s => s.right < s.total).sort((a, b) => a.right / a.total - b.right / b.total).map(s => s.title)
  let s = pct === 100 ? `Wow, ${first}! ${r.score} out of ${r.total}. Every single one right!` : pct >= 70 ? `Nice work, ${first}! You scored ${r.score} out of ${r.total}.`
    : pct >= 40 ? `Good try, ${first}. You scored ${r.score} out of ${r.total}, and we can make that better together.` : `${r.score} out of ${r.total}, ${first}. That's okay, this is exactly how we find what to work on.`
  if (strong.length && pct < 100) s += ` You're strong on ${strong.slice(0, 2).join(' and ')}.`
  if (weak.length) s += ` ${weak[0]} needs a little more work.`
  const wrong = r.total - r.score
  if (wrong) s += ` Shall we go through the ${wrong === 1 ? 'one' : wrong} you missed? I'll explain each one.`
  return s
}

function QReview({ q, bid, open }) {
  const [o, setO] = useState(open)
  return <div className={'rq ' + (q.correct ? 'ok' : 'no')}>
    <button type="button" className="rq-h" onClick={() => setO(!o)} aria-expanded={o}>
      <span className="rq-mark">{q.correct ? <Icon n="check" s={14} /> : '✕'}</span><span className="rq-t">{q.why && <em className={'why ' + q.why}>{{ mistake: 'Revision', reading: 'From your reading', new: 'New' }[q.why]}</em>}{q.text}</span><span className="bd-go">{o ? '−' : '+'}</span></button>
    {o && <div className="rq-b">
      {q.figure?.image && <BookImg className="tq-fig" src={`/api/content/${bid}/${q.figure.image}`} alt="" />}
      {!q.correct && <div>Your answer: <b className="bad">{q.your_text || 'left blank'}</b></div>}
      <div>Right answer: <b className="good">{q.right_text}</b></div>
      {q.source && <div className="tq-src"><b>Your book says:</b> {q.source}</div>}
    </div>}
  </div>
}

export default function TestResult() {
  const { aid } = useParams(); const [sp] = useSearchParams(); const nav = useNavigate()
  const [r, setR] = useState(null); const [err, setErr] = useState('')
  const [mode, setMode] = useState('summary')     // summary | teach | done
  const [k, setK] = useState(0)                   // which mistake Eddie is on
  const [explained, setExplained] = useState(false)
  const [check, setCheck] = useState(null)        // { q, same, answer, result }
  const [fixedN, setFixedN] = useState(0)
  const first = callName(me().name)
  const wrong = useMemo(() => r ? r.questions.filter(q => !q.correct) : [], [r])
  const q = wrong[k]
  const c = useEddieChat({
    first, getContext: () => '',
    send: async reason => { const x = await api(`/api/student/tests/${aid}/teach`, { method: 'POST', body: { question_id: q.id, reason } }); setExplained(true); return x },
  })

  useEffect(() => { api('/api/student/tests/' + aid).then(setR).catch(e => setErr(e.message)) }, [aid])
  // Keep the check question, and then its result, in view.
  useEffect(() => { if (check) setTimeout(() => document.querySelector('.tr-check')?.scrollIntoView({ block: check.result ? 'end' : 'center', behavior: 'smooth' }), 80) }, [check?.q?.id, !!check?.result]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (mode === 'teach') setTimeout(() => document.querySelector('.tr-eddie')?.scrollIntoView({ block: 'start', behavior: 'smooth' }), 80) }, [k, mode])
  useEffect(() => {
    if (!r) return
    if (sp.get('teach') && r.total > r.score) { startTeach(); return }
    const text = summary(r, first)
    if (mayTalkNow()) setTimeout(() => c.talk(text, { log: false }), 500); else c.typeOut(text)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [r])

  function askWhy(i) {
    const m = wrong[i]
    setK(i); setExplained(false); setCheck(null); c.reset()
    const intro = i === 0 ? `Let's go through them one by one. ` : ''
    c.talk(m.your ? `${intro}Question ${r.questions.indexOf(m) + 1}. You picked "${m.your_text}". Why did you choose that? Tell me what you were thinking.`
      : `${intro}Question ${r.questions.indexOf(m) + 1}. You left this one blank. What were you unsure about?`, { log: false })
  }
  function startTeach() { setMode('teach'); askWhy(0) }
  function next() {
    if (k + 1 < wrong.length) askWhy(k + 1)
    else {
      setMode('done')
      const all = wrong.length, f = fixedN
      c.talk(f === all ? `You fixed ${all === 1 ? 'it' : all === 2 ? 'both' : 'all ' + all}! I'll bring ${all === 1 ? 'it' : 'them'} back in a few days in your Daily 5, just to be sure it stuck.`
        : f ? `You fixed ${f} of ${all}. Great progress! I'll bring the other${all - f === 1 ? ' one' : 's'} back tomorrow in your Daily 5.`
          : `${all === 1 ? "That's the one" : all === 2 ? "That's both of them" : `That's all ${all}`}! I've added ${all === 1 ? 'it' : 'them'} to your revision list, and they'll come back tomorrow in your Daily 5.`, { log: false })
    }
  }
  async function startCheck() {
    try {
      const x = await api(`/api/student/tests/${aid}/check/${q.id}`)
      setCheck({ q: x.question, same: x.same, answer: '', result: null })
      c.talk(x.same ? `Let's see if it stuck. Same question again, but no peeking this time!` : `Let's see if it stuck. Here's a similar one. Take your time.`, { log: false })
    } catch (e) { c.talk(`Hmm, I couldn't find another question right now. Let's move on.`, { log: false }) }
  }
  async function answerCheck(ans) {
    if (check.result) return
    setCheck(x => ({ ...x, answer: ans }))
    try {
      const res = await api(`/api/student/tests/${aid}/check`, { method: 'POST', body: { original_id: q.id, question_id: check.q.id, answer: ans } })
      setCheck(x => ({ ...x, answer: ans, result: res }))
      if (res.correct) { setFixedN(n => n + 1); c.talk(`Yes! You've got it. I've marked that mistake as fixed.`, { mood: 'happy', log: false }) }
      else c.talk(`Not quite. ${res.right_text.startsWith('any of:') ? 'Any one of these was right: ' + res.right_text.slice(8) + '.' : `It's "${res.right_text}".`} ${res.explanation ? res.explanation + ' ' : ''}No worries, I'll bring this one back tomorrow.`, { mood: 'sad', log: false })
    } catch (e) { c.talk(e.message, { log: false }) }
  }
  const retry = () => nav(`/student/test/${r.book_id}/${wrong[0]?.chapter ?? r.chapter}?retry=${wrong.map(x => x.id).join(',')}`)
  const inBook = m => `/student/read/${r.book_id}?ch=${m?.chapter ?? r.chapter}${m?.section ? '&sec=' + encodeURIComponent(m.section) : ''}`
  const bookCh = r && r.chapter >= 0 ? r.chapter : (r?.questions[0]?.chapter ?? 0)

  if (err) return <div className="page"><div className="card empty">{err} <Link to="/student">Back to home</Link></div></div>
  if (!r) return <div className="page"><div className="empty">Opening your result</div></div>
  const pct = Math.round(r.score / Math.max(1, r.total) * 100)

  return (
    <div className="page tr">
      <div className="tr-head card">
        <Ring value={r.score} max={r.total} size={92} stroke={9}><span className="tr-score">{r.score}<small>/{r.total}</small></span></Ring>
        <div className="tr-h">
          <div className="k">{{ retry: 'Try again', quick: 'Quick check', daily: "Eddie's Daily 5", chapter: 'Chapter test' }[r.level] || 'Test'} result</div>
          <h1>{r.chapter > 0 ? `Unit ${r.chapter}: ` : ''}{r.chapter_title}</h1>
          <div className="muted">{pct}% right · {mmss(r.seconds)} · {r.book_title}</div>
          <div className="tr-secs">{r.by_section.map(s => <span key={s.title} className={s.right === s.total ? 'ok' : s.right ? 'mid' : 'no'}>{s.title} <b>{s.right}/{s.total}</b></span>)}</div>
        </div>
      </div>

      <section className={'buddy tr-eddie' + (c.talking ? ' is-talking' : '') + (c.listening ? ' is-listening' : '')}>
        <div className="bd-bot"><div className="bd-halo" /><EddieBot size={96} jet={false} mood={mode === 'summary' && pct < 40 ? 'idle' : c.mood} talking={c.talking} /></div>
        <div className="bd-main">
          <div className="bd-head"><div><b>Eddie</b><span>{mode === 'teach' ? `mistake ${k + 1} of ${wrong.length}` : mode === 'done' && fixedN ? `${fixedN} fixed` : 'your teacher'}</span></div>
            <Tools c={c} replay={() => c.talk(c.say, { log: false })} /></div>

          {mode === 'teach' && q && <div className="tr-q">
            {q.figure?.image && <BookImg className="tq-fig" src={`/api/content/${r.book_id}/${q.figure.image}`} alt={q.figure.caption || ''} />}
            <div className="tr-qt">{q.text}</div>
            {q.options.length ? <div className="tr-opts">{q.options.map(o => <span key={o.key} className={o.key === q.answer ? (explained ? 'right' : '') : o.key === q.your ? 'yours' : ''}>
              <b>{o.key.toUpperCase()}</b>{o.text}{o.key === q.your && <em>your answer</em>}{explained && o.key === q.answer && <em>right answer</em>}</span>)}</div>
              : <div className="tr-opts"><span className="yours"><b>You</b>{q.your_text || 'left blank'}</span>{explained && <span className="right"><b>Answer</b>{q.right_text}</span>}</div>}
          </div>}

          <Talk c={c} />

          {mode === 'summary' && <div className="tr-acts">
            {wrong.length > 0 && <button className="btn primary lg" onClick={startTeach}>Go through {wrong.length === 1 ? 'my mistake' : `my ${wrong.length} mistakes`} with Eddie</button>}
            {wrong.length > 0 && <button className="btn" onClick={retry}>Try the ones I missed</button>}
            <Link className="btn" to={`/student/read/${r.book_id}?ch=${bookCh}`}>Back to the book</Link>
            {!wrong.length && <Link className="btn primary" to="/student">Home</Link>}
          </div>}

          {mode === 'teach' && <>
            {!explained && !c.busy && <div className="bd-chips" style={{ paddingLeft: 0 }}>{['I guessed', 'I mixed it up with another word', 'I was not sure'].map(s =>
              <button key={s} type="button" className="chip" onClick={() => c.ask(s)}>{s}</button>)}</div>}
            {!explained ? <AskBar c={c} placeholder="Tell Eddie why you chose it…" />
              : !check ? <div className="tr-acts">
                <button className="btn primary" onClick={startCheck}><Icon n="check" s={16} />Check I've got it</button>
                <Link className="btn" to={inBook(q)}><Icon n="book" s={16} />Show me in the book</Link>
                <button className="btn ghost" onClick={next}>Skip</button>
              </div>
              : <div className="tr-check">
                <div className="k">{check.same ? 'Same question, no peeking' : 'A similar question'}</div>
                {check.q.figure?.image && <BookImg className="tq-fig" src={`/api/content/${r.book_id}/${check.q.figure.image}`} alt="" />}
                <div className="tr-qt">{check.q.text}</div>
                {check.q.options.length ? <div className="ct-opts">{check.q.options.map(o => {
                  const res = check.result, mine = check.answer === o.key
                  const cls = res ? (res.correct && mine ? ' good' : mine ? ' badopt' : o.text === res.right_text ? ' good' : '') : mine ? ' on' : ''
                  return <button key={o.key} type="button" className={'ct-opt' + cls} disabled={!!res} onClick={() => answerCheck(o.key)}><span className="ct-key">{o.key.toUpperCase()}</span><span>{o.text}</span></button>
                })}</div>
                  : <form className="bd-ask" onSubmit={e => { e.preventDefault(); answerCheck(e.currentTarget.elements.a.value) }}><input name="a" className="input" placeholder="Your answer" disabled={!!check.result} /><button className="btn primary" disabled={!!check.result}>Check</button></form>}
                {check.result && <div className="tr-acts">
                  {check.result.correct ? <span className="tr-fixed"><Icon n="check" s={16} />Mistake fixed</span> : <span className="tr-later">Back tomorrow in your Daily 5</span>}
                  <button className="btn primary" onClick={next}>{k + 1 < wrong.length ? 'Next mistake' : 'Done'}<Icon n="right" s={16} /></button>
                </div>}
              </div>}
            {c.note && <div className="bd-note" style={{ paddingLeft: 0 }}>{c.note}</div>}
          </>}

          {mode === 'done' && <div className="tr-acts">
            <button className="btn primary lg" onClick={retry}>Try {wrong.length === 1 ? 'it' : `all ${wrong.length}`} again</button>
            <Link className="btn" to={`/student/read/${r.book_id}?ch=${bookCh}`}>Back to the book</Link>
          </div>}
        </div>
      </section>

      <div className="card"><div className="card-h"><h3>All questions</h3><span className="sub">{plural(r.score, 'right answer')}{r.total > r.score ? `, ${r.total - r.score} to learn` : ''}</span></div>
        <div className="card-b rq-list">{r.questions.map(x => <QReview key={x.id} q={x} bid={r.book_id} open={false} />)}</div></div>
    </div>
  )
}

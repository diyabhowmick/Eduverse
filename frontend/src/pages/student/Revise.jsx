import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import { Page, Icon, MathText, Modal, useToast, plural } from '../../ui'
import { when } from '../../Study'

// One place to fix weak spots: today's cards, the Mistake book, "not sure" answers, flashcards and weak topics.
const TABS = [['today', 'Today'], ['mistakes', 'Mistake book'], ['not_sure', 'Not sure'], ['cards', 'Flashcards'], ['weak', 'Weak topics']]
const KIND = { mistake: 'From your Mistake book', word: 'A word you keep opening', saved: 'A saved explanation', note: 'From your notes' }
const GRADES = [['again', 'Again', 'Soon'], ['hard', 'Hard', ''], ['good', 'Good', ''], ['easy', 'Easy', '']]

function Session({ cards, onDone }) {
  const [i, setI] = useState(0); const [flip, setFlip] = useState(false); const [busy, setBusy] = useState(false); const toast = useToast()
  const c = cards[i]
  useEffect(() => {
    const k = e => { if (e.target.tagName === 'INPUT') return
      if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); setFlip(true) }
      if (flip && ['1', '2', '3', '4'].includes(e.key)) rate(GRADES[+e.key - 1][0]) }
    addEventListener('keydown', k); return () => removeEventListener('keydown', k)
  })
  async function rate(g) {
    if (busy) return; setBusy(true)
    try { await api(`/api/student/study/cards/${c.id}/rate`, { method: 'POST', body: { grade: g } }) } catch (e) { toast(e.message, true) }
    setBusy(false); setFlip(false)
    if (i + 1 >= cards.length) onDone(); else setI(i + 1)
  }
  if (!c) return null
  return <div className="rv-session">
    <div className="rv-prog"><i style={{ width: (i / cards.length * 100) + '%' }} /></div>
    <div className="muted" style={{ fontSize: 12.5, textAlign: 'center' }}>Card {i + 1} of {cards.length} · {KIND[c.kind] || ''}</div>
    <div className={'rv-flip' + (flip ? ' on' : '')} onClick={() => setFlip(true)} role="button" tabIndex={0} aria-label="Show the answer">
      <div className="rv-face rv-front"><div className="rv-q"><MathText text={c.front} /></div>{c.where && <div className="muted rv-where">{c.where}</div>}
        <span className="btn">Show answer</span></div>
      <div className="rv-face rv-back"><div className="rv-a"><MathText text={c.back} /></div></div>
    </div>
    <div className={'rv-rate' + (flip ? ' on' : '')}>{GRADES.map(([g, l], k) => <button key={g} className={'btn' + (g === 'good' ? ' primary' : '')} disabled={!flip || busy} onClick={() => rate(g)}>
      {l}<kbd>{k + 1}</kbd></button>)}</div>
  </div>
}

function MistakeCard({ m, onTry, onDismiss }) {
  return <div className="card mk-card">
    <div className="mk-top"><div className="sv-where"><b className={m.wrong_count ? 'k-mistake' : 'k-unsure'}>{m.origin || 'Test'}</b><span>{[m.book, m.topic].filter(Boolean).join(' · ')}</span></div>
      {m.not_sure && !m.wrong_count ? <span className="mk-flag">Not sure</span> : <span className="mk-dots" title="Answer it right on two different days to clear it">Cleared <i className={m.right_days > 0 ? 'f' : ''} /><i className={m.right_days > 1 ? 'f' : ''} /></span>}</div>
    <div className="mk-q"><MathText text={m.text} /></div>
    <div className="mk-ans"><div className={m.wrong_count ? 'bad' : 'good'}><small>{m.wrong_count ? 'Your answer' : 'Your answer, right'}</small><MathText text={m.my_answer || 'Left blank'} /></div>
      <div className="good"><small>Right answer</small><MathText text={m.right} /></div></div>
    {m.solution && <div className="mk-sol"><MathText text={m.solution} /></div>}
    <div className="sv-foot"><span>{m.wrong_count ? `Wrong ${plural(m.wrong_count, 'time')}` : 'Marked not sure'} · {when(m.updated_at)}</span>
      <button type="button" className="linkbtn" onClick={() => onDismiss(m)}>I know this now</button>
      {m.options?.length > 0 && <button type="button" className="sv-go" onClick={() => onTry(m)}>Try again</button>}</div>
  </div>
}

function TryAgain({ m, qs, title, onClose, onDone }) {
  const list = qs || [{ id: m.question_id, text: m.text, options: m.options, qsource: m.qsource }]
  const [i, setI] = useState(0); const [pick, setPick] = useState(''); const [res, setRes] = useState(null); const [unsure, setUnsure] = useState(false); const [score, setScore] = useState(0)
  const q = list[i]; const toast = useToast()
  async function check() {
    try { const r = await api('/api/student/study/answer', { method: 'POST', body: { qsource: q.qsource, question_id: q.id, given: pick, not_sure: unsure } }); setRes(r); if (r.correct) setScore(s => s + 1) } catch (e) { toast(e.message, true) }
  }
  function next() { if (i + 1 >= list.length) { onDone(score, list.length); return } setI(i + 1); setPick(''); setRes(null); setUnsure(false) }
  return <Modal title={title || 'Try it again'} onClose={onClose} footer={<>{!res ? <><button className={'notsure' + (unsure ? ' on' : '')} onClick={() => setUnsure(!unsure)}><span className="ns-box">{unsure ? '?' : ''}</span>Not sure</button>
      <button className="btn primary" disabled={!pick} onClick={check}>Check</button></>
    : <button className="btn primary" onClick={next}>{i + 1 >= list.length ? 'Done' : 'Next'}</button>}</>}>
    {list.length > 1 && <div className="muted" style={{ fontSize: 12.5, marginBottom: 8 }}>Question {i + 1} of {list.length}</div>}
    <div className="mk-q" style={{ marginBottom: 12 }}><MathText text={q.text} /></div>
    <div className="qf-opts">{(q.options || []).map(o => <button key={o.key} type="button" disabled={!!res}
      className={'qf-opt' + (pick === o.key ? ' on' : '') + (res && res.right.startsWith(`(${o.key})`) ? ' right' : '') + (res && pick === o.key && !res.correct ? ' wrong' : '')} onClick={() => setPick(o.key)}>
      <span>{o.key.toUpperCase()}</span><MathText text={o.text} /></button>)}</div>
    {res && <div className={'qf-res ' + (res.correct ? 'ok' : 'no')}><b>{res.correct ? 'Right!' : 'Not quite.'}</b> {res.correct ? '' : <>The answer is <MathText text={res.right} />.</>}
      {res.solution && <div style={{ marginTop: 6 }}><MathText text={res.solution} /></div>}</div>}
  </Modal>
}

export default function Revise() {
  const [sp, setSp] = useSearchParams(); const tab = sp.get('tab') || 'today'; const toast = useToast()
  const [d, setD] = useState(null); const [ms, setMs] = useState(null); const [cards, setCards] = useState(null)
  const [session, setSession] = useState(null); const [tryM, setTryM] = useState(null); const [fix, setFix] = useState(null)
  const load = () => api('/api/student/study/revise').then(setD).catch(e => toast(e.message, true))
  useEffect(() => { load() }, [])
  useEffect(() => {
    if (tab === 'mistakes' || tab === 'not_sure') { setMs(null); api('/api/student/study/mistakes?show=' + (tab === 'mistakes' ? 'open' : 'not_sure')).then(setMs).catch(() => {}) }
    if (tab === 'cards') api('/api/student/study/cards').then(setCards).catch(() => {})
  }, [tab])
  const go = t => setSp(t === 'today' ? {} : { tab: t })
  async function dismiss(m) { try { await api(`/api/student/study/mistakes/${m.id}/dismiss`, { method: 'POST' }); setMs(x => ({ ...x, items: x.items.filter(y => y.id !== m.id) })); load() } catch (e) { toast(e.message, true) } }
  async function quickfix(w) {
    try { const r = await api(`/api/student/study/quickfix?book_id=${w.book_id}&topic=${encodeURIComponent(w.topic)}`); setFix({ title: 'Quick fix: ' + w.topic, qs: r.questions.map(q => ({ ...q, qsource: r.qsource })) }) }
    catch (e) { toast(e.message, true) }
  }
  const count = { mistakes: d?.counts.open, not_sure: d?.counts.not_sure, cards: d?.counts.cards }
  const mixText = d ? Object.entries(d.mix).map(([k, n]) => `${n} ${{ mistake: n === 1 ? 'mistake' : 'mistakes', not_sure: 'not sure', word: n === 1 ? 'word' : 'words', saved: 'saved', note: n === 1 ? 'note' : 'notes' }[k]}`) : []
  const weakList = (d?.weak || [])
  return <Page title="Revise" sub="Your mistakes, the answers you were not sure about and what you saved, brought back just before you forget them.">
    <div className="seg rv-tabs">{TABS.map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => go(k)}>{l}{count[k] ? <em>{count[k]}</em> : null}</button>)}</div>
    {session ? <Session cards={session} onDone={() => { setSession(null); toast('Revision done. See you tomorrow!'); load() }} /> : <>
    {tab === 'today' && d && <>
      <div className="rv-hero">
        <div className="rv-today"><div className="k">Today's revision</div>
          <h2>{d.due_total ? `${plural(Math.min(d.due_total, 20), 'card')}, about ${Math.max(2, Math.round(Math.min(d.due_total, 20) * 1.3))} minutes` : 'All caught up'}</h2>
          {d.due_total > 0 && <div className="rv-mix">{mixText.map(t => <span key={t}>{t}</span>)}</div>}
          <div className="rv-cta">{d.due_total > 0 ? <button className="btn primary lg" onClick={() => setSession(d.due)}>Start revision</button>
            : <span>Nothing due today. Take a test or a Quick fix to find what needs work.</span>}
            {d.tomorrow > 0 && <span className="rv-next">Tomorrow: {plural(d.tomorrow, 'card')}</span>}</div>
          <div><div className="rv-streak-l">Revision streak: {plural(d.streak, 'day')}</div><div className="rv-streak">{d.week.map((x, i) => <i key={i} className={x ? 'd' : ''} />)}</div></div>
        </div>
        <div className="rv-peek">{d.due[0] ? <><div className="muted" style={{ fontSize: 12 }}>Up first · {KIND[d.due[0].kind]}</div><div className="rv-peek-q"><MathText text={d.due[0].front.split('\n')[0]} /></div>
          <div className="muted" style={{ fontSize: 12 }}>{d.due[0].where}</div></> : <><Icon n="check" s={30} /><b>You're up to date</b></>}</div>
      </div>
      <WeakTopics list={weakList} onFix={quickfix} />
    </>}
    {(tab === 'mistakes' || tab === 'not_sure') && <>
      {ms && !ms.items.length && <div className="card empty nb-empty"><Icon n="check" s={28} /><b>{tab === 'mistakes' ? 'No open mistakes' : 'Nothing marked not sure'}</b>
        <span>{tab === 'mistakes' ? 'Wrong answers from tests, practice and past papers appear here, and clear themselves once you get them right twice.' : 'Tap "Not sure" when you answer a question you guessed.'}</span></div>}
      <div className="mk-grid">{ms?.items.map(m => <MistakeCard key={m.id} m={m} onTry={setTryM} onDismiss={dismiss} />)}</div></>}
    {tab === 'cards' && <>
      {cards && !cards.length && <div className="card empty nb-empty"><Icon n="repeat" s={28} /><b>No flashcards yet</b><span>Save an explanation, or tap "Make a card" on a note.</span></div>}
      <div className="fc-grid">{cards?.map(c => <div key={c.id} className="fc-card"><div className="fc-k">{KIND[c.kind]}</div><div className="fc-front"><MathText text={c.front.split('\n')[0]} /></div>
        <div className="muted" style={{ fontSize: 12 }}>Next: {c.due <= new Date().toISOString().slice(0, 10) ? 'today' : c.due}</div></div>)}</div>
      {cards?.length > 0 && <button className="btn primary" style={{ marginTop: 16 }} onClick={() => setSession(cards.slice(0, 20))}>Practise these now</button>}</>}
    {tab === 'weak' && d && <WeakTopics list={weakList} onFix={quickfix} full />}
    </>}
    {tryM && <TryAgain m={tryM} onClose={() => setTryM(null)} onDone={() => { setTryM(null); go(tab); api('/api/student/study/mistakes?show=' + (tab === 'mistakes' ? 'open' : 'not_sure')).then(setMs); load() }} />}
    {fix && <TryAgain qs={fix.qs} title={fix.title} onClose={() => setFix(null)} onDone={(s, n) => { setFix(null); toast(`${s} of ${n} right`); load() }} />}
  </Page>
}

function WeakTopics({ list, onFix, full }) {
  return <div className="card rv-weak"><div className="card-h"><h3>Weak topics</h3><span className="sub">Where you lose the most marks, from tests, practice and "not sure"</span></div>
    {!list.length ? <div className="empty">No weak topics yet. They appear once you have answered a few questions on a topic.</div>
      : <div>{(full ? list : list.slice(0, 5)).map(w => <div key={w.book_id + w.topic} className="wk-row">
        <div className="wk-name"><b>{w.topic}</b><span className="muted">{[w.book, w.open ? plural(w.open, 'open mistake') : ''].filter(Boolean).join(' · ')}</span></div>
        <div className="wk-meter"><i style={{ width: w.accuracy + '%' }} /></div><span className="wk-pct">{w.accuracy}% right</span>
        <button className={'btn sm' + (w.accuracy < 60 ? ' primary' : '')} onClick={() => onFix(w)}>Quick fix</button></div>)}
        {!full && list.length > 5 && <Link className="linkbtn" to="?tab=weak" style={{ display: 'inline-block', marginTop: 10 }}>See all {list.length}</Link>}</div>}
  </div>
}

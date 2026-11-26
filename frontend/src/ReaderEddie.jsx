import { BookImg } from './ui'
// Eddie sits at the bottom of the reading page. Tap him to ask about the part you are reading, by voice or text.
import { useEffect, useState } from 'react'
import { api } from './api'
import { callName } from './callname'
import { EddieBot } from './Eddie'
import { useEddieChat, AskBar, Talk, Tools } from './EddieBuddy'

// Everything the book knows about a figure, as words Eddie can use.
export function figText(f) {
  const d = f.desc || {}, t = x => String(x).trim().replace(/[.\s]+$/, '')
  return [`${f.number ? 'Figure ' + f.number : 'A figure'}${f.caption ? ': ' + f.caption : ''}`, d.type && `Kind: ${d.type}`, d.summary && `What it shows: ${t(d.summary)}`,
    d.parts?.length && `Parts: ${d.parts.join('; ')}`, d.relations?.length && `How the parts relate: ${d.relations.map(t).join('. ')}`,
    d.data?.length && `Values: ${d.data.join('; ')}`, d.text_in_figure?.length && `Labels printed on it: ${d.text_in_figure.join(', ')}`].filter(Boolean).join('. ')
}
const figName = f => f.number ? `Figure ${f.number}` : 'this figure'

const me = () => { try { return JSON.parse(localStorage.getItem('ev_user') || '{}') } catch { return {} } }

export default function ReaderEddie({ bk, ch, section, sectionText, figures, focus, bookId }) {
  const first = callName(me().name)
  const [open, setOpen] = useState(false)
  const [hint, setHint] = useState('')
  const [greeted, setGreeted] = useState(false)
  const [fig, setFig] = useState(null)   // the figure the student asked about
  const [mem, setMem] = useState('')
  useEffect(() => { api(`/api/student/memory?book_id=${bk.id}&chapter=${ch.number}`).then(m => setMem(m.for_eddie)).catch(() => {}) }, [bk.id, ch.number])
  const where = section?.title || ch.title
  const c = useEddieChat({
    first,
    getContext: () => [`Name ${first}`, `Reading ${bk.title}`, [bk.board, bk.grade && 'Class ' + bk.grade, bk.subject].filter(Boolean).join(', '),
      `${ch.number ? 'Unit ' + ch.number : 'Opening pages'}: ${ch.title}`, section ? `Section on screen: ${section.number ? section.number + ' ' : ''}${section.title}` : '',
      fig ? `The student is asking about this figure. ${figText(fig)}` : '',
      `Text on screen: ${sectionText().slice(0, fig ? 1000 : 1400)}`, mem ? 'From their tests on this unit: ' + mem : '',
      !fig && figures().length ? 'Figures on screen: ' + figures().slice(0, 3).map(figText).join(' | ') : ''].filter(Boolean).join('. '),
  })

  // "Ask Eddie" on a figure: he opens, looks at that figure, and offers what he can do with it.
  useEffect(() => {
    if (!focus) return
    setFig(focus.f); setOpen(true); setHint(''); setGreeted(true)
    const f = focus.f, d = f.desc || {}
    c.talk(`Let's look at ${figName(f)}${f.caption ? ', ' + f.caption : ''}. ${d.summary ? d.summary.split(/(?<=\.)\s/)[0] + ' ' : ''}What would you like to know about it?`, { log: false })
  }, [focus]) // eslint-disable-line react-hooks/exhaustive-deps

  // A small nudge now and then, never while he is open.
  useEffect(() => {
    if (open) return
    const t1 = setTimeout(() => setHint(`Stuck on "${where}"? Ask me.`), 5000)
    const t2 = setTimeout(() => setHint(''), 11000)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [ch.number, open]) // eslint-disable-line react-hooks/exhaustive-deps

  function toggle() {
    setHint('')
    if (open) { c.stop(); setOpen(false); return }
    setOpen(true)
    if (!greeted) { setGreeted(true); c.talk(`Hi ${first}! I'm reading "${where}" with you. Ask me anything about it, or tap the mic.`, { log: false }) }
  }

  return (
    <div className={'reddie' + (open ? ' open' : '') + (c.talking ? ' is-talking' : '') + (c.listening ? ' is-listening' : '')}>
      {open && <div className="rd-panel" role="dialog" aria-label="Ask Eddie">
        <div className="bd-head">
          <div><b>Eddie</b><span>reading with you</span></div>
          <div style={{ display: 'flex', gap: 6 }}><Tools c={c} replay={() => c.talk(c.say, { log: false })} />
            <button type="button" className="bd-icon" aria-label="Close" title="Close" onClick={toggle}><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg></button></div>
        </div>
        {fig ? <div className="rd-fig"><BookImg src={`/api/content/${bookId}/${fig.image}`} alt={fig.caption || 'Figure'} />
            <div className="rd-fig-c"><span><b>{fig.number ? 'Figure ' + fig.number : 'Figure'}</b> {fig.caption}</span>
            <button type="button" className="linkbtn" onClick={() => setFig(null)}>Back to the page</button></div></div>
          : <div className="rd-where">Now reading: <b>{where}</b></div>}
        <Talk c={c} />
        {(c.thread.length < 2 || fig) && !c.busy && <div className="bd-chips">{(fig ? ['Explain this figure', 'What does each label mean?', 'Quiz me on this figure'] : ['Explain this part simply', 'Quiz me on this part', 'Summarise this unit']).map(s =>
          <button key={s} type="button" className="chip" onClick={() => c.ask(s)}>{s}</button>)}</div>}
        <AskBar c={c} placeholder={fig ? `Ask about ${figName(fig)}…` : "Ask about this page…"} />
        {c.note && <div className="bd-note">{c.note}</div>}
      </div>}
      {hint && !open && <button type="button" className="rd-hint" onClick={toggle}>{hint}</button>}
      <button type="button" className="rd-bot" onClick={toggle} aria-label={open ? 'Close Eddie' : 'Ask Eddie about this page'} title="Ask Eddie">
        <span className="bd-halo" />
        <EddieBot size={58} jet={false} mood={open ? c.mood : 'idle'} talking={c.talking} />
      </button>
    </div>
  )
}

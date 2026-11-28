import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { api } from '../../api'
import ExplainPanel from '../../ExplainPanel'
import ReaderEddie from '../../ReaderEddie'
import { EddieBot } from '../../Eddie'
import { Sheet, Icon, useNarrow, useToast, MathText, BookImg } from '../../ui'
import { NoteCard, Composer } from '../../Study'
import { listShape } from '../../listlabels'
import PageView from './PageView'
import '../../pageview.css'

const SIZES = [['15.5px', 'Small'], ['17.5px', 'Medium'], ['19.5px', 'Large'], ['22px', 'Extra large']]
const LEADS = [['1.6', 'Close'], ['1.8', 'Normal'], ['2.05', 'Loose']]
const THEMES = [['', 'Light'], ['warm', 'Warm paper'], ['night', 'Night']]
const loadLook = () => { try { return { size: '17.5px', lead: '1.8', theme: '', ...JSON.parse(localStorage.getItem('ev_reader') || '{}') } } catch { return { size: '17.5px', lead: '1.8', theme: '' } } }

// Desktop split between the book and the side panel (explain, notes, saved, mistakes): the share of their combined
// width the panel takes. It opens wider than the book, since the explanation is what a tap asked for, and the
// divider can move it. Remembered per device, next to the 'ev_reader' look settings.
const SPLIT_KEY = 'ev_reader_split', SPLIT_DEFAULT = .56, MIN_BOOK = 400, MIN_SIDE = 340, RAIL_W = 270
const loadSplit = () => { try { const v = parseFloat(localStorage.getItem(SPLIT_KEY)); return v > 0 && v < 1 ? v : SPLIT_DEFAULT } catch { return SPLIT_DEFAULT } }
const saveSplit = v => { try { localStorage.setItem(SPLIT_KEY, String(Math.round(v * 1000) / 1000)) } catch { /* private mode */ } }
// Panel width in px for a split, keeping both panes above their minimums (the panel wins on a small screen).
const sidePx = (split, room) => room > 0 ? Math.round(Math.min(Math.max(MIN_SIDE, room - MIN_BOOK), Math.max(MIN_SIDE, split * room))) : 400

function LookSheet({ look, set, onClose }) {
  const row = (label, opts, k) => <div><div className="muted" style={{ fontSize: 13, marginBottom: 6 }}>{label}</div>
    <div className="seg">{opts.map(([v, l]) => <button key={v} type="button" className={look[k] === v ? 'on' : ''} onClick={() => set({ ...look, [k]: v })}>{l}</button>)}</div></div>
  return <Sheet title="Reading comfort" onClose={onClose}><div className="rset">{row('Text size', SIZES, 'size')}{row('Line spacing', LEADS, 'lead')}{row('Page colour', THEMES, 'theme')}</div></Sheet>
}

const tex = l => { try { return katex.renderToString(l, { displayMode: true, throwOnError: false }) } catch { return l } }
const scrollToSec = (page, id) => { const el = page?.querySelector(`[data-sec="${id}"]`); if (el) page.scrollTop += el.getBoundingClientRect().top - page.getBoundingClientRect().top - 12 }
const DEPTH = { exam: 'Exam', concept_clarity: 'Concept clarity', curiosity: 'Curiosity', research: 'Research' }

function Text({ text, marks, onWord }) {
  if (!marks?.length) return text
  const out = []; let at = 0
  marks.forEach(([s, e, id], i) => {
    out.push(text.slice(at, s))
    out.push(<span key={i} className="kw" role="button" tabIndex={0} data-k={id} onClick={ev => onWord(id, ev.currentTarget)} onKeyDown={ev => (ev.key === 'Enter' || ev.key === ' ') && (ev.preventDefault(), onWord(id, ev.currentTarget))}>{text.slice(s, e)}</span>)
    at = e
  })
  out.push(text.slice(at)); return out
}

function Blk({ b, bookId, onWord, onFig }) {
  const a = { 'data-sec': b.section, id: b.id }
  switch (b.type) {
    case 'heading': return b.level === 3 ? <h3 className="sec" {...a}><span className="n">{b.number}</span>{b.text}</h3> : <h2 className="sec" {...a}>{b.number && <span className="n">{b.number}</span>}{b.text}</h2>
    case 'subheading': return <p {...a}><b>{b.text}</b></p>
    case 'paragraph': return <p {...a}><Text text={b.text} marks={b.marks} onWord={onWord} />{(b.math || []).map((m, i) => <span key={i} dangerouslySetInnerHTML={{ __html: tex(m) }} />)}</p>
    case 'list': { const L = b.ordered ? 'ol' : 'ul'; const sh = listShape(b.items); return <L {...a} className={sh.own ? 'own-labels' : undefined}>{b.items.map((it, i) => <li key={i} className={sh.sub[i] ? 'sub' : undefined}><Text text={it.text} marks={it.marks} onWord={onWord} /></li>)}</L> }
    case 'equation': return <div className="eq" {...a} dangerouslySetInnerHTML={{ __html: b.latex.map(tex).join('') }} />
    case 'figure': return <figure {...a}><BookImg src={`/api/content/${bookId}/${b.image}`} alt={b.desc?.summary || b.caption} loading="lazy" onClick={e => e.currentTarget.classList.toggle('big')} />
      <figcaption>{b.number && <b>Figure {b.number} </b>}{b.caption}
        {onFig && <button type="button" className="fig-ask" onClick={() => onFig(b)} title="Ask Eddie about this figure"><EddieBot size={18} jet={false} />Ask Eddie</button>}</figcaption></figure>
    case 'table': return <div className="tbl" {...a}>{(b.caption || b.number) && <div className="tcap"><b>{b.label || 'Table'} {b.number}</b> {b.caption}</div>}<table><tbody>{b.rows.map((r, i) => <tr key={i}>{r.map((c, j) => i === 0 ? <th key={j}>{c}</th> : <td key={j}>{c}</td>)}</tr>)}</tbody></table></div>
    case 'marker': return null
    case 'box': return <div className={'box ' + b.kind} {...a}><div className="bt">{b.title}</div>{b.children.map(c => <Blk key={c.id} b={c} bookId={bookId} onWord={onWord} onFig={onFig} />)}</div>
    default: return null
  }
}

function figuresOf(ch) { const out = []; const w = bs => bs.forEach(b => { if (b.type === 'figure') out.push(b); if (b.type === 'box') w(b.children) }); w(ch.blocks); return out }

export default function Reader() {
  const { id } = useParams(); const [sp] = useSearchParams()
  const [bk, setBk] = useState(null); const [err, setErr] = useState('')
  const [chNo, setChNo] = useState(null); const [cur, setCur] = useState(null)
  const [figAsk, setFigAsk] = useState(null)
  const [sel, setSel] = useState(null); const [selBtn, setSelBtn] = useState(null)
  // The side panel: Explain, Notes, Saved and Mistakes for this chapter. panel is null when it is closed.
  const [panel, setPanel] = useState(null); const [mine, setMine] = useState({ notes: [], saved: [], mistakes: [] }); const [draft, setDraft] = useState(null)
  const toast = useToast()
  const [look, setLookState] = useState(loadLook); const [lookOpen, setLookOpen] = useState(false)
  const setLook = l => { setLookState(l); localStorage.setItem('ev_reader', JSON.stringify(l)) }
  const narrow = useNarrow(1000)
  // Page view (the printed page) on a wide screen when this book has it; Reading view on a phone. The choice is remembered.
  const [viewPick, setViewPick] = useState(() => { try { return localStorage.getItem('ev_view') || '' } catch { return '' } })
  const pickView = v => { setViewPick(v); try { localStorage.setItem('ev_view', v) } catch { /* private mode */ } }
  const [split, setSplit] = useState(loadSplit); const [dragging, setDragging] = useState(false)
  const readerRef = useRef(); const [readerW, setReaderW] = useState(0)
  useEffect(() => {
    const el = readerRef.current; if (!el || narrow) return
    const ro = new ResizeObserver(([e]) => setReaderW(e.contentRect.width)); ro.observe(el); return () => ro.disconnect()
  }, [narrow, !!bk, chNo])   // the reader element exists once the book and its chapter are in
  const pageRef = useRef(); const lastPing = useRef(Date.now()); const curRef = useRef(null)
  useEffect(() => { api('/api/student/books/' + id).then(b => { setBk(b); const qc = sp.get('ch'); setChNo(qc != null && b.chapters.some(c => String(c.number) === qc) ? +qc : (b.progress.position?.chapter ?? (b.chapters.find(c => c.number > 0) || b.chapters[0])?.number)) }).catch(e => setErr(e.message)) }, [id])
  const ch = useMemo(() => bk?.chapters.find(c => c.number === chNo), [bk, chNo])
  const loadMine = () => ch && api(`/api/student/study/chapter?book_id=${id}&chapter=${ch.number}`).then(setMine).catch(() => {})
  useEffect(() => { loadMine() }, [ch?.number])
  // Highlights and note markers painted onto the page after it renders.
  useEffect(() => {
    const page = pageRef.current; if (!page || !ch) return
    if (page.querySelector('.pv-wrap')) return   // Page view paints its own highlights; editing its text here would break it
    page.querySelectorAll('mark.uhl').forEach(m => m.replaceWith(...m.childNodes)); page.querySelectorAll('.note-mk').forEach(m => m.remove())
    page.normalize()
    const inner = page.querySelector('.inner'); const seen = {}
    for (const n of mine.notes) {
      const el = n.block_id && page.querySelector(`[id="${CSS.escape(n.block_id)}"]`); if (!el) continue
      if (n.quote) {
        const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let t
        while ((t = w.nextNode())) { const k = t.data.indexOf(n.quote); if (k >= 0) { const r = document.createRange(); r.setStart(t, k); r.setEnd(t, k + n.quote.length)
          const m = document.createElement('mark'); m.className = 'uhl hl-' + n.color; m.dataset.note = n.id; try { r.surroundContents(m) } catch { /* crosses an element */ } break } }
      }
      if (n.kind !== 'highlight' && inner && !seen[n.block_id]) {
        seen[n.block_id] = 1; const mk = document.createElement('button'); mk.type = 'button'; mk.className = 'note-mk' + (n.kind === 'voice' ? ' voice' : '')
        mk.textContent = n.kind === 'voice' ? '\u25B6' : '\u270E'; mk.title = 'Your note'; mk.style.top = (el.offsetTop + 4) + 'px'; mk.onclick = () => setPanel('notes'); inner.appendChild(mk)
      }
    }
  }, [mine.notes, ch, look.size, look.lead, viewPick])
  const kws = useMemo(() => Object.fromEntries((ch?.keywords || []).map(k => [k.id, k])), [ch])
  // progress: on topic change and every 30 seconds while reading
  const ping = (section) => {
    if (!ch) return
    const secs = Math.round((Date.now() - lastPing.current) / 1000); lastPing.current = Date.now()
    api(`/api/student/books/${id}/progress`, { method: 'POST', body: { chapter: ch.number, section: section || curRef.current || '', seconds: document.hidden ? 0 : Math.min(secs, 300) } })
      .then(p => setBk(b => b && { ...b, progress: { ...b.progress, percent: p.percent, sections: p.sections } })).catch(() => {})
  }
  useEffect(() => { const t = setInterval(() => ping(), 30000); return () => clearInterval(t) }, [ch])
  useEffect(() => {
    if (!ch || !pageRef.current) return
    const pos = bk.progress.position
    const qs = sp.get('sec')
    if (qs && String(ch.number) === sp.get('ch')) { setTimeout(() => { scrollToSec(pageRef.current, qs); pageRef.current?.querySelectorAll(`[data-sec="${qs}"]`).forEach(e => { e.classList.add('flash'); setTimeout(() => e.classList.remove('flash'), 2400) }) }, 60) }
    else if (pos?.chapter === ch.number && pos.section) scrollToSec(pageRef.current, pos.section); else pageRef.current.scrollTop = 0
    onScroll()
    // First time in the reader: the first highlighted word gently pulses until one is tapped.
    let first = null
    try { if (localStorage.getItem('ev_hint_kw') !== '1') { first = pageRef.current.querySelector('.kw'); first?.classList.add('kw-pulse') } } catch { /* private mode */ }
    return () => first?.classList.remove('kw-pulse')
  }, [ch])
  function onScroll() {
    const page = pageRef.current; if (!page) return
    const top = page.getBoundingClientRect().top + 90; let s = null
    for (const el of page.querySelectorAll('[data-sec]')) { if (el.getBoundingClientRect().top < top) s = el.dataset.sec; else break }
    s = s || ch?.sections[0]?.id
    if (s !== curRef.current) { curRef.current = s; setCur(s); ping(s) }
    setSelBtn(null)
  }
  function explain(term, paragraph, definition, figs, keyword_id, block_id) {
    setPanel('explain')
    setSel({ term, paragraph, definition, figs, keyword_id, block_id, key: [ch.number, keyword_id, block_id, term].join('|') })
  }
  function onWord(kid, el) {
    const k = kws[kid]; if (!k) return
    try { localStorage.setItem('ev_hint_kw', '1') } catch { /* private mode */ }
    document.querySelectorAll('.kw-pulse').forEach(x => x.classList.remove('kw-pulse'))
    document.querySelectorAll('.kw.sel').forEach(x => x.classList.remove('sel')); el.classList.add('sel')
    const figs = figuresOf(ch).filter(f => ((f.caption || '') + ' ' + (f.desc?.summary || '')).toLowerCase().includes(k.key)).slice(0, 2)
    explain(k.term, el.closest('p,li')?.textContent || '', k.definition || '', figs, String(kid), el.closest('[id]')?.id || '')
  }
  // The digital block on printed page n that holds this text: gives Page view the same context the Reading view has.
  function blockFor(n, text) {
    const want = (text || '').toLowerCase(); let first = null, hit = null
    const walk = bs => bs.forEach(b => {
      if (hit) return
      if (b.type === 'box') return walk(b.children)
      const on = b.page === n || b.page_end === n
      if (!on) return
      const tx = b.type === 'list' ? b.items.map(i => i.text).join(' ') : (b.text || b.caption || '')
      if (!first && tx) first = { ...b, tx }
      if (want && tx.toLowerCase().includes(want.slice(0, 60))) hit = { ...b, tx }
    })
    walk(ch.blocks)
    return hit || first
  }
  function onPageWord(kid, el, n) {
    const k = kws[kid]; if (!k) return
    try { localStorage.setItem('ev_hint_kw', '1') } catch { /* private mode */ }
    document.querySelectorAll('.kw.sel').forEach(x => x.classList.remove('sel')); el.classList.add('sel')
    const b = blockFor(n, k.key)
    const figs = figuresOf(ch).filter(f => ((f.caption || '') + ' ' + (f.desc?.summary || '')).toLowerCase().includes(k.key)).slice(0, 2)
    explain(k.term, b?.tx || '', k.definition || '', figs, String(kid), b?.id || '')
  }
  function onMouseUp() {
    setTimeout(() => {
      const s = getSelection(); const t = s.toString().trim()
      if (!t || t.length < 2 || t.length > 400) return setSelBtn(null)
      const r = s.getRangeAt(0).getBoundingClientRect()
      const host = s.anchorNode?.parentElement
      const pv = host?.closest('[data-pv-page]')
      if (pv) {   // Page view: the text is laid over the printed page, so find the block it came from
        const b = blockFor(+pv.dataset.pvPage, t)
        return setSelBtn({ t, x: r.left, y: r.bottom + 6, para: b?.tx || '', block: b?.id || '', section: b?.section || cur || '' })
      }
      setSelBtn({ t, x: r.left, y: r.bottom + 6, para: host?.closest('p,li')?.textContent || '', block: host?.closest('[id]')?.id || '', section: host?.closest('[data-sec]')?.dataset.sec || cur || '' })
    }, 0)
  }
  function close() { setPanel(null); setSel(null); setDraft(null); document.querySelectorAll('.kw.sel').forEach(x => x.classList.remove('sel')) }
  function noteAt(b) { setDraft({ book_id: +id, chapter: ch.number, section: b.section || cur || '', block_id: b.block || '', quote: b.t.slice(0, 1200) }); setPanel('notes') }
  async function highlight(b) {
    try { await api('/api/student/study/notes', { method: 'POST', body: { kind: 'highlight', book_id: +id, chapter: ch.number, section: b.section || '', block_id: b.block || '', quote: b.t.slice(0, 1200), color: 'yellow' } }); loadMine() }
    catch (e) { toast(e.message, true) }
  }
  async function delNote(n) { try { await api('/api/student/study/notes/' + n.id, { method: 'DELETE' }); loadMine() } catch (e) { toast(e.message, true) } }
  if (err) return <div className="page"><div className="card empty">{err} <Link to="/student">Back to home</Link></div></div>
  if (!bk || !ch) return <div className="page"><div className="empty">Opening your book</div></div>
  const tail = s => !s.number && !s.id.endsWith('-intro')
  const secs = ch.sections.filter(s => !s.id.endsWith('-intro') || ch.blocks.some(b => b.section === s.id))
  let sepShown = false
  const counts = { notes: mine.notes.length, saved: mine.saved.length, mistakes: mine.mistakes.length }
  const secTitle = ch.sections.find(x => x.id === cur)?.title || ch.title
  const hasPages = !!bk.layout?.available
  const pageMode = hasPages && (viewPick ? viewPick === 'page' : !narrow)
  // Page view folds the topic list away while the panel is open (pageview.css), so the book and panel share its room too.
  const room = Math.max(0, readerW - (pageMode && panel ? 0 : RAIL_W))
  const sideW = sidePx(split, room)
  const bookPct = room ? Math.round(100 * (room - sideW) / room) : 50
  const setSide = px => { const s = room ? sidePx(px / room, room) / room : split; setSplit(s); return s }
  function dragStart(e) {
    if (e.button !== 0 || !room) return
    e.preventDefault()
    const el = e.currentTarget, right = readerRef.current.getBoundingClientRect().right
    el.setPointerCapture(e.pointerId); setDragging(true)
    let last = split
    const move = ev => { last = setSide(right - ev.clientX) }
    const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); el.removeEventListener('pointercancel', up); setDragging(false); saveSplit(last) }
    el.addEventListener('pointermove', move); el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up)
  }
  function dragKey(e) {
    const step = e.shiftKey ? 80 : 24
    const px = { ArrowLeft: sideW + step, ArrowRight: sideW - step, Home: room, End: 0 }[e.key]
    if (px === undefined) return
    e.preventDefault(); saveSplit(setSide(px))
  }
  const side = <>
    <div className="sside-h"><div><div className="k">{panel === 'explain' && sel ? 'Explained for you' : 'Unit ' + ch.number}</div><h2>{panel === 'explain' && sel ? sel.term : secTitle}</h2></div>
      {!narrow && <button className="btn ghost sm" aria-label="Close" onClick={close}><Icon n="x" s={18} /></button>}</div>
    <div className="rd-tabs" role="tablist">{[['explain', 'Explain'], ['notes', 'Notes'], ['saved', 'Saved'], ['mistakes', 'Mistakes']].map(([k, l]) =>
      <button key={k} role="tab" aria-selected={panel === k} className={panel === k ? 'on' : ''} onClick={() => setPanel(k)}>{l}{counts[k] ? <em>{counts[k]}</em> : null}</button>)}</div>
    {panel === 'explain' && (!sel ? <div className="empty" style={{ marginTop: 30 }}><b>Tap a highlighted word</b><br />or select any words and choose Explain.</div> : <>
      {bk.rules.exam_mode && <div className="note" style={{ marginBottom: 10 }}>{bk.rules.exam_mode}: exam answers only</div>}
      <div className="scard"><div className="h">What your book says</div>{sel.definition || 'Your book uses this word without defining it here.'}</div>
      <div className="scard ai"><div className="h">Explanation</div>
        <ExplainPanel key={sel.key} styles={bk.rules.allowed_depths} onSaved={loadMine} request={{ scope: 'book', book_id: +id, chapter: ch.number, keyword_id: sel.keyword_id || null, block_id: sel.block_id || null,
          term: sel.term, paragraph: sel.paragraph, definition: sel.definition, figures: sel.figs.map(f => [f.number && 'Figure ' + f.number, f.caption, f.desc?.summary].filter(Boolean).join(': ')) }} /></div>
      {sel.figs.map(f => <div className="scard" key={f.id}><div className="h">{f.number ? 'Figure ' + f.number : 'Figure'}</div><BookImg src={`/api/content/${id}/${f.image}`} alt="" /><div className="muted" style={{ fontSize: 13 }}>{f.caption}</div></div>)}</>)}
    {panel === 'notes' && <div className="rd-list">
      {draft ? <Composer key={draft.quote} at={draft} onCancel={() => setDraft(null)} onSaved={() => { setDraft(null); loadMine(); toast('Saved to your Notebook') }} />
        : <button className="btn rd-new" onClick={() => setDraft({ book_id: +id, chapter: ch.number, section: cur || '', block_id: '', quote: '' })}><Icon n="note" s={15} />New note on this unit</button>}
      {mine.notes.map(n => <NoteCard key={n.id} n={n} compact onDelete={delNote} onOpen={x => { const el = x.block_id && pageRef.current?.querySelector(`[id="${CSS.escape(x.block_id)}"]`); if (el) { pageRef.current.scrollTop += el.getBoundingClientRect().top - pageRef.current.getBoundingClientRect().top - 40; el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 2400) } }} />)}
      {!mine.notes.length && !draft && <div className="muted rd-empty">Select words in the book and choose Note, Highlight or Voice.</div>}</div>}
    {panel === 'saved' && <div className="rd-list">{mine.saved.map(x => <div key={x.id} className="sv-card compact"><div className="sv-where"><b className="k-saved">Saved</b><span>{x.path.join(' › ')}</span></div>
      <div className="sv-body"><b>{x.term}</b> <MathText text={x.text.length > 300 ? x.text.slice(0, 300) + '...' : x.text} /></div></div>)}
      {!mine.saved.length && <div className="muted rd-empty">Tap the star on an explanation to keep it here and in your Notebook.</div>}</div>}
    {panel === 'mistakes' && <div className="rd-list">{mine.mistakes.map(m => <div key={m.id} className="sv-card compact"><div className="sv-where"><b className="k-mistake">{m.origin || 'Test'}</b><span>{m.topic}</span></div>
      <div className="sv-body"><MathText text={m.text} /></div>
      <div className="mk-ans"><div className={m.wrong_count ? 'bad' : 'good'}><small>You</small><MathText text={m.my_answer || 'Blank'} /></div><div className="good"><small>Right</small><MathText text={m.right} /></div></div></div>)}
      {!mine.mistakes.length && <div className="muted rd-empty">No open mistakes from this unit's tests.</div>}
      {mine.mistakes.length > 0 && <Link className="btn sm" to="/student/revise?tab=mistakes">Open the Mistake book</Link>}</div>}
  </>
  return (
    <div ref={readerRef} className={'sreader' + (panel && !narrow ? ' has-side' : '') + (pageMode ? ' pv-on' : '') + (dragging ? ' dragging' : '')} style={narrow ? undefined : { '--sw': sideW + 'px' }}>
      <nav className="srail">
        <Link to="/student" className="btn ghost sm">My books</Link>
        <div className="sbook">{bk.title}<div className="bar-track" style={{ marginTop: 6 }}><i style={{ width: bk.progress.percent + '%' }} /></div><span className="muted" style={{ fontSize: 12 }}>{bk.progress.percent}% of the book read</span></div>
        <select className="input" value={chNo} onChange={e => setChNo(+e.target.value)}>{bk.chapters.map(c => <option key={c.number} value={c.number}>{c.number ? `Unit ${c.number}: ` : ''}{c.title}</option>)}</select>
        <div className="stopics">{secs.map(s => { const sep = tail(s) && !sepShown; if (sep) sepShown = true; return <div key={s.id}>{sep && <div className="sep" />}
          <a className={'l' + s.level + (cur === s.id ? ' cur' : '') + (bk.progress.sections.includes(s.id) ? ' done' : '')} onClick={() => scrollToSec(pageRef.current, s.id)}>
            {s.number && <span className="num">{s.number}</span>}{s.title}</a></div> })}</div>
      </nav>
      <article className={'spage ' + look.theme} style={{ '--rs': look.size, '--rl': look.lead }} ref={pageRef} onScroll={onScroll} onMouseUp={onMouseUp}>
        <div className="rbar"><Link to="/student" className="btn ghost sm" aria-label="Back to home"><Icon n="left" s={18} /></Link>
          <select className="input" aria-label="Chapter" value={chNo} onChange={e => setChNo(+e.target.value)}>{bk.chapters.map(c => <option key={c.number} value={c.number}>{c.number ? `Unit ${c.number}: ` : ''}{c.title}</option>)}</select>
          <button className="btn ghost sm" onClick={() => setLookOpen(true)} aria-label="Reading comfort"><Icon n="text" s={18} /></button></div>
        <div className="inner">
          <div className="chap-head"><span className="u">{ch.number ? `Unit ${ch.number}` : 'Before Unit 1'}</span><h1>{ch.title}</h1><span className="muted chap-tip">Tap a <span className="kw demo">highlighted word</span> to have it explained, or select any words.</span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {hasPages && <span className="seg pv-switch" role="group" aria-label="How to show the book">
              <button type="button" className={pageMode ? 'on' : ''} onClick={() => pickView('page')} title="The printed page, exactly as in the textbook">Page view</button>
              <button type="button" className={!pageMode ? 'on' : ''} onClick={() => pickView('flow')} title="Flowing text you can resize">Reading view</button></span>}
            <button className="btn ghost sm" onClick={() => setPanel('notes')}><Icon n="note" s={16} />My notes{mine.notes.length ? ` (${mine.notes.length})` : ''}</button>
            {!pageMode && <button className="btn ghost sm" onClick={() => setLookOpen(true)}><Icon n="text" s={16} />Text size and colour</button>}</span></div>
          {pageMode ? <PageView bookId={id} layout={bk.layout} ch={ch} notes={mine.notes} onWord={onPageWord} />
            : ch.blocks.map(b => <Blk key={b.id} b={b} bookId={id} onWord={onWord} onFig={f => setFigAsk({ f, n: Date.now() })} />)}
          <div className="chap-end">
            <div style={{ flex: 1, minWidth: 200 }}><b>{ch.number ? `End of unit ${ch.number}` : `End of ${ch.title || "the opening pages"}`}</b><div className="muted" style={{ fontSize: 13 }}>{bk.tests?.[ch.number] ? 'Check what stayed with you. Eddie will go through anything you miss.' : bk.practice_packs?.length ? 'Check what stayed with you: try past exam questions from this chapter.' : bk.chapters.find(c => c.number > ch.number) ? 'Well done. On to the next one.' : 'Well done. You have reached the end of this book.'}</div></div>
            {bk.tests?.[ch.number] > 0 && <div className="chap-test"><EddieBot size={34} jet={false} />
              <Link className="btn primary" to={`/student/test/${id}/${ch.number}?level=quick`}>Quick check ({Math.min(5, bk.tests[ch.number])})</Link>
              {bk.tests[ch.number] > 5 && <Link className="btn" to={`/student/test/${id}/${ch.number}?level=chapter`}>Chapter test ({Math.min(15, bk.tests[ch.number])})</Link>}</div>}
            {bk.practice_packs?.map(p => p.owned ? <Link key={p.id} className="btn" to={`/student/exam/${p.id}?tab=practice&chapter=${encodeURIComponent(ch.title)}`}>Practise this chapter</Link>
              : <Link key={p.id} className="btn" to="/student/store">Get {p.title} to practise</Link>)}
            {bk.chapters.find(c => c.number > ch.number) && <button className="btn primary lg inline" onClick={() => setChNo(bk.chapters.find(c => c.number > ch.number).number)}>Next unit<Icon n="right" s={18} /></button>}</div>
        </div>
      </article>
      <aside className="sside" id="reader-side" aria-hidden={!panel || narrow}>
        {panel && !narrow && <div className="sside-in" key={panel === 'explain' ? sel?.key : 'study'}>{side}</div>}
      </aside>
      {panel && !narrow && <div className="sdivider" role="separator" tabIndex={0} aria-orientation="vertical" aria-controls="reader-side"
        aria-label="Resize the book and the side panel" aria-valuemin={0} aria-valuemax={100} aria-valuenow={bookPct} aria-valuetext={`Book ${bookPct}%, panel ${100 - bookPct}%`}
        title="Drag to resize, or use the arrow keys. Double-click to reset." onPointerDown={dragStart} onKeyDown={dragKey}
        onDoubleClick={() => { setSplit(SPLIT_DEFAULT); saveSplit(SPLIT_DEFAULT) }}><i /></div>}
      {narrow && panel && <Sheet title={panel === 'explain' ? sel?.term : 'This unit'} onClose={close}>{side}</Sheet>}
      <ReaderEddie bk={bk} ch={ch} section={ch.sections.find(s => s.id === cur)} focus={figAsk} bookId={id}
        figures={() => figuresOf(ch).filter(f => f.section === (cur || ch.sections[0]?.id))}
        sectionText={() => [...(pageRef.current?.querySelectorAll(`[data-sec="${cur || ch.sections[0]?.id}"]`) || [])].map(e => e.innerText).join(' ').replace(/\s+/g, ' ')} />
      {lookOpen && <LookSheet look={look} set={setLook} onClose={() => setLookOpen(false)} />}
      {selBtn && <div className="seltools" style={{ left: Math.min(selBtn.x, innerWidth - 330), top: selBtn.y }} onMouseDown={e => e.preventDefault()}>
        {selBtn.t.length <= 60 && <button onClick={() => { explain(selBtn.t, selBtn.para, '', [], null, selBtn.block); setSelBtn(null); getSelection().removeAllRanges() }}>Explain</button>}
        <button className="on" onClick={() => { noteAt(selBtn); setSelBtn(null) }}><Icon n="note" s={14} />Note</button>
        <button onClick={() => { highlight(selBtn); setSelBtn(null); getSelection().removeAllRanges() }}><span className="hl-dot" />Highlight</button>
        <button onClick={() => { noteAt(selBtn); setSelBtn(null) }}><Icon n="mic" s={14} />Voice</button></div>}
    </div>
  )
}

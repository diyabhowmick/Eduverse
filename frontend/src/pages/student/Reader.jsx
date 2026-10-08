import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { api } from '../../api'

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

function Blk({ b, bookId, onWord }) {
  const a = { 'data-sec': b.section, id: b.id }
  switch (b.type) {
    case 'heading': return b.level === 3 ? <h3 className="sec" {...a}><span className="n">{b.number}</span>{b.text}</h3> : <h2 className="sec" {...a}>{b.number && <span className="n">{b.number}</span>}{b.text}</h2>
    case 'subheading': return <p {...a}><b>{b.text}</b></p>
    case 'paragraph': return <p {...a}><Text text={b.text} marks={b.marks} onWord={onWord} />{(b.math || []).map((m, i) => <span key={i} dangerouslySetInnerHTML={{ __html: tex(m) }} />)}</p>
    case 'list': { const L = b.ordered ? 'ol' : 'ul'; return <L {...a}>{b.items.map((it, i) => <li key={i}><Text text={it.text} marks={it.marks} onWord={onWord} /></li>)}</L> }
    case 'equation': return <div className="eq" {...a} dangerouslySetInnerHTML={{ __html: b.latex.map(tex).join('') }} />
    case 'figure': return <figure {...a}><img src={`/api/content/${bookId}/${b.image}`} alt={b.desc?.summary || b.caption} loading="lazy" onClick={e => e.currentTarget.classList.toggle('big')} />{(b.caption || b.number) && <figcaption>{b.number && <b>Figure {b.number} </b>}{b.caption}</figcaption>}</figure>
    case 'table': return <div className="tbl" {...a}>{(b.caption || b.number) && <div className="tcap"><b>{b.label || 'Table'} {b.number}</b> {b.caption}</div>}<table><tbody>{b.rows.map((r, i) => <tr key={i}>{r.map((c, j) => i === 0 ? <th key={j}>{c}</th> : <td key={j}>{c}</td>)}</tr>)}</tbody></table></div>
    case 'marker': return null
    case 'box': return <div className={'box ' + b.kind} {...a}><div className="bt">{b.title}</div>{b.children.map(c => <Blk key={c.id} b={c} bookId={bookId} onWord={onWord} />)}</div>
    default: return null
  }
}

function figuresOf(ch) { const out = []; const w = bs => bs.forEach(b => { if (b.type === 'figure') out.push(b); if (b.type === 'box') w(b.children) }); w(ch.blocks); return out }

export default function Reader() {
  const { id } = useParams()
  const [bk, setBk] = useState(null); const [err, setErr] = useState('')
  const [chNo, setChNo] = useState(null); const [cur, setCur] = useState(null)
  const [sel, setSel] = useState(null); const [depth, setDepth] = useState(null)
  // Tapping a word is free — that answer was written while the book was with a
  // reviewer. Asking your own question is the one thing that costs something
  // every time, so it is capped per student per day and the count is shown.
  const [q, setQ] = useState(''); const [asked, setAsked] = useState([])
  const [quota, setQuota] = useState(null); const [asking, setAsking] = useState(false)
  const [ans, setAns] = useState({}); const [selBtn, setSelBtn] = useState(null)
  const pageRef = useRef(); const lastPing = useRef(Date.now()); const curRef = useRef(null)
  useEffect(() => { api('/api/student/books/' + id).then(b => { setBk(b); setChNo(b.progress.position?.chapter || b.chapters[0]?.number); setDepth(b.rules.allowed_depths.includes('concept_clarity') ? 'concept_clarity' : b.rules.allowed_depths[0]) }).catch(e => setErr(e.message)) }, [id])
  const ch = useMemo(() => bk?.chapters.find(c => c.number === chNo), [bk, chNo])
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
    if (pos?.chapter === ch.number && pos.section) scrollToSec(pageRef.current, pos.section); else pageRef.current.scrollTop = 0
    onScroll()
  }, [ch])
  function onScroll() {
    const page = pageRef.current; if (!page) return
    const top = page.getBoundingClientRect().top + 90; let s = null
    for (const el of page.querySelectorAll('[data-sec]')) { if (el.getBoundingClientRect().top < top) s = el.dataset.sec; else break }
    s = s || ch?.sections[0]?.id
    if (s !== curRef.current) { curRef.current = s; setCur(s); ping(s) }
    setSelBtn(null)
  }
  useEffect(() => { api('/api/ask/quota').then(setQuota).catch(() => {}) }, [])

  async function ask() {
    const text = q.trim()
    if (!text || asking) return
    setAsking(true)
    try {
      const para = document.querySelector('.spage .inner p')?.textContent || ''
      const r = await api('/api/ask', { method: 'POST', body: {
        book_id: +id, section: ch?.number ? String(ch.number) : '', passage: para, question: text } })
      setAsked(x => [...x, { q: text, a: r.answer, counted: r.counted }])
      setQuota({ used_today: r.used_today, cap: r.cap, left: r.left,
                 pool_left: r.pool_left, pool_total: r.pool_total })
      setQ('')
    } catch (e) {
      setAsked(x => [...x, { q: text, a: e.message, counted: false }])
    } finally { setAsking(false) }
  }

  async function explain(term, paragraph, definition, figs, d = depth) {
    const key = term + '|' + d
    setSel({ term, paragraph, definition, figs, key }); if (ans[key]?.text) return
    setAns(a => ({ ...a, [key]: { loading: true } }))
    try {
      const r = await api('/api/explain', { method: 'POST', body: { term, paragraph, definition, figures: figs.map(f => [f.number && 'Figure ' + f.number, f.caption, f.desc?.summary].filter(Boolean).join(': ')), depth: d, chapter: ch.title, book_id: +id, book: { class: bk.grade, subject: bk.subject, board: bk.board } } })
      setAns(a => ({ ...a, [key]: { text: r.text, meta: `${r.provider} ${r.model}` } }))
    } catch (e) { setAns(a => ({ ...a, [key]: { error: e.message } })) }
  }
  function onWord(kid, el) {
    const k = kws[kid]; if (!k) return
    document.querySelectorAll('.kw.sel').forEach(x => x.classList.remove('sel')); el.classList.add('sel')
    const figs = figuresOf(ch).filter(f => ((f.caption || '') + ' ' + (f.desc?.summary || '')).toLowerCase().includes(k.key)).slice(0, 2)
    explain(k.term, el.closest('p,li')?.textContent || '', k.definition || '', figs)
  }
  function onMouseUp() {
    setTimeout(() => {
      const s = getSelection(); const t = s.toString().trim()
      if (!t || t.length < 2 || t.length > 60 || t.split(/\s+/).length > 6) return setSelBtn(null)
      const r = s.getRangeAt(0).getBoundingClientRect()
      setSelBtn({ t, x: r.left, y: r.bottom + 6, para: s.anchorNode?.parentElement?.closest('p,li')?.textContent || '' })
    }, 0)
  }
  if (err) return <div className="page"><div className="card empty">{err} <Link to="/student">Back to home</Link></div></div>
  if (!bk || !ch) return <div className="page"><div className="empty">Opening your book</div></div>
  const a = sel && ans[sel.key]
  const tail = s => !s.number && !s.id.endsWith('-intro')
  const secs = ch.sections.filter(s => !s.id.endsWith('-intro') || ch.blocks.some(b => b.section === s.id))
  let sepShown = false
  return (
    <div className="sreader">
      <nav className="srail">
        <Link to="/student" className="btn ghost sm">My books</Link>
        <div className="sbook">{bk.title}<div className="bar-track" style={{ marginTop: 6 }}><i style={{ width: bk.progress.percent + '%' }} /></div><span className="muted" style={{ fontSize: 12 }}>{bk.progress.percent}% of the book read</span></div>
        <select className="input" value={chNo} onChange={e => setChNo(+e.target.value)}>{bk.chapters.map(c => <option key={c.number} value={c.number}>Unit {c.number}: {c.title}</option>)}</select>
        <div className="stopics">{secs.map(s => { const sep = tail(s) && !sepShown; if (sep) sepShown = true; return <div key={s.id}>{sep && <div className="sep" />}
          <a className={'l' + s.level + (cur === s.id ? ' cur' : '') + (bk.progress.sections.includes(s.id) ? ' done' : '')} onClick={() => scrollToSec(pageRef.current, s.id)}>
            {s.number && <span className="num">{s.number}</span>}{s.title}</a></div> })}</div>
      </nav>
      <article className="spage" ref={pageRef} onScroll={onScroll} onMouseUp={onMouseUp}>
        <div className="inner">
          <div className="chap-head"><span className="u">Unit {ch.number}</span><h1>{ch.title}</h1><span className="muted">Tap a highlighted word to have it explained, or select any words.</span></div>
          {ch.blocks.map(b => <Blk key={b.id} b={b} bookId={id} onWord={onWord} />)}
          <div className="chap-next">{bk.chapters.find(c => c.number > ch.number) && <button className="btn primary" onClick={() => setChNo(bk.chapters.find(c => c.number > ch.number).number)}>Next unit</button>}</div>
        </div>
      </article>
      <aside className="sside">
        {!sel ? <div className="empty"><b>Tap a highlighted word</b><br />or select any words and press Explain.{bk.rules.exam_mode && <div className="note" style={{ marginTop: 12 }}>{bk.rules.exam_mode}: exam answers only</div>}</div> : <>
          <h2>{sel.term}</h2>
          <div className="scard"><div className="h">What your book says</div>{sel.definition || 'Your book uses this word without defining it here.'}</div>
          <div className="scard ai"><div className="h">Explanation</div>
            <div className="depths">{bk.rules.allowed_depths.map(d => <button key={d} className={d === depth ? 'on' : ''} onClick={() => { setDepth(d); explain(sel.term, sel.paragraph, sel.definition, sel.figs, d) }}>{DEPTH[d]}</button>)}</div>
            {a?.loading && <div className="muted">Explaining {sel.term}<span className="dots" /></div>}
            {a?.error && <div className="muted">{a.error}</div>}
            {a?.text && <div className="answer">{a.text}<span className="meta">{a.meta}</span></div>}</div>
          {sel.figs.map(f => <div className="scard" key={f.id}><div className="h">{f.number ? 'Figure ' + f.number : 'Figure'}</div><img src={`/api/content/${id}/${f.image}`} alt="" /><div className="muted" style={{ fontSize: 13 }}>{f.caption}</div></div>)}
        </>}
        <div className="askbox">
          <div className="h">Ask your own question
            {quota && <span className={'tag ' + (quota.left > 3 ? 'ok' : quota.left > 0 ? 'warn' : 'bad')}>
              {quota.left} left today</span>}</div>
          {asked.map((x, i) => <div key={i} className="asked">
            <b>{x.q}</b><div>{x.a}</div>
            {!x.counted && <span className="free">this one did not use a question</span>}
          </div>)}
          <div className="askrow">
            <input value={q} placeholder="Ask about this page…"
              onChange={e => setQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && ask()} />
            <button className="btn primary sm" onClick={ask} disabled={asking || !q.trim()}>
              {asking ? '…' : 'Ask'}</button>
          </div>
          <div className="muted" style={{ fontSize: 11.5, marginTop: 8, lineHeight: 1.5 }}>
            Tapping a highlighted word is always free. Only your own questions count, and a question
            we cannot answer from this page does not.
          </div>
        </div>
      </aside>
      {selBtn && <button className="selbtn" style={{ left: selBtn.x, top: selBtn.y }} onMouseDown={e => { e.preventDefault(); explain(selBtn.t, selBtn.para, '', []); setSelBtn(null); getSelection().removeAllRanges() }}>Explain</button>}
    </div>
  )
}

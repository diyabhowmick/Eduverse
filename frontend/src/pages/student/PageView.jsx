import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

/* Page view: the printed page exactly as the textbook prints it, with the book's real text laid over it.

   The text is invisible but real, so everything the Reading view does still works here: tap a highlighted word,
   select words to explain, highlight, take a note. Two columns, side boxes, text wrapped round pictures and
   labels on diagrams look exactly like the book because they are the book.

   Each line of the page is one span, placed on the printed line and stretched to its width, so a selection
   follows the printed words. */

const pad = n => String(n).padStart(4, '0')
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function useWidth(ref) {
  const [w, setW] = useState(0)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(e => setW(Math.round(e[0].contentRect.width)))
    ro.observe(ref.current); return () => ro.disconnect()
  }, [])
  return w
}

// Splits one line into plain text, important words (first use on the page) and the student's highlights.
function pieces(text, kwRes, used, quotes) {
  const marks = []
  for (const k of kwRes) {
    if (used.has(k.id)) continue
    const m = k.re.exec(text)
    if (m) { marks.push([m.index, m.index + m[0].length, 'kw', k.id]); used.add(k.id) }
  }
  for (const q of quotes) {
    const i = text.toLowerCase().indexOf(q.text)
    if (i >= 0) marks.push([i, i + q.text.length, 'hl', q.color])
  }
  marks.sort((a, b) => a[0] - b[0])
  const out = []; let at = 0
  for (const [s, e, kind, v] of marks) {
    if (s < at) continue
    if (s > at) out.push({ t: text.slice(at, s) })
    out.push({ t: text.slice(s, e), kind, v }); at = e
  }
  if (at < text.length) out.push({ t: text.slice(at) })
  return out
}

function Page({ bookId, n, w, h, approx, kwRes, quotes, anchors, onWord }) {
  const box = useRef(); const width = useWidth(box)
  const [data, setData] = useState(null); const [err, setErr] = useState(false)
  useEffect(() => {
    let live = true
    fetch(`/api/content/${bookId}/layout/p${pad(n)}.json`, { credentials: 'same-origin' })
      .then(r => { if (!r.ok) throw new Error(); return r.json() }).then(d => live && setData(d)).catch(() => live && setErr(true))
    return () => { live = false }
  }, [bookId, n])
  const scale = width / w
  // stretch each line to the printed width once the browser has laid it out
  useLayoutEffect(() => {
    if (!box.current || !scale) return
    box.current.querySelectorAll('.pv-line').forEach(el => {
      el.style.transform = 'none'
      const want = +el.dataset.w * scale, got = el.scrollWidth
      if (got > 0 && want > 0) el.style.transform = `scaleX(${want / got})`
    })
  }, [data, scale])
  const lines = useMemo(() => {
    if (!data) return []
    const used = new Set()   // each important word once per page, at its first printed use
    return data.lines.map(l => ({ l, parts: l[5] ? [{ t: l[4] }] : pieces(l[4], kwRes, used, quotes) }))
  }, [data, kwRes, quotes])
  return <div className="pv-page" ref={box} data-pv-page={n} style={{ aspectRatio: `${w} / ${h}` }}>
    <img src={`/api/content/${bookId}/layout/p${pad(n)}.webp`} alt={`Page ${n}`} loading="lazy" draggable="false"
      onError={() => setErr(true)} />
    {anchors.map((a, i) => {
      const key = (a.text || '').toLowerCase().slice(0, 24)
      const line = key && data?.lines.find(l => l[4].toLowerCase().includes(key))
      return <i key={a.sec} className="pv-anchor" data-sec={a.sec} style={{ top: ((line ? line[1] : i * 4) / h * 100) + '%' }} />
    })}
    {scale > 0 && <div className="pv-text" aria-label={`Text of page ${n}`}>
      {lines.map(({ l, parts }, i) => {
        const [x0, y0, x1, y1] = l
        const lh = Math.max(4, (y1 - y0) * scale)
        return <span key={i} className="pv-line" data-w={x1 - x0} style={{ left: x0 * scale, top: y0 * scale, height: lh, fontSize: lh * 0.86 }}>
          {parts.map((p, j) => p.kind === 'kw'
            ? <span key={j} className="pv-kw kw" role="button" tabIndex={0} data-k={p.v} onClick={e => onWord(p.v, e.currentTarget, n)}
              onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onWord(p.v, e.currentTarget, n))}>{p.t}</span>
            : p.kind === 'hl' ? <mark key={j} className={'pv-hl hl-' + p.v}>{p.t}</mark> : p.t)}
          {'\n'}</span>
      })}
    </div>}
    {err && <div className="pv-err">This page could not be loaded. Switch to Reading view.</div>}
    <div className="pv-no">{approx ? `Page ${n} · scanned page: selection is approximate` : `Page ${n}`}</div>
  </div>
}

export default function PageView({ bookId, layout, ch, notes, onWord }) {
  // The pages this unit spans, from the blocks that came from them.
  const pages = useMemo(() => {
    let lo = Infinity, hi = -Infinity
    const walk = bs => bs.forEach(b => {
      if (b.page != null) { lo = Math.min(lo, b.page); hi = Math.max(hi, b.page_end || b.page) }
      if (b.type === 'box') walk(b.children)
    })
    walk(ch.blocks)
    return layout.pages.filter(p => p.n >= lo && p.n <= hi)
  }, [layout, ch])
  // Each section starts where its heading is printed.
  const anchors = useMemo(() => {
    const out = {}
    const walk = bs => bs.forEach(b => {
      if (b.type === 'box') return walk(b.children)
      if (b.section && b.page != null && !(out[b.page] || []).some(a => a.sec === b.section)) {
        (out[b.page] ||= []).push({ sec: b.section, text: b.type === 'heading' ? b.text : '' })
      }
    })
    walk(ch.blocks)
    return out
  }, [ch])
  const kwRes = useMemo(() => (ch.keywords || []).map(k => ({ id: k.id, re: new RegExp(`(?<![A-Za-z])${esc(k.key || k.term)}(?:s|es)?(?![A-Za-z])`, 'i') })), [ch])
  const quotes = useMemo(() => (notes || []).filter(x => x.quote && x.quote.length >= 3).map(x => ({ text: x.quote.toLowerCase().slice(0, 120), color: x.color || 'yellow' })), [notes])
  return <div className="pv-wrap">
    {pages.map(p => <Page key={p.n} n={p.n} w={p.w} h={p.h} approx={p.approx} bookId={bookId} kwRes={kwRes} quotes={quotes} onWord={onWord} anchors={anchors[p.n] || []} />)}
    {!pages.length && <div className="empty">This unit has no printed pages to show. Switch to Reading view.</div>}
  </div>
}

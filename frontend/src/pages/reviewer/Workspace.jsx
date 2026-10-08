import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { api } from '../../api'
import { Modal, Field, useToast, Icon } from '../../ui'

const tex = l => { try { return katex.renderToString(l, { displayMode: true, throwOnError: false }) } catch { return l } }

function Marked({ text, marks, kws }) {
  if (!marks?.length) return text
  const out = []; let at = 0
  marks.forEach(([s, e, id], i) => { out.push(text.slice(at, s)); out.push(<span key={i} className="rv-kw" title={kws[id]?.term}>{text.slice(s, e)}</span>); at = e })
  out.push(text.slice(at)); return out
}

function Editable({ value, multiline = true, onSave, children }) {
  const [edit, setEdit] = useState(false); const [v, setV] = useState(value)
  useEffect(() => setV(value), [value])
  if (!edit) return <div className="rv-editable">{children}<button className="rv-pen" onClick={() => setEdit(true)} title="Edit">Edit</button></div>
  return <div className="rv-editbox">{multiline ? <textarea className="input" rows={Math.min(10, Math.max(2, Math.ceil(v.length / 70)))} value={v} onChange={e => setV(e.target.value)} autoFocus />
    : <input className="input" value={v} onChange={e => setV(e.target.value)} autoFocus />}
    <div style={{ display: 'flex', gap: 6, marginTop: 6 }}><button className="btn primary sm" onClick={async () => { if (await onSave(v)) setEdit(false) }}>Save</button><button className="btn sm" onClick={() => { setV(value); setEdit(false) }}>Cancel</button></div></div>
}

const METHOD = { svg: 'SVG redraw', openai: 'OpenAI', gemini: 'Gemini', local: 'Local model' }

function FigureM2({ b, bookId, act }) {
  const m = b.m2; const [edit, setEdit] = useState(false); const [desc, setDesc] = useState(b.desc?.summary || ''); const [busy, setBusy] = useState(false)
  useEffect(() => setDesc(b.desc?.summary || ''), [b.desc?.summary])
  const url = `/api/review/books/${bookId}/figures/${b.id}`
  const choose = c => act(() => api(url + '/choice', { method: 'POST', body: { choice: c } }), c === 'generated' ? 'Students will see the new picture' : 'Students will see the original')
  const redraw = async body => { setBusy(true); const ok = await act(() => api(url + '/regenerate', { method: 'POST', body }), 'New picture made. Choose which one students see.'); setBusy(false); if (ok) setEdit(false) }
  const made = m?.status === 'generated'
  const pill = !made ? null : m.choice === 'pending' ? <span className="tag warn">Choose one</span> : m.choice === 'generated' ? <span className="tag ok">New picture in use</span> : <span className="tag">Original in use</span>
  return <>
    {made ? <div className="m2-cmp">
      <figure className={m.choice === 'original' ? 'on' : ''}><figcaption>Original from the book</figcaption><img src={`/api/content/${bookId}/${m.original}`} alt="Original figure" /></figure>
      <figure className={m.choice === 'generated' ? 'on' : ''}><figcaption>New, from the description<span className="muted">{METHOD[m.method] || m.method}{m.model ? ' ' + m.model : ''}</span></figcaption><img src={`/api/content/${bookId}/${m.image}`} alt="Regenerated figure" /></figure>
    </div> : <img className="rv-img" src={`/api/content/${bookId}/${b.image}`} alt="" />}
    <div className="m2-bar">{pill}
      {made && m.choice !== 'generated' && <button className="btn primary sm" onClick={() => choose('generated')}>Use new picture</button>}
      {made && m.choice !== 'original' && <button className="btn sm" onClick={() => choose('original')}>Keep original</button>}
      <button className="btn ghost sm" onClick={() => setEdit(e => !e)}>{made ? 'Edit description and redraw' : 'Describe and draw'}</button>
      {!made && m && <span className="m2-err">M2: {m.error || 'no new picture'}</span>}</div>
    {edit && <div className="rv-editbox" style={{ marginTop: 8 }}><textarea className="input" rows="5" value={desc} onChange={e => setDesc(e.target.value)} placeholder="Describe the figure: layout, every part, labels" />
      <div style={{ display: 'flex', gap: 6, marginTop: 6 }}><button className="btn primary sm" disabled={busy || !desc.trim()} onClick={() => redraw({ summary: desc })}>{busy ? 'Drawing' : 'Redraw from this description'}</button>
        <button className="btn sm" onClick={() => setEdit(false)}>Cancel</button></div></div>}
  </>
}

function Block({ b, kws, bookId, onChange, onRemove, act }) {
  const save = body => onChange(b.id, body)
  const tools = <button className="rv-x" title="Remove this block" onClick={() => onRemove(b)}><Icon n="x" s={14} /></button>
  const wrap = (inner, cls = '') => <div className={'rv-block ' + cls} data-edited={b.edits?.length ? '1' : undefined}>{tools}{inner}{b.edits?.length ? <span className="rv-edited">edited</span> : null}</div>
  switch (b.type) {
    case 'heading': return wrap(<Editable value={b.text} multiline={false} onSave={t => save({ text: t })}><div className={b.level === 3 ? 'rv-h3' : 'rv-h2'}>{b.number && <span className="n">{b.number}</span>}{b.text}</div></Editable>)
    case 'subheading': return wrap(<Editable value={b.text} multiline={false} onSave={t => save({ text: t })}><b>{b.text}</b></Editable>)
    case 'paragraph': return wrap(<Editable value={b.text} onSave={t => save({ text: t })}><p><Marked text={b.text} marks={b.marks} kws={kws} /></p></Editable>)
    case 'list': { const L = b.ordered ? 'ol' : 'ul'; return wrap(<L>{b.items.map((it, i) => <li key={i}><Editable value={it.text} onSave={t => save({ text: t, item: i })}><Marked text={it.text} marks={it.marks} kws={kws} /></Editable></li>)}</L>) }
    case 'equation': return wrap(<Editable value={b.latex.join('\n')} onSave={t => save({ latex: t.split('\n') })}><div className="rv-eq" dangerouslySetInnerHTML={{ __html: b.latex.map(tex).join('') }} /></Editable>, 'eq')
    case 'figure': return wrap(<><FigureM2 b={b} bookId={bookId} act={act} />
      <Editable value={b.caption || ''} multiline={false} onSave={t => save({ caption: t })}><div className="rv-cap">{b.number ? <b>Figure {b.number} </b> : null}{b.caption || <i className="muted">No caption</i>}</div></Editable>
      {b.desc ? <details className="rv-desc"><summary>Image description for the AI</summary>{b.desc.summary}</details> : <div className="tag warn">No description</div>}</>)
    case 'table': return wrap(<>
      <Editable value={b.caption || ''} multiline={false} onSave={t => save({ caption: t })}><div className="rv-cap">{b.number ? <b>{b.label || 'Table'} {b.number} </b> : null}{b.caption || <i className="muted">No caption</i>}</div></Editable>
      <div style={{ overflowX: 'auto' }}><table className="rv-table"><tbody>{b.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} title="Click to edit" onClick={() => { const v = prompt('Cell text', c); if (v !== null) save({ cell: [i, j], text: v }) }}>{c}</td>)}</tr>)}</tbody></table></div></>)
    case 'marker': return wrap(<div className="rv-marker">{b.text} <span className="muted">(label only: the converter could not find this box's text)</span></div>, 'flag')
    case 'box': return wrap(<div className="rv-box"><div className="rv-boxt">{b.title}</div>{b.children.map(c => <Block key={c.id} b={c} kws={kws} bookId={bookId} onChange={onChange} onRemove={onRemove} act={act} />)}</div>)
    default: return null
  }
}

function Original({ bookId, page, orig }) {
  if (orig.pdf) return <img className="rv-orig" src={`/api/review/books/${bookId}/pages/${page}/original.png`} alt={'Original page ' + page} />
  return <div className="rv-flow">{orig.flow.map((e, i) => {
    if (e.kind === 'image') return <img key={i} src={`/api/content/${bookId}/${e.src}`} alt="" />
    if (e.kind === 'table') return <table key={i} className="rv-table"><tbody>{e.rows.map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k}>{c}</td>)}</tr>)}</tbody></table>
    if (e.kind === 'desc') return <div key={i} className="rv-fdesc">{e.type}: {e.text}</div>
    if (e.kind === 'math') return <div key={i} className="rv-eq" dangerouslySetInnerHTML={{ __html: tex(e.latex) }} />
    return <div key={i} className={'rv-ft ' + (e.style || '')}>{e.text}</div>
  })}{!orig.flow.length && <div className="empty">Nothing extracted on this page</div>}</div>
}

export default function Workspace() {
  const { id } = useParams(); const nav = useNavigate(); const toast = useToast()
  const [book, setBook] = useState(null); const [page, setPage] = useState(null); const [pg, setPg] = useState(null)
  const [reject, setReject] = useState(null); const [comment, setComment] = useState(''); const [word, setWord] = useState('')
  const [final, setFinal] = useState(null); const [note, setNote] = useState('')
  const loadBook = useCallback(() => api('/api/review/books/' + id).then(b => { setBook(b); setPage(p => p ?? (b.pages.find(x => x.status !== 'approved') || b.pages[0])?.page) }), [id])
  const loadPage = useCallback(() => page != null && api(`/api/review/books/${id}/pages/${page}`).then(setPg), [id, page])
  useEffect(() => { loadBook().catch(e => toast(e.message, true)) }, [loadBook])
  useEffect(() => { setPg(null); loadPage() }, [loadPage])
  if (!book) return <div className="page"><div className="empty">Loading book</div></div>
  const kws = Object.fromEntries((pg?.chapters || []).flatMap(c => c.keywords.map(k => [k.id, k])))
  const onPageKws = pg ? [...new Set(pg.chapters.flatMap(c => JSON.stringify(c.blocks).match(/k\d+-[a-z0-9-]+/g) || []))].map(k => kws[k]).filter(Boolean) : []
  const chapterNo = pg?.chapters[0]?.number
  const idx = book.pages.findIndex(p => p.page === page)
  const next = () => { const n = book.pages.slice(idx + 1).find(p => p.status !== 'approved') || book.pages[idx + 1]; if (n) setPage(n.page) }
  const act = async (fn, msg, after = () => {}) => { try { const r = await fn(); msg && toast(msg); await loadBook(); await loadPage(); after(r); return true } catch (e) { toast(e.message, true); return false } }
  const change = (bid, body) => act(() => api(`/api/review/books/${id}/blocks/${bid}`, { method: 'PATCH', body }), 'Saved')
  const remove = b => confirm('Remove this block from the digital book? The original stays in the source.') && act(() => api(`/api/review/books/${id}/blocks/${b.id}`, { method: 'DELETE' }), 'Block removed')
  const decide = (d, c = '') => act(() => api(`/api/review/books/${id}/pages/${page}/${d}`, { method: 'POST', body: { comment: c } }), d === 'approve' ? `Page ${page} approved` : d === 'reject' ? `Page ${page} rejected` : 'Page reopened', () => d === 'approve' && next())
  const p = book.progress; const allOk = p.total && p.approved === p.total
  const cur = book.pages[idx]
  return (
    <div className="rv">
      <div className="rv-top">
        <Link to="/review" className="btn ghost sm">Queue</Link>
        <div><b>{book.title}</b><div className="muted" style={{ fontSize: 12 }}>{book.board}, Class {book.grade}. Detected from the file: {book.detected.title}</div></div>
        <div className="rv-prog"><div className="bar-track" style={{ width: 180 }}><i style={{ width: (p.approved / Math.max(1, p.total) * 100) + '%' }} /></div><span className="muted">{p.approved} of {p.total} pages approved{p.rejected ? `, ${p.rejected} rejected` : ''}{book.to_choose ? `, ${book.to_choose} pictures to choose` : ''}</span></div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="btn sm" onClick={() => setFinal('back')}>Send back</button>
          <button className="btn sm" disabled={!p.pending} onClick={() => confirm(`Approve the ${p.pending} pages still pending?`) && act(() => api(`/api/review/books/${id}/approve-all-remaining`, { method: 'POST' }), null, r => toast(r.held.length ? `${r.approved} pages approved. Still to choose a picture on page ${r.held.join(', ')}` : `${r.approved} pages approved`, !!r.held.length))}>Approve remaining</button>
          <button className="btn primary sm" disabled={!allOk} title={allOk ? '' : 'Approve every page first'} onClick={() => setFinal('publish')}>Approve and publish</button>
        </div>
      </div>
      <div className="rv-body">
        <nav className="rv-pages">{book.pages.map(x => <button key={x.page} className={'rv-p ' + x.status + (x.page === page ? ' cur' : '')} onClick={() => setPage(x.page)} title={`Page ${x.page}${x.flags ? `, ${x.flags} flagged` : ''}`}>
          {x.page}{x.choose ? <i className="m2" title={`${x.choose} pictures to choose`}>{x.choose}</i> : x.flags ? <i>{x.flags}</i> : null}</button>)}</nav>
        <section className="rv-col"><div className="rv-colh">Original page {page}<span className="muted">{pg?.original.pdf ? 'Uploaded PDF' : 'M1 extraction'}</span></div>
          <div className="rv-scroll">{pg ? <Original bookId={id} page={page} orig={pg.original} /> : <div className="empty">Loading</div>}</div></section>
        <section className="rv-col"><div className="rv-colh">Digital book, page {page}<span className="muted">{pg?.chapters.map(c => `Unit ${c.number} ${c.title}`).join(', ')}</span></div>
          <div className="rv-scroll rv-digital">{pg?.chapters.flatMap(c => c.blocks).map(b => <Block key={b.id} b={b} kws={kws} bookId={id} onChange={change} onRemove={remove} act={act} />)}
            {pg && !pg.chapters.length && <div className="empty">This page has no reading content (front matter or removed items only)</div>}</div></section>
        <aside className="rv-side">
          <div className="rv-card"><div className="h">Page {page}</div>
            <div style={{ margin: '4px 0 10px' }}>{cur?.status === 'approved' ? <span className="tag ok">Approved by {cur.reviewer}</span> : cur?.status === 'rejected' ? <span className="tag bad">Rejected</span> : <span className="tag">Not reviewed</span>}</div>
            {cur?.comment && <div className="note" style={{ marginBottom: 10 }}>{cur.comment}</div>}
            {book.status === 'in_review' && <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {cur?.status !== 'approved' && <button className="btn primary sm" onClick={() => decide('approve')}>Approve page</button>}
              {cur?.status !== 'rejected' && <button className="btn sm" onClick={() => { setReject(page); setComment('') }}>Reject page</button>}
              {cur?.status !== 'pending' && <button className="btn ghost sm" onClick={() => decide('reopen')}>Reopen</button>}
              <button className="btn ghost sm" onClick={next}>Next page</button></div>}</div>
          {pg?.flags.length > 0 && <div className="rv-card flag"><div className="h">Flagged by the converter ({pg.flags.length})</div>{pg.flags.map((f, i) => <div key={i} className="rv-flag"><b>{f.what}</b>{f.text && <div className="muted">{f.text}</div>}</div>)}</div>}
          <div className="rv-card"><div className="h">Important words on this page</div>
            <div className="chips">{onPageKws.map(k => <span key={k.id} className="chip on">{k.term}<button className="rv-chipx" title="Stop highlighting" onClick={() => act(() => api(`/api/review/books/${id}/keywords/${k.id}`, { method: 'DELETE' }), `${k.term} no longer highlighted`)}>×</button></span>)}
              {!onPageKws.length && <span className="muted">None highlighted here</span>}</div>
            {chapterNo && <form onSubmit={e => { e.preventDefault(); word.trim() && act(() => api(`/api/review/books/${id}/keywords`, { method: 'POST', body: { chapter: chapterNo, term: word } }), `${word} highlighted`, () => setWord('')) }} style={{ display: 'flex', gap: 6, marginTop: 10 }}>
              <input className="input" placeholder={`Add a word to Unit ${chapterNo}`} value={word} onChange={e => setWord(e.target.value)} /><button className="btn sm">Add</button></form>}</div>
          {pg?.removed.length > 0 && <div className="rv-card"><div className="h">Removed by the converter ({pg.removed.length})</div>{pg.removed.map((r, i) => <div key={i} className="rv-flag"><span className="muted">{r.what}:</span> {r.text || 'image'}</div>)}</div>}
        </aside>
      </div>
      {reject != null && <Modal title={`Reject page ${reject}`} onClose={() => setReject(null)} footer={<><button className="btn" onClick={() => setReject(null)}>Cancel</button><button className="btn primary" onClick={async () => { if (await decide('reject', comment)) setReject(null) }}>Reject page</button></>}>
        <Field label="What is wrong" hint="Shown to the team that fixes the book"><textarea className="input" rows="3" value={comment} onChange={e => setComment(e.target.value)} placeholder="Figure 1.4 is cut off; the second half of the paragraph is missing" /></Field></Modal>}
      {final && <Modal title={final === 'publish' ? 'Approve and publish' : 'Send the book back'} onClose={() => setFinal(null)} footer={<><button className="btn" onClick={() => setFinal(null)}>Cancel</button>
        <button className="btn primary" onClick={() => act(() => api(`/api/review/books/${id}/${final === 'publish' ? 'publish' : 'send-back'}`, { method: 'POST', body: { comment: note } }), final === 'publish' ? 'Book published' : 'Book sent back', () => nav('/review'))}>{final === 'publish' ? 'Publish book' : 'Send back'}</button></>}>
        {final === 'publish' ? <p style={{ margin: 0 }}>All {p.total} pages are approved. Publishing makes <b>{book.title}</b> available to schools and students straight away.</p>
          : <p style={{ margin: 0 }}>The book leaves the queue and is not published. Super Admin sees your note and reruns extraction.</p>}
        <Field label={final === 'publish' ? 'Note (optional)' : 'Why it is going back'}><textarea className="input" rows="3" value={note} onChange={e => setNote(e.target.value)} /></Field></Modal>}
    </div>
  )
}

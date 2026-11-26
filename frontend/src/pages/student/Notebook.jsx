import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api'
import { Page, Icon, Sheet, MathText, useToast, ask } from '../../ui'
import { NoteCard, Composer, when } from '../../Study'

// Every note, highlight, voice note and saved explanation from every book, private to the learner.
const KINDS = [['', 'All'], ['note', 'Notes'], ['highlight', 'Highlights'], ['voice', 'Voice'], ['saved', 'Saved']]

export default function Notebook() {
  const nav = useNavigate(); const toast = useToast()
  const [kind, setKind] = useState(''); const [q, setQ] = useState(''); const [book, setBook] = useState(''); const [tag, setTag] = useState('')
  const [data, setData] = useState(null); const [saved, setSaved] = useState(null); const [compose, setCompose] = useState(null)
  const load = () => {
    const p = new URLSearchParams(Object.entries({ q, book_id: book, tag, kind: kind === 'saved' ? '' : kind }).filter(([, v]) => v)).toString()
    api('/api/student/study/notes?' + p).then(setData).catch(e => toast(e.message, true))
    api('/api/student/study/saved' + (book ? '?book_id=' + book : '')).then(setSaved).catch(() => {})
  }
  useEffect(() => { const t = setTimeout(load, q ? 250 : 0); return () => clearTimeout(t) }, [q, book, tag, kind])
  const open = n => nav(`/student/read/${n.book_id}?ch=${n.chapter ?? ''}${n.section ? '&sec=' + encodeURIComponent(n.section) : ''}`)
  async function del(n) { if (!(await ask('Delete this ' + (n.kind === 'voice' ? 'voice note' : n.kind) + '?', { yes: 'Delete', danger: true }))) return
    try { await api('/api/student/study/notes/' + n.id, { method: 'DELETE' }); load() } catch (e) { toast(e.message, true) } }
  async function card(n) { try { await api('/api/student/study/cards/from-note', { method: 'POST', body: { note_id: n.id } }); toast('Added to Revise') } catch (e) { toast(e.message, true) } }
  async function unsave(s) { try { await api('/api/student/study/saved/' + s.id, { method: 'DELETE' }); load() } catch (e) { toast(e.message, true) } }
  const notes = data?.notes || []
  const count = k => k === 'saved' ? saved?.length || 0 : k ? notes.filter(n => n.kind === k).length : notes.length + (saved?.length || 0)
  const showSaved = (kind === '' || kind === 'saved') && !tag
  const items = [...(kind === 'saved' ? [] : notes.map(n => ({ t: 'n', at: n.created_at, n }))),
    ...(showSaved ? (saved || []).filter(s => !q || (s.term + s.text).toLowerCase().includes(q.toLowerCase())).map(s => ({ t: 's', at: s.created_at, s })) : [])]
    .sort((a, b) => String(b.at).localeCompare(String(a.at)))
  return <Page title="Notebook" sub="Your notes, highlights and voice notes from every book, in one place. Only you can see them.">
    <div className="nb-bar">
      <div className="nb-search"><input placeholder="Search your notes, highlights and voice transcripts" value={q} onChange={e => setQ(e.target.value)} aria-label="Search notes" /></div>
      <div className="seg nb-kinds">{KINDS.map(([k, l]) => <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>{l}<em>{count(k)}</em></button>)}</div>
    </div>
    {(data?.books?.length > 0 || data?.tags?.length > 0) && <div className="nb-chips">
      {data.books.map(b => <button key={b.id} className={'chip' + (String(book) === String(b.id) ? ' on' : '')} onClick={() => setBook(String(book) === String(b.id) ? '' : b.id)}>{b.title}</button>)}
      {data.tags.map(t => <button key={t} className={'chip' + (tag === t ? ' on' : '')} onClick={() => setTag(tag === t ? '' : t)}>#{t}</button>)}</div>}
    {data && !items.length && <div className="card empty nb-empty"><Icon n="note" s={28} /><b>Nothing here yet</b>
      <span>In any book, select words and choose Note, Highlight or Voice. Tap the star on an explanation to save it.</span></div>}
    <div className="nb-grid">{items.map(it => it.t === 'n'
      ? <NoteCard key={'n' + it.n.id} n={it.n} onOpen={open} onDelete={del} onCard={card} onSaved={() => { toast('Saved'); load() }} />
      : <div key={'s' + it.s.id} className="sv-card">
        <div className="sv-where"><b className="k-saved">Saved explanation</b><span>{it.s.path.join(' › ') || it.s.term}</span></div>
        <div className="sv-body"><b>{it.s.term}</b> <MathText text={it.s.text.length > 260 ? it.s.text.slice(0, 260) + '...' : it.s.text} /></div>
        <div className="sv-foot"><span>Saved {when(it.s.created_at)}</span><button type="button" className="linkbtn" onClick={() => unsave(it.s)}>Remove</button>
          {it.s.book_id && <button type="button" className="sv-go" onClick={() => open(it.s)}>Open in the book</button>}</div></div>)}</div>
    <div className="nb-fab"><button className="btn lg" onClick={() => setCompose({})}><Icon n="note" s={16} />New note</button></div>
    {compose && <Sheet title="New note" onClose={() => setCompose(null)}>
      <Composer at={{ book_id: book || null }} onCancel={() => setCompose(null)} onSaved={() => { setCompose(null); toast('Saved'); load() }} /></Sheet>}
  </Page>
}

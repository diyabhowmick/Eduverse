import { useEffect, useState } from 'react'
import { api, num } from '../../api'
import { useLoad, Page, Modal, Field, Tag, MathText, useToast } from '../../ui'
import { STYLE } from '../../ExplainPanel'

// Saved explanations of one textbook: level 1 with its underlined words, level 2 shared across the book,
// anything written live for a student (unchecked), and the replies kept for students' own questions.
const VIEWS = [['1', 'Level 1'], ['2', 'Level 2'], ['3', 'Level 3'], ['unchecked', 'Written live'], ['flagged', 'Reported'], ['replies', 'Student questions']]

function Editor({ item, onClose, onSaved, path }) {
  const [text, setText] = useState(item.text ?? item.reply); const toast = useToast()
  async function save() { try { await api(path, { method: 'PUT', body: { text } }); toast('Saved'); onSaved() } catch (e) { toast(e.message, true) } }
  return <Modal title={'Edit: ' + (item.term || item.sample)} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={save}>Save</button></>}>
    <textarea className="input" rows="12" value={text} onChange={e => setText(e.target.value)} />
    <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>Write maths as LaTeX between $ signs.</div>
  </Modal>
}

const esc = t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
function Mark({ text, term }) {
  if (!term) return <MathText text={text} />
  const parts = String(text).split(new RegExp('(' + esc(term) + ')', 'gi'))
  return <span style={{ whiteSpace: 'pre-wrap' }}>{parts.map((p, i) => i % 2 ? <mark key={i} className="rv-mark">{p}</mark> : <MathText key={i} text={p} />)}</span>
}
const dot = st => st === 'final' ? 'ok' : st === 'flagged' ? 'bad' : st === 'retired' ? 'off' : 'wait'

function Book({ book, back }) {
  const [view, setView] = useState('1'); const toast = useToast()
  const q = view === 'unchecked' ? 'source=live&status=candidate' : view === 'flagged' ? 'status=flagged' : 'level=' + view
  const ex = useLoad(view === 'replies' ? null : `/api/learn/admin/explanations?book_id=${book.id}&${q}`, [view])
  const mc = useLoad(view === 'replies' ? `/api/learn/admin/misconceptions?book_id=${book.id}` : null, [view])
  const [edit, setEdit] = useState(null); const [add, setAdd] = useState(null); const [at, setAt] = useState(0)
  const reload = () => { ex.reload?.(); mc.reload?.() }
  const rows = (view === 'replies' ? mc.data : ex.data) || []
  const cur = rows[Math.min(at, rows.length - 1)]
  const isMc = view === 'replies'
  useEffect(() => { setAt(0) }, [view])
  const act = async (url, msg, next = true) => { try { await api(url, { method: 'POST' }); toast(msg); if (next) setAt(i => Math.min(i + 1, rows.length - 1)); reload() } catch (x) { toast(x.message, true) } }
  const approve = () => cur && cur.status !== 'final' && act(isMc ? `/api/learn/admin/misconceptions/${cur.id}/approve` : `/api/learn/admin/explanations/${cur.id}/pin`, 'Approved')
  const retire = () => cur && act(isMc ? `/api/learn/admin/misconceptions/${cur.id}/${cur.status === 'retired' ? 'restore' : 'retire'}` : `/api/learn/admin/explanations/${cur.id}/${cur.status === 'retired' ? 'restore' : 'retire'}`, cur.status === 'retired' ? 'Back in use' : 'Retired')
  const unlink = async l => { try { await api('/api/learn/admin/links/' + l.id, { method: 'DELETE' }); reload() } catch (x) { toast(x.message, true) } }
  async function link() { try { await api(`/api/learn/admin/explanations/${add.id}/links`, { method: 'POST', body: { term: add.term, bridge: add.bridge } }); setAdd(null); reload() } catch (x) { toast(x.message, true) } }
  async function approveAll() { try { const r = await api(`/api/learn/admin/books/${book.id}/explanations/approve_all`, { method: 'POST', body: { level: ['1', '2'].includes(view) ? +view : null } }); toast(`${r.approved} approved`); reload() } catch (x) { toast(x.message, true) } }

  // Keyboard: J or down for next, K or up for previous, A approve, E edit, R retire or restore.
  useEffect(() => {
    const k = e => {
      if (edit || add || /input|textarea|select/i.test(e.target.tagName)) return
      const key = e.key.toLowerCase()
      if (key === 'j' || key === 'arrowdown') { e.preventDefault(); setAt(i => Math.min(i + 1, rows.length - 1)) }
      else if (key === 'k' || key === 'arrowup') { e.preventDefault(); setAt(i => Math.max(i - 1, 0)) }
      else if (key === 'a') approve()
      else if (key === 'e' && cur) setEdit(isMc ? { ...cur, mc: true } : cur)
      else if (key === 'r') retire()
    }
    addEventListener('keydown', k); return () => removeEventListener('keydown', k)
  })
  useEffect(() => { document.querySelector('.rv-list .on')?.scrollIntoView({ block: 'nearest' }) }, [at])

  return <Page title={book.title} sub="Every level 1 and level 2 explanation must be approved before the book can be published" actions={<>
    {['1', '2', 'unchecked'].includes(view) && <button className="btn primary" onClick={approveAll}>Approve all {view === 'unchecked' ? 'level 1 and 2' : 'on this tab'}</button>}
    <button className="btn" onClick={back}>All books</button></>}>
    <div className="seg" style={{ flexWrap: 'wrap', marginBottom: 12 }}>{VIEWS.map(([k, l]) => <button key={k} className={view === k ? 'on' : ''} onClick={() => setView(k)}>{l}</button>)}</div>
    {!rows.length ? <div className="card empty">Nothing here yet</div> : <div className="rv-split">
      <div className="card rv-list" role="listbox" aria-label="Explanations">{rows.map((r, i) => <button key={r.id} type="button" role="option" aria-selected={i === at} className={i === at ? 'on' : ''} onClick={() => setAt(i)}>
        <i className={'rv-dot ' + dot(r.status)} /><span>{isMc ? r.sample : r.term}</span>{!isMc && <small>L{r.level}</small>}</button>)}</div>
      {cur && <div className="rv-detail" key={cur.id}>
        <div className="rv-pair">
          <div className="card"><div className="card-h"><h3>{isMc ? 'The student wrote' : 'In the book'}</h3><span className="sub">{isMc ? 'asked in ' + cur.asked_in : cur.context?.where || ''}</span></div>
            <div className="card-b rv-ctx">{isMc ? <b>"{cur.sample}"</b> : cur.context?.parts?.length ? cur.context.parts.map((t, i) => <p key={i}><Mark text={t} term={cur.term} /></p>) : <span className="muted">No source text found for this one.</span>}</div></div>
          <div className="card"><div className="card-h"><h3>{isMc ? 'Reply given' : cur.term}</h3>
            <span className="sub">{isMc ? (cur.kind === 'bridge' ? 'leads into ' + cur.leads_to : 'full reply') + ' · reused ' + num(cur.hits) + ' times'
              : (STYLE[cur.style] || cur.style) + ' · ' + (cur.source === 'prepared' ? 'written ahead' : cur.source === 'edited' ? 'edited' : 'written live') + ' · shown ' + num(cur.shown) + ' · ' + cur.helpful + ' helpful, ' + cur.unhelpful + ' not'}</span></div>
            <div className="card-b rv-ctx"><MathText text={isMc ? cur.reply : cur.text} /></div></div>
        </div>
        {!isMc && cur.level === 1 && <div className="card"><div className="card-h"><h3>Underlined for students</h3>
          <button className="btn ghost sm right" onClick={() => setAdd({ id: cur.id, term: '', bridge: '' })}>Underline a word</button></div>
          <div className="card-b stack" style={{ gap: 6 }}>{cur.links.map(l => <div key={l.id} className="rv-link"><b>{l.term}</b><span className="muted">{l.bridge}</span>
            <button className="btn ghost sm" onClick={() => unlink(l)}>Remove</button></div>)}{!cur.links.length && <span className="muted">None</span>}</div></div>}
        <div className="rv-bar">
          <Tag s={cur.status === 'final' ? 'ok' : cur.status === 'flagged' ? 'bad' : ''}>{cur.status === 'final' ? 'Approved' : cur.status === 'flagged' ? 'Reported' : cur.status === 'retired' ? 'Retired' : 'Waiting'}</Tag>
          <span className="muted">{at + 1} of {rows.length}</span>
          <span className="rv-keys"><kbd>J</kbd><kbd>K</kbd> move <kbd>A</kbd> approve <kbd>E</kbd> edit <kbd>R</kbd> retire</span>
          <button className="btn" onClick={() => setEdit(isMc ? { ...cur, mc: true } : cur)}>Edit</button>
          <button className="btn" onClick={retire}>{cur.status === 'retired' ? 'Restore' : 'Retire'}</button>
          {cur.status !== 'final' && <button className="btn primary" onClick={approve}>Approve and next</button>}
        </div>
      </div>}
    </div>}
    {edit && <Editor item={edit} path={edit.mc ? '/api/learn/admin/misconceptions/' + edit.id : '/api/learn/admin/explanations/' + edit.id} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload() }} />}
    {add && <Modal title="Underline a word" onClose={() => setAdd(null)} footer={<><button className="btn" onClick={() => setAdd(null)}>Cancel</button><button className="btn primary" disabled={!add.term.trim()} onClick={link}>Add</button></>}>
      <Field label="Word, exactly as it appears in the explanation"><input className="input" autoFocus value={add.term} onChange={e => setAdd(a => ({ ...a, term: e.target.value }))} /></Field>
      <Field label="One line tying it back (optional)"><input className="input" value={add.bridge} onChange={e => setAdd(a => ({ ...a, bridge: e.target.value }))} /></Field>
    </Modal>}
  </Page>
}

export default function Explanations() {
  const { data } = useLoad('/api/learn/admin/explained_books'); const [book, setBook] = useState(null)
  if (book) return <Book book={book} back={() => setBook(null)} />
  return <Page title="Explanations" sub="Written once, served to every student. Check what was written live and what students asked.">
    <div className="card"><table className="t"><thead><tr><th>Textbook</th><th className="num">Level 1</th><th className="num">Level 2</th><th className="num">To approve</th><th className="num">Written live</th><th className="num">Reported</th><th className="num">Student questions</th><th /></tr></thead>
      <tbody>{(data || []).map(b => <tr key={b.id}><td><b>{b.title}</b> <Tag s={b.status} /></td><td className="num">{num(b.l1 || 0)}</td><td className="num">{num(b.l2 || 0)}</td><td className="num">{b.waiting ? <b>{num(b.waiting)}</b> : 'Done'}</td>
        <td className="num">{b.unchecked ? <b>{num(b.unchecked)}</b> : ''}</td><td className="num">{b.flagged ? <b>{num(b.flagged)}</b> : ''}</td><td className="num">{num(b.replies || 0)}</td>
        <td className="acts"><button className="btn sm" onClick={() => setBook(b)}>Open</button></td></tr>)}</tbody></table>
      {data && !data.length && <div className="empty">No saved explanations yet. Write them ahead from AI usage, or they build up as students read.</div>}</div>
  </Page>
}

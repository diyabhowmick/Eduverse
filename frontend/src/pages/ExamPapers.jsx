import { useState } from 'react'
import { useParams, Link, useSearchParams } from 'react-router-dom'
import { api, day } from '../api'
import { useLoad, Page, Modal, Field, Tag, useToast, Icon, ask } from '../ui'
import PaperEditor from './PaperEditor'

function AddPaper({ bid, onClose, onDone }) {
  const [v, setV] = useState({ year: new Date().getFullYear() - 1, session: '', title: '', text: '' }); const [file, setFile] = useState(null)
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  async function save() {
    setErr(''); setBusy(true)
    const f = new FormData(); Object.entries(v).forEach(([k, x]) => f.append(k, x)); if (file) f.append('file', file)
    try { onDone(await api(`/api/exams/${bid}/papers`, { method: 'POST', form: f })) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return <Modal title="Add a past paper" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={busy} onClick={save}>{busy ? 'Reading the paper' : 'Add paper'}</button></>}>
    {err && <div className="err">{err}</div>}
    <div className="grid2"><Field label="Year"><input className="input" type="number" value={v.year} onChange={e => setV({ ...v, year: e.target.value })} /></Field>
      <Field label="Session" hint="March, Supplementary, Shift 1"><input className="input" value={v.session} onChange={e => setV({ ...v, session: e.target.value })} /></Field></div>
    <Field label="Title (optional)"><input className="input" value={v.title} onChange={e => setV({ ...v, title: e.target.value })} /></Field>
    <Field label="File" hint="Word (an M1 flow document works), PDF with a text layer, or plain text"><input className="input" type="file" accept=".docx,.pdf,.txt" onChange={e => setFile(e.target.files[0])} /></Field>
    <Field label="Or paste the paper" hint="Numbered questions, (a) to (d) options, then Answer: and Solution: lines"><textarea className="input" rows={8} value={v.text} onChange={e => setV({ ...v, text: e.target.value })} /></Field>
    <div className="note">Questions are split out automatically and tagged to chapters of the linked textbooks. Check them, then send the paper for review. Students only see approved papers.</div>
  </Modal>
}

export default function ExamPapers() {
  const { id } = useParams()
  const { data, reload } = useLoad(`/api/exams/${id}/papers`, [id])
  const [params] = useSearchParams()
  const [add, setAdd] = useState(false); const [open, setOpen] = useState(+params.get('paper') || null); const toast = useToast()
  if (open) return <Page title="Question paper"><PaperEditor pid={open} role="super_admin" onBack={() => { setOpen(null); reload() }} /></Page>
  const approved = data?.papers.filter(p => p.status === 'approved').length || 0
  return (
    <Page title={data?.pack.title || 'Exam pack'} sub={data ? [data.pack.exam, data.pack.board].filter(Boolean).join(', ') + `. ${approved} of ${data.papers.length} papers approved` : ''}
      actions={<><Link className="btn" to="/sa/catalogue">Catalogue</Link><button className="btn primary" onClick={() => setAdd(true)}><Icon n="plus" s={16} />Add past paper</button></>}>
      {data && <div className="note" style={{ marginBottom: 12 }}>{data.pack.linked.length ? <>Chapters come from {data.pack.linked.map(b => b.title).join(', ')}.</> : <>No textbook is linked, so questions cannot be tagged to chapters. Link one with Edit in the catalogue.</>}
        {' '}{data.pack.status !== 'live' && (approved ? 'Ready to go live from the catalogue.' : 'The pack can go live once a paper is approved.')}</div>}
      <div className="card"><table className="t"><thead><tr><th>Year</th><th>Paper</th><th className="num">Questions</th><th>Stage</th><th>Added</th><th /></tr></thead>
        <tbody>{data?.papers.map(p => <tr key={p.id}><td><b>{p.year}</b></td><td>{p.title}</td><td className="num">{p.questions}</td>
          <td><Tag s={p.status}>{p.status === 'draft' ? 'Draft' : undefined}</Tag>{p.reviewed_by && <div className="muted" style={{ fontSize: 12 }}>by {p.reviewed_by}</div>}</td><td className="muted">{day(p.created_at)}</td>
          <td className="acts"><button className="btn sm" onClick={() => setOpen(p.id)}>Open</button>
            <button className="btn ghost sm" onClick={async () => { if (!(await ask(`Delete the ${p.year} paper and its questions?`, { yes: 'Delete' }))) return; try { await api('/api/exams/papers/' + p.id, { method: 'DELETE' }); toast('Paper deleted'); reload() } catch (e) { toast(e.message, true) } }}>Delete</button></td></tr>)}</tbody></table>
        {data && !data.papers.length && <div className="empty">No papers yet. Add the last 10 or 20 years.</div>}</div>
      {add && <AddPaper bid={id} onClose={() => setAdd(false)} onDone={r => { setAdd(false); toast(r.warning || `${r.found} questions found, ${r.tagged} tagged to a chapter`, !!r.warning); reload(); setOpen(r.id) }} />}
    </Page>
  )
}

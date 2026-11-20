import { useState } from 'react'
import { Link } from 'react-router-dom'
import { when } from '../api'
import { api as call } from '../api'
import { api, useLoad, Page, Tag, useToast, Modal, Field } from '../ui'

/* Flags and issues.

   A reviewer's comment used to live on one page of one book, where nobody
   looked at it again. This is every flag in the catalogue in one list, with
   the thing that makes it useful: a category, so problems can be counted
   rather than only read.

   There is no issues table. A rejected page IS the open issue — the page
   carries the book, the page number, the reviewer, what they wrote, the
   category and the suggested fix, and its own status is the lifecycle:

     rejected   open
     pending    somebody fixed it, waiting to be checked again
     approved   closed

   One source of truth, so the list can never disagree with the page. */

const STATES = [
  ['open', 'Open'],
  ['to_recheck', 'Fixed, needs checking'],
  ['fixed', 'Closed'],
  ['all', 'All'],
]
const TONE = { open: 'bad', to_recheck: 'warn', fixed: 'ok' }
const LABEL = { open: 'Open', to_recheck: 'Needs checking', fixed: 'Closed' }

export default function Issues() {
  const [state, setState] = useState('open')
  const [cat, setCat] = useState('')
  const { data, reload } = useLoad(`/api/books/issues?status=${state}&category=${cat}`, [state, cat])
  const { data: sum, reload: reloadSum } = useLoad('/api/books/issues/summary', [state, cat])
  // A book whose converted file is gone looks fine in the catalogue and fails
  // the moment anybody opens it, including a student. Surface it here.
  const { data: broken } = useLoad('/api/books/content-check')
  // Why they went missing, which is a different question from which ones did.
  const { data: store } = useLoad('/api/books/storage-check')
  const [fixing, setFixing] = useState(null); const [note, setNote] = useState('')
  const toast = useToast()
  async function markFixed() {
    try {
      await call(`/api/books/${fixing.book_id}/issues/${fixing.page}/fixed`, { method: 'POST', body: { note } })
      toast(`Page ${fixing.page} is waiting to be checked again`); setFixing(null); setNote(''); reload(); reloadSum()
    } catch (e) { toast(e.message, true) }
  }

  const open = sum?.by_state?.open ?? 0
  const recheck = sum?.by_state?.to_recheck ?? 0
  const books = Object.keys(sum?.open_by_book || {}).length

  return (
    <Page title="Flags and issues" sub="Every problem a reviewer found, across the whole catalogue">
      <p className="headline">
        {!sum ? 'Loading'
          : open === 0
            ? <>Nothing is open. {recheck > 0 && <>{recheck} {recheck === 1 ? 'fix is' : 'fixes are'} waiting to be checked again.</>}</>
            : <><em>{open}</em> open {open === 1 ? 'issue' : 'issues'} across <em>{books}</em> {books === 1 ? 'book' : 'books'}.
              {recheck > 0 && <> {recheck} fixed and waiting to be checked.</>}</>}
      </p>

      <div className="stack">
        {store && <div className="card">
          <div className="card-h"><h3>Where files are stored</h3>
            <Tag s={!store.writable ? 'bad' : store.persistent || store.on_volume ? 'ok' : 'warn'}>
              {!store.writable ? 'Cannot save' : store.persistent || store.on_volume ? 'Safe' : 'Not safe'}</Tag>
            <span className="sub">Uploads and converted books</span></div>
          <table className="t">
            <tbody>
              <tr><td>Folder</td><td><code>{store.root}</code></td></tr>
              {store.backend === 'local' && <tr><td>Mounted at</td><td>{store.on_volume
                ? <><code>{store.mount}</code> <span className="muted">— a volume, so it survives a deploy</span></>
                : <b style={{ color: 'var(--red)' }}>the container's own disk — wiped on every deploy</b>}</td></tr>}
              <tr><td>Can write</td><td>{store.writable ? 'Yes' : <b style={{ color: 'var(--red)' }}>No — {store.probe}</b>}</td></tr>
              {store.free_gb !== undefined && <tr><td>Space</td><td>{store.free_gb} GB free of {store.total_gb} GB</td></tr>}
              {store.books && <tr><td>Holding now</td><td>{store.books.files} converted files ({store.books.mb} MB), {store.originals.files} originals ({store.originals.mb} MB)</td></tr>}
            </tbody>
          </table>
          <div className="note">{store.verdict}</div>
        </div>}
        {!!broken?.length && <div className="card">
          <div className="card-h"><h3>Books with no content file</h3><Tag s="bad">{broken.length}</Tag>
            <span className="sub">These fail for anyone who opens them, students included</span></div>
          <table className="t">
            <thead><tr><th>Book</th><th>Stage</th><th className="num">Pages</th><th>What is wrong</th></tr></thead>
            <tbody>{broken.map(b => (
              <tr key={b.id}><td><b>{b.title}</b><div className="muted" style={{ fontSize: 12 }}>{b.content_key}</div></td>
                <td><Tag s={b.status} /></td><td className="num">{b.pages}</td><td>{b.why}</td></tr>))}</tbody>
          </table>
          <div className="note">
            The database says these were converted, but the file is not in storage. That happens when a book is
            processed while no volume is mounted: the content goes to the container's own disk and the next deploy
            takes it with it. <b>Process the book again</b> from Add content. If the original upload is gone too,
            it has to be re-uploaded.
          </div>
        </div>}
        {!!sum?.by_category?.length && <div className="card">
          <div className="card-h"><h3>What is going wrong</h3><span className="sub">Open issues by kind. The biggest number is where the pipeline needs work.</span></div>
          <table className="t">
            <thead><tr><th>Problem</th><th className="num">Pages</th><th /></tr></thead>
            <tbody>{sum.by_category.map(c => (
              <tr key={c.key}>
                <td>{c.label}</td>
                <td className="num">{c.n}</td>
                <td><button className="btn ghost sm" onClick={() => { setCat(cat === c.key ? '' : c.key); setState('open') }}>
                  {cat === c.key ? 'Show all kinds' : 'Only these'}</button></td>
              </tr>))}</tbody>
          </table>
        </div>}

        <div className="card">
          <div className="card-h">
            <h3>Issues</h3>
            <span className="right"><div className="seg">{STATES.map(([k, l]) =>
              <button key={k} className={state === k ? 'on' : ''} onClick={() => setState(k)}>{l}</button>)}</div></span>
          </div>
          <table className="t">
            <thead><tr><th>Book</th><th className="num">Page</th><th>Problem</th><th>What the reviewer said</th><th>Fix</th><th>Status</th><th /></tr></thead>
            <tbody>{data?.map((r, i) => (
              <tr key={i}>
                <td><b>{r.book}</b><div className="muted" style={{ fontSize: 12 }}><Tag s={r.book_status} /></div></td>
                <td className="num">{r.page}</td>
                <td>{r.category_label}</td>
                <td style={{ maxWidth: 320 }}>{r.comment}
                  <div className="muted" style={{ fontSize: 12 }}>{r.reviewer}{r.at ? ' · ' + when(r.at) : ''}</div></td>
                <td className="muted">{r.rerun_label}</td>
                <td><Tag s={TONE[r.state]}>{LABEL[r.state]}</Tag></td>
                {/* Straight to the page itself, original beside digital. */}
                <td className="acts">
                  <Link className="btn ghost sm" to={`/sa/books/${r.book_id}?page=${r.page}`}>Open page {r.page}</Link>
                  {r.state === 'open' && <button className="btn sm" onClick={() => { setFixing(r); setNote('') }} title="Send just this page back to a reviewer, leaving every other page as it is">Mark fixed</button>}
                </td>
              </tr>))}</tbody>
          </table>
          {data && !data.length && <div className="empty">
            {state === 'open' ? 'No open issues. Either the books are clean or nobody has reviewed one yet.'
              : state === 'to_recheck' ? 'Nothing is waiting to be checked again.'
                : 'Nothing here.'}
          </div>}
        </div>

        <div className="note">
          A flag is raised by a reviewer on the page it belongs to, so it always points at something
          you can look at. <b>Fix</b> is the reviewer's suggestion of what would put it right, taken
          from the kind of problem — it is a starting point, not an instruction.
        </div>
      </div>
      {fixing && <Modal title={`Page ${fixing.page} of ${fixing.book}`} onClose={() => setFixing(null)}
        footer={<><button className="btn" onClick={() => setFixing(null)}>Cancel</button><button className="btn primary" onClick={markFixed}>Mark fixed</button></>}>
        <p style={{ margin: 0 }}>This page goes back to a reviewer to be checked. <b>Only this page</b> — every other page keeps the state it is in, so a 300 page book is not reviewed again over one figure.</p>
        <div className="note" style={{ margin: '10px 0' }}><b>The reviewer said:</b> {fixing.comment}</div>
        {fixing.book_status === 'live' && <div className="note">This book is live and <b>stays live</b>. Students keep reading it while this page is checked.</div>}
        <Field label="What was done (optional)" hint="Added to the page so the reviewer knows what changed">
          <textarea className="input" rows="2" value={note} onChange={e => setNote(e.target.value)} placeholder="Re-ran M2 on this page; the figure is whole now" /></Field></Modal>}
    </Page>
  )
}

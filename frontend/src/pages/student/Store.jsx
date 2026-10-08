import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, inr } from '../../api'
import { useLoad, Page, Modal, useToast } from '../../ui'
import { BookTile, Cover } from './common'

export default function Store() {
  const { data: home } = useLoad('/api/student/home')
  const [board, setBoard] = useState(null); const [grade, setGrade] = useState(null)
  useEffect(() => { if (home && board === null) { setBoard(home.me.board || ''); setGrade(home.me.grade || '') } }, [home])
  const ready = board !== null
  const { data, reload } = useLoad(ready ? `/api/student/store?board=${encodeURIComponent(board)}&grade=${grade}` : '/api/student/store', [board, grade])
  const [buy, setBuy] = useState(null); const toast = useToast(); const nav = useNavigate()
  async function confirm() {
    try { const r = await api('/api/student/purchase', { method: 'POST', body: { book_id: buy.id } }); toast('Added to My books'); setBuy(null); reload(); if (buy.readable) nav('/student/read/' + buy.id) }
    catch (e) { toast(e.message, true) }
  }
  return (
    <Page title="Store" sub="Pick your syllabus and class to see its textbooks">
      <div className="toolbar">
        <select className="input" style={{ maxWidth: 260 }} value={board || ''} onChange={e => setBoard(e.target.value)}><option value="">Every syllabus</option>{data?.boards.map(b => <option key={b}>{b}</option>)}</select>
        <select className="input" style={{ maxWidth: 160 }} value={grade || ''} onChange={e => setGrade(e.target.value)}><option value="">Every class</option>{data?.grades.map(g => <option key={g} value={g}>Class {g}</option>)}</select>
      </div>
      <div className="tiles">{data?.books.map(b => <BookTile key={b.id} b={b} action={
        b.status === 'upcoming' ? <span className="tag" style={{ marginTop: 8 }}>Coming soon</span>
          : b.owned ? <span className="tag ok" style={{ marginTop: 8 }}>In My books</span>
            : <button className="btn primary sm" style={{ marginTop: 8 }} onClick={e => { e.preventDefault(); setBuy(b) }}>Get for {inr(b.price)}</button>} />)}</div>
      {data && !data.books.length && <div className="card empty">No books for this syllabus and class yet</div>}
      {buy && <Modal title="Get this book" onClose={() => setBuy(null)} footer={<><button className="btn" onClick={() => setBuy(null)}>Cancel</button><button className="btn primary" onClick={confirm}>Confirm</button></>}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}><Cover b={buy} size="sm" /><div><b>{buy.title}</b><div className="muted">{buy.board}</div><div style={{ fontSize: 20, fontWeight: 700, marginTop: 6 }}>{inr(buy.price)}</div></div></div>
        <div className="note">Payments are not connected yet. Confirming adds the book to My books as a demo purchase; no money is taken.</div>
      </Modal>}
    </Page>
  )
}

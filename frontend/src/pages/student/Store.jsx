import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, inr } from '../../api'
import { useLoad, Page, Modal, useToast } from '../../ui'
import { BookTile, Cover, openPath } from './common'

const LEVEL = { school: 'School', degree: 'Degree college', competitive: 'Competitive' }

export default function Store() {
  const { data: home } = useLoad('/api/student/home')
  const { data: tx } = useLoad('/api/taxonomy')
  const [f, setF] = useState(null)
  useEffect(() => {
    if (home && !f) { const p = home.me.profile || {}; setF({ track: p.track || 'textbook', level: p.level || '', board: home.me.board || '', grade: home.me.grade || '', exam: p.exam || '', university: p.university || '' }) }
  }, [home])
  // Board and class only narrow the school shelf; university only the degree shelf; exam only the exam shelf.
  const params = f ? Object.fromEntries(Object.entries(f).filter(([k, v]) => v && (
    k === 'track' || k === 'level' || (k === 'exam' && f.track === 'exam') || (k === 'university' && f.level === 'degree')
    || ((k === 'board' || k === 'grade') && (f.level === 'school' || (!f.level && f.track === 'textbook')))))) : { track: 'textbook' }
  const qs = new URLSearchParams(params).toString()
  const { data, reload } = useLoad('/api/student/store?' + qs, [qs])
  const [buy, setBuy] = useState(null); const toast = useToast(); const nav = useNavigate()
  const set = (k, val) => setF(x => ({ ...x, [k]: val, ...(k === 'track' ? { level: '', exam: '', board: x.board, grade: x.grade } : {}), ...(k === 'level' ? { exam: '', university: '' } : {}) }))
  async function confirm() {
    try { await api('/api/student/purchase', { method: 'POST', body: { book_id: buy.id } }); toast('Added to My books'); setBuy(null); reload(); if (buy.readable) nav(openPath(buy)) }
    catch (e) { toast(e.message, true) }
  }
  const exam = f?.track === 'exam'
  const levels = exam ? ['school', 'degree', 'competitive'] : ['school', 'degree']
  const sel = (k, opts, all, w = 220) => <select className="input" style={{ maxWidth: w }} value={f?.[k] || ''} onChange={e => set(k, e.target.value)}><option value="">{all}</option>{opts.map(o => Array.isArray(o) ? <option key={o[0]} value={o[0]}>{o[1]}</option> : <option key={o}>{o}</option>)}</select>
  return (
    <Page title="Store" sub={exam ? 'Past papers, quick recaps and mock tests for your exam' : 'Digital textbooks for every board, state and university'}>
      <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
        <div className="seg">
          <button className={!exam ? 'on' : ''} onClick={() => set('track', 'textbook')}>Textbooks</button>
          {tx?.exam_track !== false && <button className={exam ? 'on' : ''} onClick={() => set('track', 'exam')}>Exam preparation</button>}</div>
        <div className="seg"><button className={!f?.level ? 'on' : ''} onClick={() => set('level', '')}>All</button>
          {levels.map(l => <button key={l} className={f?.level === l ? 'on' : ''} onClick={() => set('level', l)}>{LEVEL[l]}</button>)}</div>
      </div>
      <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
        {(f?.level === 'school' || (!f?.level && !exam)) && <>{sel('board', data?.boards || [], 'Every board')}{sel('grade', (data?.grades || []).map(g => [g, 'Class ' + g]), 'Every class', 160)}</>}
        {f?.level === 'degree' && sel('university', data?.universities || [], 'Every university', 260)}
        {exam && sel('exam', data?.exams || [], 'Every exam')}
      </div>
      <div className="tiles">{data?.books.map(b => <BookTile key={b.id} b={b} action={
        b.status === 'upcoming' ? <span className="tag" style={{ marginTop: 8 }}>Coming soon</span>
          : b.owned ? <span className="tag ok" style={{ marginTop: 8 }}>In My books</span>
            : <button className="btn primary sm" style={{ marginTop: 8 }} onClick={e => { e.preventDefault(); setBuy(b) }}>Get for {inr(b.price)}</button>} />)}</div>
      {data && !data.books.length && <div className="card empty">Nothing on this shelf yet. Try another {exam ? 'exam' : 'board or class'}.</div>}
      {buy && <Modal title={buy.track === 'exam' ? 'Get this exam pack' : 'Get this book'} onClose={() => setBuy(null)} footer={<><button className="btn" onClick={() => setBuy(null)}>Cancel</button><button className="btn primary" onClick={confirm}>Confirm</button></>}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}><Cover b={buy} size="sm" /><div><b>{buy.title}</b><div className="muted">{buy.exam || buy.board}</div><div style={{ fontSize: 20, fontWeight: 700, marginTop: 6 }}>{inr(buy.price)}</div></div></div>
        <div className="note">Payments are not connected yet. Confirming adds it to My books as a demo purchase; no money is taken.</div>
      </Modal>}
    </Page>
  )
}

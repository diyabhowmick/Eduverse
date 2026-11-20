import { useState } from 'react'
import { day } from '../../api'
import { useLoad, Page, Tag } from '../../ui'
import PaperEditor from '../PaperEditor'

export default function Papers() {
  const { data, reload } = useLoad('/api/exams/review/queue'); const [open, setOpen] = useState(null)
  if (open) return <Page title="Question paper"><PaperEditor pid={open} role="reviewer" onBack={() => { setOpen(null); reload() }} /></Page>
  const waiting = data?.filter(p => p.status === 'in_review') || []
  return (
    <Page title="Question papers" sub="Check every question, its answer and its chapter against the printed paper. Students see a paper only after you approve it.">
      <div className="card"><table className="t"><thead><tr><th>Exam pack</th><th>Paper</th><th className="num">Questions</th><th>Stage</th><th>Added</th><th /></tr></thead>
        <tbody>{[...waiting, ...(data || []).filter(p => p.status !== 'in_review')].map(p => <tr key={p.id}><td><b>{p.pack}</b><div className="muted">{p.exam}</div></td><td>{p.title}</td>
          <td className="num">{p.questions}</td><td><Tag s={p.status} /></td><td className="muted">{day(p.created_at)}</td>
          <td className="acts"><button className={'btn sm ' + (p.status === 'in_review' ? 'primary' : '')} onClick={() => setOpen(p.id)}>{p.status === 'in_review' ? 'Review' : 'View'}</button></td></tr>)}</tbody></table>
        {data && !data.length && <div className="empty">No question papers yet</div>}</div>
    </Page>
  )
}

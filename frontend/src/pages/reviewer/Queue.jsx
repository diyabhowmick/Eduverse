import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useLoad, Page, Tag } from '../../ui'

export default function Queue() {
  const { data, reload } = useLoad('/api/review/queue')
  useEffect(() => { const t = setInterval(reload, 10000); return () => clearInterval(t) }, [reload])  // new books appear without reloading
  const ready = data?.filter(b => b.status === 'in_review' && b.has_content) || []
  const waiting = data?.filter(b => !(b.status === 'in_review' && b.has_content)) || []
  return (
    <Page title="Review queue" sub="Books extracted by M1 wait here. Nothing is published until you approve every page.">
      <div className="stack">
        <div className="card"><div className="card-h"><h3>Ready for review</h3><span className="sub">{ready.length} books</span></div>
          <table className="t"><thead><tr><th>Book</th><th>Found in the file</th><th>Pages approved</th><th className="num">Flagged by the converter</th><th /></tr></thead>
            <tbody>{ready.map(b => { const p = b.progress; const pct = p.total ? p.approved / p.total * 100 : 0; return (
              <tr key={b.id}><td><b>{b.title}</b><div className="muted">{b.board}, Class {b.grade}</div><div>{b.assigned_to_me ? <span className="tag info">Assigned to you</span> : <span className="tag">Open to any reviewer</span>}</div></td>
                <td className="muted">Units {b.chapters.join(', ')}, {b.figures} figures</td>
                <td style={{ minWidth: 200 }}><div className="bar-track"><i style={{ width: pct + '%' }} /></div><div className="muted">{p.approved} of {p.total}{p.rejected ? `, ${p.rejected} rejected` : ''}</div></td>
                <td className="num">{b.flags ? <span className="tag warn">{b.flags} to check</span> : 0}</td>
                <td className="acts"><Link className="btn primary sm" to={'/review/books/' + b.id}>{p.approved || p.rejected ? 'Continue review' : 'Start review'}</Link></td></tr>) })}</tbody></table>
          {data && !ready.length && <div className="empty">Nothing to review right now</div>}</div>
        <div className="card"><div className="card-h"><h3>Not ready yet</h3><span className="sub">Extraction running, or sent back for a fix</span></div>
          <table className="t"><thead><tr><th>Book</th><th>Status</th><th>Note</th></tr></thead>
            <tbody>{waiting.map(b => <tr key={b.id}><td><b>{b.title}</b><div className="muted">{b.board}, Class {b.grade}</div></td>
              <td><Tag s={b.status === 'in_review' ? 'processing' : b.status}>{b.status === 'rejected' ? 'Sent back' : 'Waiting for extraction'}</Tag></td>
              <td className="muted">{b.review_note || 'Appears in the queue when M1 and the converter finish'}</td></tr>)}</tbody></table>
          {data && !waiting.length && <div className="empty">Nothing waiting</div>}</div>
      </div>
    </Page>
  )
}

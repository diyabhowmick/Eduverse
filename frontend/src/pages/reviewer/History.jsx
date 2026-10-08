import { when } from '../../api'
import { useLoad, Page, Tag } from '../../ui'

export default function History() {
  const { data } = useLoad('/api/review/history')
  return (
    <Page title="Reviewed books" sub="Books published or sent back, with who decided">
      <div className="card"><table className="t"><thead><tr><th>Book</th><th>Decision</th><th>By</th><th>When</th><th>Note</th></tr></thead>
        <tbody>{data?.map(b => <tr key={b.id}><td><b>{b.title}</b><div className="muted">{b.board}, Class {b.grade}</div></td>
          <td><Tag s={b.status} /></td><td>{b.reviewed_by}</td><td className="muted">{when(b.reviewed_at)}</td><td className="muted">{b.review_note}</td></tr>)}</tbody></table>
        {data && !data.length && <div className="empty">No decisions yet</div>}</div>
    </Page>
  )
}

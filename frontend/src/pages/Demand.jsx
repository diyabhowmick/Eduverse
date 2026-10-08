import { useState } from 'react'
import { useLoad, Page, Tag } from '../ui'
import { num } from '../api'

/* Books by demand — the business model on one screen.

   A book is paid for once and read by every school on that syllabus. So the
   number that matters is not what a book cost, it is what it cost per school,
   which falls every time another school picks it up. */
export default function Demand() {
  const { data: books } = useLoad('/api/money/books')
  const [est, setEst] = useState({ pages: 288, route: 'native', figures: 330, keywords: 2000 })
  const q = `pages=${est.pages}&route=${est.route}&figures=${est.figures}&keywords=${est.keywords}`
  const { data: e } = useLoad('/api/money/estimate?' + q, [q])
  if (!books) return <Page title="Books by demand" />

  const total = books.reduce((a, b) => a + b.cost_usd, 0)
  const shared = books.filter(b => b.classes > 0)
  const idle = books.filter(b => b.status === 'live' && !b.classes)
  const best = [...shared].sort((a, b) => a.cost_per_class - b.cost_per_class)[0]

  return (
    <Page title="Books by demand" sub="Which books are actually read, and what each one costs per class">
      {best && <p className="headline">
        <em>{best.title}</em> cost <em>${best.cost_usd.toFixed(2)}</em> to make and is read by{' '}
        <em>{best.classes}</em> classes — <em>${best.cost_per_class.toFixed(3)}</em> each. Every
        class that picks it up makes it cheaper.
      </p>}
      <div className="stack">
        <div className="metrics">
          <div className="metric"><div className="v">${total.toFixed(2)}</div><div className="l">Whole catalogue, processed once</div></div>
          <div className="metric"><div className="v">{shared.length}</div><div className="l">Books being read</div></div>
          <div className="metric"><div className="v">{idle.length}</div><div className="l">Live but nobody reads them</div></div>
          <div className="metric"><div className="v">{num(books.reduce((a, b) => a + b.classes, 0))}</div><div className="l">Classes reading</div></div>
        </div>

        <div className="card">
          <div className="card-h"><h3>What a book would cost</h3></div>
          <div className="card-b">
            <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
              Worth checking before you upload. A scanned book has to be read page by page by a
              model; a book with a text layer does not. Figures and explanations cost the same
              either way — the page reading is the whole difference.
            </p>
            <div className="grid3">
              <div className="field"><label>Pages</label>
                <input className="input" type="number" value={est.pages}
                  onChange={ev => setEst({ ...est, pages: +ev.target.value || 0 })} /></div>
              <div className="field"><label>Does the PDF have a text layer?</label>
                <select className="input" value={est.route}
                  onChange={ev => setEst({ ...est, route: ev.target.value })}>
                  <option value="native">Yes — native, no page reading</option>
                  <option value="scanned">No — every page read by a model</option>
                </select></div>
              <div className="field"><label>Figures, roughly</label>
                <input className="input" type="number" value={est.figures}
                  onChange={ev => setEst({ ...est, figures: +ev.target.value || 0 })} /></div>
            </div>
            {e && <div className="row" style={{ marginTop: 14, alignItems: 'flex-start' }}>
              <div style={{ minWidth: 130 }}>
                <div className="muted" style={{ fontSize: 12 }}>About</div>
                <div style={{ fontSize: 26, fontWeight: 740, letterSpacing: '-.03em' }}>
                  ${e.total.toFixed(2)}</div>
                <div className="muted" style={{ fontSize: 11.5 }}>
                  pages ${e.pages.toFixed(2)} · figures ${e.figures.toFixed(2)} · explanations ${e.explanations.toFixed(2)}
                </div>
              </div>
              <div className={'note' + (est.route === 'scanned' ? ' warn' : '')} style={{ flex: 1, margin: 0 }}>
                {e.note}
              </div>
            </div>}
          </div>
        </div>

        <div className="card">
          <div className="card-h"><h3>Every book</h3><span className="muted" style={{ fontSize: 12.5 }}>most read first</span></div>
          <table className="t">
            <thead><tr>
              <th>Book</th><th>Stage</th><th>How it was read</th>
              <th className="num">Cost</th><th className="num">Classes</th><th className="num">Each</th>
            </tr></thead>
            <tbody>{books.map(b => (
              <tr key={b.id}>
                <td><b>{b.title}</b>
                  <div className="muted" style={{ fontSize: 12 }}>{b.pages || '—'} pages · {b.figures || 0} figures</div></td>
                <td><Tag s={b.status} /></td>
                <td>{b.route === 'scanned'
                  ? <Tag s="warn">scanned — paid</Tag>
                  : <Tag s="ok">native — free</Tag>}</td>
                <td className="num">${b.cost_usd.toFixed(2)}</td>
                <td className="num">{b.classes || '—'}</td>
                <td className="num">{b.cost_per_class
                  ? <b style={{ color: 'var(--ok, #1F7A4C)' }}>${b.cost_per_class.toFixed(3)}</b>
                  : <span className="muted">not shared yet</span>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>

        {idle.length > 0 && <div className="note warn">
          <b>{idle.length} live book{idle.length > 1 ? 's' : ''} nobody reads.</b>{' '}
          {idle.map(b => b.title).join(', ')} — processed, published, and assigned to no class.
          Either sell {idle.length > 1 ? 'them' : 'it'} or stop making books for that grade.
        </div>}

        {books.some(b => b.split_by === 'pages') && <div className="note warn">
          <b>Some books converted badly.</b>{' '}
          {books.filter(b => b.split_by === 'pages').map(b => b.title).join(', ')} found almost no
          headings, so {books.filter(b => b.split_by === 'pages').length > 1 ? 'they were' : 'it was'} split
          page by page instead of by chapter. The text is all there, but there is no structure to
          navigate — a reviewer will spend hours on it either way.
        </div>}
      </div>
    </Page>
  )
}

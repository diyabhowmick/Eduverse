import { Link } from 'react-router-dom'
import { when } from '../../api'
import { useLoad, Page, Tag } from '../../ui'

/* What needs doing — Platform Admin's home.

   The same idea as Super Admin's home screen, pointed at the factory instead
   of the money: what is broken, what is waiting on a person, and what is
   running. Nothing here is a price. */
export default function Needs() {
  const { data: h } = useLoad('/api/factory/health?days=30')
  const { data: k } = useLoad('/api/factory/keys')
  if (!h || !k) return <Page title="What needs doing" />

  const jobs = h.jobs
  const items = [
    k.missing.length && {
      t: k.missing.length === 1 ? 'A key is missing' : `${k.missing.length} keys are missing`,
      s: k.missing.join(' and ') + ' — that part of the pipeline cannot run at all.',
      to: '/pa/keys', go: 'Keys and spending', tone: 'bad', n: k.missing.length,
    },
    jobs.failed && {
      t: `${jobs.failed} ${jobs.failed === 1 ? 'book' : 'books'} failed to process`,
      s: h.failures.length ? 'Commonest reason: ' + h.failures[0].why : 'No reason recorded.',
      to: '/pa/health', go: 'Pipeline health', tone: 'bad', n: jobs.failed,
    },
    h.stuck_in_review.length && {
      t: `${h.stuck_in_review.length} ${h.stuck_in_review.length === 1 ? 'book has' : 'books have'} sat in review over two weeks`,
      s: 'A reviewer has it and is not working on it. Hand it to someone else.',
      to: '/pa/reviewers', go: 'Reviewers', tone: 'warn', n: h.stuck_in_review.length,
    },
    h.poor_conversions.length && {
      t: `${h.poor_conversions.length} ${h.poor_conversions.length === 1 ? 'book' : 'books'} came out with no chapter list`,
      s: 'No section numbers and no headings found, so every page became its own unit. Readable, but worth checking the original.',
      to: '/pa/health', go: 'Pipeline health', tone: 'warn', n: h.poor_conversions.length,
    },
    h.no_figures.length && {
      t: `${h.no_figures.length} long ${h.no_figures.length === 1 ? 'book has' : 'books have'} no figures at all`,
      s: 'Figure detection probably missed them rather than the book having none.',
      to: '/pa/health', go: 'Pipeline health', tone: 'warn', n: h.no_figures.length,
    },
    jobs.running + jobs.queued && {
      t: `${jobs.running + jobs.queued} ${jobs.running + jobs.queued === 1 ? 'book is' : 'books are'} in the pipeline now`,
      s: `${jobs.running} running, ${jobs.queued} waiting${h.min_per_page ? ` · about ${h.min_per_page} minutes a page` : ''}.`,
      to: '/pa/processing', go: 'Processing', tone: 'info', n: jobs.running + jobs.queued,
    },
  ].filter(Boolean)

  const urgent = items.filter(i => i.tone === 'bad').length

  return (
    <Page title="What needs doing" sub="The factory — what is broken, what is waiting on a person, what is running">
      <p className="headline">
        {!items.length
          ? <>Nothing needs doing. Every key is set, nothing failed in the last 30 days, and nothing is stuck.</>
          : urgent
            ? <><em>{urgent}</em> {urgent === 1 ? 'thing is' : 'things are'} actually broken.
              {items.length > urgent && <> {items.length - urgent} more worth a look.</>}</>
            : <><em>{items.length}</em> {items.length === 1 ? 'thing' : 'things'} worth a look. Nothing is broken.</>}
      </p>

      <div className="stack">
        {items.map((i, n) => (
          <div className="card" key={n}>
            <div className="card-h">
              <Tag s={i.tone}>{i.n}</Tag>
              <h3>{i.t}</h3>
              <span className="right"><Link className="btn" to={i.to}>{i.go}</Link></span>
            </div>
            <div className="note">{i.s}</div>
          </div>))}

        {!items.length && <div className="card"><div className="empty">
          Nothing is waiting on you. <Link to="/pa/demand" style={{ marginLeft: 4 }}>Catalogue and cost</Link> shows
          what the books built so far have cost, and how many classes each one serves.
        </div></div>}

        <div className="note">
          <b>Where the money goes is on <Link to="/pa/keys">Keys and spending</Link>.</b> This side of
          the product sees what a book costs to make — never what a school is charged for it. The
          catalogue has cost ${k.spend.all_time_usd.toFixed(2)} in all, across {k.spend.books_all_time} books.
        </div>

        {!!h.recent_failures.length && <div className="card">
          <div className="card-h"><h3>The last thing that failed</h3></div>
          <div className="note">
            <b>{h.recent_failures[0].filename}</b> stopped after {h.recent_failures[0].pages_done} pages
            on {when(h.recent_failures[0].at)}. {h.recent_failures[0].why}
          </div>
        </div>}
      </div>
    </Page>
  )
}

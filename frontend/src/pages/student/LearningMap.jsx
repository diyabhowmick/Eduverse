import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useLoad, Page } from '../../ui'

/* The book as a road.

   One stretch of road per chapter, one stop per section, and the chapter test
   at the end of the stretch. Everything shown here comes from progress the
   reader already records — the sections opened, the chapter tests taken and
   the daily rows — so the map never disagrees with the percentage on Home.

   The road is drawn as one cubic segment between each pair of stops rather
   than a single path, so how much of it is finished needs no path-length
   arithmetic: a segment is simply red when the stop it leads to is done. */

const ROW = 112, LEFT = 150, RIGHT = 470, TOP = 76, PAD = 150, ROAD_W = 620

function layout(chapters) {
  const nodes = []
  let row = 0
  chapters.forEach(ch => {
    nodes.push({ kind: 'banner', ch, row: row++ })
    ch.sections.forEach(s => nodes.push({ kind: 'sec', ch, s, row: row++ }))
    nodes.push({ kind: 'test', ch, row: row++ })
  })
  nodes.forEach(n => {
    const wobble = Math.sin(n.row * 0.8)
    const half = (RIGHT - LEFT) / 2
    n.x = (LEFT + RIGHT) / 2 + wobble * (n.kind === 'banner' ? half - 56 : half)
    n.y = TOP + n.row * ROW
  })
  return nodes
}

/* An S-curve between two stops, so the road bends instead of zig-zagging. */
const link = (a, b) => `M ${a.x} ${a.y} C ${a.x} ${(a.y + b.y) / 2}, ${b.x} ${(a.y + b.y) / 2}, ${b.x} ${b.y}`

const stars = k => '★★★☆☆☆'.slice(3 - k, 6 - k)

export default function LearningMap() {
  const { id } = useParams()
  const nav = useNavigate()
  const { data: home } = useLoad(id ? null : '/api/student/home', [id])
  const { data, error } = useLoad(id ? `/api/student/books/${id}/map` : null, [id])
  const scroller = useRef(null)
  const nodes = useMemo(() => (data ? layout(data.chapters) : []), [data])
  // The road is laid out at a fixed width and then scaled to whatever room
  // there is, so it fits a phone without the stops falling off the right.
  const [scale, setScale] = useState(1)

  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const fit = () => setScale(Math.min(1, (el.clientWidth - 16) / ROAD_W))
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [data])

  // Open where the student actually is, not at the top of the book.
  useEffect(() => {
    if (!data || !scroller.current) return
    const here = nodes.find(n => n.kind === 'sec' && n.s.id === data.current?.section)
    const el = scroller.current
    el.scrollTop = Math.max(0, (here ? here.y : 0) * scale - el.clientHeight / 2)
  }, [data, nodes, scale])

  /* ---- no book chosen: offer the ones they have ---- */
  if (!id) {
    const books = (home?.books || []).filter(b => b.track !== 'exam')
    if (books.length === 1) return <Navigateish to={`/student/map/${books[0].id}`} nav={nav} />
    return (
      <Page title="Your learning map" sub="Pick a book to see its road">
        {home && !books.length && <div className="card empty">No textbooks yet. Get one from the store and its map appears here.</div>}
        <div className="map-pick">
          {books.map(b => (
            <Link key={b.id} className="map-pick-card" to={`/student/map/${b.id}`}>
              <b>{b.title}</b>
              <span>{[b.board, b.grade && 'Class ' + b.grade, b.subject].filter(Boolean).join(' · ')}</span>
              <div className="map-pick-bar"><i style={{ width: Math.round(b.progress || 0) + "%" }} /></div>
              <span className="muted">{Math.round(b.progress || 0)}% of the road travelled</span>
            </Link>
          ))}
        </div>
      </Page>
    )
  }

  if (error) return <Page title="Your learning map"><div className="card empty">{error}</div></Page>
  if (!data) return <Page title="Your learning map"><div className="card empty">Loading the road…</div></Page>

  const height = (nodes.length ? nodes[nodes.length - 1].y : TOP) + PAD
  const isHere = n => n.kind === 'sec' && n.s.id === data.current?.section
  const here = nodes.find(isHere)
  // How far along the road has actually been walked: up to the first stop
  // still to do. Everything past that is still grey, however much of it the
  // student may have dipped into out of order.
  const firstTodo = nodes.findIndex(n => (n.kind === 'sec' && !n.s.done) || (n.kind === 'test' && !n.ch.test.taken))
  const travelled = firstTodo < 0 ? nodes.length : firstTodo

  return (
    <Page
      title={data.book.title}
      sub={`${data.done} of ${data.total} stops · ${data.percent}% of the road`}
      actions={<>
        <span className="map-chip gold">★ {data.stars}</span>
        <span className="map-chip fire">🔥 {data.streak}</span>
        <Link className="btn" to={`/student/read/${id}`}>Open the book</Link>
      </>}>

      <div className="map-scroll" ref={scroller}>
        <div className="map-fit" style={{ height: height * scale }}>
        <div className="map-road" style={{ height, transform: `scale(${scale})` }}>
          <svg width={ROAD_W} height={height} aria-hidden="true">
            {nodes.slice(0, -1).map((n, i) => {
              // Red is the road already travelled, so it stops at the first
              // stop not yet done. Without that the road runs red past a
              // section the student has not read, to a unit test they happen
              // to have taken early.
              const next = nodes[i + 1]
              return <path key={i} className={'map-seg' + (i < travelled ? ' done' : '')} d={link(n, next)} />
            })}
          </svg>

          {nodes.map((n, i) => {
            if (n.kind === 'banner') return (
              <div key={i} className={'map-banner' + (n.ch.complete ? ' done' : '')} style={{ left: n.x, top: n.y }}>
                <div className="num">{n.ch.number}</div>
                <div className="tt"><b>{n.ch.title}</b><span>{n.ch.done} of {n.ch.total} done</span></div>
              </div>
            )
            if (n.kind === 'test') {
              const t = n.ch.test
              const open = n.ch.complete && t.questions > 0
              // Gold is for a test that went well. Sitting it and scoring
              // nothing is not a trophy, so that shows as attempted instead.
              const cls = t.taken ? (t.stars > 0 ? ' done' : ' attempted') : open ? ' open' : ''
              return (
                <button key={i} className={'map-node boss' + cls} style={{ left: n.x, top: n.y }}
                  disabled={!t.questions}
                  title={!t.questions ? 'No questions for this unit yet' : t.taken ? `Best ${t.score} of ${t.out_of}` : 'Take the unit test'}
                  onClick={() => nav(`/student/test/${id}/${n.ch.number}`)}>
                  {t.stars > 0 && <span className="map-stars">{stars(t.stars)}</span>}
                  <span className="disc">🏆</span>
                  <span className="map-label">
                    {t.questions ? `Unit ${n.ch.number} test` : 'Unit test — no questions yet'}
                    {t.taken && <i> · {t.score}/{t.out_of}</i>}
                  </span>
                </button>
              )
            }
            const cls = n.s.done ? ' done' : isHere(n) ? ' here' : ''
            return (
              <button key={i} className={'map-node' + cls} style={{ left: n.x, top: n.y }}
                title={`${n.s.number} ${n.s.title}`}
                onClick={() => nav(`/student/read/${id}?ch=${n.ch.number}&sec=${encodeURIComponent(n.s.id)}`)}>
                <span className="disc">{n.s.done ? '✓' : n.s.number}</span>
                <span className="map-label">{n.s.title}</span>
              </button>
            )
          })}

          {here && (
            <div className="map-hero" style={{ left: here.x + 46, top: here.y - 6 }}>
              <span className="map-hero-name">You</span>
              <span className="map-hero-face">🧑‍🚀</span>
            </div>
          )}
        </div>
        </div>
      </div>

      <div className="note">
        A stop turns red once you have read that section. The trophy at the end of each unit is its chapter
        test, and the stars on it come from how well you did.
      </div>
    </Page>
  )
}

/* One book, so go straight to it rather than making them choose from a list of one. */
function Navigateish({ to, nav }) {
  useEffect(() => { nav(to, { replace: true }) }, [to, nav])
  return null
}

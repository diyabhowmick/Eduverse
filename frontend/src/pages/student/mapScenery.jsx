/* The landscape the learning map's road runs through: hills, trees, bushes, clouds, and a science prop by each
   unit test. Pure decoration: aria-hidden, never focusable, never under a pointer.

   Placement rules
   - Coordinates are the road's own (the same x and y as the stops), so on a phone the scenery shrinks with the
     road. The layer is wider than the road, sceneW, so it also fills the margins of a wide screen; ox is how
     far it reaches left of the road's box.
   - Hills are ground and may lie under the road. Everything else keeps clear of the road (sampled along each
     curve), every stop and its label, every chapter banner and the "You" marker. Label sizes are estimated
     from their text, not measured, so placement is the same before and after fonts load.
   - Deterministic: every random choice comes from a generator seeded with the book id and the row index, so a
     book draws the same landscape every time at a given width. A different width moves the road, and the
     scenery moves with it.
   - Static shapes of one colour are merged into one <path> per band of BAND px, so a long book costs a few
     elements a band, not a few an item. Bands matter: one path running the whole length of the map made every
     tile Chrome rasterises while scrolling walk all of it, and scrolling a long book dropped to about 25 fps.
     All hill bands come before all plant bands, so a hill never covers a tree from the band above. Clouds are
     separate small elements, because they move: the compositor can slide them without repainting the land.
     Colours come from CSS variables (styles.css), so the theme switches without a render. */

const ROW = 112, TOP = 76
const ROAD_HALF = 16        // half the road's casing, px
const CLEAR = 12            // px kept between scenery and the road, a stop, a label or a banner
const HILL_BAND = 360       // px of map height per band of hills
const DRIFT = 28            // px a cloud drifts either way (styles.css map-drift)
const BAND = 1200           // px of map height per scenery tile
const SKY = 460             // px of sky gradient at the top of the journey

/* How wide a label may be on a phone: twice its stop's distance to the nearer edge of the box (the road's box
   plus the 8px each side the map keeps), less a little. LearningMap.jsx sets it as max-width; the obstacles
   below use it to know when a label wraps. BANNER_NUM is the chapter number badge and the gap after it. */
export const labelRoom = (x, roadW) => Math.round(2 * Math.min(x + 8, roadW - x + 8) - 4)
export const BANNER_NUM = 37

/* A small, fast, seeded generator (mulberry32) and a seed from the book id, the row and what it is for. */
function rng(book, row, what) {
  let h = 2166136261
  for (const ch of `${book}:${row}:${what}`) h = Math.imul(h ^ ch.charCodeAt(0), 16777619)
  let a = h >>> 0
  return () => {
    a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const f = n => Math.round(n * 10) / 10
const circle = (x, y, r) => `M${f(x - r)} ${f(y)}a${f(r)} ${f(r)} 0 1 0 ${f(2 * r)} 0a${f(r)} ${f(r)} 0 1 0 ${f(-2 * r)} 0`

/* What must stay clear: boxes for stops, labels, banners and the "You" marker, and points along the road. */
function obstacles(nodes, here, narrow, roadW) {
  const boxes = [], road = []
  const box = (x0, y0, x1, y1) => boxes.push([x0 - CLEAR, y0 - CLEAR, x1 + CLEAR, y1 + CLEAR])
  nodes.forEach((n, i) => {
    if (n.kind === 'banner') {
      let w = BANNER_NUM + Math.max(n.ch.title.length * 7.4, 14 * 5.8) + 26, h = 23
      if (narrow && w > labelRoom(n.x, roadW)) { w = labelRoom(n.x, roadW); h = 31 }     // the title wraps
      box(n.x - w / 2, n.y - h, n.x + w / 2, n.y + h)
    } else {
      const r = n.kind === 'test' ? 38 : 30
      const t = n.ch.test                            // the same words LearningMap.jsx prints under the stop
      const label = n.kind === 'sec' ? n.s.title
        : t.questions ? `Unit ${n.ch.number} test${t.taken ? ` · ${t.score}/${t.out_of}` : ''}` : 'Unit test — no questions yet'
      let w = label.length * 6.6 + 18, lines = 1
      if (narrow && w > labelRoom(n.x, roadW)) { w = labelRoom(n.x, roadW); lines = 2 }   // wraps, two lines at most
      box(n.x - r, n.y - r - (n.kind === 'test' ? 14 : 0), n.x + r, n.y + r)
      box(n.x - w / 2, n.y + r + 1, n.x + w / 2, n.y + r + 25 + (lines - 1) * 15)
    }
    if (n.kind === 'sec' && n.s.id === here) box(n.x + 20, n.y - 51, n.x + 72, n.y + 20)
    const m = nodes[i + 1]
    if (m) {                                         // the same cubic as link() in LearningMap.jsx
      const my = (n.y + m.y) / 2
      for (let k = 0; k <= 12; k++) {
        const t = k / 12, u = 1 - t
        road.push([u * u * u * n.x + 3 * u * u * t * n.x + 3 * u * t * t * m.x + t * t * t * m.x,
                   u * u * u * n.y + 3 * u * u * t * my + 3 * u * t * t * my + t * t * t * m.y])
      }
    }
  })
  return { boxes, road }
}

export function scenery({ nodes, roadW, sceneW, height, bookId, here, narrow = false }) {
  if (!nodes.length) return null
  const ox = (sceneW - roadW) / 2
  const { boxes, road } = obstacles(nodes, here, narrow, roadW)
  const placed = []
  const free = (x, y, rx, ry = rx) => {
    if (x - rx < -ox || x + rx > roadW + ox || y - ry < 0 || y + ry > height) return false
    for (const [x0, y0, x1, y1] of boxes) if (x + rx > x0 && x - rx < x1 && y + ry > y0 && y - ry < y1) return false
    const reach = ROAD_HALF + CLEAR + Math.max(rx, ry)
    for (const [px, py] of road) if (Math.abs(py - y) < reach && Math.hypot(px - x, py - y) < reach) return false
    for (const p of placed) if (Math.hypot(p.x - x, p.y - y) < p.r + Math.max(rx, ry) + 6) return false
    return true
  }
  const keep = (x, y, r) => placed.push({ x, y, r })
  const bands = Array.from({ length: Math.ceil(height / BAND) }, () => ({ leafA: [], leafB: [], pine: [], trunk: [], hills: [] }))
  const bandOf = y => bands[Math.max(0, Math.min(bands.length - 1, Math.floor(y / BAND)))]

  // Soft rolling hills: ground, behind everything, the road included. A hill is a smooth mound standing on a
  // base line, filled down past the next band. On the horizon there are three depths: far hills, palest, widest
  // and tallest; then middle; then near, lowest. Each has its own crest, so the skyline rises and falls. Every
  // band below gets its own row of lower mounds over the last. Coordinates here are the scene's (0..sceneW).
  const horizon = []                                  // the horizon's mounds, for groundY
  const mound = (cx, w, h, base) => {
    let d = `M${f(cx - w / 2)} ${f(base)}`
    for (let k = 1; k <= 24; k++) d += `L${f(cx - w / 2 + w * k / 24)} ${f(base - h * (1 - Math.cos(2 * Math.PI * k / 24)) / 2)}`
    return d + 'z'
  }
  const layer = (R, shade, base, spacing, w0, w1, h0, h1, depth, keepTop) => {
    const n = Math.ceil(sceneW / spacing) + 1, out = [`M-40 ${f(base)}H${f(sceneW + 40)}V${f(base + depth)}H-40z`]
    for (let k = 0; k <= n; k++) {
      const cx = (k + (R() - 0.5) * 0.7) * (sceneW / n), w = w0 + R() * (w1 - w0), h = h0 + R() * (h1 - h0)
      out.push(mound(cx, w, h, base))
      if (keepTop) horizon.push({ cx, w, h, base })
    }
    const hills = bandOf(base).hills                  // painted in the order pushed: far, middle, near, then lower bands
    if (hills.at(-1)?.[0] === shade) hills.at(-1)[1].push(...out)
    else hills.push([shade, out])
  }
  const B0 = SKY - 60
  const R1 = rng(bookId, 0, 'hills')
  layer(R1, 3, B0, 380, 440, 780, 80, 170, HILL_BAND + 140, true)              // far: the palest, map-hill h3
  layer(R1, 1, B0 + 34, 320, 340, 620, 45, 105, HILL_BAND + 100, true)         // middle: h1
  layer(R1, 2, B0 + 72, 420, 300, 560, 22, 64, HILL_BAND + 60, true)           // near: the deepest, h2
  for (let band = 1, base = B0 + 72 + HILL_BAND; base < height + 40; band++, base += HILL_BAND)
    layer(rng(bookId, band, 'hills'), 1 + band % 3, base, 400, 380, 780, 28, 84, HILL_BAND + 140, false)
  // the top of the ground at scene x: the highest of the horizon's base lines and mounds over it
  const groundY = X => {
    let y = B0
    for (const m of horizon) {
      const u = (X - (m.cx - m.w / 2)) / m.w
      if (u > 0 && u < 1) y = Math.min(y, m.base - m.h * (1 - Math.cos(2 * Math.PI * u)) / 2)
    }
    return y
  }
  // something standing at road x, whose foot is at y, is on the ground
  const onGround = (x, foot) => foot >= groundY(x + ox) + 4

  // a science prop beside each unit test, to mark it as a milestone
  const props = []
  nodes.forEach(n => {
    if (n.kind !== 'test') return
    const R = rng(bookId, n.row, 'prop'), s = 44
    const kind = ['atom', 'flask', 'planet'][Math.floor(R() * 3)]
    const side = R() < 0.5 ? -1 : 1
    for (const dx of [110, 150, 200, 250]) for (const sgn of [side, -side]) for (const dy of [0, -28, 28]) {
      const x = n.x + sgn * dx, y = n.y + dy
      if (props.at(-1)?.row === n.row || !onGround(x, y + s / 2) || !free(x, y, s / 2)) continue
      props.push({ kind, x: x + ox, y, s, row: n.row }); keep(x, y, s / 2)
    }
  })

  // a few clouds across the top
  const clouds = []
  const R0 = rng(bookId, 0, 'cloud')
  const nClouds = 2 + Math.floor(sceneW / 700)
  for (let i = 0; i < nClouds; i++) {
    const w = 84 + R0() * 60, h = w * 0.46
    for (let k = 0; k < 10; k++) {
      const x = -ox + (i + R0()) * (sceneW / nClouds), y = 14 + R0() * 150
      const X = x + ox, low = y + h / 2 + 10
      if ([X - w / 2 - DRIFT, X, X + w / 2 + DRIFT].some(gx => low > groundY(gx)) || !free(x, y, w / 2 + DRIFT, h / 2)) continue
      clouds.push({ x: f(x + ox - w / 2), y: f(y - h / 2), w: f(w), h: f(h), dur: Math.round(46 + R0() * 30), delay: Math.round(R0() * 40) })
      keep(x, y, w / 2 + DRIFT)
      break
    }
  }

  // trees, pines and bushes: a few a screen, more on a wide canvas, kept off the road
  const rows = Math.ceil((height - TOP) / ROW) + 1
  const perRow = 0.3 + 0.62 * sceneW / 1000          // about 0.7 a row on a phone's 620, 1.7 at 2560
  for (let row = 0; row < rows; row++) {
    const R = rng(bookId, row, 'plants')
    const count = Math.floor(perRow + R())
    for (let i = 0; i < count; i++) {
      const pick = R(), size = 0.85 + R() * 0.4
      const kind = pick < 0.45 ? 'tree' : pick < 0.8 ? 'bush' : 'pine'
      const r = (kind === 'bush' ? 15 : kind === 'pine' ? 18 : 20) * size
      for (let k = 0; k < 8; k++) {
        const x = -ox + R() * sceneW, y = TOP + row * ROW + (R() - 0.5) * ROW
        if (!onGround(x, y + r * 0.6) || !free(x, y, r)) continue
        const X = x + ox, { leafA, leafB, pine, trunk } = bandOf(y)
        if (kind === 'tree') {
          const c = 14 * size;
          (R() < 0.5 ? leafA : leafB).push(circle(X, y - c * 0.5, c), circle(X - c * 0.6, y - c * 0.05, c * 0.68), circle(X + c * 0.62, y, c * 0.62))
          trunk.push(`M${f(X - 2.5)} ${f(y + c * 0.25)}h5v${f(c * 0.75)}h-5z`)
        } else if (kind === 'pine') {
          const c = 15 * size
          pine.push(`M${f(X)} ${f(y - c * 1.15)}L${f(X + c * 0.62)} ${f(y - c * 0.1)}L${f(X - c * 0.62)} ${f(y - c * 0.1)}z`,
                    `M${f(X)} ${f(y - c * 0.6)}L${f(X + c * 0.8)} ${f(y + c * 0.55)}L${f(X - c * 0.8)} ${f(y + c * 0.55)}z`)
          trunk.push(`M${f(X - 2)} ${f(y + c * 0.55)}h4v${f(c * 0.4)}h-4z`)
        } else {
          const c = 9 * size
          leafB.push(circle(X - c * 0.85, y + 2, c * 0.8), circle(X, y - c * 0.35, c), circle(X + c * 0.85, y + 2, c * 0.78))
        }
        keep(x, y, r)
        break
      }
    }
  }

  return { ox, w: sceneW, props, clouds,
           bands: bands.map(b => ({ hills: b.hills.map(([shade, d]) => [shade, d.join('')]), leafA: b.leafA.join(''), leafB: b.leafB.join(''),
                                     pine: b.pine.join(''), trunk: b.trunk.join('') })) }
}

const CLOUD = 'M20 42a13 13 0 0 1 1-26a19 19 0 0 1 35-7a15 15 0 0 1 27 9a12 12 0 0 1-2 24z'

const SYMBOLS = <>
  <symbol id="map-atom" viewBox="0 0 48 48">
    <g className="map-prop-line" fill="none" strokeWidth="2.2">
      <ellipse cx="24" cy="24" rx="20" ry="7.5" /><ellipse cx="24" cy="24" rx="20" ry="7.5" transform="rotate(60 24 24)" />
      <ellipse cx="24" cy="24" rx="20" ry="7.5" transform="rotate(-60 24 24)" />
    </g>
    <circle className="map-prop-dot" cx="24" cy="24" r="4.2" />
  </symbol>
  <symbol id="map-flask" viewBox="0 0 48 48">
    <path className="map-prop-fill" d="M15.5 33h17l4.3 7.6c.9 1.6-.2 3.4-2 3.4H13.2c-1.8 0-2.9-1.8-2-3.4z" />
    <path className="map-prop-line" fill="none" strokeWidth="2.2" strokeLinejoin="round"
      d="M19 5h10M20.5 5v13L9.4 39.6c-1.4 2.6.5 5.4 3.4 5.4h22.4c2.9 0 4.8-2.8 3.4-5.4L27.5 18V5" />
  </symbol>
  <symbol id="map-planet" viewBox="0 0 48 48">
    <circle className="map-prop-fill" cx="24" cy="24" r="12" />
    <ellipse className="map-prop-line" fill="none" strokeWidth="2.2" cx="24" cy="24" rx="21" ry="6.5" transform="rotate(-18 24 24)" />
  </symbol>
</>

/* One tile of the landscape: its own small SVG at its place, drawing in map coordinates. Shapes that cross the
   tile's edge still show (overflow visible); the tile only decides what Chrome has to walk to paint it. */
const Tile = ({ i, w, children }) => (
  <svg className="map-tile" width={w} height={BAND} viewBox={`0 ${i * BAND} ${w} ${BAND}`} style={{ top: i * BAND }} focusable="false">{children}</svg>
)

export function MapScene({ scene, height }) {
  if (!scene) return null
  const { w, bands } = scene
  return (
    <div className="map-scene" style={{ left: -scene.ox, width: w, height }} aria-hidden="true">
      {bands.map((b, i) => (
        <Tile key={'h' + i} i={i} w={w}>
          {i === 0 && <>
            <defs><linearGradient id="map-sky" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" className="map-sky-a" /><stop offset="1" className="map-sky-b" />
            </linearGradient></defs>
            <rect width={w} height={SKY} fill="url(#map-sky)" />
          </>}
          {b.hills.map(([shade, d], k) => <path key={k} className={'map-hill h' + shade} d={d} />)}
        </Tile>
      ))}
      {bands.map((b, i) => (b.trunk || b.leafB) && (
        <Tile key={'p' + i} i={i} w={w}>
          {b.trunk && <path className="map-trunk" d={b.trunk} />}
          {b.pine && <path className="map-pine" d={b.pine} />}
          {b.leafA && <path className="map-leaf a" d={b.leafA} />}
          {b.leafB && <path className="map-leaf b" d={b.leafB} />}
        </Tile>
      ))}
      <svg width={w} height={height} focusable="false">
        <defs>{SYMBOLS}</defs>
        {scene.props.map(p => <use key={p.row} href={'#map-' + p.kind} x={p.x - p.s / 2} y={p.y - p.s / 2} width={p.s} height={p.s} />)}
      </svg>
      {scene.clouds.map((c, i) => (
        <svg key={i} className="map-cloud" viewBox="0 0 100 46" focusable="false"
          style={{ left: c.x, top: c.y, width: c.w, height: c.h, '--dur': c.dur + 's', '--delay': -c.delay + 's' }}>
          <path d={CLOUD} />
        </svg>
      ))}
    </div>
  )
}

import { useEffect, useId, useRef } from 'react'
import './fold.css'

// The EduVerse fold-the-page logo as a living, looping piece.
// width: px number. offset: seconds into the 12s loop to start from. dur: loop length (s).
// tilt: follow the mouse a little (desktop). The whole loop ends on flat pages, so it never "restarts".
// Paper chips that drift in during the scan, themed by who is signing in
const PTS = [[250, 120], [700, 110], [220, 300], [740, 320], [300, 470], [660, 480], [160, 200], [800, 220]]
const CHIPS = {
  student: [['Σ'], ['π', 1], ['√'], ['∫', 1], ['λ'], ['x²', 1], ['Δ'], ['∞', 1]],
  teacher: [['A+', 1], ['✓'], ['92%'], ['↗', 1], ['★'], ['A', 1], ['✓'], ['B+', 1]],
  reviewer: [['✓', 1], ['¶'], ['✓'], ['§', 1], ['Aa'], ['✓', 1], ['✎'], ['✓', 1]],
  admin: [['IX', 1], ['X'], ['A'], ['✓', 1], ['B'], ['XI', 1], ['C'], ['✓', 1]],
  super_admin: [['AI', 1], ['₹'], ['%'], ['✓', 1], ['∑'], ['★', 1], ['#'], ['AI', 1]],
}

// What bursts out of the box the moment it closes: the theme's symbols plus sparks, flung up and out,
// falling a little as they fade. Fixed numbers, so every loop looks the same and nothing jumps.
const SPARKS = ['✦', '✦', '●', '✧', '★', '●']
const BURST = Array.from({ length: 18 }, (_, i) => {
  const a = (-198 + i * (216 / 17) + ((i * 37) % 11) - 5) * Math.PI / 180      // spread across the top half and sides
  const d = 170 + ((i * 53) % 140)
  return { dx: Math.round(Math.cos(a) * d), dy: Math.round(Math.sin(a) * d * 0.78), r: ((i * 71) % 260) - 130, s: 0.75 + ((i * 29) % 50) / 100, bd: ((i * 17) % 9) * 0.025, spark: i % 3 === 2 }
})

export default function FoldLogo({ width = 440, offset = 0, dur = 12, tilt = false, className = '', style, hold = false, theme = 'student', onBurst }) {
  const root = useRef(null), tiltEl = useRef(null)
  const u = useId().replace(/:/g, '')

  // Centre "ASK • ANALYSE • ACHIEVE" using real text widths
  useEffect(() => {
    const lay = () => {
      const r = root.current; if (!r) return
      const ws = [1, 2, 3].map(i => r.querySelector('.tw' + i)); if (!ws[0]?.getComputedTextLength) return
      const gap = 26, d = 8, widths = ws.map(w => Math.max(0, w.getComputedTextLength() - 9))
      let x = 480 - (widths[0] + widths[1] + widths[2] + 2 * (gap * 2 + d * 2)) / 2
      ws.forEach((w, i) => { w.setAttribute('x', x.toFixed(1)); x += widths[i]; if (i < 2) { r.querySelector('.td' + (i + 1)).setAttribute('cx', (x + gap + d).toFixed(1)); x += gap * 2 + d * 2 } })
    }
    lay(); document.fonts?.ready.then(lay)
  }, [])

  // Tell the page the moment the box closes and things burst out (Eddie watches it).
  const burstCb = useRef(onBurst); burstCb.current = onBurst
  useEffect(() => {
    if (!onBurst) return
    let last = -1
    const t = setInterval(() => {
      const a = root.current?.querySelector('.flash')?.getAnimations?.()[0]
      if (!a || a.playState !== 'running') return
      const p = a.effect?.getComputedTiming().progress ?? 0
      if (last >= 0 && last < 0.43 && p >= 0.43) burstCb.current?.()
      last = p
    }, 100)
    return () => clearInterval(t)
  }, [!!onBurst])

  // Pause when the tab is hidden (saves battery), and gentle mouse tilt
  useEffect(() => {
    const vis = () => root.current?.classList.toggle('paused', document.hidden)
    document.addEventListener('visibilitychange', vis)
    let raf = 0, tx = 0, ty = 0, cx = 0, cy = 0, on = true
    const move = e => { tx = -((e.clientY / innerHeight) - .5) * 10; ty = ((e.clientX / innerWidth) - .5) * 16 }
    const loop = () => { if (!on) return; cx += (tx - cx) * .06; cy += (ty - cy) * .06; if (tiltEl.current) tiltEl.current.style.transform = `rotateX(${cx.toFixed(2)}deg) rotateY(${cy.toFixed(2)}deg)`; root.current?.style.setProperty('--lx', (30 + cy * 3).toFixed(1) + '%'); root.current?.style.setProperty('--ly', (22 - cx * 3).toFixed(1) + '%'); raf = requestAnimationFrame(loop) }
    const fine = matchMedia('(pointer:fine)').matches && !matchMedia('(prefers-reduced-motion: reduce)').matches
    if (tilt && fine) { addEventListener('pointermove', move); loop() }
    return () => { on = false; cancelAnimationFrame(raf); removeEventListener('pointermove', move); document.removeEventListener('visibilitychange', vis) }
  }, [tilt])

  const pg = (g, a, b, c, red) => <div className="page anim pg"><div className={'g' + (red ? ' red' : '')}>{g}</div><i style={{ width: a }} /><i style={{ width: b }} /><i style={{ width: c }} /></div>
  const page = (g, a, b, c) => <div className="page"><div className="g">{g}</div><i style={{ width: a }} /><i style={{ width: b }} /><i style={{ width: c }} /></div>

  return <div ref={root} className={'fold ' + className + (hold ? ' paused' : '')} style={{ '--fw': width + 'px', '--off': -offset + 's', '--dur': dur + 's', ...style }}
    role="img" aria-label="EduVerse. Ask, Analyse, Achieve.">
    <div className="fold-stage">
      <div className="fader">
        <svg width="960" height="540" viewBox="0 0 960 540" aria-hidden="true" style={{ position: 'absolute', inset: 0 }}>
          <defs><radialGradient id={u + "fl-glow-g"}><stop offset="0" stopColor="#E0212F" stopOpacity=".6" /><stop offset="1" stopColor="#E0212F" stopOpacity="0" /></radialGradient>
            <radialGradient id={u + "fl-floor-g"}><stop offset="0" stopColor="#FFFFFF" stopOpacity=".09" /><stop offset=".6" stopColor="#FFFFFF" stopOpacity=".03" /><stop offset="1" stopColor="#FFFFFF" stopOpacity="0" /></radialGradient>
            <radialGradient id={u + "fl-halo-g"}><stop offset="0" stopColor="#E0212F" stopOpacity=".22" /><stop offset="1" stopColor="#E0212F" stopOpacity="0" /></radialGradient></defs>
          <ellipse className="anim glow" cx="480" cy="170" rx="230" ry="150" fill={`url(#${u}fl-halo-g)`} />
          <ellipse className="anim shadow" cx="480" cy="292" rx="230" ry="26" fill={`url(#${u}fl-floor-g)`} />
          <ellipse className="anim shadow" cx="480" cy="284" rx="125" ry="18" fill={`url(#${u}fl-glow-g)`} />
          <ellipse className="anim flash" cx="480" cy="250" rx="140" ry="70" fill="none" stroke="#E0212F" strokeWidth="3" />
        </svg>
        {(CHIPS[theme] || CHIPS.student).map(([g, red], i) => <div key={i} className={'pt anim pt' + i + (red ? ' r' : '')} style={{ left: PTS[i][0], top: PTS[i][1] }}>{g}</div>)}
        <div className="fl-burst" aria-hidden="true">{BURST.map((b, i) => {
          const set = CHIPS[theme] || CHIPS.student, g = b.spark ? SPARKS[i % SPARKS.length] : set[i % set.length][0]
          return <span key={i} className={'bp anim' + (b.spark ? ' spark' : '') + (i % 4 === 1 ? ' r' : '')}
            style={{ '--dx': b.dx + 'px', '--dy': b.dy + 'px', '--rot': b.r + 'deg', '--sc': b.s, '--bd': b.bd + 's' }}>{g}</span>
        })}</div>
        <div className="p3" style={{ position: 'absolute', left: 480, top: 165, width: 0, height: 0 }}>
          <div className="p3 fl-float"><div ref={tiltEl} className="p3 tilt"><div className="p3 anim cam">
            <div className="p3" style={{ position: 'absolute', left: -55, top: -55, width: 110, height: 110, transform: 'translateZ(55px)' }}>
              <div className="face">
                {pg('E', '85%', '62%', '74%', true)}
                <div className="anim lg" style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg,#fff,#EEEEEA)' }}>
                  <div className="slot" style={{ left: '30%', right: -4, top: '25%', height: '15%' }} />
                  <div className="slot" style={{ left: '30%', right: -4, top: '60%', height: '15%' }} />
                  <i className="sheen anim" /><i className="spec dim" />
                </div>
                <div className="shade anim sh-f" />
              </div>
              <div className="p3 h h-top anim">
                <div className="face">
                  {pg('Σ', '80%', '58%', '70%')}
                  <div className="anim lg lid"><i className="sheen anim" /><i className="spec" /></div>
                  <div className="shade anim sh-t" />
                </div>
                <div className="p3 h h-back anim"><div className="face">{page('Aa', '78%', '66%', '52%')}</div></div>
              </div>
              <div className="p3 h h-right anim">
                <div className="face">
                  {pg('π', '84%', '60%', '72%')}
                  <div className="anim lg rface" style={{ position: 'absolute', inset: 0 }}>
                    <div className="slot" style={{ left: -4, right: 0, top: '60%', height: '15%', borderLeft: 0, borderRight: 0 }} />
                    <div style={{ position: 'absolute', left: 0, right: 0, top: '75%', bottom: 0, background: 'linear-gradient(180deg,#E8232F,#C3131F)' }} />
                      <i className="spec dim" />
                  </div>
                  <div className="shade anim sh-r" />
                </div>
              </div>
              <div className="p3 h h-left anim"><div className="face">{page('λ', '76%', '64%', '82%')}</div></div>
              <div className="p3 h h-bottom anim"><div className="face">{page('√', '70%', '86%', '58%')}</div></div>
            </div>
          </div></div></div>
        </div>
        <div className="scanglow anim" aria-hidden="true" />
        <div className="scan anim" aria-hidden="true" />
        <svg width="960" height="540" viewBox="0 0 960 540" aria-hidden="true" style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
          <defs><clipPath id={u + "fl-rise"}><rect x="0" y="264" width="960" height="160" /></clipPath></defs>
          <g clipPath={`url(#${u}fl-rise)`}>
            <text className="wm anim edu" x="394" y="406" textAnchor="end" fill="#FFFFFF">EDU</text>
            <text className="wm anim vrs" x="389" y="406" textAnchor="start" fill="#E0212F">VERSE</text>
          </g>
          <text className="tg anim t1 tw1" x="165" y="478">ASK</text>
          <circle className="anim d1 td1" cx="286" cy="469" r="7" fill="#E0212F" />
          <text className="tg anim t2 tw2" x="322" y="478">ANALYSE</text>
          <circle className="anim d2 td2" cx="560" cy="469" r="7" fill="#E0212F" />
          <text className="tg anim t3 tw3" x="596" y="478">ACHIEVE</text>
        </svg>
      </div>
    </div>
  </div>
}

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import FoldLogo from './FoldLogo'
import { HERO_DUR } from './introGate'
import { play } from './sound'

// Sign-in timing (ms). Total from login success to app visible is about LEAD + Eddie's flight + ZOOM + LIFT.
export const LAUNCH = {
  LEAD: 120,      // chime lands before the cube takes over
  FLIGHT: 460,    // Eddie flies into the cube (Eddie.jsx)
  LID: 260,       // lid snaps shut as he arrives
  ZOOM: 420,      // cube spins and rushes towards you
  COVER: .5,      // share of ZOOM after which the backdrop is fully opaque and the app is mounted underneath
  LIFT: 220,      // backdrop fades to reveal the app
  WAIT_MAX: 1500, // longest the backdrop waits for a slow page after the zoom, then lifts anyway
}
// The cube never grows past this. A 3D subtree scaled ~40x forces a huge raster and stutters; at 6x it is
// already fading out over an opaque backdrop, so the rush still reads as flying into it.
const MAX_SCALE = 6

// Lives in App, outside the routes, so the animation keeps playing while the login page is replaced by the app.
let state = null
const subs = new Set()
const emit = s => { state = s; subs.forEach(f => f(s)) }
export const launcher = {
  start: s => emit({ ...s, phase: 'in' }),
  zoom: () => { if (state && state.phase === 'in') emit({ ...state, phase: 'zoom' }) },
  clear: () => emit(null),
}
export function LaunchHost() {
  const [s, set] = useState(state)
  useEffect(() => { subs.add(set); set(state); return () => { subs.delete(set) } }, [])
  return s ? <Launch {...s} onDone={launcher.clear} /> : null
}

// A still, folded copy of the hero cube sits exactly over it, Eddie flies in, the lid snaps shut, then the cube
// spins and rushes towards you. Halfway through, the backdrop is opaque: onCovered navigates, the app mounts
// underneath, and once its first screen has rendered (ready) the backdrop lifts.
export default function Launch({ rect, phase, onDone, onCovered, ready, portal }) {
  const root = useRef(null), wrap = useRef(null), bg = useRef(null)
  useLayoutEffect(() => {
    if (phase !== 'zoom' || !wrap.current) return
    let dead = false
    const fold = wrap.current.querySelector('.fold'), tilt = wrap.current.querySelector('.tilt')
    fold?.classList.remove('lid-pop'); fold?.classList.add('launch-zoom')
    const cx = rect.left + rect.width * .5, cy = rect.top + rect.height * .287
    wrap.current.style.transformOrigin = `${rect.width * .5}px ${rect.height * .287}px`
    const s = Math.min(MAX_SCALE, Math.max(innerWidth, innerHeight) / (rect.width * .16))
    const dx = innerWidth / 2 - cx, dy = innerHeight / 2 - cy
    const d = LAUNCH.ZOOM
    play('whoosh')
    const zoom = wrap.current.animate([
      { transform: 'translate(0,0) scale(1)', offset: 0 },
      { transform: 'translate(0,0) scale(.9)', offset: .18, easing: 'cubic-bezier(.6,0,.2,1)' },
      { transform: `translate(${dx}px,${dy}px) scale(1.4)`, offset: .55, easing: 'cubic-bezier(.7,0,.9,.6)' },
      { transform: `translate(${dx}px,${dy}px) scale(${s})`, offset: 1 },
    ], { duration: d, fill: 'forwards' })
    // gone before it reaches full size, so the largest scale is never on screen
    wrap.current.animate([{ opacity: 1 }, { opacity: 1, offset: .5 }, { opacity: 0, offset: .9 }, { opacity: 0 }], { duration: d, fill: 'forwards' })
    if (tilt) { tilt.style.transition = 'none'; tilt.animate([{ transform: 'rotateY(0deg)' }, { transform: 'rotateY(0deg)', offset: .18 }, { transform: 'rotateY(-360deg)' }], { duration: d, easing: 'cubic-bezier(.5,0,.3,1)', fill: 'forwards' }) }
    const cover = bg.current.animate([{ opacity: 0 }, { opacity: 0, offset: .24 }, { opacity: 1 }], { duration: d * LAUNCH.COVER, fill: 'forwards', easing: 'ease-in' })
    cover.finished.then(() => { if (!dead) onCovered?.() }, () => {})
    const slow = new Promise(r => setTimeout(r, d + LAUNCH.WAIT_MAX))
    Promise.all([zoom.finished, Promise.race([Promise.resolve(ready), slow])]).then(() => {
      // two frames: React commits the new route, then the browser paints it under the backdrop
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (dead || !root.current) return
        root.current.animate([{ opacity: 1 }, { opacity: 0 }], { duration: LAUNCH.LIFT, easing: 'cubic-bezier(.4,0,.2,1)', fill: 'forwards' })
          .finished.then(() => onDone?.(), () => onDone?.())
      }))
    }, () => onDone?.())
    return () => { dead = true }
  }, [phase])
  return <div ref={root} className={'launch launch-' + phase} aria-hidden="true">
    <div ref={bg} className="launch-bg" />
    <div ref={wrap} className="launch-cube" style={{ left: rect.left, top: rect.top, width: rect.width, height: rect.height }}>
      <FoldLogo width={rect.width} dur={HERO_DUR} offset={HERO_DUR * .7} hold theme={portal} />
    </div>
  </div>
}

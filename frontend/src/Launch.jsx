import { useLayoutEffect, useRef } from 'react'
import FoldLogo from './FoldLogo'
import { HERO_DUR } from './introGate'
import { play } from './sound'

// Sign-in success: a still, folded copy of the hero cube sits exactly over it, Eddie flies in,
// the lid snaps shut, then the cube spins and rushes towards you to open the app.
export default function Launch({ rect, phase, onDone, portal }) {
  const wrap = useRef(null), bg = useRef(null)
  useLayoutEffect(() => {
    if (phase !== 'zoom' || !wrap.current) return
    const fold = wrap.current.querySelector('.fold'), tilt = wrap.current.querySelector('.tilt')
    fold?.classList.remove('lid-pop'); fold?.classList.add('launch-zoom')
    const cx = rect.left + rect.width * .5, cy = rect.top + rect.height * .287
    wrap.current.style.transformOrigin = `${rect.width * .5}px ${rect.height * .287}px`
    const s = Math.max(innerWidth, innerHeight) / (rect.width * .16)
    const dx = innerWidth / 2 - cx, dy = innerHeight / 2 - cy
    const d = 1150
    play('whoosh')
    wrap.current.animate([
      { transform: 'translate(0,0) scale(1)', offset: 0 },
      { transform: 'translate(0,0) scale(.9)', offset: .18, easing: 'cubic-bezier(.6,0,.2,1)' },
      { transform: `translate(${dx}px,${dy}px) scale(1.4)`, offset: .55, easing: 'cubic-bezier(.7,0,.9,.6)' },
      { transform: `translate(${dx}px,${dy}px) scale(${s})`, offset: 1 },
    ], { duration: d, fill: 'forwards' })
    if (tilt) { tilt.style.transition = 'none'; tilt.animate([{ transform: 'rotateY(0deg)' }, { transform: 'rotateY(0deg)', offset: .18 }, { transform: 'rotateY(-360deg)' }], { duration: d, easing: 'cubic-bezier(.5,0,.3,1)', fill: 'forwards' }) }
    bg.current.animate([{ opacity: 0 }, { opacity: 0, offset: .35 }, { opacity: 1 }], { duration: d, fill: 'forwards', easing: 'ease-in' })
    wrap.current.animate([{ opacity: 1 }, { opacity: 1, offset: .82 }, { opacity: 0 }], { duration: d, fill: 'forwards', composite: 'add' })
    const t = setTimeout(onDone, d + 60)
    return () => clearTimeout(t)
  }, [phase])
  return <div className={'launch launch-' + phase} aria-hidden="true">
    <div ref={bg} className="launch-bg" />
    <div ref={wrap} className="launch-cube" style={{ left: rect.left, top: rect.top, width: rect.width, height: rect.height }}>
      <FoldLogo width={rect.width} dur={HERO_DUR} offset={HERO_DUR * .7} hold theme={portal} />
    </div>
  </div>
}

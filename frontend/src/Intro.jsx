import { useEffect, useRef, useState } from 'react'
import FoldLogo from './FoldLogo'
import './intro.css'

// Full-screen opening on every load of a login page. The fold logo plays big, then shrinks
// straight into the hero slot on the page (.fold-slot), where the same logo keeps looping.
// Skip with click, Esc, Enter or Space.
export const INTRO_DUR = 7          // seconds for one loop at intro speed
export const LAND_AT = 0.68         // share of the loop where the logo is complete and we land
import { HERO_DUR } from './introGate'
export { HERO_DUR }
const FLY = 1000

export { shouldPlayIntro, markIntroSeen, slowNet } from './introGate'

const size = () => Math.round(Math.min(innerWidth * (innerWidth < 700 ? .92 : .72), 980, innerHeight * .72 * 1.574))

export default function Intro({ onReveal, onDone, theme }) {
  const fly = useRef(null)
  const [phase, setPhase] = useState('play')
  const done = useRef(false)
  const [w, setW] = useState(size)
  useEffect(() => { const r = () => setW(size()); addEventListener('resize', r); return () => removeEventListener('resize', r) }, [])

  function land() {
    if (done.current) return; done.current = true
    setPhase('fly'); onReveal?.(); fly.current?.querySelector('.fold')?.classList.add('paused')
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const t = [...document.querySelectorAll('.fold-slot')].find(el => el.offsetParent !== null)
      const el = fly.current
      if (!t || !el?.animate) { setPhase('gone'); onDone?.(); return }
      const tr = t.getBoundingClientRect(), sr = el.getBoundingClientRect()
      const s = tr.width / sr.width
      const dx = (tr.left + tr.width / 2) - (sr.left + sr.width / 2), dy = (tr.top + tr.height / 2) - (sr.top + sr.height / 2)
      el.animate([{ transform: 'translate(0,0) scale(1)' }, { transform: `translate(${dx}px,${dy}px) scale(${s})` }],
        { duration: FLY, easing: 'cubic-bezier(.65,0,.2,1)', fill: 'forwards' })
      el.animate([{ opacity: 1 }, { opacity: 1, offset: .8 }, { opacity: 0 }], { duration: FLY + 250, fill: 'forwards' })
      setTimeout(() => { setPhase('gone'); onDone?.() }, FLY + 280)
    }))
  }

  useEffect(() => {
    const t = setTimeout(land, INTRO_DUR * LAND_AT * 1000)
    const key = e => { if (['Escape', 'Enter', ' '].includes(e.key)) { e.preventDefault(); land() } }
    addEventListener('keydown', key)
    return () => { clearTimeout(t); removeEventListener('keydown', key) }
  }, [])

  if (phase === 'gone') return null
  return <div className={'evi is-' + phase} onClick={land}>
    <div className="evi-bg" />
    <div className="evi-center"><div ref={fly} className="evi-flyer"><FoldLogo width={w} dur={INTRO_DUR} theme={theme} /></div></div>
    <button type="button" className="evi-skip" onClick={e => { e.stopPropagation(); land() }}>Skip</button>
    <div className="evi-progress"><i style={{ animationDuration: INTRO_DUR * LAND_AT + 's' }} /></div>
  </div>
}

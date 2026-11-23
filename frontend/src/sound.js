// Soft synthesized sounds (no audio files) and phone haptics. Off by default; the choice is remembered.
const KEY = 'ev_sound'
// On unless the person turned it off. Browsers still keep pages silent until they are touched.
let on = (() => { try { return localStorage.getItem(KEY) !== '0' } catch { return true } })()
let ctx = null
const subs = new Set()
export const sound = {
  get on() { return on },
  set(v) { on = v; try { localStorage.setItem(KEY, v ? '1' : '0') } catch { /* private mode */ } subs.forEach(f => f(on)); if (on) play('chime', .5) },
  sub(f) { subs.add(f); return () => subs.delete(f) },
}
function ac() { if (!ctx) { const C = window.AudioContext || window.webkitAudioContext; if (!C) return null; ctx = new C() } if (ctx.state === 'suspended') ctx.resume(); return ctx }
function tone(c, { f = 440, f2, t = .15, type = 'sine', g = .08, at = 0 }) {
  const o = c.createOscillator(), v = c.createGain(), s = c.currentTime + at
  o.type = type; o.frequency.setValueAtTime(f, s); if (f2) o.frequency.exponentialRampToValueAtTime(f2, s + t)
  v.gain.setValueAtTime(0, s); v.gain.linearRampToValueAtTime(g, s + .012); v.gain.exponentialRampToValueAtTime(.0001, s + t)
  o.connect(v).connect(c.destination); o.start(s); o.stop(s + t + .02)
}
function noise(c, { t = 1, g = .05, f = 900, f2 = 400 }) {
  const n = c.sampleRate * t, b = c.createBuffer(1, n, c.sampleRate), d = b.getChannelData(0)
  for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1
  const src = c.createBufferSource(), bp = c.createBiquadFilter(), v = c.createGain(), s = c.currentTime
  src.buffer = b; bp.type = 'bandpass'; bp.Q.value = .8; bp.frequency.setValueAtTime(f, s); bp.frequency.linearRampToValueAtTime(f2, s + t)
  v.gain.setValueAtTime(0, s); v.gain.linearRampToValueAtTime(g, s + .25); v.gain.setValueAtTime(g, s + t * .7); v.gain.linearRampToValueAtTime(0, s + t)
  src.connect(bp).connect(v).connect(c.destination); src.start(s); src.stop(s + t)
}
export function play(name, vol = 1) {
  if (!on) return; const c = ac(); if (!c) return
  const g = x => x * vol
  if (name === 'pop') { tone(c, { f: 380, f2: 900, t: .14, g: g(.07) }); tone(c, { f: 1200, f2: 1600, t: .08, g: g(.03), at: .05 }) }
  if (name === 'jet') noise(c, { t: 2.6, g: g(.035), f: 700, f2: 1300 })
  if (name === 'land') { tone(c, { f: 180, f2: 90, t: .18, g: g(.09) }); tone(c, { f: 880, t: .12, g: g(.025), at: .06 }) }
  if (name === 'chime') { [660, 880, 1320].forEach((f, i) => tone(c, { f, t: .5, g: g(.045), at: i * .07 })) }
  if (name === 'error') { tone(c, { f: 260, f2: 220, t: .16, g: g(.06), type: 'triangle' }); tone(c, { f: 220, f2: 180, t: .2, g: g(.06), type: 'triangle', at: .15 }) }
  if (name === 'whoosh') noise(c, { t: 1.1, g: g(.05), f: 400, f2: 2200 })
  if (name === 'tap') tone(c, { f: 1000, t: .05, g: g(.02) })
}
export function buzz(p) { try { navigator.vibrate?.(p) } catch { /* not supported */ } }


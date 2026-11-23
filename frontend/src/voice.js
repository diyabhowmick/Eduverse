// Eddie's voice: the browser's own speech engine, no audio files, nothing sent anywhere.
// Browsers only let a page speak after the person has touched it, so speak() reports whether it could.
import { sound } from './sound'

let chosen = null
function pickVoice() {
  if (chosen || !('speechSynthesis' in window)) return chosen
  const vs = speechSynthesis.getVoices()
  if (!vs.length) return null
  // Friendly, clear English voices first; Indian English where the device has one.
  const prefs = [/en-IN.*(Neerja|Heera|female)/i, /Google UK English Female/i, /Samantha/i, /Microsoft (Aria|Jenny|Sonia|Libby)/i,
    /en-IN/i, /Google US English/i, /en-GB/i, /en-US/i, /^en/i]
  for (const re of prefs) { const v = vs.find(x => re.test(x.name + ' ' + x.lang)); if (v) { chosen = v; break } }
  return chosen
}
if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = () => { chosen = null; pickVoice() }

// Recorded greetings (a natural human-sounding voice, shipped with the app) play first.
// The browser's own speech engine is only the fallback for lines with no recording.
let clip = null
export function playClip(src, { onStart, onProgress, onEnd } = {}) {
  if (!sound.on || !src) return false
  try {
    hush()
    const a = new Audio(src); clip = a; a.volume = 0.95
    a.onplay = () => onStart?.()
    a.ontimeupdate = () => a.duration && onProgress?.(a.currentTime / a.duration)
    a.onended = a.onerror = () => onEnd?.()
    const p = a.play()
    if (p && p.catch) p.catch(() => onEnd?.())
    return true
  } catch { return false }
}

export const canTalk = () => true
export const mayTalkNow = () => sound.on && (navigator.userActivation ? navigator.userActivation.hasBeenActive : false)

// Eddie's own voice from the server (the same male voice as the greetings), a sentence at a time so he
// starts talking quickly. Falls back to the phone's voice if the server has no voice set up.
let server = null            // null: not checked yet, true / false after the first try
let run = 0                  // bumps on every new speech or hush, so an old queue stops
let current = null
// Short pieces start sooner: sentences, and long sentences split at a comma.
const sentences = t => (t.match(/[^.!?]+[.!?]*["')\]]*\s*/g) || [t]).map(x => x.trim()).filter(Boolean)
  .flatMap(x => x.split(' ').length > 14 ? x.split(/(?<=[,;:])\s+/) : [x]).filter(Boolean)
export const serverVoice = () => server === true
async function fetchSay(text) {
  const tok = localStorage.getItem('ev_token')
  const r = await fetch('/api/voice/say', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tok }, body: JSON.stringify({ text }) })
  if (r.status === 503) { server = false; throw new Error('no server voice') }
  if (!r.ok) throw new Error('voice ' + r.status)
  return URL.createObjectURL(await r.blob())
}
function serverSpeak(text, { onStart, onWord, onEnd }, fallback) {
  const me = ++run, parts = sentences(text), urls = parts.map(() => null)
  let offset = 0, started = false
  const get = i => (urls[i] ||= fetchSay(parts[i]))
  const playAt = async i => {
    if (me !== run) return
    if (i >= parts.length) { current = null; onEnd?.(); return }
    let url
    try { url = await get(i) } catch { if (me === run) { if (!started) fallback(); else onEnd?.() } return }
    if (me !== run) return
    if (i + 1 < parts.length) get(i + 1).catch(() => {})       // fetch the next sentence while this one plays
    const a = new Audio(url); current = a; a.volume = 0.95
    const start = offset, len = parts[i].length
    a.onplay = () => { if (!started) { started = true; server = true; onStart?.() } onWord?.(start) }
    a.ontimeupdate = () => a.duration && onWord?.(start + Math.floor(len * Math.min(1, a.currentTime / a.duration)))
    a.onended = a.onerror = () => { URL.revokeObjectURL(url); offset = start + len + 1; playAt(i + 1) }
    a.play().catch(() => { if (!started) fallback(); else onEnd?.() })
  }
  playAt(0)
  return true
}

// onWord(charIndex) lets the bubble type the words as they are spoken.
export function speak(text, cbs = {}) {
  if (!canTalk() || !sound.on) return false
  if (server !== false && localStorage.getItem('ev_token')) return serverSpeak(text, cbs, () => browserSpeak(text, cbs))
  return browserSpeak(text, cbs)
}
function browserSpeak(text, { onStart, onWord, onEnd } = {}) {
  try {
    speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text)
    const v = pickVoice(); if (v) { u.voice = v; u.lang = v.lang }
    u.rate = 0.98; u.pitch = 1.25; u.volume = 0.9
    u.onstart = () => onStart?.()
    u.onboundary = e => onWord?.(e.charIndex)
    u.onend = u.onerror = () => onEnd?.()
    speechSynthesis.speak(u)
    return true
  } catch { return false }
}
export function hush() {
  run++
  try { if (current) { current.pause(); current = null } } catch { /* already gone */ }
  try { speechSynthesis.cancel() } catch { /* nothing to stop */ }
  try { if (clip) { clip.pause(); clip = null } } catch { /* already gone */ }
}

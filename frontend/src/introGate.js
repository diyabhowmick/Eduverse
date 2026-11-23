export const HERO_DUR = 12          // the on-page loop length
// The full intro plays on the first visit only; after that the login page opens straight away.
// It is also skipped on slow connections or with Data Saver on, so the form is usable at once.
export const slowNet = () => { const c = navigator.connection; return !!c && (c.saveData || /(^|-)2g|3g/.test(c.effectiveType || '')) }
export function shouldPlayIntro() {
  if (typeof window === 'undefined') return false
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || slowNet()) return false
  if (new URLSearchParams(location.search).has('intro')) return true
  try { return !localStorage.getItem('ev_intro_seen') } catch { return true }
}
export function markIntroSeen() { try { localStorage.setItem('ev_intro_seen', '1') } catch { /* private mode */ } }

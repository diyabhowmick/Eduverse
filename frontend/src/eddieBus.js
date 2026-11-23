// Tiny event bus so the login form can talk to Eddie without prop drilling.
const T = new EventTarget()
export const eddie = {
  emit: (type, detail = {}) => T.dispatchEvent(new CustomEvent(type, { detail })),
  on: (type, fn) => { const h = e => fn(e.detail); T.addEventListener(type, h); return () => T.removeEventListener(type, h) },
}

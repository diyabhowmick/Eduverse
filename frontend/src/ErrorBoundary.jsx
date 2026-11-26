import { Component } from 'react'

/* One screen failing must never take the whole app down.

   Without this, any error while drawing a screen made React remove everything,
   sidebar included, and the person saw a white page until they reloaded.

   Two kinds of failure are handled:
   - A screen file that is gone. Every deploy renames the screen files, so a tab
     opened before the deploy asks for a file that no longer exists. The cure is
     to load the new version, so the page reloads itself, once.
   - Anything else. The screen shows what happened with Reload and Go back, the
     sidebar stays, and the error goes to the server log as [EV CLIENT]. */

const CHUNK = /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|ChunkLoadError|Loading chunk .* failed/i

export function isChunkError(e) { return CHUNK.test(String(e?.message || e || '')) }

export function reloadOnce() {
  // Reload at most once a minute, so a real outage cannot loop the page.
  try {
    const last = +sessionStorage.getItem('ev_reloaded_at') || 0
    if (Date.now() - last < 60000) return false
    sessionStorage.setItem('ev_reloaded_at', String(Date.now()))
  } catch { /* private mode: still reload */ }
  location.reload()
  return true
}

export function report(error, where) {
  try {
    const body = JSON.stringify({ message: String(error?.message || error).slice(0, 500), stack: String(error?.stack || '').slice(0, 1500), where: where || location.pathname })
    navigator.sendBeacon ? navigator.sendBeacon('/api/client-error', new Blob([body], { type: 'application/json' }))
      : fetch('/api/client-error', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body }).catch(() => {})
  } catch { /* reporting must never throw */ }
}

export default class ErrorBoundary extends Component {
  constructor(p) { super(p); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  componentDidCatch(error, info) {
    if (isChunkError(error) && reloadOnce()) return
    report(error, (this.props.where || location.pathname) + (info?.componentStack ? ' | ' + info.componentStack.split('\n').slice(0, 4).join(' ') : ''))
  }
  render() {
    const { error } = this.state
    if (!error) return this.props.children
    const chunk = isChunkError(error)
    return (
      <div className="card" style={{ margin: 24, maxWidth: 640 }} role="alert">
        <div className="card-h"><h3>{chunk ? 'A new version of EduVerse is ready' : 'This screen hit a problem'}</h3></div>
        <p style={{ margin: '0 0 12px' }}>
          {chunk ? 'The app was updated while this tab was open. Reload to continue. Nothing you saved is lost.'
            : 'The rest of the app still works. Reload this screen, or go back and try again. The problem has been sent to the server log.'}
        </p>
        {!chunk && <div className="muted" style={{ fontSize: 12, marginBottom: 12, wordBreak: 'break-word' }}>{String(error.message || error).slice(0, 200)}</div>}
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn primary" onClick={() => location.reload()}>Reload</button>
          {!chunk && <button className="btn" onClick={() => { this.setState({ error: null }); history.back() }}>Go back</button>}
        </div>
      </div>
    )
  }
}

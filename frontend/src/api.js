const KEY = 'ev_token'
export const auth = {
  get token() { return localStorage.getItem(KEY) },
  set(t, user) { try { sessionStorage.setItem('ev_ck', '1') } catch { /* */ } localStorage.setItem(KEY, t); localStorage.setItem('ev_user', JSON.stringify(user)); localStorage.removeItem('ev_nick') },
  user() { try { return JSON.parse(localStorage.getItem('ev_user')) } catch { return null } },
  clear() { localStorage.removeItem(KEY); localStorage.removeItem('ev_user'); localStorage.removeItem('ev_nick'); try { sessionStorage.removeItem('ev_ck') } catch { /* */ }
    fetch('/api/auth/logout', { method: 'POST' }).catch(() => {}) },
}

// Book images need the session cookie. A session from before the cookie existed gets one now, once per tab.
try {
  if (auth.token && !sessionStorage.getItem('ev_ck')) {
    fetch('/api/auth/refresh', { method: 'POST', headers: { Authorization: 'Bearer ' + auth.token } })
      .then(r => r.ok ? r.json() : null).then(d => { if (d?.token) { localStorage.setItem(KEY, d.token); sessionStorage.setItem('ev_ck', '1') } }).catch(() => {})
  }
} catch { /* private mode */ }

export const LOGIN = { super_admin: '/login/superadmin', admin: '/login/admin', reviewer: '/login/reviewer', student: '/login/student', teacher: '/login/teacher' }

// Anyone still working gets a fresh token before the old one runs out.
let lastRenew = 0
function renew() {
  const now = Date.now()
  if (!auth.token || now - lastRenew < 600000) return
  try {
    const exp = JSON.parse(atob(auth.token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).exp * 1000
    if (exp - now > 6 * 3600000) return
  } catch { return }
  lastRenew = now
  fetch('/api/auth/refresh', { method: 'POST', headers: { Authorization: 'Bearer ' + auth.token } })
    .then(r => r.ok ? r.json() : null).then(d => { if (d?.token) localStorage.setItem(KEY, d.token) }).catch(() => {})
}

export async function api(path, { method = 'GET', body, form } = {}) {
  const headers = {}
  if (auth.token) headers.Authorization = 'Bearer ' + auth.token
  let payload
  if (form) payload = form
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
  let r
  try {
    r = await fetch(path, { method, headers, body: payload })
  } catch (e) {
    // fetch only ever says "Failed to fetch". Say what that means here: the
    // request never finished, which on a big upload is almost always the
    // connection, and on a redeploy is the server coming back up.
    throw new Error('The connection to the server was lost before the request finished. Check the internet connection and try again.')
  }
  if (r.status === 401 && !path.includes('/auth/login')) {
    // The page stays as it is, with its form and chosen files, while the person signs in again on top of it.
    if (auth.user()) { window.dispatchEvent(new Event('ev:session-expired')); throw new Error('Your session expired. Sign in again, then try once more. Nothing on this page was lost.') }
    auth.clear(); location.href = LOGIN.super_admin
  }
  const data = await r.json().catch(() => ({}))
  if (!r.ok) {
    const d = data.detail
    if (Array.isArray(d)) throw new Error(d.map(x => `${x.loc?.slice(-1)[0]}: ${x.msg}`).join(', '))
    if (d) throw new Error(d + (data.where ? ` (${data.where})` : ''))
    // No readable body: the reply did not come from the application at all.
    // 502 and 504 come from the platform's own proxy, which is what a dropped
    // upload looks like from here.
    throw new Error(r.status === 502 || r.status === 504
      ? `The server did not answer (${r.status}). On a large upload this means the request was cut off before it arrived. Try again, or upload a smaller file.`
      : r.status === 413
        ? 'The file is too large for the server to accept in one request.'
        : `The server returned ${r.status}${r.statusText ? ' ' + r.statusText : ''} with no explanation. The reason will be in the server log.`)
  }
  renew()
  return data
}

/* Send a big file in pieces.

   A Tamil Nadu textbook PDF is 75-85 MB, and the platform's edge closes any
   request whose body has not finished uploading within five minutes. That
   needs a steady 2.4 Mbps held for the whole five minutes, which an ordinary
   broadband line does not manage, so the request was being cut off before it
   reached the server: the upload "just failed", with nothing in the server log
   because the server never got it.

   Each piece is its own short request, well inside every limit, and a piece
   that fails is retried on its own rather than starting the book again. */
export async function sendInPieces(file, onProgress) {
  const begin = new FormData()
  begin.append('filename', file.name)
  begin.append('size', file.size)
  const { upload_id, part_size } = await api('/api/jobs/upload/start', { method: 'POST', form: begin })
  const n = Math.max(1, Math.ceil(file.size / part_size))
  for (let i = 0; i < n; i++) {
    const f = new FormData()
    f.append('upload_id', upload_id)
    f.append('index', i)
    f.append('chunk', file.slice(i * part_size, (i + 1) * part_size), 'part')
    let failed = null
    for (let attempt = 0; attempt < 3; attempt++) {
      try { await api('/api/jobs/upload/part', { method: 'POST', form: f }); failed = null; break }
      catch (e) {
        failed = e
        if (/no longer open/i.test(e.message)) break   // retrying cannot help
        await new Promise(r => setTimeout(r, 1500 * (attempt + 1)))
      }
    }
    if (failed) throw new Error(`The upload stopped at ${Math.round(i / n * 100)}% — piece ${i + 1} of ${n} did not go through after three tries. ${failed.message}`)
    onProgress?.(Math.round((i + 1) / n * 100))
  }
  return upload_id
}

export const inr = n => '₹' + Math.round(n || 0).toLocaleString('en-IN')
export const num = n => (n || 0).toLocaleString('en-IN')
export const compact = n => n >= 1e7 ? (n / 1e7).toFixed(2) + ' Cr' : n >= 1e5 ? (n / 1e5).toFixed(1) + ' L' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'k' : String(Math.round(n || 0))
export const when = d => d ? new Date(d + (String(d).endsWith('Z') ? '' : 'Z')).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''
export const day = d => d ? new Date(d + (String(d).endsWith('Z') ? '' : 'Z')).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : ''

const ACTIONS = {
  login: 'Signed in', 'admin.create': 'Added admin', 'admin.update': 'Updated admin', 'admin.delete': 'Removed admin', 'admin.reset_password': 'Reset admin password',
  'school.create': 'Added school', 'school.update': 'Updated school', 'school.delete': 'Deleted school',
  'plan.create': 'Created plan', 'plan.update': 'Changed plan', 'plan.delete': 'Deleted plan',
  'discount.create': 'Created discount', 'discount.update': 'Changed discount', 'discount.delete': 'Deleted discount',
  'book.create': 'Added upcoming book', 'book.update': 'Edited book', 'book.go_live': 'Put book live', 'book.retire': 'Retired book', 'book.restore': 'Restored book',
  'job.create': 'Uploaded book for M1', 'job.retry': 'Retried job', 'job.cancel': 'Cancelled job',
  'request.create': 'Sent request', 'request.approve': 'Approved request', 'request.decline': 'Declined request',
  'class.create': 'Added class', 'class.update': 'Edited class', 'class.delete': 'Deleted class', 'class.books': 'Assigned books',
  'student.create': 'Added student', 'student.update': 'Updated student', 'student.delete': 'Removed student', 'student.reset_password': 'Reset student password',
  'student.bulk_upload': 'Uploaded students', 'student.bulk_activate': 'Activated students', 'student.bulk_suspend': 'Suspended students', 'student.bulk_move': 'Moved students',
  'school.profile': 'Updated school profile', 'school.rules': 'Changed learning rules',
  'review.edit': 'Edited text in review', 'review.remove_block': 'Removed a block in review', 'review.add_keyword': 'Added an important word', 'review.remove_keyword': 'Removed an important word',
  'review.page_approve': 'Approved a page', 'review.page_reject': 'Rejected a page', 'review.page_reopen': 'Reopened a page', 'review.approve_remaining': 'Approved remaining pages',
  'review.publish': 'Published a book', 'review.send_back': 'Sent a book back',
  'reviewer.create': 'Added reviewer', 'reviewer.update': 'Updated reviewer', 'reviewer.reset_password': 'Reset reviewer password', 'book.assign_reviewer': 'Assigned a reviewer',
  'student.purchase': 'Got a book from the store',
  'explanation.pin': 'Pinned an explanation', 'explanation.retire': 'Retired an explanation', 'explanation.restore': 'Restored an explanation',
  'explanation.edit': 'Edited an explanation', 'explanation.prepare': 'Wrote explanations ahead',
  'paper.create': 'Added a question paper', 'paper.publish': 'Published a question paper', 'paper.read_ai': 'Read a paper with AI', 'paper.answer_ai': 'Generated answers with AI',
  'settings.ai': 'Changed AI settings', 'settings.branding': 'Changed branding', 'settings.features': 'Changed features', 'settings.permissions': 'Changed permissions',
}
export const actionLabel = a => ACTIONS[a] || a

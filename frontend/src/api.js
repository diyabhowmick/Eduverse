const KEY = 'ev_token'
export const auth = {
  get token() { return localStorage.getItem(KEY) },
  set(t, user) { localStorage.setItem(KEY, t); localStorage.setItem('ev_user', JSON.stringify(user)) },
  user() { try { return JSON.parse(localStorage.getItem('ev_user')) } catch { return null } },
  clear() { localStorage.removeItem(KEY); localStorage.removeItem('ev_user') },
}

export async function api(path, { method = 'GET', body, form } = {}) {
  const headers = {}
  if (auth.token) headers.Authorization = 'Bearer ' + auth.token
  let payload
  if (form) payload = form
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
  const r = await fetch(path, { method, headers, body: payload })
  if (r.status === 401 && !path.includes('/auth/login')) { const r = auth.user()?.role; auth.clear(); location.href = { admin: '/login/admin', reviewer: '/login/reviewer', student: '/login/student' }[r] || '/login/superadmin' }
  const data = await r.json().catch(() => ({}))
  if (!r.ok) {
    const d = data.detail
    throw new Error(Array.isArray(d) ? d.map(x => `${x.loc?.slice(-1)[0]}: ${x.msg}`).join(', ') : d || 'Request failed')
  }
  return data
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
  'settings.ai': 'Changed AI settings', 'settings.branding': 'Changed branding', 'settings.features': 'Changed features', 'settings.permissions': 'Changed permissions',
}
export const actionLabel = a => ACTIONS[a] || a

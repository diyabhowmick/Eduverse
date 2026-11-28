// The first screen of each portal. App.jsx lazy-loads these; Login starts the download the moment
// sign-in succeeds, so the page is ready (or nearly) by the time the launch animation hands over.
export const HOME_CHUNKS = {
  '/sa': () => import('./pages/Dashboard'),
  '/admin': () => import('./pages/admin/Overview'),
  '/review': () => import('./pages/reviewer/Queue'),
  '/student': () => import('./pages/student/Home'),
  '/teacher': () => import('./pages/teacher/Overview'),
}

// Never rejects: a failed prefetch must not hold the launch veil; the route's own lazy() retries and reports it.
export const prefetchHome = home => (HOME_CHUNKS[home]?.() || Promise.resolve()).catch(() => {})

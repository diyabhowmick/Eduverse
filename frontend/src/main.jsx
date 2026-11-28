import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './styles.css'
import './polish.css'
import './ux.css'
import './motion.css'
import './wide.css'
import ErrorBoundary, { isChunkError, reloadOnce, report } from './ErrorBoundary'

// A deploy renames the screen files. Vite raises this when a tab opened before the deploy asks for one that is gone:
// load the new version instead of showing a blank page.
window.addEventListener('vite:preloadError', e => { if (reloadOnce()) e.preventDefault() })
window.addEventListener('unhandledrejection', e => { if (isChunkError(e.reason)) reloadOnce(); else report(e.reason, 'promise ' + location.pathname) })
createRoot(document.getElementById('root')).render(<BrowserRouter><ErrorBoundary where="app"><App /></ErrorBoundary></BrowserRouter>)

import { lazy, Suspense, useEffect, useState } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { auth, api, LOGIN } from './api'
import { ToastHost, Modal, Field, ConfirmHost } from './ui'
import AddContent from './pages/AddContent'
const AiUsage = lazy(() => import('./pages/AiUsage'))
import Layout from './Layout'
import Login from './pages/Login'
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Admins = lazy(() => import('./pages/Admins'))
const Schools = lazy(() => import('./pages/Schools'))
const Pricing = lazy(() => import('./pages/Pricing'))
const Catalogue = lazy(() => import('./pages/Catalogue'))
const Processing = lazy(() => import('./pages/Processing'))
const AISettings = lazy(() => import('./pages/AISettings'))
const M1Settings = lazy(() => import('./pages/M1Settings'))
const M2Settings = lazy(() => import('./pages/M2Settings'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Platform = lazy(() => import('./pages/Platform'))
const Audit = lazy(() => import('./pages/Audit'))
const Requests = lazy(() => import('./pages/Requests'))
const Reviewers = lazy(() => import('./pages/Reviewers'))
const AOverview = lazy(() => import('./pages/admin/Overview'))
const AStudents = lazy(() => import('./pages/admin/Students'))
const AClasses = lazy(() => import('./pages/admin/Classes'))
const ABooks = lazy(() => import('./pages/admin/Books'))
const AAnalytics = lazy(() => import('./pages/admin/Analytics'))
const ARules = lazy(() => import('./pages/admin/Rules'))
const ARequests = lazy(() => import('./pages/admin/Requests'))
const AProfile = lazy(() => import('./pages/admin/Profile'))
const RQueue = lazy(() => import('./pages/reviewer/Queue'))
const RHistory = lazy(() => import('./pages/reviewer/History'))
const RWorkspace = lazy(() => import('./pages/reviewer/Workspace'))
import SHome from './pages/student/Home'
const TOverview = lazy(() => import('./pages/teacher/Overview'))
const TClasses = lazy(() => import('./pages/teacher/Classes'))
const TClass = lazy(() => import('./pages/teacher/ClassDetail'))
const TAnalytics = lazy(() => import('./pages/teacher/Analytics'))
import SBooks from './pages/student/MyBooks'
import SStore from './pages/student/Store'
import SReader from './pages/student/Reader'
import SExam from './pages/student/ExamPack'
import SProgress from './pages/student/Progress'
import Signup from './pages/Signup'
const ExamPapers = lazy(() => import('./pages/ExamPapers'))
const RPapers = lazy(() => import('./pages/reviewer/Papers'))

const SA_NAV = [
  ['', 'home', 'Overview'], ['add', 'upload', 'Add content'],
  ['__group', 'Content'], ['catalogue', 'book', 'Catalogue'], ['processing', 'job', 'Processing'], ['extraction', 'scan', 'Book reading (M1)'], ['figures', 'image', 'Figure redraw (M2)'],
  ['__group', 'People'], ['schools', 'school', 'Organisations'], ['requests', 'inbox', 'Organisation requests'], ['admins', 'admins', 'Admins'], ['reviewers', 'shield', 'Reviewers'],
  ['__group', 'Business'], ['pricing', 'price', 'Pricing'], ['analytics', 'chart', 'Analytics'], ['usage', 'target', 'AI usage'],
  ['__group', 'Settings'], ['ai', 'ai', 'AI settings'], ['platform', 'settings', 'Platform settings'], ['audit', 'audit', 'Audit log'],
]
const AD_NAV = [
  ['', 'home', 'Overview'], ['students', 'admins', 'Students'], ['classes', 'school', 'Classes'], ['books', 'book', 'Books'],
  ['analytics', 'chart', 'Analytics'], ['rules', 'shield', 'Learning rules'], ['requests', 'inbox', 'Requests'], ['profile', 'settings', 'Profile'],
]

function SuperShell() {
  const [c, setC] = useState({}); const loc = useLocation()
  useEffect(() => { api('/api/dashboard').then(d => setC({ catalogue: d.needs_attention.sent_back, processing: d.needs_attention.failed_jobs, requests: d.needs_attention.open_requests })).catch(() => {}) }, [loc.pathname])
  return (
    <Layout nav={SA_NAV} base="/sa" role="Super Admin" loginPath="/login/superadmin" counts={c}>
      <Routes>
        <Route index element={<Dashboard />} /><Route path="add" element={<AddContent />} /><Route path="admins" element={<Admins />} /><Route path="reviewers" element={<Reviewers />} /><Route path="schools" element={<Schools />} />
        <Route path="requests" element={<Requests />} /><Route path="pricing" element={<Pricing />} /><Route path="catalogue" element={<Catalogue />} /><Route path="exams/:id" element={<ExamPapers />} />
        <Route path="processing" element={<Processing />} /><Route path="ai" element={<AISettings />} /><Route path="usage" element={<AiUsage />} /><Route path="extraction" element={<M1Settings />} /><Route path="figures" element={<M2Settings />} /><Route path="analytics" element={<Analytics />} />
        <Route path="platform" element={<Platform />} /><Route path="audit" element={<Audit />} />
      </Routes>
    </Layout>
  )
}

function AdminShell() {
  const [o, setO] = useState(null); const loc = useLocation()
  useEffect(() => { api('/api/school/overview').then(setO).catch(() => {}) }, [loc.pathname])
  const badge = o?.school.logo ? <img className="school-badge" src={o.school.logo} alt="" /> : null
  const counts = o ? { students: o.attention.unassigned_students, classes: o.attention.classes_without_books } : {}
  return (
    <Layout nav={AD_NAV} base="/admin" role={o?.school.name || 'Organisation Admin'} loginPath="/login/admin" counts={counts} badge={badge}>
      <Routes>
        <Route index element={<AOverview />} /><Route path="students" element={<AStudents />} /><Route path="classes" element={<AClasses />} />
        <Route path="books" element={<ABooks />} /><Route path="analytics" element={<AAnalytics />} /><Route path="rules" element={<ARules />} />
        <Route path="requests" element={<ARequests />} /><Route path="profile" element={<AProfile />} />
      </Routes>
    </Layout>
  )
}

const RV_NAV = [['', 'inbox', 'Review queue'], ['papers', 'job', 'Question papers'], ['history', 'audit', 'Reviewed books']]

function ReviewerShell() {
  const [n, setN] = useState(0); const loc = useLocation()
  useEffect(() => { api('/api/review/queue').then(q => setN(q.filter(b => b.status === 'in_review' && b.has_content).length)).catch(() => {}) }, [loc.pathname])
  return (
    <Layout nav={RV_NAV} base="/review" role="Reviewer" loginPath="/login/reviewer" counts={{ '': n }}>
      <Routes><Route index element={<RQueue />} /><Route path="papers" element={<RPapers />} /><Route path="history" element={<RHistory />} /><Route path="books/:id" element={<RWorkspace />} /></Routes>
    </Layout>
  )
}

const TE_NAV = [['', 'home', 'Home'], ['classes', 'admins', 'My classes'], ['analytics', 'chart', 'Analytics']]

function TeacherShell() {
  const u = auth.user()
  return (
    <Layout nav={TE_NAV} base="/teacher" role={u?.school || 'Teacher'} loginPath="/login/teacher">
      <Routes><Route index element={<TOverview />} /><Route path="classes" element={<TClasses />} /><Route path="classes/:cid" element={<TClass />} /><Route path="analytics" element={<TAnalytics />} /></Routes>
    </Layout>
  )
}

const ST_NAV = [['', 'home', 'Home'], ['books', 'book', 'My books'], ['progress', 'chart', 'Progress'], ['store', 'price', 'Store']]

function StudentShell() {
  const u = auth.user(); const loc = useLocation()
  return (
    <Layout nav={ST_NAV} base="/student" role={u?.school || 'Learner'} loginPath="/login/student" collapse={loc.pathname.includes('/read/')}>
      <Routes><Route index element={<SHome />} /><Route path="books" element={<SBooks />} /><Route path="store" element={<SStore />} /><Route path="progress" element={<SProgress />} /><Route path="read/:id" element={<SReader />} /><Route path="exam/:id" element={<SExam />} /></Routes>
    </Layout>
  )
}

// Sign in again over the page, so a half filled form and its chosen files stay where they are.
function SessionGate() {
  const [open, setOpen] = useState(false); const [pw, setPw] = useState(''); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  useEffect(() => { const f = () => setOpen(true); addEventListener('ev:session-expired', f); return () => removeEventListener('ev:session-expired', f) }, [])
  if (!open) return null
  const u = auth.user()
  const out = () => { auth.clear(); location.href = LOGIN[u?.role] || LOGIN.super_admin }
  async function go(e) {
    e.preventDefault(); setBusy(true); setErr('')
    try { const r = await api('/api/auth/login', { method: 'POST', body: { email: u.email, password: pw, portal: u.role } }); auth.set(r.token, r.user); setPw(''); setOpen(false) }
    catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  return <Modal title="Sign in to continue" onClose={() => setOpen(false)} footer={<><button className="btn" onClick={out}>Sign out</button><button className="btn primary" form="session-gate" disabled={busy}>{busy ? 'Signing in' : 'Sign in'}</button></>}>
    <form id="session-gate" onSubmit={go}>
      <p style={{ marginTop: 0 }}>Your session ended. Everything on this page is still here.</p>
      {err && <div className="err" role="alert">{err}</div>}
      <Field label={u?.email || 'Password'}><input className="input" type="password" autoFocus autoComplete="current-password" placeholder="Password" value={pw} onChange={e => setPw(e.target.value)} required /></Field>
    </form></Modal>
}

const Guard = ({ role, to, children }) => auth.token && auth.user()?.role === role ? children : <Navigate to={to} replace />

export default function App() {
  return (
    <ToastHost>
      <SessionGate />
      <ConfirmHost />
      <Suspense fallback={<div className="empty" style={{ padding: 40 }}>Loading</div>}>
      <Routes>
        <Route path="/login/superadmin" element={<Login portal="super_admin" />} />
        <Route path="/login/admin" element={<Login portal="admin" />} />
        <Route path="/sa/*" element={<Guard role="super_admin" to="/login/superadmin"><SuperShell /></Guard>} />
        <Route path="/admin/*" element={<Guard role="admin" to="/login/admin"><AdminShell /></Guard>} />
        <Route path="/login/reviewer" element={<Login portal="reviewer" />} />
        <Route path="/login/student" element={<Login portal="student" />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/login/teacher" element={<Login portal="teacher" />} />
        <Route path="/student/*" element={<Guard role="student" to="/login/student"><StudentShell /></Guard>} />
        <Route path="/teacher/*" element={<Guard role="teacher" to="/login/teacher"><TeacherShell /></Guard>} />
        <Route path="/review/*" element={<Guard role="reviewer" to="/login/reviewer"><ReviewerShell /></Guard>} />
        <Route path="*" element={<Navigate to={{ admin: '/admin', reviewer: '/review', student: '/student', teacher: '/teacher' }[auth.user()?.role] || '/sa'} replace />} />
      </Routes>
      </Suspense>
    </ToastHost>
  )
}

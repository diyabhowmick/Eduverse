import { useEffect, useState } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { auth, api } from './api'
import { ToastHost } from './ui'
import Layout from './Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Admins from './pages/Admins'
import Schools from './pages/Schools'
import Pricing from './pages/Pricing'
import Catalogue from './pages/Catalogue'
import Processing from './pages/Processing'
import AISettings from './pages/AISettings'
import M1Settings from './pages/M1Settings'
import M2Settings from './pages/M2Settings'
import Analytics from './pages/Analytics'
import Platform from './pages/Platform'
import Audit from './pages/Audit'
import Requests from './pages/Requests'
import Reviewers from './pages/Reviewers'
import AOverview from './pages/admin/Overview'
import AStudents from './pages/admin/Students'
import AClasses from './pages/admin/Classes'
import ABooks from './pages/admin/Books'
import AAnalytics from './pages/admin/Analytics'
import ARules from './pages/admin/Rules'
import ARequests from './pages/admin/Requests'
import AProfile from './pages/admin/Profile'
import RQueue from './pages/reviewer/Queue'
import RHistory from './pages/reviewer/History'
import RWorkspace from './pages/reviewer/Workspace'
import SHome from './pages/student/Home'
import TOverview from './pages/teacher/Overview'
import TClasses from './pages/teacher/Classes'
import TClass from './pages/teacher/ClassDetail'
import TAnalytics from './pages/teacher/Analytics'
import SBooks from './pages/student/MyBooks'
import SStore from './pages/student/Store'
import SReader from './pages/student/Reader'
import Money from './pages/Money'
import Demand from './pages/Demand'
import Needs from './pages/Needs'
import PNeeds from './pages/pa/Needs'
import PHealth from './pages/pa/Health'
import PKeys from './pages/pa/Keys'
import PCost from './pages/pa/CostSettings'

/* Two admin roles, split down the middle.

   Super Admin owns the money: who the schools are, what they pay, what renews.
   Platform Admin owns the factory: books in, books out, and what that costs.
   The factory never sees a school's price — that is the whole point of the
   split, and it is enforced in the backend, not here.

   Super Admin keeps the factory screens too, because the backend already lets
   them do anything a Platform Admin can and being locked out of your own
   pipeline on a Sunday is worse than a longer menu. */
const SA_NAV = [
  ['', 'home', 'What needs you today'], ['schools', 'school', 'Schools'], ['requests', 'inbox', 'School requests'],
  ['admins', 'admins', 'Admins'], ['pricing', 'price', 'Pricing'], ['money', 'price', 'Money and renewals'],
  ['analytics', 'chart', 'Analytics'], ['platform', 'settings', 'Platform settings'], ['audit', 'audit', 'Audit log'],
  // the factory, same screens Platform Admin runs
  ['demand', 'chart', 'Catalogue and cost'], ['catalogue', 'book', 'Book catalogue'], ['processing', 'job', 'Processing'],
  ['reviewers', 'shield', 'Reviewers'], ['health', 'pulse', 'Pipeline health'], ['keys', 'key', 'Keys and spending'],
  ['cost', 'price', 'Cost settings'], ['extraction', 'scan', 'Book extraction (M1)'], ['figures', 'image', 'Figure redraw (M2)'], ['ai', 'ai', 'AI settings'],
]

const PA_NAV = [
  ['', 'inbox', 'What needs doing'], ['demand', 'chart', 'Catalogue and cost'], ['catalogue', 'book', 'Book catalogue'],
  ['processing', 'job', 'Processing'], ['reviewers', 'shield', 'Reviewers'], ['health', 'pulse', 'Pipeline health'],
  ['keys', 'key', 'Keys and spending'], ['cost', 'price', 'Cost settings'],
  ['extraction', 'scan', 'Book extraction (M1)'], ['figures', 'image', 'Figure redraw (M2)'], ['ai', 'ai', 'AI settings'],
]
const AD_NAV = [
  ['', 'home', 'Overview'], ['students', 'admins', 'Students'], ['classes', 'school', 'Classes'], ['books', 'book', 'Books'],
  ['analytics', 'chart', 'Analytics'], ['rules', 'shield', 'Learning rules'], ['requests', 'inbox', 'Requests'], ['profile', 'settings', 'School profile'],
]

/* The factory screens, shared by both admin roles. Mounted twice so the links
   inside them stay inside whichever side the person signed in on. */
const factoryRoutes = (
  <>
    <Route path="demand" element={<Demand />} /><Route path="catalogue" element={<Catalogue />} />
    <Route path="processing" element={<Processing />} /><Route path="reviewers" element={<Reviewers />} />
    <Route path="health" element={<PHealth />} /><Route path="keys" element={<PKeys />} /><Route path="cost" element={<PCost />} />
    <Route path="extraction" element={<M1Settings />} /><Route path="figures" element={<M2Settings />} /><Route path="ai" element={<AISettings />} />
  </>
)

function SuperShell() {
  const [c, setC] = useState({}); const loc = useLocation()
  useEffect(() => { api('/api/dashboard').then(d => setC({ catalogue: d.needs_attention.sent_back, processing: d.needs_attention.failed_jobs, requests: d.needs_attention.open_requests })).catch(() => {}) }, [loc.pathname])
  return (
    <Layout nav={SA_NAV} base="/sa" role="Super Admin" loginPath="/login/superadmin" counts={c}>
      <Routes>
        <Route index element={<Needs />} /><Route path="numbers" element={<Dashboard />} />
        <Route path="admins" element={<Admins />} /><Route path="schools" element={<Schools />} />
        <Route path="requests" element={<Requests />} /><Route path="pricing" element={<Pricing />} /><Route path="money" element={<Money />} />
        <Route path="analytics" element={<Analytics />} /><Route path="platform" element={<Platform />} /><Route path="audit" element={<Audit />} />
        {factoryRoutes}
      </Routes>
    </Layout>
  )
}

function PlatformShell() {
  const [c, setC] = useState({}); const loc = useLocation()
  useEffect(() => {
    api('/api/factory/health?days=30')
      .then(h => setC({ processing: h.jobs.running + h.jobs.queued, health: h.failures.length, reviewers: h.stuck_in_review.length }))
      .catch(() => {})
  }, [loc.pathname])
  return (
    <Layout nav={PA_NAV} base="/pa" role="Platform Admin" loginPath="/login/platform" counts={c}>
      <Routes>
        <Route index element={<PNeeds />} />
        {factoryRoutes}
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
    <Layout nav={AD_NAV} base="/admin" role={o?.school.name || 'School Admin'} loginPath="/login/admin" counts={counts} badge={badge}>
      <Routes>
        <Route index element={<AOverview />} /><Route path="students" element={<AStudents />} /><Route path="classes" element={<AClasses />} />
        <Route path="books" element={<ABooks />} /><Route path="analytics" element={<AAnalytics />} /><Route path="rules" element={<ARules />} />
        <Route path="requests" element={<ARequests />} /><Route path="profile" element={<AProfile />} />
      </Routes>
    </Layout>
  )
}

const RV_NAV = [['', 'inbox', 'Review queue'], ['history', 'audit', 'Reviewed books']]

function ReviewerShell() {
  const [n, setN] = useState(0); const loc = useLocation()
  useEffect(() => { api('/api/review/queue').then(q => setN(q.filter(b => b.status === 'in_review' && b.has_content).length)).catch(() => {}) }, [loc.pathname])
  return (
    <Layout nav={RV_NAV} base="/review" role="Reviewer" loginPath="/login/reviewer" counts={{ '': n }}>
      <Routes><Route index element={<RQueue />} /><Route path="history" element={<RHistory />} /><Route path="books/:id" element={<RWorkspace />} /></Routes>
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

const ST_NAV = [['', 'home', 'Home'], ['books', 'book', 'My books'], ['store', 'price', 'Store']]

function StudentShell() {
  const u = auth.user(); const loc = useLocation()
  return (
    <Layout nav={ST_NAV} base="/student" role={u?.school || 'Student'} loginPath="/login/student" collapse={loc.pathname.includes('/read/')}>
      <Routes><Route index element={<SHome />} /><Route path="books" element={<SBooks />} /><Route path="store" element={<SStore />} /><Route path="read/:id" element={<SReader />} /></Routes>
    </Layout>
  )
}

const Guard = ({ role, to, children }) => auth.token && auth.user()?.role === role ? children : <Navigate to={to} replace />

export default function App() {
  return (
    <ToastHost>
      <Routes>
        <Route path="/login/superadmin" element={<Login portal="super_admin" />} />
        <Route path="/login/platform" element={<Login portal="platform_admin" />} />
        <Route path="/login/admin" element={<Login portal="admin" />} />
        <Route path="/sa/*" element={<Guard role="super_admin" to="/login/superadmin"><SuperShell /></Guard>} />
        <Route path="/pa/*" element={<Guard role="platform_admin" to="/login/platform"><PlatformShell /></Guard>} />
        <Route path="/admin/*" element={<Guard role="admin" to="/login/admin"><AdminShell /></Guard>} />
        <Route path="/login/reviewer" element={<Login portal="reviewer" />} />
        <Route path="/login/student" element={<Login portal="student" />} />
        <Route path="/login/teacher" element={<Login portal="teacher" />} />
        <Route path="/student/*" element={<Guard role="student" to="/login/student"><StudentShell /></Guard>} />
        <Route path="/teacher/*" element={<Guard role="teacher" to="/login/teacher"><TeacherShell /></Guard>} />
        <Route path="/review/*" element={<Guard role="reviewer" to="/login/reviewer"><ReviewerShell /></Guard>} />
        <Route path="*" element={<Navigate to={{ platform_admin: '/pa', admin: '/admin', reviewer: '/review', student: '/student', teacher: '/teacher' }[auth.user()?.role] || '/sa'} replace />} />
      </Routes>
    </ToastHost>
  )
}

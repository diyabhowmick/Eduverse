import { Suspense, useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { auth } from './api'
import { Icon, Sheet } from './ui'
import ErrorBoundary from './ErrorBoundary'

export function ZLogo({ theme }) {
  return <img className="zlogo-img" src={theme === 'dark' ? '/brand/zprox_logo_dark.png' : '/brand/zprox_logo_light.png'} alt="zPROx.AI" />
}

// nav: [path, icon, label] items, with optional ['__group', 'Heading'] entries to group the menu.
export default function Layout({ nav, base, role, loginPath, counts = {}, badge, collapse = false, children }) {
  const [collapsed, setCollapsed] = useState(localStorage.getItem('ev_rail') === '1')
  const [theme, setTheme] = useState(localStorage.getItem('ev_theme') || 'light')
  const [more, setMore] = useState(false)
  const [peek, setPeek] = useState(false)   // pages that keep the menu narrow (the reader) can still open it for a moment
  const go = useNavigate(); const loc = useLocation(); const user = auth.user()
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('ev_theme', theme) }, [theme])
  useEffect(() => { localStorage.setItem('ev_rail', collapsed ? '1' : '0') }, [collapsed])
  useEffect(() => { setMore(false); setPeek(false) }, [loc.pathname])
  const items = nav.filter(n => n[0] !== '__group')
  // Exact match first, then the deepest section the page sits under; detail pages that belong to no section get a plain label.
  const DETAIL = { exam: 'Exam pack', exams: 'Question papers', read: 'Reader', books: 'Book', test: 'Chapter test', result: 'Test result' }
  const seg = loc.pathname.slice(base.length + 1).split('/')[0]
  const current = items.find(([p]) => loc.pathname === base + (p ? '/' + p : '')) || items.find(([p]) => p && seg === p) || (DETAIL[seg] ? [seg, '', DETAIL[seg]] : items[0])
  const to = p => base + (p ? '/' + p : '')
  const signOut = () => { auth.clear(); go(loginPath) }
  // On phones the menu moves to a bar at the bottom: up to five tabs, or four and More.
  const tabs = items.length <= 5 ? items : [...items.slice(0, 4), ['__more', 'menu', 'More']]
  const moreCount = items.slice(4).reduce((n, [p]) => n + (counts[p] || 0), 0)
  return (
    <div className={'shell' + ((collapse ? !peek : collapsed) ? ' collapsed' : '')}>
      <aside className="rail">
        <div className="rail-top"><img className="mark-img" src="/brand/zprox_mark.png" alt="" /><div className="brand">EduVerse<small>{role}</small></div></div>
        <nav className="nav" aria-label="Main">
          {nav.map(([p, i, l]) => p === '__group' ? <div key={'g' + i} className="grp">{i}</div> : (
            <NavLink key={p} to={to(p)} end={!p} title={l}>
              <Icon n={i} /><span>{l}</span>{counts[p] ? <em className="count">{counts[p]}</em> : null}
            </NavLink>
          ))}
        </nav>
        <div className="rail-foot">
          <div className="rail-tools">
            <button className="icon-btn" onClick={() => (collapse ? setPeek(v => !v) : setCollapsed(c => !c))} aria-label={(collapse ? !peek : collapsed) ? 'Open menu' : 'Collapse menu'} aria-expanded={!(collapse ? !peek : collapsed)}><Icon n="menu" s={16} /></button>
            <button className="icon-btn" onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')} aria-label="Switch theme"><Icon n={theme === 'dark' ? 'sun' : 'moon'} s={16} /><span>{theme === 'dark' ? 'Light' : 'Dark'}</span></button>
          </div>
          <div className="company"><ZLogo theme="dark" /><span className="tagline">Automate everything effortlessly</span></div>
          <img className="company-mark" src="/brand/zprox_mark.png" alt="zPROx.AI" />
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <img className="topbar-mark" src="/brand/zprox_mark.png" alt="" />
          {badge}<span className="crumb">{role}</span><span className="crumb-sep">/</span><b>{current[2]}</b>
          <div className="who"><span>{user?.email}</span><div className="avatar" title={user?.email}>{(user?.name || 'U')[0]}</div>
            <button className="btn ghost" onClick={signOut} title="Sign out" aria-label="Sign out"><Icon n="out" s={16} /></button></div>
        </header>
        <div className="route-fx" key={loc.pathname}><ErrorBoundary where={loc.pathname}><Suspense fallback={<div className="empty" style={{ padding: 40 }}>Loading</div>}>{children}</Suspense></ErrorBoundary></div>
      </main>
      <nav className="tabbar" aria-label="Main">
        {tabs.map(([p, i, l]) => p === '__more'
          ? <button key={p} type="button" className={items.slice(4).some(x => x === current) ? 'active' : ''} onClick={() => setMore(true)}><Icon n={i} s={22} /><span>{l}</span>{moreCount ? <em>{moreCount}</em> : null}</button>
          : <NavLink key={p} to={to(p)} end={!p}><Icon n={i} s={22} /><span>{l}</span>{counts[p] ? <em>{counts[p]}</em> : null}</NavLink>)}
      </nav>
      {more && <Sheet title="Menu" onClose={() => setMore(false)}>
        <div className="menu-list">
          {nav.map(([p, i, l]) => p === '__group' ? <div key={'g' + i} className="grp">{i}</div>
            : <NavLink key={p} to={to(p)} end={!p}><Icon n={i} /><span>{l}</span>{counts[p] ? <em className="count" style={{ marginLeft: 'auto' }}>{counts[p]}</em> : null}</NavLink>)}
          <div className="grp">You</div>
          <button type="button" onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}><Icon n={theme === 'dark' ? 'sun' : 'moon'} /><span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span></button>
          <button type="button" onClick={signOut}><Icon n="out" /><span>Sign out</span><span className="muted" style={{ marginLeft: 'auto', fontSize: 12 }}>{user?.email}</span></button>
        </div>
      </Sheet>}
    </div>
  )
}

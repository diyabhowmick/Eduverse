import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { auth } from './api'
import { Icon } from './ui'

export function ZLogo({ theme }) {
  return <img className="zlogo-img" src={theme === 'dark' ? '/brand/zprox_logo_dark.png' : '/brand/zprox_logo_light.png'} alt="zPROx.AI" />
}

export default function Layout({ nav, base, role, loginPath, counts = {}, badge, collapse = false, children }) {
  const [collapsed, setCollapsed] = useState(localStorage.getItem('ev_rail') === '1')
  const [theme, setTheme] = useState(localStorage.getItem('ev_theme') || 'light')
  const go = useNavigate(); const loc = useLocation(); const user = auth.user()
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('ev_theme', theme) }, [theme])
  useEffect(() => { localStorage.setItem('ev_rail', collapsed ? '1' : '0') }, [collapsed])
  const current = nav.find(([p]) => loc.pathname === base + (p ? '/' + p : '')) || nav[0]
  return (
    <div className={'shell' + (collapsed || collapse ? ' collapsed' : '')}>
      <aside className="rail">
        <div className="rail-top"><img className="mark-img" src="/brand/zprox_mark.png" alt="" /><div className="brand">EduVerse<small>{role}</small></div></div>
        <nav className="nav" aria-label="Main">
          {nav.map(([p, i, l]) => (
            <NavLink key={p} to={base + (p ? '/' + p : '')} end={!p} title={l}>
              <Icon n={i} /><span>{l}</span>{counts[p] ? <em className="count">{counts[p]}</em> : null}
            </NavLink>
          ))}
        </nav>
        <div className="rail-foot">
          <div className="rail-tools">
            <button className="icon-btn" onClick={() => setCollapsed(c => !c)} aria-label="Collapse menu"><Icon n="menu" s={16} /></button>
            <button className="icon-btn" onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')} aria-label="Switch theme"><Icon n={theme === 'dark' ? 'sun' : 'moon'} s={16} /><span>{theme === 'dark' ? 'Light' : 'Dark'}</span></button>
          </div>
          <div className="company"><ZLogo theme={theme} /><span className="tagline">Automate everything effortlessly</span></div>
          <img className="company-mark" src="/brand/zprox_mark.png" alt="zPROx.AI" />
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          {badge}<span className="crumb">{role}</span><span>/</span><b>{current[2]}</b>
          <div className="who"><span>{user?.email}</span><div className="avatar">{(user?.name || 'U')[0]}</div>
            <button className="btn ghost" onClick={() => { auth.clear(); go(loginPath) }} title="Sign out"><Icon n="out" s={16} /></button></div>
        </header>
        {children}
      </main>
    </div>
  )
}

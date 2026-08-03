import { NavLink, Outlet } from 'react-router-dom'
import { FiActivity, FiDatabase, FiLayout, FiTrendingUp } from 'react-icons/fi'

function tabClassName({ isActive }: { isActive: boolean }) {
  return `view-tab ghost-button-with-icon${isActive ? ' is-active' : ''}`
}

export default function Layout() {
  return (
    <div className="app-shell">
      <div className="top-nav">
        <nav className="view-tabs">
          <NavLink to="/" end className={tabClassName}>
            <FiLayout aria-hidden="true" className="button-icon" />
            Overview
          </NavLink>
          <NavLink to="/jobs" className={tabClassName}>
            <FiDatabase aria-hidden="true" className="button-icon" />
            Jobs
          </NavLink>
          <NavLink to="/matches" className={tabClassName}>
            <FiTrendingUp aria-hidden="true" className="button-icon" />
            Matches
          </NavLink>
          <NavLink to="/vitals" className={tabClassName}>
            <FiActivity aria-hidden="true" className="button-icon" />
            Agent Vitals
          </NavLink>
        </nav>
      </div>

      <Outlet />
    </div>
  )
}

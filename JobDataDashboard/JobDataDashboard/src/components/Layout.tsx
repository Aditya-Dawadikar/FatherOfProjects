import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { FiActivity, FiBarChart2, FiDatabase, FiLayout } from 'react-icons/fi'
import ObservabilityPage from '../pages/ObservabilityPage'

function tabClassName({ isActive }: { isActive: boolean }) {
  return `view-tab${isActive ? ' is-active' : ''}`
}

export default function Layout() {
  // React Router unmounts/remounts whatever <Outlet /> renders on every navigation -- fine for
  // every other page, but it would tear down and reload the Grafana iframe (losing its own
  // client-side state, e.g. zoom/time-range) every time this tab is merely revisited. Rendered
  // here instead, once, for the app's whole lifetime, and just shown/hidden with CSS based on
  // the current route -- the "observability" child route below still exists (so /observability
  // is a real, refreshable, linkable URL and its NavLink still activates) but renders nothing;
  // this is the thing actually on screen there.
  const isObservability = useLocation().pathname === '/observability'

  return (
    <div className="app-shell">
      <div className="top-nav">
        <nav className="view-tabs">
          <NavLink to="/" end className={tabClassName}>
            <FiLayout aria-hidden="true" className="button-icon" />
            Agent Overview
          </NavLink>
          <NavLink to="/observability" className={tabClassName}>
            <FiBarChart2 aria-hidden="true" className="button-icon" />
            Agent Observability
          </NavLink>
          <NavLink to="/evals" className={tabClassName}>
            <FiActivity aria-hidden="true" className="button-icon" />
            Agent Evals
          </NavLink>
          <NavLink to="/etl-data" className={tabClassName}>
            <FiDatabase aria-hidden="true" className="button-icon" />
            ETL Data
          </NavLink>
        </nav>
      </div>

      <div style={{ display: isObservability ? 'contents' : 'none' }}>
        <ObservabilityPage />
      </div>
      <div style={{ display: isObservability ? 'none' : 'contents' }}>
        <Outlet />
      </div>
    </div>
  )
}

import { NavLink, Outlet } from 'react-router-dom'

// Jobs and Matches used to be their own top-level nav tabs, each with its own <main>/content-panel
// wrapper. Grouped here under one "ETL Data" tab instead (same structure as EvalsLayout: one
// shared <main>/content-panel holding the tab bar and whichever tab's content is active) since
// both are just different views over the same scrape -> match pipeline data -- JobsPage/MatchesView
// no longer wrap themselves, this is the thing that does it now.
const ETL_TABS = [
  { path: 'jobs', label: 'Jobs' },
  { path: 'matches', label: 'Matches' },
]

export default function EtlDataLayout() {
  return (
    <main className="app-body app-body-single">
      <section className="content-panel">
        <div className="etl-subnav pane-tabs">
          {ETL_TABS.map((tab) => (
            <NavLink
              key={tab.path}
              to={tab.path}
              className={({ isActive }) => `pane-tab${isActive ? ' is-active' : ''}`}
            >
              {tab.label}
            </NavLink>
          ))}
        </div>

        <Outlet />
      </section>
    </main>
  )
}

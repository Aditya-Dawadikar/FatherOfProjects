import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import TabBar from '../components/TabBar'

// Jobs and Matches used to be their own top-level nav tabs, each with its own <main>/content-panel
// wrapper. Grouped here under one "ETL Data" tab instead (same structure as EvalsLayout: one
// shared <main>/content-panel holding the tab bar and whichever tab's content is active) since
// both are just different views over the same scrape -> match pipeline data -- JobsPage/MatchesView
// no longer wrap themselves, this is the thing that does it now.
const ETL_TABS = [
  { path: 'matches', label: 'Matched & Processed Data' },
  { path: 'jobs', label: 'All Data' },
]

export default function EtlDataLayout() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <main className="app-body app-body-single">
      <section className="content-panel">
        <TabBar
          ariaLabel="ETL Data sub-tabs"
          className="etl-subnav"
          items={ETL_TABS.map((tab) => ({
            key: tab.path,
            label: tab.label,
            isActive: location.pathname.endsWith(`/${tab.path}`),
            onSelect: () => navigate(tab.path),
          }))}
        />

        <Outlet />
      </section>
    </main>
  )
}

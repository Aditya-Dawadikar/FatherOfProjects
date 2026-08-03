import { NavLink, Outlet } from 'react-router-dom'

// One route per experiment type this dashboard tracks (currently prompt-version comparison and
// tool-selection/agent-behavior evals), plus KPIs (a curated cross-experiment summary), Run
// History (spanning every experiment type at once), and System Metrics (infra-level, not an eval
// result) last. Adding a new experiment type later means adding one more tab here, not
// restructuring the tab bar.
const VITALS_TABS = [
  { path: 'kpis', label: 'KPIs' },
  { path: 'prompt', label: 'Prompt Version Comparison' },
  { path: 'behavior', label: 'Agent Behavior' },
  { path: 'history', label: 'Run History' },
  { path: 'system', label: 'System Metrics' },
]

export default function VitalsLayout() {
  return (
    <section className="content-panel">
      <div className="vitals-tabs-bar pane-tabs">
        {VITALS_TABS.map((tab) => (
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
  )
}

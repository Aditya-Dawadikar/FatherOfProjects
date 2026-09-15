import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import TabBar from '../../components/TabBar'

// One route per experiment type this dashboard tracks (currently prompt-version comparison,
// tool-selection/agent-behavior evals, and guardrails evals), plus KPIs (a curated
// cross-experiment summary) and Run History (spanning every experiment type at once). System
// Metrics (infra-level, not an eval result) now lives on its own top-level Observability tab
// (see Layout.tsx) rather than as a sub-tab here. Adding a new experiment type later means adding
// one more tab here, not restructuring the tab bar.
const EVALS_TABS = [
  { path: 'kpis', label: 'KPIs' },
  { path: 'prompt', label: 'Prompt Version Comparison' },
  { path: 'prompt-versions', label: 'Prompt Versions' },
  { path: 'datasets', label: 'Datasets' },
  { path: 'behavior', label: 'Agent Behavior' },
  { path: 'guardrails', label: 'Guardrails' },
  { path: 'history', label: 'Run History' },
]

export default function EvalsLayout() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <section className="content-panel">
      <TabBar
        ariaLabel="Evals sub-tabs"
        className="evals-tabs-bar"
        items={EVALS_TABS.map((tab) => ({
          key: tab.path,
          label: tab.label,
          isActive: location.pathname.endsWith(`/${tab.path}`),
          onSelect: () => navigate(tab.path),
        }))}
      />

      <Outlet />
    </section>
  )
}

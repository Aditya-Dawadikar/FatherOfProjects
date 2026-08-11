import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Navigate, Route, HashRouter as Router, Routes } from 'react-router-dom'
import './App.css'
import Layout from './components/Layout'
import EtlDataLayout from './pages/EtlDataLayout'
import JobsPage from './pages/JobsPage'
import MatchesPage from './pages/MatchesPage'
import MigrationPage from './pages/MigrationPage'
import MigrationLayout from './pages/migration/MigrationLayout'
import PromptVersionTab from './pages/migration/PromptVersionTab'
import BackfillHandoffTab from './pages/migration/BackfillHandoffTab'
import PromptCatalogTab from './pages/migration/PromptCatalogTab'
import OverviewPage from './pages/OverviewPage'
import RateLimitsPage from './pages/RateLimitsPage'
import EvalsPage from './pages/EvalsPage'
import AgentBehaviorTab from './pages/evals/AgentBehaviorTab'
import DatasetsTab from './pages/evals/DatasetsTab'
import GuardrailsTab from './pages/evals/GuardrailsTab'
import KpisTab from './pages/evals/KpisTab'
import PromptComparisonTab from './pages/evals/PromptComparisonTab'
import PromptVersionsTab from './pages/evals/PromptVersionsTab'
import RunHistoryTab from './pages/evals/RunHistoryTab'
import EvalsLayout from './pages/evals/EvalsLayout'

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<OverviewPage />} />
            {/* Actually rendered by Layout (kept permanently mounted there, shown/hidden with CSS,
                so its Grafana iframe doesn't reload every time this tab is revisited) -- this
                route exists only so /observability is a real, matchable, refreshable URL. */}
            <Route path="observability" element={null} />
            <Route path="etl-data" element={<EtlDataLayout />}>
              <Route index element={<Navigate to="jobs" replace />} />
              <Route path="jobs" element={<JobsPage />} />
              <Route path="matches" element={<MatchesPage />} />
            </Route>
            <Route path="migration" element={<MigrationPage />}>
              <Route element={<MigrationLayout />}>
                <Route index element={<Navigate to="prompt-version" replace />} />
                <Route path="prompt-version" element={<PromptVersionTab />} />
                <Route path="backfill-handoff" element={<BackfillHandoffTab />} />
                <Route path="prompt-catalog" element={<PromptCatalogTab />} />
              </Route>
            </Route>
            <Route path="rate-limits" element={<RateLimitsPage />} />
            <Route path="evals" element={<EvalsPage />}>
              <Route element={<EvalsLayout />}>
                <Route index element={<Navigate to="kpis" replace />} />
                <Route path="kpis" element={<KpisTab />} />
                <Route path="prompt" element={<PromptComparisonTab />} />
                <Route path="prompt-versions" element={<PromptVersionsTab />} />
                <Route path="datasets" element={<DatasetsTab />} />
                <Route path="behavior" element={<AgentBehaviorTab />} />
                <Route path="guardrails" element={<GuardrailsTab />} />
                <Route path="history" element={<RunHistoryTab />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Router>
    </QueryClientProvider>
  )
}

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Navigate, Route, HashRouter as Router, Routes } from 'react-router-dom'
import './App.css'
import Layout from './components/Layout'
import JobsPage from './pages/JobsPage'
import MatchesPage from './pages/MatchesPage'
import OverviewPage from './pages/OverviewPage'
import VitalsPage from './pages/VitalsPage'
import AgentBehaviorTab from './pages/vitals/AgentBehaviorTab'
import KpisTab from './pages/vitals/KpisTab'
import PromptComparisonTab from './pages/vitals/PromptComparisonTab'
import RunHistoryTab from './pages/vitals/RunHistoryTab'
import SystemMetricsTab from './pages/vitals/SystemMetricsTab'
import VitalsLayout from './pages/vitals/VitalsLayout'

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<OverviewPage />} />
            <Route path="jobs" element={<JobsPage />} />
            <Route path="matches" element={<MatchesPage />} />
            <Route path="vitals" element={<VitalsPage />}>
              <Route element={<VitalsLayout />}>
                <Route index element={<Navigate to="kpis" replace />} />
                <Route path="kpis" element={<KpisTab />} />
                <Route path="prompt" element={<PromptComparisonTab />} />
                <Route path="behavior" element={<AgentBehaviorTab />} />
                <Route path="history" element={<RunHistoryTab />} />
                <Route path="system" element={<SystemMetricsTab />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Router>
    </QueryClientProvider>
  )
}

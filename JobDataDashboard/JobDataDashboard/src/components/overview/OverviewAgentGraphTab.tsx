import AgentTopologyHero from '../AgentTopologyHero'
import { useAgentTopology } from '../../hooks'

export default function OverviewAgentGraphTab() {
  const topologyQuery = useAgentTopology()
  const topology = topologyQuery.data

  return (
    <div className="overview-tab-panel" role="tabpanel" aria-label="Agent Graph">
      {topologyQuery.isLoading && (
        <div className="agent-hero-skeleton">Loading interactive agent topology...</div>
      )}

      {topologyQuery.error && (
        <div className="banner banner-error">
          Could not load live agent topology: {topologyQuery.error.message}
        </div>
      )}

      {topology && <AgentTopologyHero topology={topology} />}
    </div>
  )
}

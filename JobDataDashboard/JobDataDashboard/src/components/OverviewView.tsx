import { useState } from 'react'
import TabBar from './TabBar'
import MlflowSummaryStrip from './overview/MlflowSummaryStrip'
import OverviewAgentGraphTab from './overview/OverviewAgentGraphTab'
import OverviewDataOverviewTab from './overview/OverviewDataOverviewTab'
import OverviewEtlArchitectureTab from './overview/OverviewEtlArchitectureTab'

type OverviewTab = 'agent' | 'data' | 'tracking' | 'architecture'

export default function OverviewView() {
  const [activeTab, setActiveTab] = useState<OverviewTab>('agent')

  const tabs: Array<{ key: OverviewTab; label: string }> = [
    { key: 'agent', label: 'Agent Architecture' },
    { key: 'tracking', label: 'Agent Tracking' },
    { key: 'architecture', label: 'ETL Architecture' },
    { key: 'data', label: 'Data Overview' },
  ]

  return (
    <section className="content-panel">
      <TabBar
        ariaLabel="Overview sub-tabs"
        className="overview-subtabs"
        items={tabs.map((tab) => ({
          key: tab.key,
          label: tab.label,
          isActive: activeTab === tab.key,
          onSelect: () => setActiveTab(tab.key),
        }))}
      />

      {activeTab === 'agent' && <OverviewAgentGraphTab />}
      {activeTab === 'data' && <OverviewDataOverviewTab />}
      {activeTab === 'tracking' && (
        <div className="overview-tab-panel" role="tabpanel" aria-label="Agent Tracking">
          <MlflowSummaryStrip />
        </div>
      )}
      {activeTab === 'architecture' && <OverviewEtlArchitectureTab />}
    </section>
  )
}

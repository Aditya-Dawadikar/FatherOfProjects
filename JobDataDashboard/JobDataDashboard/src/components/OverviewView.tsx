import { useState } from 'react'
import MlflowSummaryStrip from './overview/MlflowSummaryStrip'
import OverviewAgentGraphTab from './overview/OverviewAgentGraphTab'
import OverviewDataOverviewTab from './overview/OverviewDataOverviewTab'
import OverviewEtlArchitectureTab from './overview/OverviewEtlArchitectureTab'

export default function OverviewView() {
  const [activeTab, setActiveTab] = useState<'agent' | 'data' | 'tracking' | 'architecture'>('agent')

  return (
    <section className="content-panel">
      <div className="overview-subtabs pane-tabs" role="tablist" aria-label="Overview sub-tabs">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'agent'}
          className={`pane-tab${activeTab === 'agent' ? ' is-active' : ''}`}
          onClick={() => setActiveTab('agent')}
        >
          Agent Architecture
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'tracking'}
          className={`pane-tab${activeTab === 'tracking' ? ' is-active' : ''}`}
          onClick={() => setActiveTab('tracking')}
        >
          Agent Tracking
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'architecture'}
          className={`pane-tab${activeTab === 'architecture' ? ' is-active' : ''}`}
          onClick={() => setActiveTab('architecture')}
        >
          ETL Architecture
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'data'}
          className={`pane-tab${activeTab === 'data' ? ' is-active' : ''}`}
          onClick={() => setActiveTab('data')}
        >
          Data Overview
        </button>
      </div>

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

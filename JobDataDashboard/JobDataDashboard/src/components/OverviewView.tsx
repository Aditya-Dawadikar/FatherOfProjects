import { useState } from 'react'
import MlflowSummaryStrip from './overview/MlflowSummaryStrip'
import OverviewAgentGraphTab from './overview/OverviewAgentGraphTab'
import OverviewDataOverviewTab from './overview/OverviewDataOverviewTab'

export default function OverviewView() {
  const [activeTab, setActiveTab] = useState<'agent' | 'data'>('agent')

  return (
    <section className="content-panel">
      <MlflowSummaryStrip />

      <div className="overview-subtabs pane-tabs" role="tablist" aria-label="Overview sub-tabs">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'agent'}
          className={`pane-tab${activeTab === 'agent' ? ' is-active' : ''}`}
          onClick={() => setActiveTab('agent')}
        >
          Agent Graph
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
    </section>
  )
}

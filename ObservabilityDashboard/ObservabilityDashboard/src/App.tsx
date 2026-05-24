import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Header from './components/Header'
import NodeGraph from './components/NodeGraph'
import Inspector from './components/Inspector'
import { useObservabilityStream, useSystemDag } from './hooks'
import './App.css'

const queryClient = new QueryClient()

function DashboardApp() {
  const [selectedNodeId, setSelectedNodeId] = useState<string>('observability-server')
  const { data: dag } = useSystemDag()
  const liveStream = useObservabilityStream()
  const footerLabel = liveStream.connected ? 'SSE connected' : 'SSE reconnecting'
  const footerEventTime = liveStream.lastEventAt
    ? new Date(liveStream.lastEventAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : 'Awaiting events'

  return (
    <div className="dash-layout">
      <Header />
      <div className="dash-body">
        <main className="graph-area">
          {dag && (
            <NodeGraph
              dag={dag}
              selectedNodeId={selectedNodeId}
              onSelectNode={setSelectedNodeId}
            />
          )}
        </main>
        <Inspector nodeId={selectedNodeId} onSelectNode={setSelectedNodeId} />
      </div>
      <footer className="dash-footer">
        <span className="footer-stream">
          <span className="footer-dot" />
          {footerLabel} · observability-server
        </span>
        <span>{footerEventTime}</span>
      </footer>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <DashboardApp />
    </QueryClientProvider>
  )
}

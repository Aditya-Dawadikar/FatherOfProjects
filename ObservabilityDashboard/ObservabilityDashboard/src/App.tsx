import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Header from './components/Header'
import NodeGraph from './components/NodeGraph'
import Inspector from './components/Inspector'
import { useSystemDag } from './hooks'
import './App.css'

const queryClient = new QueryClient()

function DashboardApp() {
  const [selectedNodeId, setSelectedNodeId] = useState<string>('observability-server')
  const { data: dag } = useSystemDag()

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
          SSE connected · observability-server
        </span>
        <span>Observability Platform v1.0</span>
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

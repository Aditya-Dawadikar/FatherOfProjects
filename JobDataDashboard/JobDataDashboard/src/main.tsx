import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initAnalytics } from './lib/posthog'
import { MobileLayoutProvider } from './lib/experiment'

initAnalytics()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MobileLayoutProvider>
      <App />
    </MobileLayoutProvider>
  </StrictMode>,
)
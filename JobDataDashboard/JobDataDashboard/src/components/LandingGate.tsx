import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { arrivedAtRoot, LANDING_PATH, resolveLandingVariant } from '../lib/landingExperiment'

// Holds the dashboard back (rendering nothing) for the brief moment it takes to learn this
// visitor's variant, then either redirects to the landing page or lets the dashboard render --
// so a test visitor never sees a flash of the Overview tab before being sent to /welcome, and
// the Overview's own $pageview isn't logged for them before they've seen the landing page.
export default function LandingGate({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [isResolving, setIsResolving] = useState(arrivedAtRoot)

  useEffect(() => {
    if (!arrivedAtRoot) {
      return
    }
    let cancelled = false
    resolveLandingVariant().then((variant) => {
      if (cancelled) {
        return
      }
      if (variant === 'test') {
        navigate(LANDING_PATH, { replace: true })
      }
      setIsResolving(false)
    })
    return () => {
      cancelled = true
    }
  }, [navigate])

  if (isResolving) {
    return <div className="landing-gate-pending" aria-busy="true" />
  }
  return <>{children}</>
}

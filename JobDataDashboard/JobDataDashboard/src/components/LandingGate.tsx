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

  // Keyed on isResolving, not just navigate: useNavigate() hands back a new function after every
  // navigation, so without the guard this would re-run on each click and bounce the visitor back
  // to /welcome. The redirect only ever belongs to the initial arrival.
  useEffect(() => {
    if (!isResolving) {
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
  }, [isResolving, navigate])

  if (isResolving) {
    return <div className="landing-gate-pending" aria-busy="true" />
  }
  return <>{children}</>
}

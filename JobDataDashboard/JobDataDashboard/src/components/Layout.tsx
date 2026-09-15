import { useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { FiActivity, FiAlertTriangle, FiBarChart2, FiDatabase, FiLayout, FiSettings } from 'react-icons/fi'
import { useBillingStatus } from '../hooks'
import { trackPageview } from '../lib/posthog'
import { useMobileLayout } from '../lib/experiment'
import MobileLayoutDevToggle from './MobileLayoutDevToggle'
import ObservabilityPage from '../pages/ObservabilityPage'

// Shared between the desktop top nav and the mobile-first bottom tab bar (see App.css's
// `.mobile-first .bottom-nav` rules) -- one source of truth for routes/icons, shortLabel only
// used by the bottom bar where horizontal space is tight.
const NAV_ITEMS = [
  { to: '/', end: true, icon: FiLayout, label: 'Agent Overview', shortLabel: 'Overview' },
  { to: '/observability', end: false, icon: FiBarChart2, label: 'Agent Observability', shortLabel: 'Metrics' },
  { to: '/evals', end: false, icon: FiActivity, label: 'Agent Evals', shortLabel: 'Evals' },
  { to: '/etl-data', end: false, icon: FiDatabase, label: 'ETL Data', shortLabel: 'Data' },
  { to: '/admin', end: false, icon: FiSettings, label: 'Admin', shortLabel: 'Admin' },
]

function tabClassName({ isActive }: { isActive: boolean }) {
  return `view-tab${isActive ? ' is-active' : ''}`
}

function bottomTabClassName({ isActive }: { isActive: boolean }) {
  return `bottom-nav-link${isActive ? ' is-active' : ''}`
}

export default function Layout() {
  // React Router unmounts/remounts whatever <Outlet /> renders on every navigation -- fine for
  // every other page, but it would tear down and reload the Grafana iframe (losing its own
  // client-side state, e.g. zoom/time-range) every time this tab is merely revisited. Rendered
  // here instead, once, for the app's whole lifetime, and just shown/hidden with CSS based on
  // the current route -- the "observability" child route below still exists (so /observability
  // is a real, refreshable, linkable URL and its NavLink still activates) but renders nothing;
  // this is the thing actually on screen there.
  const location = useLocation()
  const isObservability = location.pathname === '/observability'
  // Gates the mobile-first-layout PostHog experiment variant (see src/lib/experiment.tsx) --
  // independent of actual viewport width so control/test stay comparable.
  const isMobileFirst = useMobileLayout()
  // HashRouter navigation never triggers a real page load, so posthog-js's own history-based
  // pageview autocapture (disabled in src/lib/posthog.ts) would miss every tab switch -- fire one
  // manually here instead, in the one place every route renders through.
  useEffect(() => {
    trackPageview(location.pathname)
  }, [location.pathname])
  // Polls from every tab (not just Rate Limits, where the billing-exhaustion alert detail lives)
  // -- billing exhaustion means every subsequent live/backfill scoring call keeps failing the
  // same way, so it needs to be visible no matter what an operator happens to have open when it
  // hits.
  const billingStatusQuery = useBillingStatus()
  const isBillingExhausted = billingStatusQuery.data?.is_billing_exhausted ?? false

  return (
    <div className={`app-shell${isMobileFirst ? ' mobile-first' : ''}`}>
      <MobileLayoutDevToggle />
      {isBillingExhausted && (
        <NavLink to="/rate-limits" className="global-alert-banner">
          <FiAlertTriangle aria-hidden="true" className="button-icon" />
          Gemini billing exhausted -- live and backfill scoring calls are failing. Go to Rate
          Limits for details.
        </NavLink>
      )}
      <div className="top-nav">
        <nav className="view-tabs">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={tabClassName}>
              <item.icon aria-hidden="true" className="button-icon" />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="app-main">
        <div style={{ display: isObservability ? 'contents' : 'none' }}>
          <ObservabilityPage />
        </div>
        <div style={{ display: isObservability ? 'none' : 'contents' }}>
          <Outlet />
        </div>
      </div>

      {/* Only ever shown under .mobile-first (see App.css) -- replaces the top tab row with a
          thumb-reachable bottom bar so switching sections never costs a reach-to-the-top-of-the-
          screen tap. */}
      <nav className="bottom-nav" aria-label="Primary">
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={bottomTabClassName}>
            <item.icon aria-hidden="true" className="bottom-nav-icon" />
            <span>{item.shortLabel}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

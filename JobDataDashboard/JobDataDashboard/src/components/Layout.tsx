import { useEffect } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { FiActivity, FiAlertTriangle, FiBarChart2, FiDatabase, FiLayout, FiSettings } from 'react-icons/fi'
import { useBillingStatus } from '../hooks'
import { PRODUCT_NAME } from '../lib/brand'
import { LANDING_PATH } from '../lib/landingExperiment'
import { trackEvent, trackPageview, trackSectionReached } from '../lib/posthog'
import BrandMark from './BrandMark'
import ObservabilityPage from '../pages/ObservabilityPage'

// The bottom tab bar's sections (see App.css's `.bottom-nav` rules) -- short labels since
// horizontal space is tight.
const NAV_ITEMS = [
  { to: '/', end: true, icon: FiLayout, label: 'Overview' },
  { to: '/observability', end: false, icon: FiBarChart2, label: 'Metrics' },
  { to: '/evals', end: false, icon: FiActivity, label: 'Evals' },
  { to: '/etl-data', end: false, icon: FiDatabase, label: 'Data' },
  { to: '/admin', end: false, icon: FiSettings, label: 'Admin' },
]

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
  // HashRouter navigation never triggers a real page load, so posthog-js's own history-based
  // pageview autocapture (disabled in src/lib/posthog.ts) would miss every tab switch -- fire one
  // manually here instead, in the one place every route renders through.
  useEffect(() => {
    trackPageview(location.pathname)
    trackSectionReached(location.pathname)
  }, [location.pathname])
  // Polls from every tab (not just Rate Limits, where the billing-exhaustion alert detail lives)
  // -- billing exhaustion means every subsequent live/backfill scoring call keeps failing the
  // same way, so it needs to be visible no matter what an operator happens to have open when it
  // hits.
  const billingStatusQuery = useBillingStatus()
  const isBillingExhausted = billingStatusQuery.data?.is_billing_exhausted ?? false

  return (
    <div className="app-shell">
      {isBillingExhausted && (
        <NavLink to="/rate-limits" className="global-alert-banner">
          <FiAlertTriangle aria-hidden="true" className="button-icon" />
          Gemini billing exhausted -- live and backfill scoring calls are failing. Go to Rate
          Limits for details.
        </NavLink>
      )}
      <div className="top-nav">
        {/* Way back to the landing page from anywhere in the dashboard. Reachable by control
            visitors of the landing-page experiment too -- landing_viewed's `entry` property
            ("dashboard-nav") is how the analysis tells those visits apart. */}
        <Link
          to={LANDING_PATH}
          state={{ entry: 'dashboard-nav' }}
          className="top-nav-brand"
          aria-label={`${PRODUCT_NAME}: about this project`}
          onClick={() => trackEvent('landing_link_clicked', { from: location.pathname })}
        >
          <BrandMark size={24} />
          <span>{PRODUCT_NAME}</span>
        </Link>
      </div>

      <div className="app-main">
        <div style={{ display: isObservability ? 'contents' : 'none' }}>
          <ObservabilityPage />
        </div>
        <div style={{ display: isObservability ? 'none' : 'contents' }}>
          <Outlet />
        </div>
      </div>

      {/* Primary navigation: a thumb-reachable bottom bar so switching sections never costs a
          reach-to-the-top-of-the-screen tap. The top bar above only holds the brand link. */}
      <nav className="bottom-nav" aria-label="Primary">
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={bottomTabClassName}>
            <item.icon aria-hidden="true" className="bottom-nav-icon" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

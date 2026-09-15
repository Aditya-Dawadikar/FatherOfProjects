import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import HamburgerTabMenu from '../components/HamburgerTabMenu'
import { useMobileLayout } from '../lib/experiment'

// Sidebar (not the horizontal pane-tabs bar used elsewhere, e.g. EtlDataLayout/EvalsLayout) since
// "Migrations" below is itself a multi-tab page (MigrationLayout's own Prompt Version/Backfill
// Handoff/Prompt Catalog pane-tabs) -- nesting a second horizontal tab row under a first one reads
// worse than a vertical section list next to whichever section's content is open. Under the
// mobile-first-layout experiment this becomes a hamburger menu instead (see HamburgerTabMenu) --
// desktop keeps this exact vertical sidebar.
const ADMIN_SECTIONS = [
  { path: 'billing', label: 'Billing' },
  { path: 'rate-limits', label: 'Rate Limits' },
  { path: 'feature-flags', label: 'Feature Flags' },
  { path: 'migrations', label: 'Migrations' },
]

export default function AdminLayout() {
  const isMobileFirst = useMobileLayout()
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <div className="admin-layout">
      {isMobileFirst ? (
        <HamburgerTabMenu
          ariaLabel="Admin sections"
          className="admin-sidebar-menu"
          items={ADMIN_SECTIONS.map((section) => ({
            key: section.path,
            label: section.label,
            isActive: location.pathname.includes(`/admin/${section.path}`),
            onSelect: () => navigate(`/admin/${section.path}`),
          }))}
        />
      ) : (
        <nav className="admin-sidebar">
          {ADMIN_SECTIONS.map((section) => (
            <NavLink
              key={section.path}
              to={section.path}
              className={({ isActive }) => `admin-sidebar-link${isActive ? ' is-active' : ''}`}
            >
              {section.label}
            </NavLink>
          ))}
        </nav>
      )}
      <div className="admin-content">
        <Outlet />
      </div>
    </div>
  )
}

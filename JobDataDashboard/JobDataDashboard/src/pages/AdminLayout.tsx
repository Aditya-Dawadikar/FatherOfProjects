import { NavLink, Outlet } from 'react-router-dom'

// Sidebar (not the horizontal pane-tabs bar used elsewhere, e.g. EtlDataLayout/EvalsLayout) since
// "Migrations" below is itself a multi-tab page (MigrationLayout's own Prompt Version/Backfill
// Handoff/Prompt Catalog pane-tabs) -- nesting a second horizontal tab row under a first one reads
// worse than a vertical section list next to whichever section's content is open.
const ADMIN_SECTIONS = [
  { path: 'billing', label: 'Billing' },
  { path: 'rate-limits', label: 'Rate Limits' },
  { path: 'feature-flags', label: 'Feature Flags' },
  { path: 'migrations', label: 'Migrations' },
]

export default function AdminLayout() {
  return (
    <div className="admin-layout">
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
      <div className="admin-content">
        <Outlet />
      </div>
    </div>
  )
}

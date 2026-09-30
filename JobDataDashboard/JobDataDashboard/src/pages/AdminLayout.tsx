import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import HamburgerTabMenu from '../components/HamburgerTabMenu'

// Admin sections switch through a hamburger menu (see HamburgerTabMenu), same as every other
// sub-tab bar -- "Migrations" below is itself a multi-tab page with its own menu underneath.
const ADMIN_SECTIONS = [
  { path: 'billing', label: 'Billing' },
  { path: 'rate-limits', label: 'Rate Limits' },
  { path: 'feature-flags', label: 'Feature Flags' },
  { path: 'migrations', label: 'Migrations' },
]

export default function AdminLayout() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <div className="admin-layout">
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
      <div className="admin-content">
        <Outlet />
      </div>
    </div>
  )
}

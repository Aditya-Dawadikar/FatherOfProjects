import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import TabBar from '../../components/TabBar'

// Three views grouped under one Migration tab: cutting the live feature flag over to a new prompt
// version, the separate rescore-under-a-new-prompt backfill process (its own reserved RPM bucket,
// its own candidate query -- see docs/backfill-design.md), and a reference catalog of every
// registered version's metadata + usage so either decision has a track record to go on. Same
// structure as EvalsLayout/EtlDataLayout -- one shared content-panel holding the tab bar and
// whichever tab's content is active.
const MIGRATION_TABS = [
  { path: 'prompt-version', label: 'Prompt Version' },
  { path: 'backfill-handoff', label: 'Backfill Handoff' },
  { path: 'prompt-catalog', label: 'Prompt Catalog' },
]

export default function MigrationLayout() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <section className="content-panel">
      <TabBar
        ariaLabel="Migration sub-tabs"
        className="migration-tabs-bar"
        items={MIGRATION_TABS.map((tab) => ({
          key: tab.path,
          label: tab.label,
          isActive: location.pathname.endsWith(`/${tab.path}`),
          onSelect: () => navigate(tab.path),
        }))}
      />

      <Outlet />
    </section>
  )
}

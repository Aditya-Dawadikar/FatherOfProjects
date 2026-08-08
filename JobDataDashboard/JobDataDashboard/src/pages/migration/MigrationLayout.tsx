import { NavLink, Outlet } from 'react-router-dom'

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
  return (
    <section className="content-panel">
      <div className="migration-tabs-bar pane-tabs">
        {MIGRATION_TABS.map((tab) => (
          <NavLink
            key={tab.path}
            to={tab.path}
            className={({ isActive }) => `pane-tab${isActive ? ' is-active' : ''}`}
          >
            {tab.label}
          </NavLink>
        ))}
      </div>

      <Outlet />
    </section>
  )
}

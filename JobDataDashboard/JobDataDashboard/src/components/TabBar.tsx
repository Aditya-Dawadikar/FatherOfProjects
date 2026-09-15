import HamburgerTabMenu, { type TabMenuItem } from './HamburgerTabMenu'
import { useMobileLayout } from '../lib/experiment'

type TabBarProps = {
  items: TabMenuItem[]
  ariaLabel: string
  className?: string
}

// Shared by every pane-tabs sub-tab bar (Overview, ETL Data, Evals, Migrations). Renders the
// classic horizontal .pane-tabs row for the current desktop-first layout unchanged, and swaps to
// a hamburger-triggered vertical menu under the mobile-first-layout experiment variant (see
// src/lib/experiment.tsx) -- replacing what used to be that same row squeezed into a horizontally
// scrolling strip.
export default function TabBar({ items, ariaLabel, className }: TabBarProps) {
  const isMobileFirst = useMobileLayout()

  if (isMobileFirst) {
    return <HamburgerTabMenu items={items} ariaLabel={ariaLabel} className={className} />
  }

  return (
    <div className={`pane-tabs${className ? ` ${className}` : ''}`} role="tablist" aria-label={ariaLabel}>
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          role="tab"
          aria-selected={item.isActive}
          className={`pane-tab${item.isActive ? ' is-active' : ''}`}
          onClick={item.onSelect}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}

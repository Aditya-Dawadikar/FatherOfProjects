import HamburgerTabMenu, { type TabMenuItem } from './HamburgerTabMenu'

type TabBarProps = {
  items: TabMenuItem[]
  ariaLabel: string
  className?: string
}

// Shared by every sub-tab bar (Overview, ETL Data, Evals, Migrations): a hamburger-triggered
// vertical menu rather than a horizontal row of tabs, so it fits any screen width.
export default function TabBar({ items, ariaLabel, className }: TabBarProps) {
  return <HamburgerTabMenu items={items} ariaLabel={ariaLabel} className={className} />
}

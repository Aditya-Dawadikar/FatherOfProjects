import { useState } from 'react'
import { FiChevronDown, FiMenu, FiX } from 'react-icons/fi'

export type TabMenuItem = {
  key: string
  label: string
  isActive: boolean
  onSelect: () => void
}

type HamburgerTabMenuProps = {
  items: TabMenuItem[]
  ariaLabel: string
  className?: string
}

// The mobile-first replacement for a row of tabs/sidebar links -- a single button showing the
// current section, which expands into a vertical list instead of a horizontally scrolling row.
// Used directly (e.g. AdminLayout, which needs an entirely different desktop rendering) or via
// TabBar (which also renders the classic .pane-tabs row for non-mobile-first).
export default function HamburgerTabMenu({ items, ariaLabel, className }: HamburgerTabMenuProps) {
  const [isOpen, setIsOpen] = useState(false)
  const activeItem = items.find((item) => item.isActive) ?? items[0]

  function selectItem(item: TabMenuItem) {
    item.onSelect()
    setIsOpen(false)
  }

  return (
    <div className={`tab-menu${className ? ` ${className}` : ''}`}>
      <button
        type="button"
        className="tab-menu-trigger"
        aria-haspopup="true"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((current) => !current)}
      >
        {isOpen ? <FiX aria-hidden="true" className="button-icon" /> : <FiMenu aria-hidden="true" className="button-icon" />}
        <span className="tab-menu-trigger-label">{activeItem?.label}</span>
        <FiChevronDown aria-hidden="true" className={`tab-menu-chevron${isOpen ? ' is-open' : ''}`} />
      </button>

      {isOpen && (
        <>
          <button
            type="button"
            className="tab-menu-backdrop"
            aria-label={`Close ${ariaLabel}`}
            onClick={() => setIsOpen(false)}
          />
          <div className="tab-menu-list" role="menu" aria-label={ariaLabel}>
            {items.map((item) => (
              <button
                key={item.key}
                type="button"
                role="menuitemradio"
                aria-checked={item.isActive}
                className={`tab-menu-item${item.isActive ? ' is-active' : ''}`}
                onClick={() => selectItem(item)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

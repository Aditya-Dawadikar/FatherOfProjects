import { useSyncExternalStore } from 'react'

// Phone-shaped layout (bottom tab bar, hamburger section menus, locked graphs) vs. the desktop
// layout (top tab row, pane-tabs, admin sidebar, pannable graphs). Picked per visitor from the
// actual screen: a narrow viewport, or a real phone even when it's held in landscape.
const MOBILE_LAYOUT_QUERY = '(max-width: 820px)'

// User-Agent Client Hints "mobile" flag where available (Chromium), falling back to a standard UA
// regex (Safari/Firefox on iOS/Android don't expose userAgentData).
function isMobileDevice(): boolean {
  if (typeof navigator === 'undefined') {
    return false
  }

  const uaData = (navigator as Navigator & { userAgentData?: { mobile?: boolean } }).userAgentData
  if (uaData && typeof uaData.mobile === 'boolean') {
    return uaData.mobile
  }

  return /Mobi|Android|iPhone|iPod/i.test(navigator.userAgent)
}

function subscribe(onChange: () => void) {
  const mediaQuery = window.matchMedia(MOBILE_LAYOUT_QUERY)
  mediaQuery.addEventListener('change', onChange)
  return () => mediaQuery.removeEventListener('change', onChange)
}

function getSnapshot(): boolean {
  return isMobileDevice() || window.matchMedia(MOBILE_LAYOUT_QUERY).matches
}

export function useMobileLayout(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, () => false)
}

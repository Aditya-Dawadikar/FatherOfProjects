import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import posthog from 'posthog-js'
import { isAnalyticsEnabled } from './posthog'

// Browser-first vs. mobile-first layout A/B test. The experiment itself (variants, allocation,
// targeting) lives entirely in PostHog Cloud -- this is just the flag key both sides need to
// agree on. Multivariate flag with variants "control" and "test" (a plain boolean flag also
// works: `true` is treated the same as "test").
export const MOBILE_LAYOUT_FLAG_KEY = 'mobile-first-layout'

type Variant = 'control' | 'test'

// QA/screenshot override: ?mobile_layout=test|control in the URL, remembered in localStorage so
// it survives navigating around the app. Takes priority over whatever PostHog would assign --
// without it there'd be no way to preview the "test" variant locally before the experiment (or
// its targeting) is actually live in PostHog.
const OVERRIDE_PARAM = 'mobile_layout'
const OVERRIDE_STORAGE_KEY = 'mobile_layout_override'

function readOverride(): Variant | null {
  if (typeof window === 'undefined') {
    return null
  }

  const fromUrl = new URLSearchParams(window.location.search).get(OVERRIDE_PARAM)
  if (fromUrl === 'test' || fromUrl === 'control') {
    window.localStorage.setItem(OVERRIDE_STORAGE_KEY, fromUrl)
    return fromUrl
  }

  const stored = window.localStorage.getItem(OVERRIDE_STORAGE_KEY)
  return stored === 'test' || stored === 'control' ? stored : null
}

// A real phone/mobile browser always gets the mobile-first layout outright, without going
// through PostHog's random per-visitor assignment -- the experiment's random split is what's
// meant to decide *desktop* traffic (that's the actual A/B question: is mobile-first worth
// shipping to browser visitors too), not whether someone on a phone gets a phone-shaped UI. Uses
// the User-Agent Client Hints "mobile" flag where available (Chromium), falling back to a
// standard UA regex (Safari/Firefox on iOS/Android don't expose userAgentData).
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

const MobileLayoutContext = createContext(false)

export function MobileLayoutProvider({ children }: { children: ReactNode }) {
  const [isMobileFirst, setIsMobileFirst] = useState(() => {
    const override = readOverride()
    if (override) {
      return override === 'test'
    }
    return isMobileDevice()
  })

  useEffect(() => {
    if (readOverride()) {
      // Override wins for the lifetime of this session -- don't let a later PostHog flag
      // evaluation clobber it.
      return
    }

    if (isMobileDevice()) {
      // Already set from the initializer above; skip asking PostHog entirely -- this visitor was
      // never actually part of the randomized split, so evaluating the flag here would both be a
      // no-op for what's rendered and would log a misleading exposure (PostHog recording "shown
      // control" for someone who in fact always sees the mobile-first UI).
      return
    }

    if (!isAnalyticsEnabled()) {
      return
    }

    // Fires once flags are first loaded and again on any later reload (e.g. after identify) --
    // calling getFeatureFlag here (rather than posthog.getFeatureFlag at render time) is also
    // what makes posthog-js report the experiment exposure event automatically.
    posthog.onFeatureFlags(() => {
      const flagValue = posthog.getFeatureFlag(MOBILE_LAYOUT_FLAG_KEY)
      setIsMobileFirst(flagValue === 'test' || flagValue === true)
    })
  }, [])

  return <MobileLayoutContext.Provider value={isMobileFirst}>{children}</MobileLayoutContext.Provider>
}

export function useMobileLayout(): boolean {
  return useContext(MobileLayoutContext)
}

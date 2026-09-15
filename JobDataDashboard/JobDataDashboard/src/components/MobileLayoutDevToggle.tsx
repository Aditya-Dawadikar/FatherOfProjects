import { useMobileLayout } from '../lib/experiment'

// Dev-only QA control for the mobile-first-layout experiment (see src/lib/experiment.tsx) --
// lets you flip between the two variants without hand-editing the URL while screenshotting or
// eyeballing the layout locally. import.meta.env.DEV is inlined by Vite, so this whole component
// (and the branch below) is dead code in production builds, not just hidden.
export default function MobileLayoutDevToggle() {
  const isMobileFirst = useMobileLayout()

  if (!import.meta.env.DEV) {
    return null
  }

  function setVariant(variant: 'control' | 'test') {
    const url = new URL(window.location.href)
    url.searchParams.set('mobile_layout', variant)
    window.location.href = url.toString()
  }

  return (
    <div className="dev-layout-toggle" role="group" aria-label="Mobile layout experiment override (dev only)">
      <button type="button" className={isMobileFirst ? '' : 'is-active'} onClick={() => setVariant('control')}>
        Control
      </button>
      <button type="button" className={isMobileFirst ? 'is-active' : ''} onClick={() => setVariant('test')}>
        Test
      </button>
    </div>
  )
}

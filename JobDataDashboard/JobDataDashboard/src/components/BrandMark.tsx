// The product's logo mark: a ring (the agent) around a dot (the one match that comes out). The
// ring takes the surrounding text color, so it follows whatever it sits in (landing header, dashboard
// nav).
export default function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" aria-hidden="true" className="brand-mark">
      <circle cx="14" cy="14" r="12" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="14" cy="14" r="4" fill="#FF9B7A" />
    </svg>
  )
}

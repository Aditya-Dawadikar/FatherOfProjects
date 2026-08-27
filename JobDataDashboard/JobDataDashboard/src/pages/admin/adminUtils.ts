export const BUCKET_LABEL: Record<string, string> = {
  live: 'Live (x)',
  backfill: 'Backfill (y)',
  eval: 'Eval (z)',
}

export function formatDateTime(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

export function usagePercent(count: number, cap: number) {
  if (cap <= 0) return 0
  return Math.min(100, Math.round((count / cap) * 100))
}

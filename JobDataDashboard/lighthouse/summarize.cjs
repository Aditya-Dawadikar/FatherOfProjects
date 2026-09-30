// Turns Lighthouse CI's filesystem output (lhci-reports/manifest.json + per-run JSON reports) into
// a Markdown table of each URL's median run -- appended to the GitHub Actions job summary when
// run in CI, printed to stdout otherwise.
const fs = require('node:fs')
const path = require('node:path')

const reportsDir = path.join(__dirname, 'lhci-reports')
const manifest = JSON.parse(fs.readFileSync(path.join(reportsDir, 'manifest.json'), 'utf8'))

const CATEGORIES = [
  ['performance', 'Perf'],
  ['accessibility', 'A11y'],
  ['best-practices', 'Best practices'],
  ['seo', 'SEO'],
]
const METRICS = [
  ['first-contentful-paint', 'FCP', (v) => `${(v / 1000).toFixed(1)} s`],
  ['largest-contentful-paint', 'LCP', (v) => `${(v / 1000).toFixed(1)} s`],
  ['total-blocking-time', 'TBT', (v) => `${Math.round(v)} ms`],
  ['cumulative-layout-shift', 'CLS', (v) => v.toFixed(3)],
]

function score(value) {
  if (typeof value !== 'number') return 'n/a'
  const pct = Math.round(value * 100)
  const badge = pct >= 90 ? '🟢' : pct >= 50 ? '🟠' : '🔴'
  return `${badge} ${pct}`
}

// Hash routes all share pathname "/", so label rows by the route itself.
function label(url) {
  return `\`${new URL(url).hash || '#/'}\``
}

const rows = manifest
  .filter((run) => run.isRepresentativeRun)
  .map((run) => {
    const report = JSON.parse(fs.readFileSync(run.jsonPath, 'utf8'))
    const metrics = METRICS.map(([id, , format]) => {
      const value = report.audits[id]?.numericValue
      return typeof value === 'number' ? format(value) : 'n/a'
    })
    return [label(run.url), ...CATEGORIES.map(([id]) => score(run.summary[id])), ...metrics]
  })

const header = ['Page', ...CATEGORIES.map(([, name]) => name), ...METRICS.map(([, name]) => name)]
const lines = [
  `### Lighthouse (mobile, median of ${manifest.length / Math.max(rows.length, 1)} runs)`,
  '',
  `| ${header.join(' | ')} |`,
  `| ${header.map(() => '---').join(' | ')} |`,
  ...rows.map((row) => `| ${row.join(' | ')} |`),
  '',
  'Full HTML reports are in the `lighthouse-reports` artifact of this run.',
  '',
]
const markdown = lines.join('\n')

if (process.env.GITHUB_STEP_SUMMARY) {
  fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, markdown)
}
console.log(markdown)

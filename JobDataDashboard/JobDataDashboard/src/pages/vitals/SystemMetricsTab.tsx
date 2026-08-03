// JobManagerAgent System Metrics dashboard (Observability/grafana/provisioning/dashboards/json/jobmanageragent.json).
// kiosk=tv hides Grafana's own nav chrome so it reads as one panel of this dashboard rather than
// a page-within-a-page; theme=light matches this app's palette (see src/index.css's --bg/--panel).
// Grafana must have GF_SECURITY_ALLOW_EMBEDDING=true (Observability/grafana/Dockerfile) or every
// browser refuses this iframe outright via X-Frame-Options.
const GRAFANA_DASHBOARD_URL =
  import.meta.env.VITE_GRAFANA_DASHBOARD_URL ??
  'https://fatherofprojects-production-181c.up.railway.app/d/jobmanageragent-system-metrics/jobmanageragent-system-metrics?orgId=1&kiosk=tv&theme=light'

export default function SystemMetricsTab() {
  return (
    <>
      <div className="toolbar">
        <div className="toolbar-copy">
          <p className="eyebrow">JobManagerAgent</p>
          <h2>System metrics</h2>
        </div>
      </div>
      <iframe
        className="grafana-embed"
        src={GRAFANA_DASHBOARD_URL}
        title="JobManagerAgent System Metrics (Grafana)"
        loading="lazy"
      />
    </>
  )
}

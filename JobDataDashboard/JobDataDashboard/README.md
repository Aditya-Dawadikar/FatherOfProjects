# Job Data Dashboard

Simple React UI for browsing and editing records exposed by JobDataServer.

## Development

Create a local env file and run Vite:

```powershell
Copy-Item .env.example .env
npm.cmd install
npm.cmd run dev
```

Required env variables:

- `JOB_DATA_API_PROXY`: target used by Vite dev proxy for `/api/*` calls (default: `http://localhost:8000`)
- `VITE_JOB_DATA_API_BASE_URL`: optional API base URL in development; leave empty to use same-origin `/api/*`

The UI calls `/api/jobs` and `/api/health`; Vite and Caddy strip the `/api` prefix before proxying to JobDataServer.

## Production

The Caddy container proxies `/api/jobs` and `/api/health` to `JOB_DATA_API_UPSTREAM`.
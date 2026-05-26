# Job Data Dashboard

Simple React UI for browsing and editing records exposed by JobDataServer.

## Development

Set the API target and run Vite:

```powershell
$env:JOB_DATA_API_PROXY = "http://localhost:8000"
npm.cmd install
npm.cmd run dev
```

The UI calls `/api/jobs` and `/api/health`; Vite and Caddy strip the `/api` prefix before proxying to JobDataServer.

## Production

The Caddy container proxies `/api/jobs` and `/api/health` to `JOB_DATA_API_UPSTREAM`.
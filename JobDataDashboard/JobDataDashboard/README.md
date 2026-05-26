# Job Data Dashboard

Simple React UI for browsing and editing records exposed by JobDataServer.

## Development

Set the API target and run Vite:

```powershell
$env:JOB_DATA_API_PROXY = "http://localhost:8000"
npm.cmd install
npm.cmd run dev
```

## Production

The Caddy container proxies `/jobs` and `/health` requests to `JOB_DATA_API_UPSTREAM`.
import { defineConfig, devices } from '@playwright/test'

// The deployed dashboard to check. CI passes the URL of the deploy that just went out; locally
// point it at `npm run preview` / docker compose with e.g. DASHBOARD_URL=http://localhost:8080.
const baseURL = (process.env.DASHBOARD_URL ?? 'https://projectycjobs.buildwithadi.dev').replace(/\/$/, '')

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // A freshly-swapped Railway deploy can drop the odd request while the old container drains.
  retries: process.env.CI ? 2 : 0,
  timeout: 60_000,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})

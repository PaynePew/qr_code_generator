import { defineConfig, devices } from '@playwright/test'

// E2E config for the session-cookie auth bypass (bead 8vd / n1q).
//
// In CI (CI=true) the workflow starts both servers before `npm run e2e`, so
// `webServer` is intentionally absent — we don't want Playwright to re-start
// them and race with the already-healthy processes.  In local dev the servers
// are assumed to be up (see frontend/e2e/README.md).
//
// Env knob: E2E_BASE_URL — frontend origin; default http://localhost:5173.
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: true,
  // Allow up to 2 retries in CI so transient flake doesn't block the required
  // check, but keep retries off locally so failures are visible immediately.
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    storageState: './e2e/.auth/state.json',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})

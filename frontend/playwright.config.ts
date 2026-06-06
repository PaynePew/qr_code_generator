import { defineConfig, devices } from '@playwright/test'

// E2E config for the session-cookie auth bypass (bead 8vd). First cut assumes
// the dev stack is already running (backend :8000, frontend :5173, Postgres on
// :5432); global-setup mints a session cookie so tests skip Google entirely. CI
// orchestration (server + browser provisioning in Actions) is a separate
// follow-up, deliberately out of this first slice.
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: true,
  use: {
    baseURL: 'http://localhost:5173',
    storageState: './e2e/.auth/state.json',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})

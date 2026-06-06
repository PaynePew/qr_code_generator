import { test, expect } from '@playwright/test'

// Proves the bypass: with the minted session cookie (loaded via storageState)
// the dashboard renders its AUTHENTICATED view — never the "請先登入" logged-out
// state — with no Google round-trip (bead 8vd). "顯示已刪除" renders only when
// isAuthenticated, so it is a clean auth gate to assert on.
test('injected session cookie lands on the authenticated dashboard', async ({ page }) => {
  await page.goto('/dashboard')

  // "顯示已刪除" renders only when isAuthenticated — a clean auth gate — and the
  // logged-out "請先登入" prompt must be absent. No Google round-trip involved.
  await expect(page.getByText('顯示已刪除')).toBeVisible()
  await expect(page.getByText('請先登入')).toHaveCount(0)
})

import { describe, it, expect } from 'vitest'
import { deriveEntry, type QueryState } from './derive'
import type { HistoryEntry } from './types'
import type { GetLinkResponse } from '@/api/qr'
import type { ApiError } from '@/api/client'

function row(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    token: 'abc1234',
    originalUrl: 'https://example.com',
    createdAt: '2026-05-09T10:00:00.000Z',
    dismissed: false,
    ...overrides,
  }
}

function linkData(overrides: Partial<GetLinkResponse> = {}): GetLinkResponse {
  return {
    token: 'abc1234',
    original_url: 'https://example.com',
    short_url: 'https://qr.example/r/abc1234',
    qr_code_url: 'https://qr.example/api/qr/abc1234/image',
    status: 'active',
    created_at: '2026-05-09T10:00:00.000Z',
    updated_at: '2026-05-09T10:00:00.000Z',
    expires_at: null,
    ...overrides,
  }
}

function err(status: number): ApiError {
  return {
    status,
    code: String(status),
    detail: 'fixture',
    isNetwork: false,
  }
}

const loading: QueryState = { state: 'loading' }

describe('deriveEntry — rule 1: API 404 → missing', () => {
  it('returns missing when API returned 404, dismissed=false', () => {
    const view = deriveEntry(row(), { state: 'error', error: err(404) })
    expect(view.status).toBe('missing')
    expect(view.isLoading).toBe(false)
    expect(view.link).toBeUndefined()
    expect(view.queryError?.status).toBe(404)
  })

  it('returns missing even when dismissed=true (404 wins over dismissed)', () => {
    const view = deriveEntry(row({ dismissed: true }), { state: 'error', error: err(404) })
    expect(view.status).toBe('missing')
  })
})

describe('deriveEntry — rule 2: API has data → server status wins', () => {
  it.each([
    ['active', false],
    ['active', true], // even with dismissed=true, server truth wins
    ['expired', false],
    ['deleted', false],
    ['deleted', true],
  ] as const)('status=%s, dismissed=%s → server status', (status, dismissed) => {
    const view = deriveEntry(
      row({ dismissed }),
      { state: 'success', data: linkData({ status }) },
    )
    expect(view.status).toBe(status)
    expect(view.isLoading).toBe(false)
    expect(view.link?.status).toBe(status)
    expect(view.queryError).toBeNull()
  })

  it('exposes the full link payload on entry.link', () => {
    const data = linkData({ original_url: 'https://server-side.com' })
    const view = deriveEntry(row(), { state: 'success', data })
    expect(view.link).toEqual(data)
  })
})

describe('deriveEntry — rule 3: loading + dismissed=true → deleted (synchronous fallback)', () => {
  it('returns deleted without isLoading flag', () => {
    const view = deriveEntry(row({ dismissed: true }), loading)
    expect(view.status).toBe('deleted')
    expect(view.isLoading).toBe(false)
    expect(view.link).toBeUndefined()
    expect(view.queryError).toBeNull()
  })
})

describe('deriveEntry — rule 4: loading + dismissed=false → loading state', () => {
  it('returns isLoading=true with placeholder status', () => {
    const view = deriveEntry(row({ dismissed: false }), loading)
    expect(view.isLoading).toBe(true)
    expect(view.link).toBeUndefined()
    expect(view.queryError).toBeNull()
  })
})

describe('deriveEntry — non-404 errors', () => {
  it('non-404 error + dismissed=false: surfaces queryError, no longer loading', () => {
    const view = deriveEntry(row(), { state: 'error', error: err(500) })
    expect(view.isLoading).toBe(false)
    expect(view.queryError?.status).toBe(500)
    expect(view.link).toBeUndefined()
  })

  it('non-404 error + dismissed=true: still falls back to deleted via dismissed', () => {
    const view = deriveEntry(row({ dismissed: true }), { state: 'error', error: err(500) })
    expect(view.status).toBe('deleted')
    expect(view.isLoading).toBe(false)
    expect(view.queryError?.status).toBe(500)
  })

  it('network error (status=0) is treated like other non-404 errors', () => {
    const view = deriveEntry(row(), {
      state: 'error',
      error: { status: 0, code: 'NETWORK_ERROR', detail: 'oops', isNetwork: true },
    })
    expect(view.queryError?.isNetwork).toBe(true)
    expect(view.isLoading).toBe(false)
  })
})

describe('deriveEntry — priority interactions documented in CONTEXT.md', () => {
  it('rule 1 beats rule 3 (404 + dismissed=true → missing, not deleted)', () => {
    const view = deriveEntry(row({ dismissed: true }), { state: 'error', error: err(404) })
    expect(view.status).toBe('missing')
  })

  it('rule 2 beats rule 3 (success(active) + dismissed=true → active)', () => {
    const view = deriveEntry(
      row({ dismissed: true }),
      { state: 'success', data: linkData({ status: 'active' }) },
    )
    expect(view.status).toBe('active')
  })

  it('rule 3 beats rule 4 (loading + dismissed=true → deleted, not loading)', () => {
    const view = deriveEntry(row({ dismissed: true }), loading)
    expect(view.status).toBe('deleted')
    expect(view.isLoading).toBe(false)
  })
})

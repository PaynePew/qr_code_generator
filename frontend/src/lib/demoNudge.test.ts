import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('sonner', () => ({
  toast: { info: vi.fn() },
}))

import { toast } from 'sonner'
import type { ApiError } from '@/api/client'
import { nudgeIfDemoReadOnly } from './demoNudge'

function apiError(status: number, code: string): ApiError {
  return { status, code, detail: '', isNetwork: false }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('nudgeIfDemoReadOnly', () => {
  it('shows a login nudge and reports handled for a DEMO_READ_ONLY 403', () => {
    const handled = nudgeIfDemoReadOnly(apiError(403, 'DEMO_READ_ONLY'))

    expect(handled).toBe(true)
    expect(toast.info).toHaveBeenCalledTimes(1)
  })

  it('does nothing and reports not-handled for a 422 validation error', () => {
    const handled = nudgeIfDemoReadOnly(apiError(422, '422'))

    expect(handled).toBe(false)
    expect(toast.info).not.toHaveBeenCalled()
  })

  it('does nothing for an owner 404 (non-demo) so its own handling runs', () => {
    const handled = nudgeIfDemoReadOnly(apiError(404, '404'))

    expect(handled).toBe(false)
    expect(toast.info).not.toHaveBeenCalled()
  })
})

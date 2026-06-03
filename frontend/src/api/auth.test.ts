import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('./client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}))

import type { ApiError } from './client'
import { apiClient } from './client'
import {
  startSession,
  endSession,
  enterDemo,
  getCurrentUser,
  isDemoReadOnly,
} from './auth'

beforeEach(() => {
  vi.clearAllMocks()
})

const mockUser = {
  id: 7,
  email: 'jane@example.com',
  name: 'Jane Doe',
  picture: 'https://example.com/jane.png',
  is_demo: false,
}

describe('startSession', () => {
  it('posts the Google credential to /api/auth/session', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: mockUser })

    await startSession('google-id-token')

    expect(apiClient.post).toHaveBeenCalledWith('/api/auth/session', {
      credential: 'google-id-token',
    })
  })

  it('returns the authenticated user', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: mockUser })

    const result = await startSession('google-id-token')

    expect(result).toEqual(mockUser)
  })

  it('propagates a rejection (e.g. 401 invalid credential)', async () => {
    const err = Object.assign(new Error('Unauthorized'), { status: 401 })
    vi.mocked(apiClient.post).mockRejectedValueOnce(err)

    await expect(startSession('bad')).rejects.toMatchObject({ status: 401 })
  })
})

describe('getCurrentUser', () => {
  it('sends GET /api/auth/me', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockUser })

    await getCurrentUser()

    expect(apiClient.get).toHaveBeenCalledWith('/api/auth/me')
  })

  it('returns the current user', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockUser })

    const result = await getCurrentUser()

    expect(result).toEqual(mockUser)
  })

  it('propagates a 401 when there is no valid session', async () => {
    const err = Object.assign(new Error('Unauthorized'), { status: 401 })
    vi.mocked(apiClient.get).mockRejectedValueOnce(err)

    await expect(getCurrentUser()).rejects.toMatchObject({ status: 401 })
  })
})

describe('endSession', () => {
  it('sends DELETE /api/auth/session', async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: { status: 'signed_out' } })

    await endSession()

    expect(apiClient.delete).toHaveBeenCalledWith('/api/auth/session')
  })

  it('resolves without a return value', async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: { status: 'signed_out' } })

    const result = await endSession()

    expect(result).toBeUndefined()
  })
})

describe('enterDemo', () => {
  it('posts to /api/auth/demo-session with no body (Try as guest)', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: { ...mockUser, is_demo: true } })

    await enterDemo()

    expect(apiClient.post).toHaveBeenCalledWith('/api/auth/demo-session')
  })

  it('returns the demo user', async () => {
    const demo = { ...mockUser, is_demo: true }
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: demo })

    await expect(enterDemo()).resolves.toEqual(demo)
  })
})

describe('isDemoReadOnly', () => {
  function apiError(status: number, code: string): ApiError {
    return { status, code, detail: '', isNetwork: false }
  }

  it('is true only for a 403 carrying the DEMO_READ_ONLY code', () => {
    expect(isDemoReadOnly(apiError(403, 'DEMO_READ_ONLY'))).toBe(true)
  })

  it('is false for a 403 with any other code (e.g. a generic forbidden)', () => {
    expect(isDemoReadOnly(apiError(403, '403'))).toBe(false)
  })

  it('is false for a non-403 status even with the code (owner 404, anon 401)', () => {
    expect(isDemoReadOnly(apiError(404, 'DEMO_READ_ONLY'))).toBe(false)
    expect(isDemoReadOnly(apiError(401, 'DEMO_READ_ONLY'))).toBe(false)
  })

  it('is false for null/undefined', () => {
    expect(isDemoReadOnly(null)).toBe(false)
    expect(isDemoReadOnly(undefined)).toBe(false)
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('./client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}))

import { apiClient } from './client'
import { startSession, endSession, getCurrentUser } from './auth'

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

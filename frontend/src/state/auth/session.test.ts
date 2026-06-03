import { describe, it, expect, vi } from 'vitest'
import type { ApiError } from '@/api/client'
import { fetchSessionUser } from './session'
import type { AuthUser } from '@/api/auth'

const user: AuthUser = {
  id: 1,
  email: 'a@b.com',
  name: 'A',
  picture: null,
  is_demo: false,
}

function apiError(status: number): ApiError {
  return { status, code: String(status), detail: '', isNetwork: false }
}

describe('fetchSessionUser', () => {
  it('returns the user when a session is active', async () => {
    const getUser = vi.fn().mockResolvedValue(user)

    await expect(fetchSessionUser(getUser)).resolves.toEqual(user)
  })

  it('resolves to null on 401 (no session is a normal logged-out state, not an error)', async () => {
    const getUser = vi.fn().mockRejectedValue(apiError(401))

    await expect(fetchSessionUser(getUser)).resolves.toBeNull()
  })

  it('rethrows non-401 errors so real failures still surface', async () => {
    const getUser = vi.fn().mockRejectedValue(apiError(500))

    await expect(fetchSessionUser(getUser)).rejects.toMatchObject({ status: 500 })
  })
})

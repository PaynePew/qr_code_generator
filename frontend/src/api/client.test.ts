import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { apiClient, normalizeError, type ApiError } from './client'

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('normalizeError', () => {
  it('normalizes a 4xx response into ApiError', async () => {
    server.use(
      http.get('http://localhost/api/test-404', () =>
        HttpResponse.json(
          { code: 'NOT_FOUND', detail: '找不到資源' },
          { status: 404 },
        ),
      ),
    )

    let caught: ApiError | null = null
    try {
      await apiClient.get('/test-404', {
        baseURL: 'http://localhost/api',
      })
    } catch (err) {
      caught = err as ApiError
    }

    expect(caught).not.toBeNull()
    expect(caught!.status).toBe(404)
    expect(caught!.code).toBe('NOT_FOUND')
    expect(caught!.detail).toBe('找不到資源')
    expect(caught!.isNetwork).toBe(false)
  })

  it('normalizes a 422 response with missing body fields', async () => {
    server.use(
      http.get('http://localhost/api/test-422', () =>
        HttpResponse.json({}, { status: 422 }),
      ),
    )

    let caught: ApiError | null = null
    try {
      await apiClient.get('/test-422', {
        baseURL: 'http://localhost/api',
      })
    } catch (err) {
      caught = err as ApiError
    }

    expect(caught!.status).toBe(422)
    expect(caught!.code).toBe('422')
    expect(caught!.isNetwork).toBe(false)
  })

  it('normalizes a 500 response into ApiError', async () => {
    server.use(
      http.get('http://localhost/api/test-500', () =>
        HttpResponse.json(
          { code: 'INTERNAL_ERROR', detail: '伺服器錯誤' },
          { status: 500 },
        ),
      ),
    )

    let caught: ApiError | null = null
    try {
      await apiClient.get('/test-500', {
        baseURL: 'http://localhost/api',
      })
    } catch (err) {
      caught = err as ApiError
    }

    expect(caught!.status).toBe(500)
    expect(caught!.code).toBe('INTERNAL_ERROR')
    expect(caught!.detail).toBe('伺服器錯誤')
    expect(caught!.isNetwork).toBe(false)
  })

  it('resolves successfully on 2xx responses', async () => {
    server.use(
      http.get('http://localhost/api/test-200', () =>
        HttpResponse.json({ token: 'abc1234' }, { status: 200 }),
      ),
    )

    const response = await apiClient.get('/test-200', {
      baseURL: 'http://localhost/api',
    })
    expect(response.status).toBe(200)
    expect(response.data.token).toBe('abc1234')
  })
})

describe('normalizeError (unit)', () => {
  it('produces isNetwork:true when no response is present', () => {
    const err = normalizeError(
      Object.assign(new Error('Network Error'), {
        isAxiosError: true,
        response: undefined,
        message: 'Network Error',
      }),
    )
    expect(err.isNetwork).toBe(true)
    expect(err.status).toBe(0)
    expect(err.code).toBe('NETWORK_ERROR')
  })

  it('handles non-Axios errors gracefully', () => {
    const err = normalizeError(new Error('something broke'))
    expect(err.isNetwork).toBe(false)
    expect(err.status).toBe(0)
    expect(err.code).toBe('UNKNOWN_ERROR')
  })
})

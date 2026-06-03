/**
 * @vitest-environment jsdom
 *
 * Tests for useCustomization (ADR 0011): React Query-backed customization
 * fetch + save for a single Link token. A 404 from getCustomization means
 * "not customized yet" and is NOT treated as an error.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import { useCustomization } from './useCustomization'

vi.mock('@/api/qr', () => ({
  getCustomization: vi.fn(),
  saveCustomization: vi.fn(),
}))

import { getCustomization, saveCustomization } from '@/api/qr'

const getCustomizationMock = vi.mocked(getCustomization)
const saveCustomizationMock = vi.mocked(saveCustomization)

const MOCK_CUSTOMIZATION = {
  token: 'tok1234',
  style: {
    foreground: '#ff0000',
    background: '#ffffff',
    size: 320,
    dotType: 'square',
    ecl: 'M',
  },
  image_url: 'https://storage.example.com/qr/tok1234/composite_abc.png',
  logo_url: null,
  updated_at: '2026-06-01T00:00:00',
}

function makeWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useCustomization — fetch', () => {
  it('returns isLoading true while the query is in flight', () => {
    getCustomizationMock.mockReturnValue(new Promise(() => {}))
    const qc = makeQueryClient()
    const { result } = renderHook(() => useCustomization('tok1234'), {
      wrapper: makeWrapper(qc),
    })
    expect(result.current.isLoading).toBe(true)
    expect(result.current.customization).toBeUndefined()
  })

  it('returns the customization when it exists', async () => {
    getCustomizationMock.mockResolvedValue(MOCK_CUSTOMIZATION)
    const qc = makeQueryClient()
    const { result } = renderHook(() => useCustomization('tok1234'), {
      wrapper: makeWrapper(qc),
    })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.customization).toEqual(MOCK_CUSTOMIZATION)
    expect(result.current.fetchError).toBeNull()
  })

  it('treats 404 as "no customization" — customization is undefined, fetchError is null', async () => {
    getCustomizationMock.mockRejectedValue({ status: 404, code: 'NOT_FOUND', detail: '', isNetwork: false })
    const qc = makeQueryClient()
    const { result } = renderHook(() => useCustomization('tok1234'), {
      wrapper: makeWrapper(qc),
    })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.customization).toBeUndefined()
    expect(result.current.fetchError).toBeNull()
  })

  it('surfaces fetchError for non-404 failures', async () => {
    const serverErr = { status: 500, code: '500', detail: 'Internal error', isNetwork: false }
    getCustomizationMock.mockRejectedValue(serverErr)
    const qc = makeQueryClient()
    const { result } = renderHook(() => useCustomization('tok1234'), {
      wrapper: makeWrapper(qc),
    })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.fetchError).toMatchObject({ status: 500 })
    expect(result.current.customization).toBeUndefined()
  })
})

describe('useCustomization — save', () => {
  it('calls saveCustomization with the token + provided args', async () => {
    getCustomizationMock.mockRejectedValue({ status: 404, code: 'NOT_FOUND', detail: '', isNetwork: false })
    saveCustomizationMock.mockResolvedValue({
      token: 'tok1234',
      image_key: 'qr/tok1234/composite_new.png',
      logo_key: null,
      updated_at: '2026-06-01T00:01:00',
    })
    const qc = makeQueryClient()
    const { result } = renderHook(() => useCustomization('tok1234'), {
      wrapper: makeWrapper(qc),
    })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const style = { foreground: '#ff0000', background: '#ffffff', size: 320, dotType: 'square', ecl: 'M' }
    const image = new Blob(['fake-png'], { type: 'image/png' })

    await act(async () => {
      await result.current.save({ style, image })
    })

    expect(saveCustomizationMock).toHaveBeenCalledWith({
      token: 'tok1234',
      style,
      image,
    })
  })

  it('invalidates the customization cache on success so the next render re-fetches', async () => {
    getCustomizationMock.mockResolvedValue(MOCK_CUSTOMIZATION)
    saveCustomizationMock.mockResolvedValue({
      token: 'tok1234',
      image_key: 'qr/tok1234/composite_new.png',
      logo_key: null,
      updated_at: '2026-06-01T00:01:00',
    })
    const updatedCustomization = { ...MOCK_CUSTOMIZATION, style: { ...MOCK_CUSTOMIZATION.style, foreground: '#0000ff' } }
    getCustomizationMock
      .mockResolvedValueOnce(MOCK_CUSTOMIZATION)
      .mockResolvedValueOnce(updatedCustomization)

    const qc = makeQueryClient()
    const { result } = renderHook(() => useCustomization('tok1234'), {
      wrapper: makeWrapper(qc),
    })

    await waitFor(() => expect(result.current.customization).toEqual(MOCK_CUSTOMIZATION))

    await act(async () => {
      await result.current.save({
        style: { foreground: '#0000ff', background: '#ffffff', size: 320, dotType: 'square', ecl: 'M' },
        image: new Blob(['fake-png'], { type: 'image/png' }),
      })
    })

    await waitFor(() =>
      expect(result.current.customization?.style.foreground).toBe('#0000ff'),
    )
  })

  it('exposes saveError when the upload fails', async () => {
    getCustomizationMock.mockRejectedValue({ status: 404, code: 'NOT_FOUND', detail: '', isNetwork: false })
    const uploadErr = { status: 422, code: 'INVALID_IMAGE', detail: 'not an image', isNetwork: false }
    saveCustomizationMock.mockRejectedValue(uploadErr)

    const qc = makeQueryClient()
    const { result } = renderHook(() => useCustomization('tok1234'), {
      wrapper: makeWrapper(qc),
    })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.save({
        style: { foreground: '#ff0000', background: '#ffffff', size: 320, dotType: 'square', ecl: 'M' },
        image: new Blob(['not-an-image']),
      }).catch(() => {})
    })

    await waitFor(() => expect(result.current.saveError).not.toBeNull())
    expect(result.current.saveError).toMatchObject({ code: 'INVALID_IMAGE' })
  })
})

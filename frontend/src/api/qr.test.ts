import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('./client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    put: vi.fn(),
  },
}))

import { apiClient } from './client'
import { getLink, patchLink, deleteLink, getAnalytics, listLinks, getCustomization, saveCustomization } from './qr'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('getLink', () => {
  const mockLink = {
    token: 'abc1234',
    original_url: 'https://example.com',
    short_url: 'https://s.example.com/r/abc1234',
    qr_code_url: '',
    label: null,
    status: 'active' as const,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    expires_at: null,
  }

  it('sends GET /qr/{token}', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockLink })

    await getLink('abc1234')

    expect(apiClient.get).toHaveBeenCalledWith('/api/qr/abc1234')
  })

  it('returns the full link response', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockLink })

    const result = await getLink('abc1234')

    expect(result).toEqual(mockLink)
  })

  it('propagates rejection from the client (e.g. 404)', async () => {
    const err = Object.assign(new Error('Not Found'), { status: 404 })
    vi.mocked(apiClient.get).mockRejectedValueOnce(err)

    await expect(getLink('missing')).rejects.toMatchObject({ status: 404 })
  })
})

describe('patchLink', () => {
  it('sends PATCH /qr/{token} with original_url body', async () => {
    const mockData = {
      token: 'abc1234',
      original_url: 'https://new.example.com',
      short_url: 'https://s.example.com/r/abc1234',
      qr_code_url: '',
      label: null,
      status: 'active',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
      expires_at: null,
    }
    vi.mocked(apiClient.patch).mockResolvedValueOnce({ data: mockData })

    const result = await patchLink('abc1234', { original_url: 'https://new.example.com' })

    expect(apiClient.patch).toHaveBeenCalledWith('/api/qr/abc1234', {
      original_url: 'https://new.example.com',
    })
    expect(result.original_url).toBe('https://new.example.com')
    expect(result.token).toBe('abc1234')
  })

  it('sends PATCH /qr/{token} with expires_at body', async () => {
    const expires = '2026-12-31T00:00:00Z'
    const mockData = {
      token: 'abc1234',
      original_url: 'https://example.com',
      short_url: '',
      qr_code_url: '',
      label: null,
      status: 'active',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
      expires_at: expires,
    }
    vi.mocked(apiClient.patch).mockResolvedValueOnce({ data: mockData })

    const result = await patchLink('abc1234', { expires_at: expires })

    expect(apiClient.patch).toHaveBeenCalledWith('/api/qr/abc1234', { expires_at: expires })
    expect(result.expires_at).toBe(expires)
  })

  it('returns the updated link response', async () => {
    const mockData = {
      token: 'xyz9999',
      original_url: 'https://updated.example.com',
      short_url: 'https://s.example.com/r/xyz9999',
      qr_code_url: '',
      label: null,
      status: 'active',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-02-01T00:00:00Z',
      expires_at: null,
    }
    vi.mocked(apiClient.patch).mockResolvedValueOnce({ data: mockData })

    const result = await patchLink('xyz9999', { original_url: 'https://updated.example.com' })

    expect(result).toEqual(mockData)
  })

  it('sends PATCH /qr/{token} with label body', async () => {
    const mockData = {
      token: 'abc1234',
      original_url: 'https://example.com',
      short_url: '',
      qr_code_url: '',
      label: 'Lobby poster',
      status: 'active',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
      expires_at: null,
    }
    vi.mocked(apiClient.patch).mockResolvedValueOnce({ data: mockData })

    const result = await patchLink('abc1234', { label: 'Lobby poster' })

    expect(apiClient.patch).toHaveBeenCalledWith('/api/qr/abc1234', { label: 'Lobby poster' })
    expect(result.label).toBe('Lobby poster')
  })

  it('sends PATCH /qr/{token} with label: null to clear a label', async () => {
    const mockData = {
      token: 'abc1234',
      original_url: 'https://example.com',
      short_url: '',
      qr_code_url: '',
      label: null,
      status: 'active',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
      expires_at: null,
    }
    vi.mocked(apiClient.patch).mockResolvedValueOnce({ data: mockData })

    const result = await patchLink('abc1234', { label: null })

    expect(apiClient.patch).toHaveBeenCalledWith('/api/qr/abc1234', { label: null })
    expect(result.label).toBeNull()
  })
})

describe('deleteLink', () => {
  it('sends DELETE /qr/{token}', async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: null })

    await deleteLink('abc1234')

    expect(apiClient.delete).toHaveBeenCalledWith('/api/qr/abc1234')
  })

  it('resolves without a return value', async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: null })

    const result = await deleteLink('abc1234')

    expect(result).toBeUndefined()
  })
})

describe('listLinks', () => {
  const mockList = {
    items: [
      {
        token: 'abc1234',
        original_url: 'https://example.com',
        short_url: 'https://s.example.com/r/abc1234',
        label: 'Lobby poster',
        status: 'active' as const,
        scan_count: 7,
        created_at: '2026-01-02T00:00:00Z',
        expires_at: null,
      },
    ],
    next_cursor: null,
  }

  it('sends GET /api/qr without a deleted param by default', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockList })

    await listLinks()

    expect(apiClient.get).toHaveBeenCalledWith('/api/qr', { params: undefined })
  })

  it('sends ?deleted=true when requesting the trash filter', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockList })

    await listLinks(true)

    expect(apiClient.get).toHaveBeenCalledWith('/api/qr', { params: { deleted: true } })
  })

  it('returns the items + next_cursor envelope', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockList })

    const result = await listLinks()

    expect(result.items).toHaveLength(1)
    expect(result.items[0].scan_count).toBe(7)
    expect(result.next_cursor).toBeNull()
  })

  it('returns label in each list item', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockList })

    const result = await listLinks()

    expect(result.items[0].label).toBe('Lobby poster')
  })
})

describe('getAnalytics', () => {
  const mockAnalytics = {
    token: 'abc1234',
    timezone: 'UTC',
    total_scans: 42,
    scans_by_day: [
      { date: '2026-05-01', count: 10, status_codes: { '302': 9, '410': 1 } },
      { date: '2026-05-02', count: 5, status_codes: { '302': 5, '410': 0 } },
    ],
    recent_scans: [
      {
        scanned_at: '2026-05-02T12:00:00Z',
        status_code: 302,
        user_agent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
      },
    ],
  }

  it('sends GET /qr/{token}/analytics', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockAnalytics })

    await getAnalytics('abc1234')

    expect(apiClient.get).toHaveBeenCalledWith('/api/qr/abc1234/analytics')
  })

  it('returns the analytics response', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockAnalytics })

    const result = await getAnalytics('abc1234')

    expect(result.token).toBe('abc1234')
    expect(result.total_scans).toBe(42)
    expect(result.scans_by_day).toHaveLength(2)
    expect(result.recent_scans).toHaveLength(1)
  })

  it('returns recent scan with status_code and user_agent', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockAnalytics })

    const result = await getAnalytics('abc1234')
    const scan = result.recent_scans[0]

    expect(scan.status_code).toBe(302)
    expect(scan.user_agent).toBe('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')
  })
})

describe('getCustomization', () => {
  const mockCustomization = {
    token: 'abc1234',
    style: {
      foreground: '#ff0000',
      background: '#ffffff',
      size: 320,
      dotType: 'square',
      ecl: 'M',
    },
    image_url: 'https://storage.example.com/qr/abc1234/composite_abc.png',
    logo_url: null,
    updated_at: '2026-06-01T00:00:00',
  }

  it('sends GET /qr/{token}/customization', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockCustomization })

    await getCustomization('abc1234')

    expect(apiClient.get).toHaveBeenCalledWith('/api/qr/abc1234/customization')
  })

  it('returns the full customization response', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: mockCustomization })

    const result = await getCustomization('abc1234')

    expect(result.token).toBe('abc1234')
    expect(result.style.foreground).toBe('#ff0000')
    expect(result.logo_url).toBeNull()
  })

  it('propagates rejection (e.g. 404 when no customization exists)', async () => {
    const err = Object.assign(new Error('Not Found'), { status: 404 })
    vi.mocked(apiClient.get).mockRejectedValueOnce(err)

    await expect(getCustomization('abc1234')).rejects.toMatchObject({ status: 404 })
  })
})

describe('saveCustomization', () => {
  const mockResponse = {
    token: 'abc1234',
    image_key: 'qr/abc1234/composite_uuid.png',
    logo_key: null,
    updated_at: '2026-06-01T00:00:00',
  }

  it('sends PUT /qr/{token}/customization as multipart, letting axios derive the boundary', async () => {
    vi.mocked(apiClient.put).mockResolvedValueOnce({ data: mockResponse })

    await saveCustomization({
      token: 'abc1234',
      style: { foreground: '#ff0000', background: '#ffffff', size: 320, dotType: 'square', ecl: 'M' },
      image: new Blob(['fake-png'], { type: 'image/png' }),
    })

    // Content-Type must be undefined so axios generates `multipart/form-data;
    // boundary=…` from the FormData. Forcing 'multipart/form-data' drops the
    // boundary and the server cannot parse the parts (regression: 422).
    expect(apiClient.put).toHaveBeenCalledWith(
      '/api/qr/abc1234/customization',
      expect.any(FormData),
      { headers: { 'Content-Type': undefined } },
    )
  })

  it('returns the save response', async () => {
    vi.mocked(apiClient.put).mockResolvedValueOnce({ data: mockResponse })

    const result = await saveCustomization({
      token: 'abc1234',
      style: { foreground: '#ff0000', background: '#ffffff', size: 320, dotType: 'square', ecl: 'M' },
      image: new Blob(['fake-png'], { type: 'image/png' }),
    })

    expect(result.token).toBe('abc1234')
    expect(result.image_key).toBe('qr/abc1234/composite_uuid.png')
    expect(result.logo_key).toBeNull()
  })

  it('includes logo in form when provided', async () => {
    vi.mocked(apiClient.put).mockResolvedValueOnce({ data: { ...mockResponse, logo_key: 'qr/abc1234/logo_uuid.png' } })

    const logo = new Blob(['fake-logo'], { type: 'image/png' })
    await saveCustomization({
      token: 'abc1234',
      style: { foreground: '#ff0000', background: '#ffffff', size: 320, dotType: 'square', ecl: 'M' },
      image: new Blob(['fake-png'], { type: 'image/png' }),
      logo,
    })

    const call = vi.mocked(apiClient.put).mock.calls[0]
    const formData = call[1] as FormData
    expect(formData.get('logo')).not.toBeNull()
  })

  it('propagates rejection (e.g. INVALID_IMAGE)', async () => {
    const err = Object.assign(new Error('Unprocessable'), {
      status: 422,
      code: 'INVALID_IMAGE',
    })
    vi.mocked(apiClient.put).mockRejectedValueOnce(err)

    await expect(
      saveCustomization({
        token: 'abc1234',
        style: { foreground: '#ff0000', background: '#ffffff', size: 320, dotType: 'square', ecl: 'M' },
        image: new Blob(['not-an-image']),
      }),
    ).rejects.toMatchObject({ code: 'INVALID_IMAGE' })
  })
})

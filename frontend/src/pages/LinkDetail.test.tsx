/**
 * @vitest-environment jsdom
 *
 * Tests for LinkDetail QR view (bead 65g): the QR display must be an <img>
 * pointing at the authoritative image endpoint, not a client-rendered canvas.
 * The Download button must fetch from the image endpoint.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createElement } from 'react'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------
vi.mock('react-router-dom', () => ({
  useParams: () => ({ token: 'tok1234' }),
  useNavigate: () => vi.fn(),
  Link: ({ children }: { children: React.ReactNode }) => children,
}))

vi.mock('@tanstack/react-query', () => ({
  // Keep loading=true so AnalyticsSection renders a spinner and never calls buildChartData.
  useQuery: vi.fn().mockReturnValue({ isLoading: true, isError: false, data: undefined }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: vi.fn().mockReturnValue({ mutateAsync: vi.fn(), isPending: false, error: null }),
}))

vi.mock('@/state/linkEntry', () => ({
  useLinkEntry: vi.fn(),
}))

vi.mock('@/state/useCustomization', () => ({
  useCustomization: vi.fn(),
}))

vi.mock('@/qr/renderer', () => ({
  create: vi.fn(() => ({
    update: vi.fn(),
    attachTo: vi.fn(),
    toBlob: vi.fn(),
    destroy: vi.fn(),
  })),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/demoNudge', () => ({
  nudgeIfDemoReadOnly: () => false,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) =>
    createElement('button', props, children),
}))

vi.mock('@/components/ui/CopyButton', () => ({
  CopyButton: () => createElement('button', null, 'copy'),
}))

vi.mock('@/components/ui/StatusBadge', () => ({
  StatusBadge: ({ status }: { status: string }) => createElement('span', null, status),
}))

vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => createElement('div', null, children),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => createElement('div', null, children),
  Legend: () => null,
}))

vi.mock('date-fns', () => ({
  format: () => '2026-01-01',
  subDays: (d: Date) => d,
  parseISO: (s: string) => new Date(s),
}))

vi.mock('@/api/qr', () => ({
  getAnalytics: vi.fn(),
  getQrImageUrl: vi.fn((token: string, updatedAt?: string) => {
    const base = `/api/qr/${token}/image`
    return updatedAt ? `${base}?v=${encodeURIComponent(updatedAt)}` : base
  }),
}))

import { useLinkEntry } from '@/state/linkEntry'
import { useCustomization } from '@/state/useCustomization'

const useLinkEntryMock = vi.mocked(useLinkEntry)
const useCustomizationMock = vi.mocked(useCustomization)

const MOCK_LINK = {
  token: 'tok1234',
  original_url: 'https://example.com/page',
  short_url: 'https://s.example.com/r/tok1234',
  qr_code_url: '',
  label: 'Newsletter',
  status: 'active' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  expires_at: null,
}

const MOCK_CUSTOMIZATION = {
  token: 'tok1234',
  style: { foreground: '#ff0000', background: '#ffffff', size: 320, dotType: 'square', ecl: 'M' },
  image_url: '/api/qr/tok1234/image',
  logo_url: null,
  updated_at: '2026-06-01T10:00:00Z',
}

function makeLinkEntryStub(overrides = {}) {
  return {
    token: 'tok1234',
    link: MOCK_LINK,
    status: 'active' as const,
    isLoading: false,
    queryError: null,
    updateUrl: Object.assign(vi.fn(), { isPending: false, error: null }),
    updateExpiry: Object.assign(vi.fn(), { isPending: false, error: null }),
    updateLabel: Object.assign(vi.fn(), { isPending: false, error: null }),
    markDeleted: Object.assign(vi.fn(), { isPending: false, error: null }),
    ...overrides,
  }
}

function makeCustomizationStub(overrides = {}) {
  return {
    customization: MOCK_CUSTOMIZATION,
    isLoading: false,
    fetchError: null,
    save: vi.fn(),
    isSaving: false,
    saveError: null,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  useLinkEntryMock.mockReturnValue(makeLinkEntryStub() as ReturnType<typeof useLinkEntry>)
  useCustomizationMock.mockReturnValue(makeCustomizationStub() as ReturnType<typeof useCustomization>)
})

import { LinkDetail } from './LinkDetail'

describe('LinkDetail — QR view is an <img> (bead 65g)', () => {
  it('renders an <img> for the QR code that points at the image endpoint', () => {
    render(createElement(LinkDetail))

    const img = screen.getByAltText(/QR 碼/)
    expect(img).toBeTruthy()
    const src = (img as HTMLImageElement).src
    expect(src).toContain('/api/qr/tok1234/image')
  })

  it('cache-busts the image src with updated_at from the customization', () => {
    render(createElement(LinkDetail))

    const img = screen.getByAltText(/QR 碼/)
    const src = (img as HTMLImageElement).src
    // Should include the updated_at timestamp as a cache-bust param
    expect(src).toContain('2026-06-01')
  })

  it('falls back to the plain image endpoint when no customization is loaded', () => {
    useCustomizationMock.mockReturnValue(
      makeCustomizationStub({ customization: undefined }) as ReturnType<typeof useCustomization>,
    )
    render(createElement(LinkDetail))

    const img = screen.getByAltText(/QR 碼/)
    const src = (img as HTMLImageElement).src
    expect(src).toContain('/api/qr/tok1234/image')
  })

  it('does NOT render a canvas for the QR view', () => {
    const { container } = render(createElement(LinkDetail))

    // The view should not include a canvas element (client canvas only in Generator)
    expect(container.querySelector('canvas')).toBeNull()
  })

  it('does NOT render a "儲存自訂樣式" button (view-only; edit flow is Phase 7)', () => {
    render(createElement(LinkDetail))

    expect(screen.queryByText(/儲存自訂樣式/)).toBeNull()
  })
})

describe('LinkDetail — download (bead 65g)', () => {
  it('renders a Download button', () => {
    render(createElement(LinkDetail))

    expect(screen.getByRole('button', { name: /下載/ })).toBeTruthy()
  })
})

describe('LinkDetail — label display and edit (issue nk4)', () => {
  it('shows the label as the page heading when a label is set', () => {
    render(createElement(LinkDetail))

    const headings = screen.getAllByRole('heading', { level: 1 })
    expect(headings.some((h) => h.textContent?.includes('Newsletter'))).toBe(true)
  })

  it('shows the token alongside the label heading', () => {
    render(createElement(LinkDetail))

    // Token must still be visible (secondary) when a label is shown
    expect(screen.getByText('tok1234')).toBeTruthy()
  })

  it('shows the label in the link info section', () => {
    render(createElement(LinkDetail))

    // The label field heading must be present
    expect(screen.getByText('標籤')).toBeTruthy()
    // The mock label value appears at least once (heading + info section)
    expect(screen.getAllByText('Newsletter').length).toBeGreaterThanOrEqual(1)
  })

  it('shows "（未設定）" when label is null', () => {
    useLinkEntryMock.mockReturnValue(
      makeLinkEntryStub({
        link: { ...MOCK_LINK, label: null },
      }) as ReturnType<typeof useLinkEntry>,
    )
    render(createElement(LinkDetail))

    expect(screen.getByText('（未設定）')).toBeTruthy()
  })

  it('renders an edit button for the label field on an active link', () => {
    render(createElement(LinkDetail))

    // There should be an "編輯" button within the label section.
    // The page has multiple "編輯" buttons (URL, expiry, label), just assert at least one exists.
    const editBtns = screen.getAllByRole('button', { name: /編輯/ })
    expect(editBtns.length).toBeGreaterThanOrEqual(1)
  })

  it('does NOT render a label edit button for a deleted link', () => {
    useLinkEntryMock.mockReturnValue(
      makeLinkEntryStub({
        status: 'deleted',
        link: { ...MOCK_LINK, status: 'deleted' },
      }) as ReturnType<typeof useLinkEntry>,
    )
    render(createElement(LinkDetail))

    // No edit buttons at all on a deleted link
    expect(screen.queryAllByRole('button', { name: /編輯/ })).toHaveLength(0)
  })
})

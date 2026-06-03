import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  loadGoogleScript,
  GOOGLE_GSI_SRC,
  isOneTapDismissed,
  type GoogleNotification,
} from './googleIdentity'

describe('isOneTapDismissed', () => {
  it('is true when the prompt was not displayed (browser/policy skipped it)', () => {
    const note: GoogleNotification = {
      isNotDisplayed: () => true,
      isSkippedMoment: () => false,
      isDismissedMoment: () => false,
    }
    expect(isOneTapDismissed(note)).toBe(true)
  })

  it('is true when the prompt was skipped', () => {
    const note: GoogleNotification = {
      isNotDisplayed: () => false,
      isSkippedMoment: () => true,
      isDismissedMoment: () => false,
    }
    expect(isOneTapDismissed(note)).toBe(true)
  })

  it('is false while One Tap is actually showing', () => {
    const note: GoogleNotification = {
      isNotDisplayed: () => false,
      isSkippedMoment: () => false,
      isDismissedMoment: () => false,
    }
    expect(isOneTapDismissed(note)).toBe(false)
  })

  it('treats a user-dismissed moment as dismissed (show the fallback)', () => {
    const note: GoogleNotification = {
      isNotDisplayed: () => false,
      isSkippedMoment: () => false,
      isDismissedMoment: () => true,
    }
    expect(isOneTapDismissed(note)).toBe(true)
  })
})

describe('loadGoogleScript', () => {
  let appended: FakeScript[]

  class FakeScript {
    src = ''
    async = false
    defer = false
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
  }

  function fakeDocument(existing: FakeScript | null) {
    return {
      querySelector: vi.fn((sel: string) =>
        existing && sel.includes(GOOGLE_GSI_SRC) ? existing : null,
      ),
      createElement: vi.fn(() => {
        const s = new FakeScript()
        return s as unknown as HTMLScriptElement
      }),
      head: {
        appendChild: vi.fn((s: FakeScript) => {
          appended.push(s)
        }),
      },
    } as unknown as Document
  }

  beforeEach(() => {
    appended = []
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('appends the GSI client script and resolves once it loads', async () => {
    const doc = fakeDocument(null)
    const promise = loadGoogleScript(doc)

    expect(appended).toHaveLength(1)
    expect(appended[0].src).toBe(GOOGLE_GSI_SRC)
    expect(appended[0].async).toBe(true)

    appended[0].onload?.()
    await expect(promise).resolves.toBeUndefined()
  })

  it('does not append a second tag when the script is already present', async () => {
    const existing = new FakeScript()
    existing.src = GOOGLE_GSI_SRC
    const doc = fakeDocument(existing)

    await loadGoogleScript(doc)

    expect(appended).toHaveLength(0)
  })

  it('rejects when the script fails to load', async () => {
    const doc = fakeDocument(null)
    const promise = loadGoogleScript(doc)

    appended[0].onerror?.()

    await expect(promise).rejects.toThrow(/Google Identity/i)
  })
})

import { describe, it, expect } from 'vitest'
import { linkKey, linkListKey, analyticsKey, currentUserKey, customizationKey } from './queryKeys'

describe('linkKey', () => {
  it('returns a tuple with the link namespace and token', () => {
    expect(linkKey('abc123')).toEqual(['link', 'abc123'])
  })

  it('produces distinct keys for distinct tokens', () => {
    expect(linkKey('tok1')).not.toEqual(linkKey('tok2'))
  })
})

describe('linkListKey', () => {
  it('returns the links namespace tagged with the deleted filter', () => {
    expect(linkListKey(false)).toEqual(['links', { deleted: false }])
    expect(linkListKey(true)).toEqual(['links', { deleted: true }])
  })

  it('distinguishes the active list from the trash list', () => {
    expect(linkListKey(false)).not.toEqual(linkListKey(true))
  })
})

describe('analyticsKey', () => {
  it('returns a tuple with the analytics namespace and token', () => {
    expect(analyticsKey('abc123')).toEqual(['analytics', 'abc123'])
  })

  it('is distinct from the link key for the same token', () => {
    expect(analyticsKey('abc123')).not.toEqual(linkKey('abc123'))
  })
})

describe('currentUserKey', () => {
  it('returns the auth/me namespace tuple', () => {
    expect(currentUserKey()).toEqual(['auth', 'me'])
  })
})

describe('customizationKey', () => {
  it('returns a tuple with the customization namespace and token', () => {
    expect(customizationKey('abc123')).toEqual(['customization', 'abc123'])
  })

  it('is distinct from the link key for the same token', () => {
    expect(customizationKey('abc123')).not.toEqual(linkKey('abc123'))
  })

  it('produces distinct keys for distinct tokens', () => {
    expect(customizationKey('tok1')).not.toEqual(customizationKey('tok2'))
  })
})

import { describe, it, expect } from 'vitest'
import { linkKey, analyticsKey } from './queryKeys'

describe('linkKey', () => {
  it('returns a tuple with the link namespace and token', () => {
    expect(linkKey('abc123')).toEqual(['link', 'abc123'])
  })

  it('produces distinct keys for distinct tokens', () => {
    expect(linkKey('tok1')).not.toEqual(linkKey('tok2'))
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

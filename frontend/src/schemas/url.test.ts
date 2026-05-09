import { describe, it, expect } from 'vitest'
import { urlSchema } from './url'

describe('urlSchema', () => {
  describe('valid URLs', () => {
    it('accepts http URL', () => {
      expect(urlSchema.safeParse('http://example.com').success).toBe(true)
    })

    it('accepts https URL', () => {
      expect(urlSchema.safeParse('https://example.com').success).toBe(true)
    })

    it('accepts https URL with path and query', () => {
      expect(urlSchema.safeParse('https://example.com/path?foo=bar').success).toBe(true)
    })

    it('accepts https URL at exactly 2048 chars', () => {
      const base = 'https://example.com/'
      const url = base + 'a'.repeat(2048 - base.length)
      expect(url.length).toBe(2048)
      expect(urlSchema.safeParse(url).success).toBe(true)
    })

    it('accepts https URL at 2047 chars', () => {
      const base = 'https://example.com/'
      const url = base + 'a'.repeat(2047 - base.length)
      expect(url.length).toBe(2047)
      expect(urlSchema.safeParse(url).success).toBe(true)
    })
  })

  describe('invalid scheme', () => {
    it('rejects ftp:// scheme', () => {
      const result = urlSchema.safeParse('ftp://example.com')
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0].message).toMatch(/http/)
      }
    })

    it('rejects javascript: scheme', () => {
      const result = urlSchema.safeParse('javascript:alert(1)')
      expect(result.success).toBe(false)
    })

    it('rejects bare domain without scheme', () => {
      const result = urlSchema.safeParse('example.com')
      expect(result.success).toBe(false)
    })

    it('rejects empty string', () => {
      const result = urlSchema.safeParse('')
      expect(result.success).toBe(false)
    })
  })

  describe('length cap', () => {
    it('rejects URL over 2048 chars (2049)', () => {
      const base = 'https://example.com/'
      const url = base + 'a'.repeat(2049 - base.length)
      expect(url.length).toBe(2049)
      const result = urlSchema.safeParse(url)
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0].message).toMatch(/2048/)
      }
    })
  })

  describe('malformed input', () => {
    it('rejects URL with spaces', () => {
      expect(urlSchema.safeParse('https://exa mple.com').success).toBe(false)
    })

    it('rejects plain text', () => {
      expect(urlSchema.safeParse('not a url').success).toBe(false)
    })

    it('rejects http:// with no host', () => {
      expect(urlSchema.safeParse('http://').success).toBe(false)
    })
  })
})

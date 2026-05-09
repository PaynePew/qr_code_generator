import { describe, it, expect, beforeEach } from 'vitest'
import { addToken, listTokens, markDeleted, removeFromHistory, type HistoryEntry } from './linkHistory'

class FakeStorage implements Storage {
  private store = new Map<string, string>()
  get length() { return this.store.size }
  key(index: number) { return [...this.store.keys()][index] ?? null }
  getItem(key: string) { return this.store.get(key) ?? null }
  setItem(key: string, value: string) { this.store.set(key, value) }
  removeItem(key: string) { this.store.delete(key) }
  clear() { this.store.clear() }
}

class QuotaStorage extends FakeStorage {
  setItem(_key: string, _value: string): void {
    const err = new Error('QuotaExceededError')
    err.name = 'QuotaExceededError'
    throw err
  }
}

function makeEntry(overrides: Partial<HistoryEntry> = {}): Omit<HistoryEntry, 'dismissed'> {
  return {
    token: 'abc123',
    originalUrl: 'https://example.com',
    createdAt: '2026-05-09T10:00:00.000Z',
    ...overrides,
  }
}

describe('linkHistory', () => {
  let storage: FakeStorage

  beforeEach(() => {
    storage = new FakeStorage()
  })

  describe('addToken / listTokens round-trip', () => {
    it('stores an entry and retrieves it', () => {
      addToken(makeEntry(), storage)
      const result = listTokens(storage)
      expect(result).toHaveLength(1)
      expect(result[0].token).toBe('abc123')
      expect(result[0].originalUrl).toBe('https://example.com')
      expect(result[0].dismissed).toBe(false)
    })

    it('stores multiple entries', () => {
      addToken({ token: 'tok1', originalUrl: 'https://a.com', createdAt: '2026-05-09T10:00:00.000Z' }, storage)
      addToken({ token: 'tok2', originalUrl: 'https://b.com', createdAt: '2026-05-09T11:00:00.000Z' }, storage)
      expect(listTokens(storage)).toHaveLength(2)
    })
  })

  describe('idempotent add', () => {
    it('does not insert a duplicate if called twice with the same token', () => {
      addToken(makeEntry(), storage)
      addToken(makeEntry(), storage)
      expect(listTokens(storage)).toHaveLength(1)
    })

    it('ignores the second call even with different fields', () => {
      addToken(makeEntry(), storage)
      addToken({ token: 'abc123', originalUrl: 'https://other.com', createdAt: '2026-05-09T12:00:00.000Z' }, storage)
      const result = listTokens(storage)
      expect(result).toHaveLength(1)
      expect(result[0].originalUrl).toBe('https://example.com')
    })
  })

  describe('listTokens ordering', () => {
    it('returns entries sorted by createdAt descending', () => {
      addToken({ token: 'old', originalUrl: 'https://old.com', createdAt: '2026-05-08T10:00:00.000Z' }, storage)
      addToken({ token: 'new', originalUrl: 'https://new.com', createdAt: '2026-05-09T10:00:00.000Z' }, storage)
      const result = listTokens(storage)
      expect(result[0].token).toBe('new')
      expect(result[1].token).toBe('old')
    })
  })

  describe('markDeleted', () => {
    it('flips dismissed to true without removing the entry', () => {
      addToken(makeEntry(), storage)
      markDeleted('abc123', storage)
      const result = listTokens(storage)
      expect(result).toHaveLength(1)
      expect(result[0].token).toBe('abc123')
      expect(result[0].dismissed).toBe(true)
    })

    it('preserves all other fields when marking deleted', () => {
      addToken(makeEntry(), storage)
      markDeleted('abc123', storage)
      const entry = listTokens(storage)[0]
      expect(entry.originalUrl).toBe('https://example.com')
      expect(entry.createdAt).toBe('2026-05-09T10:00:00.000Z')
    })

    it('is a no-op for a token not in history', () => {
      addToken(makeEntry(), storage)
      markDeleted('nonexistent', storage)
      expect(listTokens(storage)).toHaveLength(1)
      expect(listTokens(storage)[0].dismissed).toBe(false)
    })
  })

  describe('removeFromHistory', () => {
    it('fully purges the entry', () => {
      addToken(makeEntry(), storage)
      removeFromHistory('abc123', storage)
      expect(listTokens(storage)).toHaveLength(0)
    })

    it('only removes the matching token', () => {
      addToken({ token: 'tok1', originalUrl: 'https://a.com', createdAt: '2026-05-09T10:00:00.000Z' }, storage)
      addToken({ token: 'tok2', originalUrl: 'https://b.com', createdAt: '2026-05-09T11:00:00.000Z' }, storage)
      removeFromHistory('tok1', storage)
      const result = listTokens(storage)
      expect(result).toHaveLength(1)
      expect(result[0].token).toBe('tok2')
    })

    it('is a no-op for a token not in history', () => {
      addToken(makeEntry(), storage)
      removeFromHistory('nonexistent', storage)
      expect(listTokens(storage)).toHaveLength(1)
    })
  })

  describe('schema-version mismatch', () => {
    it('returns empty array and clears storage when version does not match', () => {
      storage.setItem('qr-history-v1', JSON.stringify({ version: 99, entries: [makeEntry()] }))
      expect(listTokens(storage)).toHaveLength(0)
      expect(storage.getItem('qr-history-v1')).toBeNull()
    })

    it('returns empty array when JSON is corrupt', () => {
      storage.setItem('qr-history-v1', 'not-valid-json{{{')
      expect(listTokens(storage)).toHaveLength(0)
    })
  })

  describe('quota errors', () => {
    it('silently ignores QuotaExceededError on addToken', () => {
      const quotaStorage = new QuotaStorage()
      expect(() => addToken(makeEntry(), quotaStorage)).not.toThrow()
    })

    it('returns empty array when storage is inaccessible on listTokens', () => {
      const badStorage = new FakeStorage()
      badStorage.setItem('qr-history-v1', 'bad json')
      expect(listTokens(badStorage)).toEqual([])
    })
  })
})

import { useCallback, useSyncExternalStore } from 'react'
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from '@tanstack/react-query'
import { linkKey } from '@/api/queryKeys'
import {
  createQr,
  deleteLink,
  getLink,
  patchLink,
  type CreateQrRequest,
  type CreateQrResponse,
  type GetLinkResponse,
} from '@/api/qr'
import type { ApiError } from '@/api/client'
import {
  addToken,
  listTokens,
  markDismissed as storageMarkDismissed,
  removeFromHistory as storageRemoveFromHistory,
} from './storage'
import { deriveEntry, type QueryState } from './derive'
import type { DerivedEntry, EntryAction, HistoryEntry } from './types'

// --- Storage subscription ---
// useSyncExternalStore needs a stable snapshot reference between calls when nothing has changed.
// listTokens() always returns a fresh array, so we cache it and only invalidate on writes.

type Listener = () => void
const listeners = new Set<Listener>()
let cachedSnapshot: HistoryEntry[] | null = null

function getSnapshot(): HistoryEntry[] {
  if (cachedSnapshot === null) cachedSnapshot = listTokens()
  return cachedSnapshot
}

function refreshSnapshot(): void {
  cachedSnapshot = listTokens()
  for (const fn of listeners) fn()
}

function subscribe(fn: Listener): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

export function useLinkHistory(): HistoryEntry[] {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}

// --- Internal helpers ---

function makeAction<T>(
  mutate: (args: T) => Promise<unknown>,
  isPending: boolean,
  error: ApiError | null,
): EntryAction<T> {
  const fn = async (args: T): Promise<void> => {
    await mutate(args)
  }
  return Object.assign(fn, { isPending, error }) as EntryAction<T>
}

function findRow(token: string): HistoryEntry | undefined {
  return cachedSnapshot
    ? cachedSnapshot.find((e) => e.token === token)
    : listTokens().find((e) => e.token === token)
}

// --- useLinkEntry ---

export function useLinkEntry(token: string, rowHint?: HistoryEntry): DerivedEntry {
  const queryClient = useQueryClient()

  const query = useQuery<GetLinkResponse, ApiError>({
    queryKey: linkKey(token),
    queryFn: () => getLink(token),
    retry: (_count, error) => error.status !== 404,
    enabled: !!token,
  })

  const queryState: QueryState = query.data
    ? { state: 'success', data: query.data }
    : query.isError
      ? { state: 'error', error: query.error }
      : { state: 'loading' }

  // Row resolution: caller-supplied row is most reliable (Dashboard fan-out);
  // otherwise look up from snapshot; otherwise synthesize from query data so deep-links work.
  const lookedUpRow = rowHint ?? findRow(token)
  const row: HistoryEntry = lookedUpRow ?? {
    token,
    originalUrl: query.data?.original_url ?? '',
    createdAt: query.data?.created_at ?? new Date().toISOString(),
    dismissed: false,
  }

  const view = deriveEntry(row, queryState)

  const deleteMut = useMutation<void, ApiError>({
    mutationFn: () => deleteLink(token),
    onSuccess() {
      storageMarkDismissed(token)
      refreshSnapshot()
      queryClient.setQueryData<GetLinkResponse>(linkKey(token), (prev) =>
        prev ? { ...prev, status: 'deleted' } : prev,
      )
      queryClient.invalidateQueries({ queryKey: linkKey(token) })
    },
  })

  const patchExpiresMut = useMutation<GetLinkResponse, ApiError, string | null>({
    mutationFn: (expires_at) => patchLink(token, { expires_at }),
    onSuccess(data) {
      queryClient.setQueryData(linkKey(token), data)
      queryClient.invalidateQueries({ queryKey: linkKey(token) })
    },
  })

  const patchUrlMut = useMutation<GetLinkResponse, ApiError, string>({
    mutationFn: (original_url) => patchLink(token, { original_url }),
    onSuccess(data) {
      queryClient.setQueryData(linkKey(token), data)
      queryClient.invalidateQueries({ queryKey: linkKey(token) })
    },
  })

  const markDeleted = makeAction<void>(
    () => deleteMut.mutateAsync(),
    deleteMut.isPending,
    deleteMut.error,
  )
  const reactivate = makeAction<string>(
    (date) => patchExpiresMut.mutateAsync(date),
    patchExpiresMut.isPending,
    patchExpiresMut.error,
  )
  const updateExpiry = makeAction<string | null>(
    (date) => patchExpiresMut.mutateAsync(date),
    patchExpiresMut.isPending,
    patchExpiresMut.error,
  )
  const updateUrl = makeAction<string>(
    (url) => patchUrlMut.mutateAsync(url),
    patchUrlMut.isPending,
    patchUrlMut.error,
  )
  const removeFromHistory = useCallback(() => {
    storageRemoveFromHistory(token)
    refreshSnapshot()
  }, [token])

  return {
    token,
    originalUrl: row.originalUrl,
    createdAt: row.createdAt,
    status: view.status,
    isLoading: view.isLoading,
    link: view.link,
    queryError: view.queryError,
    markDeleted,
    reactivate,
    updateExpiry,
    updateUrl,
    removeFromHistory,
  }
}

// --- useCreateEntry ---
// Mints a new Link via POST + writes the new entry into history.
// Returns the standard TanStack mutation result so callers compose with onSuccess/onError as usual.

export function useCreateEntry(): UseMutationResult<CreateQrResponse, ApiError, CreateQrRequest> {
  return useMutation<CreateQrResponse, ApiError, CreateQrRequest>({
    mutationFn: async (body) => {
      const res = await createQr(body)
      addToken({
        token: res.token,
        originalUrl: res.original_url,
        createdAt: new Date().toISOString(),
      })
      refreshSnapshot()
      return res
    },
  })
}

// --- useRecoverEntry ---
// Verifies a token exists on the server, then writes it into history.
// 404 is surfaced as a normal mutation error so the UI can show "token not found."

export function useRecoverEntry(): UseMutationResult<GetLinkResponse, ApiError, string> {
  return useMutation<GetLinkResponse, ApiError, string>({
    mutationFn: async (token) => {
      const data = await getLink(token)
      addToken({
        token: data.token,
        originalUrl: data.original_url,
        createdAt: data.created_at,
      })
      refreshSnapshot()
      return data
    },
  })
}

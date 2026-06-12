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
import { invalidateLinkLists } from './lists'
import type { DerivedEntry, EntryAction } from './types'

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

// --- useLinkEntry ---
// Single-Link view (LinkDetail). The server is the source of truth (ADR 0009):
// status comes straight from GET /api/qr/{token}; a 404 surfaces as a query
// error. Mutations write the fresh Link back into the cache and invalidate the
// dashboard list so it reflects the change.

export function useLinkEntry(token: string): DerivedEntry {
  const queryClient = useQueryClient()

  const query = useQuery<GetLinkResponse, ApiError>({
    queryKey: linkKey(token),
    queryFn: () => getLink(token),
    retry: (_count, error) => error.status !== 404,
    enabled: !!token,
  })

  const onLinkMutated = (data: GetLinkResponse) => {
    queryClient.setQueryData(linkKey(token), data)
    invalidateLinkLists(queryClient)
  }

  const deleteMut = useMutation<void, ApiError>({
    mutationFn: () => deleteLink(token),
    onSuccess() {
      queryClient.setQueryData<GetLinkResponse>(linkKey(token), (prev) =>
        prev ? { ...prev, status: 'deleted' } : prev,
      )
      queryClient.invalidateQueries({ queryKey: linkKey(token) })
      invalidateLinkLists(queryClient)
    },
  })

  const patchExpiresMut = useMutation<GetLinkResponse, ApiError, string | null>({
    mutationFn: (expires_at) => patchLink(token, { expires_at }),
    onSuccess: onLinkMutated,
  })

  const patchUrlMut = useMutation<GetLinkResponse, ApiError, string>({
    mutationFn: (original_url) => patchLink(token, { original_url }),
    onSuccess: onLinkMutated,
  })

  const patchLabelMut = useMutation<GetLinkResponse, ApiError, string | null>({
    mutationFn: (label) => patchLink(token, { label }),
    onSuccess: onLinkMutated,
  })

  const markDeleted = makeAction<void>(
    () => deleteMut.mutateAsync(),
    deleteMut.isPending,
    deleteMut.error,
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
  const updateLabel = makeAction<string | null>(
    (label) => patchLabelMut.mutateAsync(label),
    patchLabelMut.isPending,
    patchLabelMut.error,
  )

  return {
    token,
    status: query.data?.status,
    isLoading: query.isLoading,
    link: query.data,
    queryError: query.isError ? query.error : null,
    markDeleted,
    updateExpiry,
    updateUrl,
    updateLabel,
  }
}

// --- useCreateEntry ---
// Mints a new Link via POST. The owner dashboard is server-driven (ADR 0009),
// so a successful create just invalidates the list — no localStorage write.
// Returns the standard TanStack mutation result so callers compose onSuccess/onError.

export function useCreateEntry(): UseMutationResult<CreateQrResponse, ApiError, CreateQrRequest> {
  const queryClient = useQueryClient()
  return useMutation<CreateQrResponse, ApiError, CreateQrRequest>({
    mutationFn: (body) => createQr(body),
    onSuccess() {
      invalidateLinkLists(queryClient)
    },
  })
}

import { useQuery, type QueryClient, type UseQueryResult } from '@tanstack/react-query'
import { linkListKey } from '@/api/queryKeys'
import { listLinks, type LinkListResponse } from '@/api/qr'
import type { ApiError } from '@/api/client'

/**
 * The owner dashboard list (ADR 0009): the signed-in user's own Links with
 * state + scan count, newest-first. `deleted` toggles the trash filter. The
 * server is the source of truth — no localStorage. Pass `enabled: false` to
 * hold the request until auth resolves (avoids a guaranteed 401 when logged out).
 */
export function useLinkList(
  deleted: boolean,
  enabled = true,
): UseQueryResult<LinkListResponse, ApiError> {
  return useQuery<LinkListResponse, ApiError>({
    queryKey: linkListKey(deleted),
    queryFn: () => listLinks(deleted),
    enabled,
    retry: (_count, error) => error.status !== 401,
  })
}

/** Invalidate both the active and trash dashboard lists after a create/mutate. */
export function invalidateLinkLists(queryClient: QueryClient): void {
  queryClient.invalidateQueries({ queryKey: ['links'] })
}

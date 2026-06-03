import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { customizationKey } from '@/api/queryKeys'
import {
  getCustomization,
  saveCustomization,
  type CustomizationResponse,
  type StyleRecipe,
  type SaveCustomizationArgs,
  type SaveCustomizationResponse,
} from '@/api/qr'
import type { ApiError } from '@/api/client'

export type { CustomizationResponse, StyleRecipe }

export interface UseCustomizationResult {
  /** Server-persisted customization, or undefined while loading / not yet saved. */
  customization: CustomizationResponse | undefined
  isLoading: boolean
  /** Non-404 fetch error; 404 means no customization yet (not an error). */
  fetchError: ApiError | null
  /**
   * Upload a new style recipe + rendered composite to the server.
   * Invalidates the cache on success so the next render re-fetches.
   */
  save: (args: Omit<SaveCustomizationArgs, 'token'>) => Promise<SaveCustomizationResponse>
  isSaving: boolean
  saveError: ApiError | null
}

/**
 * Fetch and persist QR customization for a single token (ADR 0011).
 *
 * GET /api/qr/{token}/customization returns 404 when no customization has been
 * saved yet — this is treated as "no data" rather than an error.
 * PUT /api/qr/{token}/customization uploads the recipe + rendered composite.
 */
export function useCustomization(token: string): UseCustomizationResult {
  const queryClient = useQueryClient()

  const query = useQuery<CustomizationResponse, ApiError>({
    queryKey: customizationKey(token),
    queryFn: () => getCustomization(token),
    // Never retry — 404 means "not customized yet"; other errors surface via
    // fetchError. Retrying is the caller's concern (e.g. re-mount or explicit
    // invalidation), not the hook's.
    retry: false,
    // Suppress thrown errors so the component tree does not need an error
    // boundary for this non-critical data.
    throwOnError: false,
    enabled: !!token,
  })

  const mutation = useMutation<SaveCustomizationResponse, ApiError, Omit<SaveCustomizationArgs, 'token'>>({
    mutationFn: (args) => saveCustomization({ token, ...args }),
    onSuccess() {
      queryClient.invalidateQueries({ queryKey: customizationKey(token) })
    },
  })

  const fetchError =
    query.isError && query.error?.status !== 404 ? query.error : null

  return {
    customization: query.data,
    isLoading: query.isLoading,
    fetchError,
    save: (args) => mutation.mutateAsync(args),
    isSaving: mutation.isPending,
    saveError: mutation.error,
  }
}

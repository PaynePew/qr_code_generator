import { useReducedMotion } from 'framer-motion'

export function useMotionPreference(): boolean {
  return useReducedMotion() ?? false
}

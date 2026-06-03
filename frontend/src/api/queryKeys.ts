export const linkKey = (token: string) => ['link', token] as const

export const analyticsKey = (token: string) => ['analytics', token] as const

export const currentUserKey = () => ['auth', 'me'] as const

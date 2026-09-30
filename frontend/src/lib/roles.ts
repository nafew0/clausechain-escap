/** Account roles (backend workspace/roles.py): one per user. */
export type AccountRole = 'admin' | 'reviewer' | 'viewer'

export const ROLE_LABELS: Record<AccountRole, string> = {
  admin: 'Admin',
  reviewer: 'Reviewer',
  viewer: 'Viewer',
}

export const ROLE_BADGE: Record<AccountRole, 'default' | 'success' | 'secondary'> = {
  admin: 'default',
  reviewer: 'success',
  viewer: 'secondary',
}

/** Admins run pillars and engine actions and manage users. */
export function isAdmin(user?: { role?: string | null; is_superuser?: boolean } | null) {
  return user?.role === 'admin' || Boolean(user?.is_superuser)
}

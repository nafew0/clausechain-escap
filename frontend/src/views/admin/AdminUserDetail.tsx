'use client'
import { useEffect, useState } from 'react'
import { PageLoader } from '@/components/clausechain/PageLoader'
import { useRouter, useParams } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/hooks/useToast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { CustomSelect } from '@/components/ui/custom-select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ROLE_BADGE, ROLE_LABELS, type AccountRole } from '@/lib/roles'
import {
  deleteAdminUser,
  getAdminUserDetail,
  sendAdminPasswordReset,
  updateAdminUser,
} from '@/services/admin'

import { formatDateTime } from './admin-helpers'

type AxiosError = { response?: { data?: { detail?: string } } }

const ROLE_SUMMARY: Record<AccountRole, string> = {
  admin: 'Runs pillars and every engine action, reviews at every stage, and manages users and roles.',
  reviewer: 'Records citation, mapping and status decisions, recall verdicts and indicator scores.',
  viewer: 'Reads the workspace and downloads exports; cannot record decisions or run the engine.',
}

export default function AdminUserDetail() {
  const params = useParams()
  const userId = params?.userId as string | undefined
  const router = useRouter()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { user: currentUser } = useAuth()
  const [selectedRole, setSelectedRole] = useState<AccountRole | ''>('')
  const [savingRole, setSavingRole] = useState(false)
  const [savingStatus, setSavingStatus] = useState(false)
  const [sendingReset, setSendingReset] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deletingUser, setDeletingUser] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-user-detail', userId],
    queryFn: () => getAdminUserDetail(userId as string),
    enabled: !!userId,
  })

  useEffect(() => {
    // Sync the fetched role into the role selector.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedRole((data?.user?.role as AccountRole) || '')
  }, [data?.user?.role])

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['admin-user-detail', userId] })
    await queryClient.invalidateQueries({ queryKey: ['admin-users'] })
    await queryClient.invalidateQueries({ queryKey: ['admin-roles'] })
  }

  const handleRoleSave = async () => {
    if (!selectedRole || selectedRole === data?.user?.role) return

    setSavingRole(true)
    try {
      await updateAdminUser(userId as string, { role: selectedRole })
      await refresh()
      toast({ title: 'Role updated', description: `The account is now ${ROLE_LABELS[selectedRole]}.`, variant: 'success' })
    } catch (err: unknown) {
      const e = err as AxiosError
      toast({ title: 'Role change failed', description: e.response?.data?.detail || 'ClauseChain could not change the role right now.', variant: 'error' })
    } finally {
      setSavingRole(false)
    }
  }

  const handleStatusToggle = async () => {
    if (!data?.user) return

    setSavingStatus(true)
    try {
      await updateAdminUser(userId as string, { is_active: !data.user.is_active })
      await refresh()
      toast({ title: 'User status updated', description: 'ClauseChain saved the account status change.', variant: 'success' })
    } catch (err: unknown) {
      const e = err as AxiosError
      toast({ title: 'Status update failed', description: e.response?.data?.detail || 'ClauseChain could not update this user right now.', variant: 'error' })
    } finally {
      setSavingStatus(false)
    }
  }

  const handleSendReset = async () => {
    setSendingReset(true)
    try {
      await sendAdminPasswordReset(userId as string)
      toast({ title: 'Password reset sent', description: 'ClauseChain emailed a secure password reset link to the user.', variant: 'success' })
    } catch (err: unknown) {
      const e = err as AxiosError
      toast({ title: 'Reset email failed', description: e.response?.data?.detail || 'ClauseChain could not send the reset email.', variant: 'error' })
    } finally {
      setSendingReset(false)
    }
  }

  const handleDeleteUser = async () => {
    if (!data?.user || data.user.is_superuser) return

    setDeletingUser(true)
    try {
      const response = await deleteAdminUser(userId as string) as { message?: string }
      setDeleteDialogOpen(false)
      queryClient.removeQueries({ queryKey: ['admin-user-detail', userId] })
      await queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      await queryClient.invalidateQueries({ queryKey: ['admin-roles'] })
      toast({ title: 'User deleted', description: response.message || 'ClauseChain permanently deleted this user account.', variant: 'success' })
      router.push('/admin/users')
    } catch (err: unknown) {
      const e = err as AxiosError
      toast({ title: 'Delete failed', description: e.response?.data?.detail || 'ClauseChain could not delete this user right now.', variant: 'error' })
    } finally {
      setDeletingUser(false)
    }
  }

  if (isLoading) {
    return <PageLoader label="Loading the user record" />
  }

  if (error) {
    return <div className="theme-panel rounded-[1.8rem] p-6 text-sm text-rose-600">ClauseChain could not load this user right now.</div>
  }

  const { user } = data
  const role = user.role as AccountRole
  const isSelf = currentUser?.id === user.id

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Card className="theme-panel rounded-[1.8rem] border-0">
          <CardHeader>
            <CardTitle>User profile</CardTitle>
            <CardDescription>Identity, verification, and activity metadata.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Name</p>
              <p className="mt-1 font-medium text-foreground">
                {`${user.first_name || ''} ${user.last_name || ''}`.trim() || user.username}
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Email</p>
              <p className="mt-1 font-medium text-foreground">{user.email}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Organization</p>
              <p className="mt-1 text-foreground">{user.organization || 'Not provided'}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Designation</p>
              <p className="mt-1 text-foreground">{user.designation || 'Not provided'}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Joined</p>
              <p className="mt-1 text-foreground">{formatDateTime(user.created_at)}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Last login</p>
              <p className="mt-1 text-foreground">{formatDateTime(user.last_login)}</p>
            </div>
            <div className="sm:col-span-2 flex flex-wrap gap-2">
              <Badge variant={ROLE_BADGE[role] ?? 'secondary'}>{ROLE_LABELS[role] ?? role}</Badge>
              <Badge variant={user.is_active ? 'success' : 'danger'}>
                {user.is_active ? 'Active' : 'Inactive'}
              </Badge>
              <Badge variant={user.email_verified ? 'success' : 'warning'}>
                {user.email_verified ? 'Email verified' : 'Unverified'}
              </Badge>
            </div>
          </CardContent>
        </Card>

        <Card className="theme-panel rounded-[1.8rem] border-0">
          <CardHeader>
            <CardTitle>Role and access</CardTitle>
            <CardDescription>What this account can do in ClauseChain.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Role</p>
              <div className="flex flex-col gap-3 sm:flex-row">
                <CustomSelect
                  value={selectedRole}
                  onChange={(value) => setSelectedRole(value as AccountRole)}
                  disabled={isSelf}
                  options={Object.entries(ROLE_LABELS).map(([value, label]) => ({ label, value }))}
                />
                <Button
                  className="rounded-xl"
                  onClick={handleRoleSave}
                  disabled={isSelf || savingRole || !selectedRole || selectedRole === role}
                >
                  {savingRole ? 'Saving...' : 'Save role'}
                </Button>
              </div>
              <p className="text-sm text-muted-foreground">
                {selectedRole ? ROLE_SUMMARY[selectedRole] : null}
                {isSelf ? ' You cannot change your own role.' : ''}
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <Button variant="outline" className="rounded-xl" onClick={handleStatusToggle} disabled={savingStatus || isSelf}>
                {savingStatus ? 'Saving...' : user.is_active ? 'Deactivate account' : 'Reactivate account'}
              </Button>
              <Button variant="outline" className="rounded-xl" onClick={handleSendReset} disabled={sendingReset}>
                {sendingReset ? 'Sending...' : 'Send password reset'}
              </Button>
            </div>

            <div className="rounded-[1.2rem] border border-rose-200 bg-rose-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-rose-700">Danger zone</p>
              <p className="mt-2 text-sm text-rose-800">
                Deleting this user is permanent and removes all current user-related data.
              </p>
              {user.is_superuser ? (
                <p className="mt-3 text-sm font-medium text-rose-700">
                  Admin accounts cannot be deleted. Change the role first.
                </p>
              ) : (
                <Button
                  variant="destructive"
                  className="mt-4 rounded-xl"
                  onClick={() => setDeleteDialogOpen(true)}
                >
                  Delete user
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Dialog open={deleteDialogOpen} onOpenChange={(open) => !deletingUser && setDeleteDialogOpen(open)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Delete user</DialogTitle>
            <DialogDescription>
              This permanently deletes {user.username} and removes all current user-related data. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              className="rounded-xl"
              onClick={() => setDeleteDialogOpen(false)}
              disabled={deletingUser}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              className="rounded-xl"
              onClick={handleDeleteUser}
              disabled={deletingUser}
            >
              {deletingUser ? 'Deleting...' : 'Delete user'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

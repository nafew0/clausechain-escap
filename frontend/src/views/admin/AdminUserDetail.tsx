'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useParams } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'

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
import {
  deleteAdminUser,
  getAdminUserDetail,
  sendAdminPasswordReset,
  updateAdminUser,
} from '@/services/admin'

import { formatDateTime, formatMoney, titleize } from './admin-helpers'

type AxiosError = { response?: { data?: { detail?: string } } }

export default function AdminUserDetail() {
  const params = useParams()
  const userId = params?.userId as string | undefined
  const router = useRouter()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [selectedPlanId, setSelectedPlanId] = useState('')
  const [savingPlan, setSavingPlan] = useState(false)
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
    // Sync fetched subscription data into the manual plan selector.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedPlanId(data?.subscription?.plan?.id || '')
  }, [data?.subscription?.plan?.id])

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['admin-user-detail', userId] })
    await queryClient.invalidateQueries({ queryKey: ['admin-users'] })
  }

  const handleStatusToggle = async () => {
    if (!data?.user) return

    setSavingStatus(true)
    try {
      await updateAdminUser(userId as string, { is_active: !data.user.is_active })
      await refresh()
      toast({ title: 'User status updated', description: 'reactdjango saved the account status change.', variant: 'success' })
    } catch (err: unknown) {
      const e = err as AxiosError
      toast({ title: 'Status update failed', description: e.response?.data?.detail || 'reactdjango could not update this user right now.', variant: 'error' })
    } finally {
      setSavingStatus(false)
    }
  }

  const handlePlanSave = async () => {
    if (!selectedPlanId || selectedPlanId === data?.subscription?.plan?.id) return

    setSavingPlan(true)
    try {
      await updateAdminUser(userId as string, { plan_id: selectedPlanId })
      await refresh()
      toast({ title: 'Plan updated', description: 'reactdjango applied the manual plan override.', variant: 'success' })
    } catch (err: unknown) {
      const e = err as AxiosError
      toast({ title: 'Plan change failed', description: e.response?.data?.detail || 'reactdjango could not change the plan right now.', variant: 'error' })
    } finally {
      setSavingPlan(false)
    }
  }

  const handleSendReset = async () => {
    setSendingReset(true)
    try {
      await sendAdminPasswordReset(userId as string)
      toast({ title: 'Password reset sent', description: 'reactdjango emailed a secure password reset link to the user.', variant: 'success' })
    } catch (err: unknown) {
      const e = err as AxiosError
      toast({ title: 'Reset email failed', description: e.response?.data?.detail || 'reactdjango could not send the reset email.', variant: 'error' })
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
      toast({ title: 'User deleted', description: response.message || 'reactdjango permanently deleted this user account.', variant: 'success' })
      router.push('/admin/users')
    } catch (err: unknown) {
      const e = err as AxiosError
      toast({ title: 'Delete failed', description: e.response?.data?.detail || 'reactdjango could not delete this user right now.', variant: 'error' })
    } finally {
      setDeletingUser(false)
    }
  }

  if (isLoading) {
    return <div className="theme-panel rounded-[1.8rem] p-6 text-sm text-muted-foreground">Loading user record...</div>
  }

  if (error) {
    return <div className="theme-panel rounded-[1.8rem] p-6 text-sm text-rose-600">reactdjango could not load this user right now.</div>
  }

  const { user, subscription, usage, recent_payments: recentPayments, subscription_events: events, plans, payment_warnings: paymentWarnings } = data

  return (
    <div className="space-y-6">
      {paymentWarnings?.length ? (
        <div className="rounded-[1.4rem] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {paymentWarnings.join(' ')}
        </div>
      ) : null}

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
              <Badge variant={user.is_active ? 'success' : 'danger'}>
                {user.is_active ? 'Active' : 'Inactive'}
              </Badge>
              <Badge variant={user.email_verified ? 'success' : 'warning'}>
                {user.email_verified ? 'Email verified' : 'Unverified'}
              </Badge>
              {user.is_superuser ? <Badge variant="outline">Superuser</Badge> : null}
            </div>
          </CardContent>
        </Card>

        <Card className="theme-panel rounded-[1.8rem] border-0">
          <CardHeader>
            <CardTitle>Subscription controls</CardTitle>
            <CardDescription>Manual overrides and recovery actions.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Current plan</p>
                  <p className="mt-1 text-lg font-semibold text-foreground">{subscription.plan.name}</p>
                </div>
                <Badge variant="secondary">{titleize(subscription.payment_provider)}</Badge>
              </div>
              <p className="mt-3 text-sm text-muted-foreground">
                Status: {titleize(subscription.status)}. Renewal date: {formatDateTime(subscription.current_period_end)}.
              </p>
            </div>

            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Manual plan override</p>
              <div className="flex flex-col gap-3 sm:flex-row">
                <CustomSelect
                  value={selectedPlanId}
                  onChange={(v) => setSelectedPlanId(String(v))}
                  options={(plans || []).map((plan: { name: string; id: string }) => ({ label: plan.name, value: plan.id }))}
                />
                <Button className="rounded-xl" onClick={handlePlanSave} disabled={savingPlan || !selectedPlanId}>
                  {savingPlan ? 'Saving...' : 'Save plan'}
                </Button>
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <Button variant="outline" className="rounded-xl" onClick={handleStatusToggle} disabled={savingStatus}>
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
                  Admin accounts cannot be deleted.
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

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Card className="theme-panel rounded-[1.8rem] border-0">
          <CardHeader>
            <CardTitle>Usage snapshot</CardTitle>
            <CardDescription>Current license usage against plan limits.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Items used</p>
              <p className="mt-2 text-2xl font-semibold text-foreground">
                {usage?.usage_snapshot?.items?.used ?? '—'}
              </p>
            </div>
            <div className="rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 p-4 text-sm text-muted-foreground">
              Plan limit: {usage?.usage_snapshot?.items?.unlimited ? 'Unlimited items' : `${usage?.usage_snapshot?.items?.limit ?? '—'} items`}.
            </div>
          </CardContent>
        </Card>

        <Card className="theme-panel rounded-[1.8rem] border-0">
          <CardHeader>
            <CardTitle>Subscription history</CardTitle>
            <CardDescription>Latest billing and admin audit events.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {events.map((event: { id: string; event_type: string; created_at: string; plan?: { name: string }; status: string; payment_provider: string }) => (
              <div
                key={event.id}
                className="rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 px-4 py-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <Badge variant="outline">{titleize(event.event_type)}</Badge>
                  <span className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    {formatDateTime(event.created_at)}
                  </span>
                </div>
                <p className="mt-2 text-sm text-foreground">
                  {event.plan?.name || 'No plan'} · {titleize(event.status)} · {titleize(event.payment_provider)}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-1">
        <Card className="theme-panel rounded-[1.8rem] border-0">
          <CardHeader>
            <CardTitle>Recent payments</CardTitle>
            <CardDescription>
              Filtered payment history. View all in <Link className="text-primary underline-offset-4 hover:underline" href={`/admin/payments?user_id=${user.id}`}>payments</Link>.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {recentPayments.length ? recentPayments.map((payment: { provider: string; provider_reference: string; plan: { name: string }; status: string; amount: number; currency: string; created_at: string }) => (
              <div
                key={`${payment.provider}-${payment.provider_reference}`}
                className="rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.76)] bg-white/80 px-4 py-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-medium text-foreground">{payment.plan.name || 'Unknown plan'}</p>
                    <p className="text-xs text-muted-foreground">{payment.provider_reference}</p>
                  </div>
                  <Badge variant={payment.status === 'paid' || payment.status === 'completed' ? 'success' : 'secondary'}>
                    {payment.status}
                  </Badge>
                </div>
                <p className="mt-2 text-sm text-muted-foreground">
                  {formatMoney(payment.amount, payment.currency)} · {formatDateTime(payment.created_at)}
                </p>
              </div>
            )) : <p className="text-sm text-muted-foreground">No payment history matched this user.</p>}
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

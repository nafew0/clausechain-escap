'use client'
import { useQuery } from '@tanstack/react-query'

import QBarChart from '@/components/charts/QBarChart'
import QLineChart from '@/components/charts/QLineChart'
import QPieChart from '@/components/charts/QPieChart'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { getAdminDashboard } from '@/services/admin'

import { formatDateTime, formatMoney } from './admin-helpers'

function SummaryCard({ label, value, hint }: { label: string; value: React.ReactNode; hint: string }) {
  return (
    <Card className="theme-panel rounded-[1.6rem] border-0">
      <CardHeader className="pb-3">
        <CardDescription className="text-xs font-semibold uppercase tracking-[0.2em]">
          {label}
        </CardDescription>
        <CardTitle className="text-3xl">{value}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">{hint}</CardContent>
    </Card>
  )
}

function renderRevenueSummary(revenueTotals: Record<string, number> = {}) {
  const entries = Object.entries(revenueTotals)
  if (!entries.length) {
    return 'No paid revenue yet'
  }
  return entries.map(([currency, amount]) => `${formatMoney(amount, currency)} ${currency}`).join(' · ')
}

export default function AdminDashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-dashboard'],
    queryFn: getAdminDashboard,
  })

  if (isLoading) {
    return <div className="theme-panel rounded-[1.8rem] p-6 text-sm text-muted-foreground">Loading admin analytics...</div>
  }

  if (error) {
    return <div className="theme-panel rounded-[1.8rem] p-6 text-sm text-rose-600">Could not load the admin dashboard right now.</div>
  }

  return (
    <div className="space-y-6">
      {data?.warnings?.length ? (
        <div className="rounded-[1.4rem] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {data.warnings.join(' ')}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          label="Total users"
          value={data.summary.total_users}
          hint="All registered accounts."
        />
        <SummaryCard
          label="Active paid"
          value={data.summary.active_subscriptions}
          hint="Paid subscriptions with active access."
        />
        <SummaryCard
          label="Monthly revenue"
          value={renderRevenueSummary(data.summary.monthly_revenue_totals)}
          hint="Paid revenue booked this month, grouped by billing currency."
        />
        <SummaryCard
          label="Total plans"
          value={data.summary.total_plans ?? '—'}
          hint="Active subscription plans available."
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <Card className="theme-panel rounded-[1.8rem] border-0">
          <CardHeader>
            <CardTitle>User growth</CardTitle>
            <CardDescription>Monthly signup trend for the last six months.</CardDescription>
          </CardHeader>
          <CardContent>
            <QLineChart data={data.user_growth_over_time} showArea lines={[{ dataKey: 'count', name: 'Users' }]} />
          </CardContent>
        </Card>

        <Card className="theme-panel rounded-[1.8rem] border-0">
          <CardHeader>
            <CardTitle>Users by plan</CardTitle>
            <CardDescription>Current subscriptions grouped by plan.</CardDescription>
          </CardHeader>
          <CardContent>
            <QPieChart data={data.users_by_plan} donut />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card className="theme-panel rounded-[1.8rem] border-0">
          <CardHeader>
            <CardTitle>Revenue by provider</CardTitle>
            <CardDescription>Stripe and bKash revenue totals by month.</CardDescription>
          </CardHeader>
          <CardContent>
            <QBarChart
              data={data.revenue_over_time}
              stacked
              series={[
                { dataKey: 'stripe', name: 'Stripe' },
                { dataKey: 'bkash', name: 'bKash' },
              ]}
            />
          </CardContent>
        </Card>

        <Card className="theme-panel rounded-[1.8rem] border-0">
          <CardHeader>
            <CardTitle>Recent signups</CardTitle>
            <CardDescription>The latest accounts created in reactdjango.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.recent_signups.map((signup: Record<string, string>) => (
              <div
                key={signup.id}
                className="rounded-[1.2rem] border border-[rgb(var(--theme-border-rgb)/0.78)] bg-white/80 px-4 py-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-medium text-foreground">
                      {`${signup.first_name || ''} ${signup.last_name || ''}`.trim() || signup.username}
                    </p>
                    <p className="text-sm text-muted-foreground">{signup.email}</p>
                  </div>
                  <Badge variant="outline">New</Badge>
                </div>
                <p className="mt-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                  Joined {formatDateTime(signup.created_at)}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card className="theme-panel rounded-[1.8rem] border-0">
        <CardHeader>
          <CardTitle>Recent payments</CardTitle>
          <CardDescription>Latest normalized Stripe and bKash payment records.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
              <tr>
                <th className="pb-3 pr-4">Provider</th>
                <th className="pb-3 pr-4">User</th>
                <th className="pb-3 pr-4">Plan</th>
                <th className="pb-3 pr-4">Amount</th>
                <th className="pb-3 pr-4">Status</th>
                <th className="pb-3">Created</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_payments.map((payment: Record<string, unknown> & { user: { username: string; email: string }; plan: { name: string }; amount: number; currency: string; status: string; provider: string; provider_reference: string; created_at: string }) => (
                <tr key={`${payment.provider}-${payment.provider_reference}`} className="border-t border-[rgb(var(--theme-border-rgb)/0.72)]">
                  <td className="py-3 pr-4 font-medium text-foreground">{payment.provider}</td>
                  <td className="py-3 pr-4">
                    <div className="font-medium text-foreground">{payment.user.username || 'Unmatched'}</div>
                    <div className="text-xs text-muted-foreground">{payment.user.email || 'No email'}</div>
                  </td>
                  <td className="py-3 pr-4 text-foreground">{payment.plan.name || 'Unknown'}</td>
                  <td className="py-3 pr-4 text-foreground">{formatMoney(payment.amount, payment.currency)}</td>
                  <td className="py-3 pr-4">
                    <Badge variant={payment.status === 'paid' || payment.status === 'completed' ? 'success' : 'secondary'}>
                      {payment.status}
                    </Badge>
                  </td>
                  <td className="py-3 text-muted-foreground">{formatDateTime(payment.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}

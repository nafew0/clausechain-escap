'use client'
import { useAuth } from '@/contexts/AuthContext'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import PlanBadge from '@/components/subscription/PlanBadge'
import UsageBanner from '@/components/subscription/UsageBanner'

export default function Dashboard() {
  const { user } = useAuth()

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground">
          Welcome back, {user?.first_name || user?.username || 'there'}.
        </p>
      </div>

      <UsageBanner />

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Current plan</CardDescription>
            <CardTitle className="flex items-center gap-2">
              <PlanBadge plan={user?.current_plan} />
              {user?.current_plan?.name || 'Free'}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Manage your subscription from the Pricing page.
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardDescription>Account status</CardDescription>
            <CardTitle>{user?.email_verified ? 'Verified' : 'Unverified'}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {user?.email_verified
              ? 'Your email address has been verified.'
              : 'Please check your inbox for a verification email.'}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardDescription>Get started</CardDescription>
            <CardTitle>Build your app</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            This is a placeholder dashboard. Replace this page with your own app content.
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

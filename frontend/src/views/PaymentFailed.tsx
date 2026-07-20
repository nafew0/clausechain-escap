'use client'
import { AlertTriangle } from 'lucide-react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { useAuth } from '@/contexts/AuthContext'

function describeStatus(status: string) {
  if (status === 'cancel') {
    return 'You canceled the hosted payment before completion.'
  }
  if (status === 'expired') {
    return 'The hosted payment session expired before it could be confirmed.'
  }
  return 'The payment was not completed or could not be confirmed.'
}

export default function PaymentFailed() {
  const searchParams = useSearchParams() ?? new URLSearchParams()
  const { isAuthenticated } = useAuth()
  const provider = (searchParams.get('provider') || 'stripe').toLowerCase()
  const status = (searchParams.get('status') || 'failed').toLowerCase()
  const providerLabel = provider === 'bkash' ? 'bKash' : 'Stripe'

  return (
    <div className="theme-app-gradient flex min-h-[calc(100vh-4rem)] items-center px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-3xl">
        <Card className="theme-panel rounded-[2.25rem] border-0">
          <CardHeader className="space-y-5 text-center">
            <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-[2rem] bg-amber-100 text-amber-700 shadow-[0_18px_40px_rgb(var(--theme-shadow-rgb)/0.12)]">
              <AlertTriangle className="h-10 w-10" />
            </div>
            <div className="space-y-3">
              <div className="flex justify-center">
                <Badge variant="outline">{providerLabel} payment</Badge>
              </div>
              <CardTitle className="text-4xl tracking-tight">
                Payment not completed
              </CardTitle>
              <CardDescription className="mx-auto max-w-2xl text-base leading-8">
                {describeStatus(status)}
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-6 text-center">
            <div className="theme-panel-soft rounded-[1.75rem] px-5 py-5">
              <p className="text-sm text-muted-foreground">
                No subscription upgrade was applied. You can retry the payment flow from pricing or manage your subscription from the profile page.
              </p>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
              <Button asChild className="rounded-full">
                <Link href="/pricing">Try again</Link>
              </Button>
              {isAuthenticated ? (
                <Button asChild variant="outline" className="rounded-full">
                  <Link href="/profile">Go to profile</Link>
                </Button>
              ) : null}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

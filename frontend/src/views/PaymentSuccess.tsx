'use client'
import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, LoaderCircle } from 'lucide-react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'

import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/hooks/useToast'
import {
  getBkashPaymentStatus,
  getStripeCheckoutSessionStatus,
} from '@/services/payments'
import { getSubscription } from '@/services/subscriptions'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

const REDIRECT_DELAY_MS = 3500
const SYNC_ATTEMPTS = 5
const SYNC_INTERVAL_MS = 1200

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export default function PaymentSuccess() {
  const router = useRouter()
  const searchParams = useSearchParams() ?? new URLSearchParams()
  const { isAuthenticated, refreshUser } = useAuth()
  const { toast } = useToast()
  const [syncing, setSyncing] = useState(true)
  const announcedRef = useRef(false)
  const refreshUserRef = useRef(refreshUser)
  const toastRef = useRef(toast)
  const provider = (searchParams.get('provider') || 'stripe').toLowerCase()
  const sessionId = (searchParams.get('session_id') || '').trim()
  const paymentId = (searchParams.get('payment_id') || '').trim()

  useEffect(() => {
    refreshUserRef.current = refreshUser
  }, [refreshUser])

  useEffect(() => {
    toastRef.current = toast
  }, [toast])

  useEffect(() => {
    let cancelled = false

    const syncSubscription = async () => {
      if (!isAuthenticated) {
        if (!cancelled) {
          setSyncing(false)
        }
        return
      }

      for (let attempt = 0; attempt < SYNC_ATTEMPTS && !cancelled; attempt += 1) {
        try {
          if (provider === 'stripe' && sessionId) {
            await getStripeCheckoutSessionStatus(sessionId)
          } else if (provider === 'bkash' && paymentId) {
            await getBkashPaymentStatus(paymentId)
          }
        } catch (error) {
          console.error('Unable to sync provider payment yet:', error)
        }

        try {
          const subscription = await getSubscription()
          if (
            subscription?.payment_provider === provider &&
            subscription?.plan?.slug &&
            subscription.plan.slug !== 'free'
          ) {
            await refreshUserRef.current()
            if (!cancelled) {
              setSyncing(false)
            }
            if (!announcedRef.current) {
              announcedRef.current = true
              toastRef.current({
                title: 'Payment confirmed',
                description: `Your ${provider === 'bkash' ? 'bKash' : 'Stripe'} subscription is now active.`,
                variant: 'success',
              })
            }
            return
          }
        } catch (error) {
          console.error('Unable to confirm subscription yet:', error)
        }

        await delay(SYNC_INTERVAL_MS)
      }

      if (!cancelled) {
        setSyncing(false)
      }
    }

    syncSubscription()

    return () => {
      cancelled = true
    }
  }, [isAuthenticated, paymentId, provider, sessionId])

  useEffect(() => {
    if (syncing) {
      return undefined
    }

    const redirectTimer = window.setTimeout(() => {
      router.replace('/dashboard')
    }, REDIRECT_DELAY_MS)

    return () => {
      window.clearTimeout(redirectTimer)
    }
  }, [router, syncing])

  const providerLabel = provider === 'bkash' ? 'bKash' : 'Stripe'
  const syncCopy =
    provider === 'bkash'
      ? 'reactdjango is confirming your bKash payment and refreshing your workspace access.'
      : 'reactdjango is syncing the Stripe subscription state and will return you to the dashboard automatically.'
  const pendingCopy =
    provider === 'bkash'
      ? 'Confirming your subscription with bKash and refreshing your workspace access.'
      : 'Confirming your subscription with Stripe and refreshing your workspace access.'

  return (
    <div className="theme-app-gradient flex min-h-[calc(100vh-4rem)] items-center px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-3xl">
        <Card className="theme-panel rounded-[2.25rem] border-0">
          <CardHeader className="space-y-5 text-center">
            <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-[2rem] bg-emerald-100 text-emerald-700 shadow-[0_18px_40px_rgb(var(--theme-shadow-rgb)/0.12)]">
              <CheckCircle2 className="h-10 w-10" />
            </div>
            <div className="space-y-3">
              <div className="flex justify-center">
                <Badge variant="success">{providerLabel} payment</Badge>
              </div>
              <CardTitle className="text-4xl tracking-tight">
                Payment successful
              </CardTitle>
              <CardDescription className="mx-auto max-w-2xl text-base leading-8">
                Your billing request has been accepted. {syncCopy}
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-6 text-center">
            <div className="theme-panel-soft rounded-[1.75rem] px-5 py-5">
              {syncing ? (
                <div className="flex flex-col items-center gap-3">
                  <LoaderCircle className="h-6 w-6 animate-spin text-primary" />
                  <p className="text-sm text-muted-foreground">
                    {pendingCopy}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Redirecting you to the dashboard now. If the plan badge still looks stale, refresh once after the webhook finishes processing.
                </p>
              )}
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
              <Button asChild className="rounded-full">
                <Link href="/dashboard">Go to dashboard</Link>
              </Button>
              <Button asChild variant="outline" className="rounded-full">
                <Link href="/pricing">Back to pricing</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

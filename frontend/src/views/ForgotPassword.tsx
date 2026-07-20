'use client'
import { useState } from 'react'
import Link from 'next/link'

import AuthShell from '@/components/auth/AuthShell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/hooks/useToast'
import { requestPasswordReset } from '@/services/auth'

const SHELL_PROPS = {
  eyebrow: 'Account Recovery',
  title: 'Forgot your password?',
  description: 'Enter your username or email and reactdjango will send a reset link if the account is eligible.',
  showcaseTitle: 'Self-service password recovery with generic responses.',
  showcaseDescription:
    'reactdjango keeps the recovery flow non-enumerating, rate-limited, and consistent whether the account exists or not.',
  metrics: [
    { value: '1 link', label: 'Single-use reset' },
    { value: '120s', label: 'Cooldown' },
    { value: 'Masked', label: 'No enumeration' },
  ],
  highlights: [
    'The reset request response stays generic to avoid account enumeration.',
    'reactdjango applies a per-account cooldown and an IP-level abuse throttle.',
    'Existing reset links still land on the validated reset-password page.',
    'Admins and end users now share the same secure reset infrastructure.',
  ],
}

export default function ForgotPassword() {
  const { toast } = useToast()
  const [identifier, setIdentifier] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!identifier.trim()) {
      return
    }

    setSubmitting(true)
    try {
      const response = await requestPasswordReset(identifier.trim())
      setSent(true)
      toast({
        title: 'Request received',
        description: response.detail,
        variant: 'success',
      })
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      toast({
        title: 'Request failed',
        description: axiosError.response?.data?.detail || 'reactdjango could not process the reset request right now.',
        variant: 'error',
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      {...SHELL_PROPS}
      footer={(
        <div className="text-sm text-muted-foreground">
          Remembered it?{' '}
          <Link href="/login" className="font-semibold text-primary hover:text-primary/80">
            Back to sign in
          </Link>
        </div>
      )}
    >
      {sent ? (
        <div className="rounded-2xl border border-[rgb(var(--theme-border-rgb)/0.82)] bg-white/85 px-4 py-4 text-sm text-muted-foreground">
          If an eligible account exists, a password reset email will arrive shortly.
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Username or email
            </label>
            <Input
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              placeholder="name@example.com"
              autoComplete="username"
              required
            />
          </div>
          <Button className="w-full rounded-xl" disabled={submitting}>
            {submitting ? 'Sending...' : 'Send reset link'}
          </Button>
        </form>
      )}
    </AuthShell>
  )
}

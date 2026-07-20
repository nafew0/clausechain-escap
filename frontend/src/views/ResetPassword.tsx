'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { AlertCircle, CheckCircle2, LoaderCircle } from 'lucide-react'

import AuthShell from '@/components/auth/AuthShell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/hooks/useToast'
import { confirmPasswordReset, validatePasswordReset } from '@/services/auth'

const SHELL_PROPS = {
  eyebrow: 'Password Reset',
  title: 'Reset your password',
  description: 'Choose a new password to regain access to your reactdjango workspace.',
  showcaseTitle: 'Secure account recovery without exposing user records.',
  showcaseDescription:
    'reactdjango validates every reset link before showing the form, then invalidates prior refresh tokens after the password changes.',
  metrics: [
    { value: 'JWT', label: 'Session revoked' },
    { value: '1 link', label: 'Token validation' },
    { value: 'Email', label: 'Secure delivery' },
  ],
  highlights: [
    'Reset links are verified before any password form is shown.',
    'reactdjango revokes outstanding refresh tokens after the password changes.',
    'The new password must still pass Django\'s production password validators.',
    'This reset flow works for admin-triggered recovery emails without exposing internal admin routes.',
  ],
}

export default function ResetPassword() {
  const router = useRouter()
  const searchParams = useSearchParams() ?? new URLSearchParams()
  const { toast } = useToast()
  const uid = searchParams.get('uid') || ''
  const token = searchParams.get('token') || ''
  const [validating, setValidating] = useState(true)
  const [valid, setValid] = useState(false)
  const [validationMessage, setValidationMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formState, setFormState] = useState({ new_password: '', new_password2: '' })

  useEffect(() => {
    let cancelled = false

    const validate = async () => {
      if (!uid || !token) {
        if (!cancelled) {
          setValid(false)
          setValidationMessage('This password reset link is incomplete or malformed.')
          setValidating(false)
        }
        return
      }

      try {
        await validatePasswordReset(uid, token)
        if (!cancelled) {
          setValid(true)
          setValidationMessage('')
        }
      } catch (error: unknown) {
        const axiosError = error as { response?: { data?: { detail?: string } } }
        if (!cancelled) {
          setValid(false)
          setValidationMessage(axiosError.response?.data?.detail || 'This password reset link is invalid or has expired.')
        }
      } finally {
        if (!cancelled) {
          setValidating(false)
        }
      }
    }

    validate()

    return () => {
      cancelled = true
    }
  }, [token, uid])

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target
    setFormState((current) => ({
      ...current,
      [name]: value,
    }))
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setSubmitting(true)

    try {
      await confirmPasswordReset({
        uid,
        token,
        ...formState,
      })
      toast({
        title: 'Password reset complete',
        description: 'You can sign in with your new password now.',
        variant: 'success',
      })
      router.replace('/login')
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      toast({
        title: 'Password reset failed',
        description: axiosError.response?.data?.detail || 'reactdjango could not reset the password with this link.',
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
          Remembered your password?{' '}
          <Link href="/login" className="font-semibold text-primary hover:text-primary/80">
            Back to sign in
          </Link>
        </div>
      )}
    >
      {validating ? (
        <div className="flex items-center gap-3 rounded-2xl border border-[rgb(var(--theme-border-rgb)/0.82)] bg-white/85 px-4 py-4 text-sm text-muted-foreground">
          <LoaderCircle className="h-5 w-5 animate-spin text-primary" />
          Validating your reset link...
        </div>
      ) : valid ? (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              New password
            </label>
            <Input
              type="password"
              name="new_password"
              value={formState.new_password}
              onChange={handleChange}
              autoComplete="new-password"
              required
            />
          </div>
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Confirm new password
            </label>
            <Input
              type="password"
              name="new_password2"
              value={formState.new_password2}
              onChange={handleChange}
              autoComplete="new-password"
              required
            />
          </div>
          <Button className="w-full rounded-xl" disabled={submitting}>
            {submitting ? 'Resetting...' : 'Reset password'}
          </Button>
        </form>
      ) : (
        <div className="space-y-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-4 text-sm text-rose-700">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
            <div>
              <p className="font-semibold">Reset link unavailable</p>
              <p className="mt-1">{validationMessage}</p>
            </div>
          </div>
          <Button asChild variant="outline" className="rounded-xl border-rose-200 bg-white text-rose-700 hover:bg-rose-100">
            <Link href="/login">
              <CheckCircle2 className="mr-2 h-4 w-4" />
              Return to login
            </Link>
          </Button>
        </div>
      )}
    </AuthShell>
  )
}

'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { AlertCircle, ArrowRight, CheckCircle2, LoaderCircle, MailCheck } from 'lucide-react'

import PublicAuthShell from '@/components/auth/PublicAuthShell'
import SocialLoginButtons from '@/components/auth/SocialLoginButtons'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/hooks/useToast'
import { getSafeRedirect } from '@/utils/redirects'

export default function Login() {
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [recoveryIdentifier, setRecoveryIdentifier] = useState('')
  const [resending, setResending] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const { login, resendVerificationEmail, isAuthenticated, loading: authLoading } = useAuth()
  const router = useRouter()
  const params = useSearchParams() ?? new URLSearchParams()
  const { toast } = useToast()
  const redirectTo = getSafeRedirect(params.get('redirect'))

  useEffect(() => { if (isAuthenticated) router.replace('/dashboard') }, [isAuthenticated, router])
  useEffect(() => {
    if (cooldown <= 0) return
    const timer = window.setInterval(() => setCooldown(value => Math.max(0, value - 1)), 1000)
    return () => window.clearInterval(timer)
  }, [cooldown])

  if (isAuthenticated) return null

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setSubmitting(true); setError('')
    const result = await login(form.username, form.password)
    setSubmitting(false)
    if (result.success) { setRecoveryIdentifier(''); router.push(redirectTo); return }
    setRecoveryIdentifier(form.username.trim()); setError(result.error ?? 'Sign in failed.')
  }

  const resend = async () => {
    const identifier = recoveryIdentifier || form.username.trim()
    if (!identifier || resending || cooldown) return
    setResending(true)
    const result = await resendVerificationEmail(identifier)
    setResending(false)
    if (result.success) { setCooldown(120); toast({ title: 'Verification email requested', description: result.message, variant: 'success' }) }
    else toast({ title: 'Verification email unavailable', description: result.error, variant: 'error' })
  }

  return <PublicAuthShell mode="login"><div className="public-auth-form">
    <span className="public-form-kicker">ACCOUNT ACCESS</span><h2>Sign in to ClauseChain</h2><p>Use your reviewer account to continue.</p>
    {params.get('signed_out') === '1' ? <div className="public-auth-notice success"><CheckCircle2 />You have been signed out.</div> : null}
    {params.get('logout_unconfirmed') === '1' ? <div className="public-auth-notice warning"><AlertCircle />The local session was cleared, but the server could not confirm cookie revocation. Sign in again only when the backend is available.</div> : null}
    {authLoading ? <div className="public-auth-loading"><LoaderCircle className="animate-spin" /> Checking your secure session…</div> : <>
      <form onSubmit={submit} className="public-auth-fields">
        {error ? <div className="public-auth-notice error"><AlertCircle />{error}</div> : null}
        <label><span>Username or email</span><input name="username" autoComplete="username" value={form.username} onChange={event => { setForm(current => ({ ...current, username: event.target.value })); setError('') }} placeholder="name@example.com" required /></label>
        <label><span>Password</span><input name="password" type="password" autoComplete="current-password" value={form.password} onChange={event => { setForm(current => ({ ...current, password: event.target.value })); setError('') }} placeholder="Enter your password" required /></label>
        <div className="public-auth-field-meta"><Link href="/forgot-password">Forgot password?</Link></div>
        <button className="public-auth-submit" disabled={submitting}>{submitting ? <><LoaderCircle className="animate-spin" /> Signing in…</> : <>Sign in <ArrowRight /></>}</button>
      </form>
      {recoveryIdentifier ? <div className="public-recovery"><MailCheck /><div><strong>Need help signing in?</strong><p>Request another verification email without revealing whether an account exists.</p><div><Button type="button" variant="outline" onClick={resend} disabled={resending || cooldown > 0}>{resending ? 'Requesting…' : cooldown ? `Resend in ${cooldown}s` : 'Resend verification email'}</Button><Link href="/forgot-password">Reset password</Link></div></div></div> : null}
      <div className="public-auth-social"><span>Or continue with</span><SocialLoginButtons nextPath={redirectTo} /></div>
      <p className="public-auth-switch">No account yet? <Link href="/register">Create one</Link></p>
      {/* Public read-only demo access (no reviewer roles, cannot write decisions or launch runs) */}
      <div className="public-auth-notice" style={{ marginTop: '0.75rem', display: 'block', textAlign: 'center' }}>
        <strong>Evaluator demo access (read-only)</strong>
        <p style={{ margin: '0.35rem 0 0.5rem' }}>
          username <code>viewer</code> · password <code>escap-rdtii-2026</code>
        </p>
        <Button type="button" variant="outline"
          onClick={() => { setForm({ username: 'viewer', password: 'escap-rdtii-2026' }); setError('') }}>
          Fill demo credentials
        </Button>
      </div>
    </>}
  </div></PublicAuthShell>
}

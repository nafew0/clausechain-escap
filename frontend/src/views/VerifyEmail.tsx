'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { CheckCircle2, LoaderCircle, TriangleAlert } from 'lucide-react'

import api from '@/services/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const INITIAL_STATE = {
  status: 'loading',
  message: 'Verifying your email…',
}

const INVALID_TOKEN_STATE = {
  status: 'error',
  message: 'Invalid or expired verification link. Please request a new verification email.',
}

const VerifyEmail = () => {
  const searchParams = useSearchParams()
  const token = searchParams?.get('token')?.trim() || ''
  const [verificationState, setVerificationState] = useState(() =>
    token ? INITIAL_STATE : INVALID_TOKEN_STATE
  )

  useEffect(() => {
    if (!token) {
      return
    }

    let ignore = false

    const verify = async () => {
      try {
        const response = await api.get('/auth/verify-email/', {
          params: { token },
        })

        if (!ignore) {
          setVerificationState({
            status: 'success',
            message: response.data?.detail || 'Email verified! You can now log in.',
          })
        }
      } catch (error: unknown) {
        const axiosError = error as { response?: { data?: { detail?: string } } }
        if (!ignore) {
          setVerificationState({
            status: 'error',
            message:
              axiosError.response?.data?.detail ||
              'Invalid or expired verification link. Please request a new verification email.',
          })
        }
      }
    }

    verify()

    return () => {
      ignore = true
    }
  }, [token])

  const isSuccess = verificationState.status === 'success'

  return (
    <div className="theme-app-gradient flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-8 sm:px-6">
      <Card className="theme-panel w-full max-w-xl border-0">
        <CardHeader className="items-center text-center">
          <div
            className={`inline-flex h-14 w-14 items-center justify-center rounded-full ${
              isSuccess
                ? 'bg-emerald-100 text-emerald-700'
                : verificationState.status === 'error'
                  ? 'bg-rose-100 text-rose-700'
                  : 'bg-[rgb(var(--theme-primary-soft-rgb))] text-primary'
            }`}
          >
            {verificationState.status === 'loading' ? (
              <LoaderCircle className="h-6 w-6 animate-spin" />
            ) : isSuccess ? (
              <CheckCircle2 className="h-6 w-6" />
            ) : (
              <TriangleAlert className="h-6 w-6" />
            )}
          </div>
          <CardTitle className="mt-4">
            {verificationState.status === 'loading'
              ? 'Verifying email'
              : isSuccess
                ? 'Email verified'
                : 'Verification failed'}
          </CardTitle>
          <CardDescription className="max-w-md text-center text-sm leading-6">
            {verificationState.message}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center gap-3">
          {isSuccess ? (
            <Button asChild className="rounded-full">
              <Link href="/login">Go to login</Link>
            </Button>
          ) : (
            <>
              <Button asChild className="rounded-full">
                <Link href="/login">Back to login</Link>
              </Button>
              <Button asChild variant="secondary" className="rounded-full">
                <Link href="/register">Create account again</Link>
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default VerifyEmail

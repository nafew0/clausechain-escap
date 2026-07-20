import { Suspense } from 'react'
import SocialAuthCallback from '@/views/SocialAuthCallback'

export default function SocialAuthCallbackPage() {
  return (
    <Suspense>
      <SocialAuthCallback />
    </Suspense>
  )
}

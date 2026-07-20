import type { NextConfig } from 'next'

const isDevelopment = process.env.NODE_ENV !== 'production'
const rawBackendUrl = process.env.BACKEND_URL?.trim()
const workspaceFixtureMode = process.env.NEXT_PUBLIC_WORKSPACE_FIXTURE_MODE?.trim() === '1'

if (!isDevelopment && workspaceFixtureMode) {
  throw new Error('NEXT_PUBLIC_WORKSPACE_FIXTURE_MODE is development-only and cannot be built for production.')
}

if (!isDevelopment && !rawBackendUrl) {
  throw new Error('BACKEND_URL must be set in production.')
}

const backendUrl = (rawBackendUrl || 'http://localhost:8000').replace(/\/+$/, '')
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline' https://js.stripe.com${isDevelopment ? " 'unsafe-eval'" : ''}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data: https://fonts.gstatic.com",
  `connect-src 'self' https://api.stripe.com https://r.stripe.com${isDevelopment ? ' ws: wss:' : ''}`,
  "frame-src 'self' https://js.stripe.com https://hooks.stripe.com",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  `frame-ancestors ${isDevelopment ? "'self'" : "'none'"}`,
].join('; ')

const nextConfig: NextConfig = {
  skipTrailingSlashRedirect: true,
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'Content-Security-Policy', value: contentSecurityPolicy },
          { key: 'X-Frame-Options', value: isDevelopment ? 'SAMEORIGIN' : 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
        ],
      },
    ]
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*/`,
      },
      {
        source: '/media/:path*',
        destination: `${backendUrl}/media/:path*`,
      },
    ]
  },
}

export default nextConfig

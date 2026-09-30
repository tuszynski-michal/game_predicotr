import type { NextConfig } from 'next';

const scriptPolicy =
  process.env.NODE_ENV === 'production'
    ? "script-src 'self' 'unsafe-inline'"
    : "script-src 'self' 'unsafe-inline' 'unsafe-eval'";

const DEFAULT_API_ORIGINS = ['http://127.0.0.1:8000', 'http://localhost:8000'];
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);

/**
 * A second local instance may point the Admin at another loopback API port
 * (`NEXT_PUBLIC_ADMIN_API_BASE_URL`); the policy then allows that origin too.
 * Anything that is not plain HTTP on loopback is ignored, so the default
 * policy never widens beyond the local machine.
 */
function apiOrigins(configured: string | undefined): readonly string[] {
  if (configured === undefined || configured.trim() === '') {
    return DEFAULT_API_ORIGINS;
  }
  try {
    const url = new URL(configured.trim());
    if (url.protocol !== 'http:' || !LOOPBACK_HOSTS.has(url.hostname)) {
      return DEFAULT_API_ORIGINS;
    }
    return [...new Set([...DEFAULT_API_ORIGINS, url.origin])];
  } catch {
    return DEFAULT_API_ORIGINS;
  }
}

const apiSources = apiOrigins(process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL).join(
  ' ',
);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: `default-src 'self'; img-src 'self' data: blob: ${apiSources}; style-src 'self' 'unsafe-inline'; ${scriptPolicy}; connect-src 'self' ${apiSources}; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`,
          },
          { key: 'Referrer-Policy', value: 'no-referrer' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
        ],
      },
    ];
  },
};

export default nextConfig;

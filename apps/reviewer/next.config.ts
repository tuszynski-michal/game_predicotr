import type { NextConfig } from 'next';

const scriptPolicy =
  process.env.NODE_ENV === 'production'
    ? "script-src 'self' 'unsafe-inline'"
    : "script-src 'self' 'unsafe-inline' 'unsafe-eval'";

function securityHeaders(contentSecurityPolicy: string) {
  return [
    { key: 'Content-Security-Policy', value: contentSecurityPolicy },
    { key: 'Referrer-Policy', value: 'no-referrer' },
    { key: 'X-Content-Type-Options', value: 'nosniff' },
    { key: 'X-Frame-Options', value: 'DENY' },
  ];
}

const reviewerContentSecurityPolicy = `default-src 'self'; img-src 'self' http://127.0.0.1:8000 data: blob:; style-src 'self' 'unsafe-inline'; ${scriptPolicy}; connect-src 'self' http://127.0.0.1:8000; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`;
const remoteSelectionContentSecurityPolicy = `default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; ${scriptPolicy}; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`;

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: '/((?!manual-selection(?:/|$)|selection-api(?:/|$)).*)',
        headers: securityHeaders(reviewerContentSecurityPolicy),
      },
      {
        source: '/manual-selection',
        headers: securityHeaders(remoteSelectionContentSecurityPolicy),
      },
      {
        source: '/selection-api/:path*',
        headers: securityHeaders(remoteSelectionContentSecurityPolicy),
      },
    ];
  },
};

export default nextConfig;

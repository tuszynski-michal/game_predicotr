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
// D-471: the online board-search share talks only to its own proxy prefix;
// the loopback API origin is never reachable from these pages.
const boardSearchShareContentSecurityPolicy = `default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; ${scriptPolicy}; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`;

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source:
          '/((?!manual-selection(?:/|$)|selection-api(?:/|$)|board-search(?:/|$)|board-search-api(?:/|$)).*)',
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
      {
        source: '/board-search',
        headers: securityHeaders(boardSearchShareContentSecurityPolicy),
      },
      {
        source: '/board-search-api/:path*',
        headers: securityHeaders(boardSearchShareContentSecurityPolicy),
      },
    ];
  },
};

export default nextConfig;

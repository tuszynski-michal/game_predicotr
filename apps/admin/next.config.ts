import type { NextConfig } from 'next';

const scriptPolicy =
  process.env.NODE_ENV === 'production'
    ? "script-src 'self' 'unsafe-inline'"
    : "script-src 'self' 'unsafe-inline' 'unsafe-eval'";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: `default-src 'self'; img-src 'self' data: blob: http://127.0.0.1:8000 http://localhost:8000; style-src 'self' 'unsafe-inline'; ${scriptPolicy}; connect-src 'self' http://127.0.0.1:8000 http://localhost:8000; base-uri 'none'; frame-ancestors 'none'; form-action 'self'`,
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

import { NextRequest, NextResponse } from 'next/server';

import { reviewerProxyTarget } from '@/security/reviewer-proxy-policy';

const TOKEN_COOKIE = 'gp_reviewer_token';
const MAX_REQUEST_BYTES = 128 * 1024;
const DEFAULT_INTERNAL_API = 'http://127.0.0.1:8000';

type RouteContext = {
  readonly params: Promise<{ readonly path: readonly string[] }>;
};

function internalApiOrigin(): string {
  const candidate = (
    process.env.REVIEWER_INTERNAL_API_ORIGIN ?? DEFAULT_INTERNAL_API
  ).trim();
  const parsed = new URL(candidate);
  if (
    parsed.protocol !== 'http:' ||
    !['127.0.0.1', 'localhost', '[::1]'].includes(parsed.hostname)
  ) {
    throw new Error('Reviewer internal API must remain on HTTP loopback.');
  }
  return parsed.origin;
}

async function proxy(request: NextRequest, context: RouteContext) {
  const segments = (await context.params).path;
  const incomingPath = `/api/${segments.join('/')}`.replace(
    '/api/api/',
    '/api/',
  );
  const targetPath = reviewerProxyTarget(request.method, incomingPath);
  if (targetPath === null) {
    return NextResponse.json(
      { code: 'REVIEWER_ROUTE_FORBIDDEN', message: 'Route is not public.' },
      { status: 403 },
    );
  }

  const isUnlock = targetPath.endsWith('/unlock');
  const token = request.cookies.get(TOKEN_COOKIE)?.value;
  if (!isUnlock && token === undefined) {
    return NextResponse.json(
      {
        code: 'REVIEWER_TOKEN_REQUIRED',
        message: 'Reviewer access token is required.',
      },
      { status: 401 },
    );
  }
  const contentLength = Number(request.headers.get('content-length') ?? '0');
  if (!Number.isFinite(contentLength) || contentLength > MAX_REQUEST_BYTES) {
    return NextResponse.json(
      { code: 'REVIEWER_REQUEST_TOO_LARGE', message: 'Request is too large.' },
      { status: 413 },
    );
  }

  const headers = new Headers({
    Accept: request.headers.get('accept') ?? '*/*',
  });
  const contentType = request.headers.get('content-type');
  if (contentType !== null) headers.set('Content-Type', contentType);
  if (token !== undefined) headers.set('Authorization', `Bearer ${token}`);

  const target = new URL(targetPath, internalApiOrigin());
  target.search = request.nextUrl.search;
  const body =
    request.method === 'GET' ? undefined : await request.arrayBuffer();
  if (body !== undefined && body.byteLength > MAX_REQUEST_BYTES) {
    return NextResponse.json(
      { code: 'REVIEWER_REQUEST_TOO_LARGE', message: 'Request is too large.' },
      { status: 413 },
    );
  }
  const upstream = await fetch(target, {
    body,
    cache: 'no-store',
    headers,
    method: request.method,
    redirect: 'error',
  });

  if (isUnlock && upstream.ok) {
    const payload = (await upstream.json()) as Record<string, unknown>;
    const accessToken = payload.accessToken;
    if (typeof accessToken !== 'string' || accessToken.length < 32) {
      return NextResponse.json(
        {
          code: 'REVIEWER_UPSTREAM_INVALID',
          message: 'Reviewer unlock response is invalid.',
        },
        { status: 502 },
      );
    }
    delete payload.accessToken;
    const response = NextResponse.json(payload, { status: upstream.status });
    const forwardedProtocol = request.headers.get('x-forwarded-proto');
    response.cookies.set(TOKEN_COOKIE, accessToken, {
      httpOnly: true,
      maxAge: 24 * 60 * 60,
      path: '/review-api',
      sameSite: 'strict',
      secure:
        forwardedProtocol === 'https' || request.nextUrl.protocol === 'https:',
    });
    return response;
  }

  const responseHeaders = new Headers();
  for (const name of ['cache-control', 'content-type', 'etag']) {
    const value = upstream.headers.get(name);
    if (value !== null) responseHeaders.set(name, value);
  }
  return new NextResponse(upstream.body, {
    headers: responseHeaders,
    status: upstream.status,
  });
}

export const GET = proxy;
export const POST = proxy;

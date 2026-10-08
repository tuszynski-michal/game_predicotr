/** Independent panel proxy. It cannot forward Admin endpoints or old share cookies. */
import {
  boundedBody,
  containsSensitiveData,
  internalApiOrigin,
  isJson,
  readCookie,
  validateRequestOrigin,
} from './board-search-share-proxy.ts';

export const MANAGEMENT_PUBLIC_PREFIX = '/management-api';
export const MANAGEMENT_COOKIE = 'gp_management_token';
export const MANAGEMENT_EXPECTED_SESSION_HEADER = 'X-Management-Session';
export const MANAGEMENT_PROXY_HEADER = 'X-Management-Public-Proxy';
export const MANAGEMENT_PROXY_INTENT = 'reviewer-management-v1';
const API = '/api/v1/management-public';
const UUID_PATTERN =
  '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}';
const UUID = new RegExp(`^${UUID_PATTERN}$`);
const SHA = /^[0-9a-f]{64}$/;
const TOKEN = /^[A-Za-z0-9_-]{32,256}$/;
const STAKE = '(?:2000|1000|600|400|200|120)';
const NUMBER = '[1-9]\\d{0,8}';
type Route = {
  kind: 'unlock' | 'json' | 'mutation' | 'image';
  query: (params: URLSearchParams) => boolean;
};
const none = (params: URLSearchParams) => params.size === 0;

function query(
  required: Record<string, RegExp>,
  optional: Record<string, RegExp> = {},
) {
  return (params: URLSearchParams) => {
    for (const name of Object.keys(required))
      if (params.getAll(name).length !== 1) return false;
    for (const [name, value] of params) {
      if (
        params.getAll(name).length !== 1 ||
        !(required[name] ?? optional[name])?.test(value)
      )
        return false;
    }
    return true;
  };
}

export function managementPublicRoute(
  method: string,
  path: string,
): Route | null {
  const match = (suffix: string) => new RegExp(`^${API}${suffix}$`).test(path);
  const game = `/machines/${UUID_PATTERN}/game/${UUID_PATTERN}`;
  if (method === 'POST' && match(`/sessions/${UUID_PATTERN}/unlock`))
    return { kind: 'unlock', query: none };
  if (method === 'GET') {
    if (
      path === API ||
      path === `${API}/context` ||
      match(
        `${game}/(?:stakes(?:/${STAKE})?|symbols|results/${UUID_PATTERN}|boards/${NUMBER})`,
      )
    )
      return { kind: 'json', query: none };
    if (match(`/machines/${UUID_PATTERN}/journal`))
      return {
        kind: 'json',
        query: query(
          {},
          {
            gameId: UUID,
            stakeGrosze: new RegExp(`^${STAKE}$`),
            limit: /^(?:[1-9]\d?|100)$/,
            before: /^[A-Za-z0-9_=-]{1,256}$/,
          },
        ),
      };
    if (match(`${game}/approximate-win`))
      return {
        kind: 'json',
        query: query({
          startSequenceNumber: /^[1-9]\d{0,8}$/,
          spinCount: /^(?:[1-9]\d{0,4}|100000)$/,
        }),
      };
    if (match(`${game}/symbols/${UUID_PATTERN}/image`))
      return {
        kind: 'image',
        query: query({ revision: SHA, expectedSessionId: UUID }),
      };
    if (match(`${game}/boards/${NUMBER}/view`))
      return {
        kind: 'image',
        query: query(
          { expectedBoardChecksumSha256: SHA, expectedSessionId: UUID },
          { viewRevision: SHA },
        ),
      };
  }
  if (
    method === 'POST' &&
    (path === `${API}/points` ||
      match(`/points/${UUID_PATTERN}/machines`) ||
      match(`${game}/search`) ||
      match(`${game}/stakes/${STAKE}/(?:clear|refresh)`) ||
      match(
        `${game}/stakes/${STAKE}/boards/${NUMBER}/cells/(?:[0-9]|1[0-4])/decision`,
      ))
  )
    return { kind: 'mutation', query: none };
  if (
    method === 'PUT' &&
    (match(`/points/${UUID_PATTERN}`) ||
      match(`/points/${UUID_PATTERN}/machines/${UUID_PATTERN}`) ||
      match(`/machines/${UUID_PATTERN}/assignments`) ||
      match(`${game}/stakes/${STAKE}`))
  )
    return { kind: 'mutation', query: none };
  return null;
}

const headers = () =>
  new Headers({
    'Content-Type': 'application/json',
    'Cache-Control': 'no-store',
  });
function error(status: number, code: string, message: string) {
  return new Response(JSON.stringify({ code, message }), {
    status,
    headers: headers(),
  });
}

export async function proxyManagementRequest(
  request: Request,
  options: {
    fetchImplementation?: typeof fetch;
    internalApiOrigin?: string;
    enabled?: boolean;
  } = {},
): Promise<Response> {
  const enabled =
    options.enabled ??
    (process.env.GAME_PREDICTOR_MANAGEMENT_SHARE_ENABLED ?? 'true')
      .trim()
      .toLowerCase() === 'true';
  if (!enabled)
    return error(
      404,
      'MANAGEMENT_ROUTE_DISABLED',
      'Panel sharing is disabled.',
    );
  const url = new URL(request.url);
  const path = url.pathname.startsWith(`${MANAGEMENT_PUBLIC_PREFIX}/`)
    ? url.pathname.slice(MANAGEMENT_PUBLIC_PREFIX.length)
    : '';
  const route = managementPublicRoute(request.method, path);
  if (!route || !route.query(url.searchParams))
    return error(403, 'MANAGEMENT_ROUTE_FORBIDDEN', 'Route is not public.');
  const origin = validateRequestOrigin(request);
  if (origin) return origin;
  const token = readCookie(request.headers.get('cookie'), MANAGEMENT_COOKIE);
  const expected =
    route.kind === 'image'
      ? url.searchParams.get('expectedSessionId')
      : request.headers.get(MANAGEMENT_EXPECTED_SESSION_HEADER);
  if (
    route.kind !== 'unlock' &&
    (!token || !TOKEN.test(token) || !expected || !UUID.test(expected))
  )
    return error(
      401,
      'MANAGEMENT_TOKEN_REQUIRED',
      'Enter the access code first.',
    );
  const upstreamHeaders = new Headers({
    Accept: route.kind === 'image' ? 'image/*' : 'application/json',
    [MANAGEMENT_PROXY_HEADER]: MANAGEMENT_PROXY_INTENT,
  });
  if (route.kind !== 'unlock') {
    upstreamHeaders.set('Cookie', `${MANAGEMENT_COOKIE}=${token}`);
    upstreamHeaders.set(MANAGEMENT_EXPECTED_SESSION_HEADER, expected!);
  }
  const etag = request.headers.get('if-none-match');
  if (route.kind === 'image' && etag && /^"[0-9a-f]{64}"$/.test(etag))
    upstreamHeaders.set('If-None-Match', etag);
  let body: ArrayBuffer | undefined;
  if (route.kind === 'unlock' || route.kind === 'mutation') {
    if (
      request.headers
        .get('content-type')
        ?.split(';', 1)[0]
        ?.trim()
        .toLowerCase() !== 'application/json'
    )
      return error(
        415,
        'MANAGEMENT_CONTENT_TYPE_INVALID',
        'Use application/json.',
      );
    const size = Number(request.headers.get('content-length') ?? 0);
    if (!Number.isFinite(size) || size < 0 || size > 16384)
      return error(
        413,
        'MANAGEMENT_REQUEST_TOO_LARGE',
        'The request is too large.',
      );
    const bounded = await boundedBody(request, 16384);
    if (!bounded)
      return error(
        413,
        'MANAGEMENT_REQUEST_TOO_LARGE',
        'The request is too large.',
      );
    body = bounded.buffer;
    upstreamHeaders.set('Content-Type', 'application/json');
  }
  let upstream: Response;
  try {
    upstream = await (options.fetchImplementation ?? fetch)(
      new URL(
        `${path}${url.search}`,
        internalApiOrigin(options.internalApiOrigin),
      ),
      {
        method: request.method,
        body,
        headers: upstreamHeaders,
        redirect: 'error',
        cache: 'no-store',
        signal: AbortSignal.timeout(30000),
      },
    );
  } catch {
    return error(
      502,
      'MANAGEMENT_UPSTREAM_UNAVAILABLE',
      'The panel is temporarily unavailable.',
    );
  }
  if (route.kind === 'image' && upstream.status === 304)
    return new Response(null, {
      status: 304,
      headers: {
        'Cache-Control': 'private, no-cache',
        ...(etag ? { ETag: etag } : {}),
      },
    });
  // 100000 expanded numeric payout rows require more than 16 MiB; bounded at 64 MiB.
  const bytes = await boundedBody(
    upstream,
    (route.kind === 'image' ? 8 : 64) * 1024 * 1024,
  );
  if (!bytes)
    return error(
      502,
      'MANAGEMENT_UPSTREAM_INVALID',
      'Panel data is unavailable.',
    );
  if (route.kind === 'image' && upstream.ok) {
    const type = upstream.headers.get('content-type')?.split(';', 1)[0];
    if (!type || !['image/png', 'image/jpeg', 'image/webp'].includes(type))
      return error(
        502,
        'MANAGEMENT_UPSTREAM_INVALID',
        'Panel data is unavailable.',
      );
    const imageHeaders = new Headers({
      'Content-Type': type,
      'Cache-Control': 'private, no-cache',
    });
    const imageEtag = upstream.headers.get('etag');
    if (imageEtag && /^"[0-9a-f]{64}"$/.test(imageEtag))
      imageHeaders.set('ETag', imageEtag);
    return new Response(bytes, { headers: imageHeaders });
  }
  if (!isJson(upstream))
    return error(
      502,
      'MANAGEMENT_UPSTREAM_INVALID',
      'Panel data is unavailable.',
    );
  let payload: unknown;
  try {
    payload = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return error(
      502,
      'MANAGEMENT_UPSTREAM_INVALID',
      'Panel data is unavailable.',
    );
  }
  if (containsSensitiveData(payload))
    return error(
      502,
      'MANAGEMENT_UPSTREAM_INVALID',
      'Panel data is unavailable.',
    );
  const resultHeaders = headers();
  if (route.kind === 'unlock' && upstream.ok) {
    const cookie = readCookie(
      upstream.headers.get('set-cookie'),
      MANAGEMENT_COOKIE,
    );
    const expires =
      typeof payload === 'object' && payload && 'expiresAt' in payload
        ? new Date(String(payload.expiresAt))
        : null;
    if (
      !cookie ||
      !TOKEN.test(cookie) ||
      !expires ||
      !Number.isFinite(expires.getTime())
    )
      return error(
        502,
        'MANAGEMENT_UPSTREAM_INVALID',
        'Panel data is unavailable.',
      );
    const maxAge = Math.max(
      0,
      Math.min(72 * 3600, Math.floor((expires.getTime() - Date.now()) / 1000)),
    );
    resultHeaders.append(
      'Set-Cookie',
      `${MANAGEMENT_COOKIE}=${cookie}; Max-Age=${maxAge}; Expires=${expires.toUTCString()}; Path=${MANAGEMENT_PUBLIC_PREFIX}; HttpOnly; Secure; SameSite=Strict`,
    );
  }
  const response = new Response(bytes, {
    status: upstream.status,
    headers: resultHeaders,
  });
  // A delayed response from another tab must not erase the newly unlocked cookie.
  return response;
}

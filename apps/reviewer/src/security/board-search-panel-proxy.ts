import { createHmac } from 'node:crypto';
import {
  boardSearchShareRoute,
  boundedBody,
  containsSensitiveData,
  internalApiOrigin,
  isBoardSearchShareEnabled,
  proxyBoardSearchShareRequest,
  readCookie,
  validateRequestOrigin,
  type BoardSearchShareProxyOptions,
} from './board-search-share-proxy.ts';

export const PANEL_PROXY_PREFIX = '/board-search-panel-api';
export const PANEL_COOKIE = 'gp_board_search_panel';
const UUID =
  '[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
const SECRET = /^[A-Za-z0-9_-]{32,256}$/;
const MAX_PANEL_RESPONSE_BYTES = 128 * 1024;

export function panelChildToken(
  secret: string,
  panelId: string,
  sessionId: string,
): string {
  return createHmac('sha256', secret)
    .update(
      `board-search-panel-v1\n${panelId.toLowerCase()}\n${sessionId.toLowerCase()}`,
    )
    .digest('hex');
}

function error(status: number, code: string): Response {
  return Response.json(
    { code, message: 'Dostęp do panelu jest niedostępny.', details: {} },
    { status, headers: { 'Cache-Control': 'no-store' } },
  );
}

/** Separate per-panel cookie paths; only a derived game credential reaches the existing API. */
export async function proxyBoardSearchPanelRequest(
  request: Request,
  options: BoardSearchShareProxyOptions = {},
): Promise<Response> {
  if (!(options.shareEnabled ?? isBoardSearchShareEnabled()))
    return error(404, 'BOARD_SEARCH_SHARE_DISABLED');
  const url = new URL(request.url);
  const match = url.pathname.match(
    new RegExp(`^${PANEL_PROXY_PREFIX}/panels/(${UUID})/(.+)$`, 'i'),
  );
  if (!match) return error(403, 'BOARD_SEARCH_PANEL_ROUTE_FORBIDDEN');
  const panelId = match[1].toLowerCase(),
    suffix = match[2];
  const originError = validateRequestOrigin(request);
  if (originError) return originError;
  const credential = readCookie(request.headers.get('cookie'), PANEL_COOKIE);
  const prefix = `${panelId}.`;
  const secret = credential?.startsWith(prefix)
    ? credential.slice(prefix.length)
    : null;
  const isOpen = suffix === 'open' && request.method === 'POST';
  if (!isOpen && (secret === null || !SECRET.test(secret))) {
    // Never clear a different panel's cookie because an old tab made a request.
    return error(401, 'BOARD_SEARCH_PANEL_ACCESS_INVALID');
  }
  const fetchImplementation: typeof fetch = (input, init) => {
    const path = new URL(input instanceof Request ? input.url : String(input))
      .pathname;
    // Full existing range calculations may be much slower than opening a link.
    const timeout = path.startsWith('/api/v1/board-search-shares/')
      ? 120_000
      : 12_000;
    return (options.fetchImplementation ?? globalThis.fetch)(input, {
      ...init,
      signal: AbortSignal.timeout(timeout),
    });
  };
  let requestBody: ArrayBuffer | undefined;
  if (request.method === 'POST') {
    const declared = Number(request.headers.get('content-length') ?? 0);
    if (!Number.isFinite(declared) || declared < 0 || declared > 4096)
      return error(413, 'BOARD_SEARCH_PANEL_BODY_TOO_LARGE');
    const bytes = await boundedBody(new Response(request.body), 4096);
    if (bytes === null) return error(413, 'BOARD_SEARCH_PANEL_BODY_TOO_LARGE');
    requestBody = bytes.buffer;
  }

  const child = suffix.match(
    new RegExp(`^games/(${UUID})(/api/v1/board-search-shares/.+)$`, 'i'),
  );
  if (child) {
    const apiPath = child[2];
    const route = boardSearchShareRoute(request.method, apiPath);
    if (route === null || route.kind === 'unlock')
      return error(403, 'BOARD_SEARCH_PANEL_ROUTE_FORBIDDEN');
    const forwardedUrl = new URL(
      `/board-search-api${apiPath}${url.search}`,
      url,
    );
    const headers = new Headers(request.headers);
    headers.set(
      'cookie',
      `gp_board_search_token=${panelChildToken(secret!, panelId, child[1])}`,
    );
    const forwarded = new Request(forwardedUrl, {
      method: request.method,
      headers,
      ...(request.method === 'POST' ? { body: requestBody } : {}),
    });
    const response = await proxyBoardSearchShareRequest(forwarded, {
      ...options,
      fetchImplementation,
    });
    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete('set-cookie');
    return new Response(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  }
  if (
    url.search !== '' ||
    (!isOpen && !(suffix === 'context' && request.method === 'GET'))
  ) {
    return error(403, 'BOARD_SEARCH_PANEL_ROUTE_FORBIDDEN');
  }
  const headers = new Headers({
    Accept: 'application/json',
    'X-Board-Search-Panel-Proxy': 'reviewer-board-search-panel-v1',
  });
  let body: string | undefined;
  if (isOpen) {
    if (
      request.headers.get('content-type')?.split(';')[0].trim() !==
      'application/json'
    )
      return error(415, 'BOARD_SEARCH_PANEL_CONTENT_TYPE_INVALID');
    const raw = new TextDecoder().decode(requestBody);
    try {
      const data = JSON.parse(raw) as Record<string, unknown>;
      if (
        Object.keys(data).length !== 1 ||
        typeof data.linkKey !== 'string' ||
        !SECRET.test(data.linkKey)
      )
        return error(422, 'BOARD_SEARCH_PANEL_KEY_INVALID');
      body = JSON.stringify({ linkKey: data.linkKey });
    } catch {
      return error(422, 'BOARD_SEARCH_PANEL_KEY_INVALID');
    }
    headers.set('Content-Type', 'application/json');
  } else headers.set('Cookie', `${PANEL_COOKIE}=${credential}`);
  let upstream: Response;
  try {
    upstream = await fetchImplementation(
      new URL(
        `/api/v1/board-search-panels/${panelId}/${suffix}`,
        internalApiOrigin(options.internalApiOrigin),
      ),
      {
        method: request.method,
        headers,
        body,
        cache: 'no-store',
        redirect: 'error',
      },
    );
  } catch {
    return error(502, 'BOARD_SEARCH_PANEL_UPSTREAM_UNAVAILABLE');
  }
  const declared = Number(upstream.headers.get('content-length') ?? 0);
  if (declared > MAX_PANEL_RESPONSE_BYTES)
    return error(502, 'BOARD_SEARCH_PANEL_RESPONSE_INVALID');
  const bytes = await boundedBody(upstream, MAX_PANEL_RESPONSE_BYTES);
  if (bytes === null) return error(502, 'BOARD_SEARCH_PANEL_RESPONSE_INVALID');
  const raw = new TextDecoder().decode(bytes);
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(raw) as Record<string, unknown>;
    if (containsSensitiveData(data))
      return error(502, 'BOARD_SEARCH_PANEL_RESPONSE_INVALID');
  } catch {
    return error(502, 'BOARD_SEARCH_PANEL_RESPONSE_INVALID');
  }
  const responseHeaders = new Headers({
    'Cache-Control': 'no-store',
    'Content-Type': 'application/json',
  });
  if (upstream.ok && isOpen) {
    if (data.panelId !== panelId || typeof data.expiresAt !== 'string')
      return error(502, 'BOARD_SEARCH_PANEL_RESPONSE_INVALID');
    const expiry = new Date(data.expiresAt);
    const token = upstream.headers
      .get('set-cookie')
      ?.match(/gp_board_search_panel=([^;,\s]+)/)?.[1];
    const sentKey = (JSON.parse(body!) as { linkKey: string }).linkKey;
    if (!Number.isFinite(expiry.getTime()) || token !== `${panelId}.${sentKey}`)
      return error(502, 'BOARD_SEARCH_PANEL_RESPONSE_INVALID');
    const maxAge = Math.max(
      0,
      Math.min(72 * 3600, Math.floor((expiry.getTime() - Date.now()) / 1000)),
    );
    responseHeaders.set(
      'set-cookie',
      `${PANEL_COOKIE}=${token}; Path=${PANEL_PROXY_PREFIX}/panels/${panelId}; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Strict`,
    );
  }
  return new Response(raw, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

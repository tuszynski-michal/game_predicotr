/**
 * Public proxy for the online board-search share (D-471, TASK-0768).
 *
 * The browser talks only to `/board-search-api/...` on the Reviewer; this
 * proxy forwards an exact allowlist of reads, code unlock and cell
 * corrections (D-492) to the loopback API, adds the proxy intent header, translates the
 * share cookie and refuses any response that carries internal identities,
 * paths or secrets. Images are streamed with a size limit and a checked
 * content type. It never widens the Reviewer or remote-selection surfaces:
 * their cookies are not read or forwarded here.
 */

export const BOARD_SEARCH_SHARE_PUBLIC_PREFIX = '/board-search-api';
export const BOARD_SEARCH_SHARE_COOKIE = 'gp_board_search_token';
export const BOARD_SEARCH_SHARE_COOKIE_PATH = '/board-search-api';
export const BOARD_SEARCH_SHARE_PROXY_HEADER = 'X-Board-Search-Share-Proxy';
export const BOARD_SEARCH_SHARE_PROXY_INTENT = 'reviewer-board-search-v1';
export const BOARD_SEARCH_SHARE_MAX_REQUEST_BYTES = 4 * 1024;
export const BOARD_SEARCH_SHARE_MAX_JSON_BYTES = 8 * 1024 * 1024;
export const BOARD_SEARCH_SHARE_MAX_IMAGE_BYTES = 8 * 1024 * 1024;
export const BOARD_SEARCH_SHARE_MAX_IMAGE_AGE_SECONDS = 86_400;

const API_PREFIX = '/api/v1/board-search-shares';
const DEFAULT_INTERNAL_API = 'http://127.0.0.1:8000';
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);
const TOKEN = /^[A-Za-z0-9_-]{32,256}$/;
const STRICT_UUID =
  '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}';
const SHA256 = /^[0-9a-f]{64}$/;
const POSITIVE_INTEGER = /^[1-9]\d{0,8}$/;
const CELL = /^(?:[0-9]|1[0-4]):[^\s:]{1,64}$/;
const IMAGE_TYPES = new Set(['image/webp', 'image/png', 'image/jpeg']);
const WINDOWS_ABSOLUTE_PATH = /(?:^|[\s"'])(?:[a-zA-Z]:[\\/]|[\\/]{2})[^\s"']+/;
// Internal identities, storage details and secrets a recipient must never
// receive; the API already omits them, this is a second line of defence.
const FORBIDDEN_RESPONSE_KEYS = new Set([
  'accesscode',
  'accesstoken',
  'absolutepath',
  'authorization',
  'basepath',
  'cellreviewid',
  'codehash',
  'codesalt',
  'cookie',
  'cropchecksumsha256',
  'cropsampleid',
  'hostbasepath',
  'imagepath',
  'imagerelativepath',
  'importjobid',
  'jobid',
  'recognizedboardid',
  'relativepath',
  'reviewitemid',
  'secret',
  'token',
  'tokenhash',
]);

const FREE_TEXT_KEYS = new Set([
  'gamename',
  'label',
  'name',
  'nameen',
  'namepl',
  'paylinename',
]);

type Route =
  | { readonly kind: 'unlock' }
  | { readonly kind: 'mutation'; readonly query: QueryRule }
  | { readonly kind: 'json'; readonly query: QueryRule }
  | { readonly kind: 'image'; readonly query: QueryRule };

type QueryRule = (parameters: URLSearchParams) => boolean;

const noQuery: QueryRule = (parameters) => parameters.size === 0;

export type BoardSearchShareProxyOptions = {
  readonly fetchImplementation?: typeof globalThis.fetch;
  readonly internalApiOrigin?: string;
  readonly shareEnabled?: boolean;
};

export function isBoardSearchShareEnabled(
  configured = process.env.GAME_PREDICTOR_BOARD_SEARCH_SHARE_ENABLED,
): boolean {
  // Same rule as the API: only "true" (default when unset) enables it.
  if (configured === undefined) return true;
  return configured.trim().toLowerCase() === 'true';
}

/** The allowlisted API route for one public request, or `null`. */
export function boardSearchShareRoute(
  method: string,
  apiPath: string,
): Route | null {
  if (
    method === 'POST' &&
    new RegExp(`^${API_PREFIX}/sessions/${STRICT_UUID}/unlock$`).test(apiPath)
  ) {
    return { kind: 'unlock' };
  }
  if (
    method === 'POST' &&
    new RegExp(
      `^${API_PREFIX}/boards/[1-9]\\d{0,8}/cells/(?:[0-9]|1[0-4])/decision$`,
    ).test(apiPath)
  ) {
    return { kind: 'mutation', query: noQuery };
  }
  if (method !== 'GET') return null;
  if (
    apiPath === `${API_PREFIX}/context` ||
    apiPath === `${API_PREFIX}/symbols`
  ) {
    return { kind: 'json', query: noQuery };
  }
  if (
    new RegExp(`^${API_PREFIX}/symbols/${STRICT_UUID}/image$`).test(apiPath)
  ) {
    return { kind: 'image', query: exactly({ revision: SHA256 }) };
  }
  if (apiPath === `${API_PREFIX}/search`) {
    return { kind: 'json', query: searchQuery };
  }
  if (apiPath === `${API_PREFIX}/approximate-win`) {
    return {
      kind: 'json',
      query: exactly({
        spinCount: POSITIVE_INTEGER,
        startSequenceNumber: POSITIVE_INTEGER,
      }),
    };
  }
  if (apiPath === `${API_PREFIX}/approximate-win/stake`) {
    // D-487: records the stake of a calculated range; omitted = base stake.
    return {
      kind: 'json',
      query: exactly(
        {
          spinCount: POSITIVE_INTEGER,
          startSequenceNumber: POSITIVE_INTEGER,
        },
        { stakeGrosze: POSITIVE_INTEGER },
      ),
    };
  }
  if (new RegExp(`^${API_PREFIX}/boards/[1-9]\\d{0,8}$`).test(apiPath)) {
    return { kind: 'json', query: noQuery };
  }
  if (new RegExp(`^${API_PREFIX}/boards/[1-9]\\d{0,8}/view$`).test(apiPath)) {
    return {
      kind: 'image',
      query: exactly(
        { expectedBoardChecksumSha256: SHA256 },
        { viewRevision: SHA256 },
      ),
    };
  }
  return null;
}

function exactly(
  required: Readonly<Record<string, RegExp>>,
  optional: Readonly<Record<string, RegExp>> = {},
): QueryRule {
  return (parameters) => {
    for (const name of Object.keys(required)) {
      if (parameters.getAll(name).length !== 1) return false;
    }
    for (const [name, value] of parameters) {
      const pattern = required[name] ?? optional[name];
      if (pattern === undefined || !pattern.test(value)) return false;
      if (parameters.getAll(name).length !== 1) return false;
    }
    return true;
  };
}

function searchQuery(parameters: URLSearchParams): boolean {
  const cells = parameters.getAll('cell');
  if (cells.length < 1 || cells.length > 15) return false;
  for (const [name, value] of parameters) {
    if (name === 'cell') {
      if (!CELL.test(value)) return false;
    } else if (name === 'scope') {
      if (value !== 'all_searchable' && value !== 'approved_only') return false;
      if (parameters.getAll(name).length !== 1) return false;
    } else if (name === 'limit') {
      if (!/^(?:[1-9]\d?|100)$/.test(value)) return false;
      if (parameters.getAll(name).length !== 1) return false;
    } else {
      return false;
    }
  }
  return true;
}

export async function proxyBoardSearchShareRequest(
  request: Request,
  options: BoardSearchShareProxyOptions = {},
): Promise<Response> {
  if (!(options.shareEnabled ?? isBoardSearchShareEnabled())) {
    return errorResponse(
      404,
      'BOARD_SEARCH_SHARE_ROUTE_DISABLED',
      'Online board-search sharing is disabled.',
    );
  }
  const requestUrl = new URL(request.url);
  const apiPath = publicPathToApiPath(requestUrl.pathname);
  const route = boardSearchShareRoute(request.method, apiPath);
  if (route === null) return forbidden();
  if (route.kind !== 'unlock' && !route.query(requestUrl.searchParams)) {
    return forbidden();
  }
  if (route.kind === 'unlock' && requestUrl.searchParams.size > 0) {
    return forbidden();
  }
  const originError = validateRequestOrigin(request);
  if (originError !== null) return originError;

  const publicToken = readCookie(
    request.headers.get('cookie'),
    BOARD_SEARCH_SHARE_COOKIE,
  );
  if (
    route.kind !== 'unlock' &&
    (publicToken === null || !TOKEN.test(publicToken))
  ) {
    return withClearedCookie(
      errorResponse(
        401,
        'BOARD_SEARCH_SHARE_TOKEN_REQUIRED',
        'Enter the access code first.',
      ),
    );
  }

  const headers = new Headers({
    Accept: route.kind === 'image' ? 'image/*' : 'application/json',
    [BOARD_SEARCH_SHARE_PROXY_HEADER]: BOARD_SEARCH_SHARE_PROXY_INTENT,
  });
  let body: ArrayBuffer | undefined;
  if (route.kind === 'unlock' || route.kind === 'mutation') {
    const contentType = request.headers.get('content-type')?.split(';', 1)[0];
    if (contentType?.trim().toLowerCase() !== 'application/json') {
      return errorResponse(
        415,
        'BOARD_SEARCH_SHARE_CONTENT_TYPE_INVALID',
        'The request must use application/json.',
      );
    }
    const declared = Number(request.headers.get('content-length') ?? '0');
    if (
      !Number.isFinite(declared) ||
      declared < 0 ||
      declared > BOARD_SEARCH_SHARE_MAX_REQUEST_BYTES
    ) {
      return tooLarge();
    }
    body = await request.arrayBuffer();
    if (body.byteLength > BOARD_SEARCH_SHARE_MAX_REQUEST_BYTES)
      return tooLarge();
    headers.set('Content-Type', 'application/json');
  }
  if (route.kind !== 'unlock' && publicToken !== null) {
    headers.set('Cookie', `${BOARD_SEARCH_SHARE_COOKIE}=${publicToken}`);
  }
  if (route.kind === 'image') {
    const ifNoneMatch = request.headers.get('if-none-match');
    if (ifNoneMatch !== null && /^"[0-9a-f]{64}"$/.test(ifNoneMatch.trim())) {
      headers.set('If-None-Match', ifNoneMatch.trim());
    }
  }

  let upstream: Response;
  try {
    upstream = await (options.fetchImplementation ?? globalThis.fetch)(
      new URL(
        `${apiPath}${requestUrl.search}`,
        internalApiOrigin(options.internalApiOrigin),
      ),
      {
        body,
        cache: 'no-store',
        headers,
        method: request.method,
        redirect: 'error',
      },
    );
  } catch {
    return errorResponse(
      502,
      'BOARD_SEARCH_SHARE_UPSTREAM_UNAVAILABLE',
      'The shared board search is temporarily unavailable.',
    );
  }

  if (route.kind === 'unlock') {
    return upstream.ok
      ? unlockedResponse(upstream)
      : filteredJsonResponse(upstream);
  }
  if (route.kind === 'image' && upstream.ok) return imageResponse(upstream);
  if (route.kind === 'image' && upstream.status === 304) {
    return new Response(null, { headers: imageHeaders(upstream), status: 304 });
  }
  const response = await filteredJsonResponse(upstream);
  return upstream.status === 401 ? withClearedCookie(response) : response;
}

function publicPathToApiPath(pathname: string): string {
  if (!pathname.startsWith(`${BOARD_SEARCH_SHARE_PUBLIC_PREFIX}/`)) return '';
  return pathname.slice(BOARD_SEARCH_SHARE_PUBLIC_PREFIX.length);
}

function validateRequestOrigin(request: Request): Response | null {
  const fetchSite = request.headers.get('sec-fetch-site');
  const mutation = request.method !== 'GET';
  if (
    (mutation && fetchSite !== 'same-origin') ||
    (!mutation && fetchSite !== null && fetchSite !== 'same-origin')
  ) {
    return originForbidden();
  }
  const origin = request.headers.get('origin');
  if (mutation && origin === null) return originForbidden();
  if (origin === null) return null;
  try {
    const parsed = new URL(origin);
    const host = (request.headers.get('host') ?? new URL(request.url).host)
      .trim()
      .toLowerCase();
    if (host === '' || parsed.host.toLowerCase() !== host)
      return originForbidden();
    if (parsed.protocol === 'https:') return null;
    return parsed.protocol === 'http:' && LOOPBACK_HOSTS.has(parsed.hostname)
      ? null
      : originForbidden();
  } catch {
    return originForbidden();
  }
}

function internalApiOrigin(configured: string | undefined): string {
  // Same override as the Reviewer's own proxy; loopback is still enforced.
  const parsed = new URL(
    (
      configured ??
      process.env.REVIEWER_INTERNAL_API_ORIGIN ??
      DEFAULT_INTERNAL_API
    ).trim(),
  );
  if (parsed.protocol !== 'http:' || !LOOPBACK_HOSTS.has(parsed.hostname)) {
    throw new Error('Reviewer internal API must remain on HTTP loopback.');
  }
  return parsed.origin;
}

async function unlockedResponse(upstream: Response): Promise<Response> {
  const body = await boundedBody(upstream, BOARD_SEARCH_SHARE_MAX_JSON_BYTES);
  if (body === null || !isJson(upstream)) return invalidUpstream();
  let payload: unknown;
  try {
    payload = JSON.parse(new TextDecoder().decode(body));
  } catch {
    return invalidUpstream();
  }
  if (!isRecord(payload) || containsSensitiveData(payload))
    return invalidUpstream();
  const token = upstreamCookie(upstream.headers.get('set-cookie'));
  const expiresAt = payload.expiresAt;
  if (token === null || typeof expiresAt !== 'string') return invalidUpstream();
  const expiry = new Date(expiresAt);
  if (!Number.isFinite(expiry.getTime())) return invalidUpstream();
  const maxAge = Math.max(
    0,
    Math.min(24 * 60 * 60, Math.floor((expiry.getTime() - Date.now()) / 1000)),
  );
  const headers = jsonHeaders();
  headers.append(
    'Set-Cookie',
    `${BOARD_SEARCH_SHARE_COOKIE}=${token}; Max-Age=${maxAge}; ` +
      `Expires=${expiry.toUTCString()}; Path=${BOARD_SEARCH_SHARE_COOKIE_PATH}; ` +
      'HttpOnly; Secure; SameSite=Strict',
  );
  return new Response(JSON.stringify(payload), {
    headers,
    status: upstream.status,
  });
}

function upstreamCookie(value: string | null): string | null {
  const match = value?.match(
    new RegExp(`(?:^|[,;]\\s*)${BOARD_SEARCH_SHARE_COOKIE}=([^;,\\s]+)`),
  );
  const token = match?.[1] ?? null;
  return token !== null && TOKEN.test(token) ? token : null;
}

async function filteredJsonResponse(upstream: Response): Promise<Response> {
  const body = await boundedBody(upstream, BOARD_SEARCH_SHARE_MAX_JSON_BYTES);
  if (body === null || !isJson(upstream)) return invalidUpstream();
  try {
    const payload: unknown = JSON.parse(new TextDecoder().decode(body));
    if (containsSensitiveData(payload)) return invalidUpstream();
  } catch {
    return invalidUpstream();
  }
  return new Response(body, {
    headers: jsonHeaders(),
    status: upstream.status,
  });
}

async function imageResponse(upstream: Response): Promise<Response> {
  const contentType = upstream.headers
    .get('content-type')
    ?.split(';', 1)[0]
    ?.trim()
    .toLowerCase();
  if (contentType === undefined || !IMAGE_TYPES.has(contentType))
    return invalidUpstream();
  const body = await boundedBody(upstream, BOARD_SEARCH_SHARE_MAX_IMAGE_BYTES);
  if (body === null) return invalidUpstream();
  const headers = imageHeaders(upstream);
  headers.set('Content-Type', contentType);
  return new Response(body, { headers, status: 200 });
}

/** Keeps the API's validators; caps any browser caching at one day. */
function imageHeaders(upstream: Response): Headers {
  const headers = new Headers();
  const etag = upstream.headers.get('etag');
  if (etag !== null && /^"[0-9a-f]{64}"$/.test(etag)) headers.set('ETag', etag);
  headers.set(
    'Cache-Control',
    cappedCacheControl(upstream.headers.get('cache-control')),
  );
  return headers;
}

export function cappedCacheControl(value: string | null): string {
  const directives = (value ?? '').toLowerCase();
  if (!directives.includes('immutable')) return 'private, no-cache';
  const maxAge = Number(/max-age=(\d+)/.exec(directives)?.[1] ?? '0');
  const capped = Math.min(
    Number.isFinite(maxAge) ? maxAge : 0,
    BOARD_SEARCH_SHARE_MAX_IMAGE_AGE_SECONDS,
  );
  return capped > 0
    ? `private, immutable, max-age=${capped}`
    : 'private, no-cache';
}

async function boundedBody(
  upstream: Response,
  limit: number,
): Promise<Uint8Array<ArrayBuffer> | null> {
  const declared = Number(upstream.headers.get('content-length') ?? '0');
  if (!Number.isFinite(declared) || declared < 0 || declared > limit)
    return null;
  if (upstream.body === null) return new Uint8Array();
  const reader = upstream.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      total += chunk.value.byteLength;
      if (total > limit) {
        await reader.cancel();
        return null;
      }
      chunks.push(chunk.value);
    }
  } catch {
    return null;
  }
  const joined = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    joined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return joined;
}

function isJson(upstream: Response): boolean {
  return (
    upstream.headers
      .get('content-type')
      ?.split(';', 1)[0]
      ?.trim()
      .toLowerCase() === 'application/json'
  );
}

export function containsSensitiveData(payload: unknown): boolean {
  if (typeof payload === 'string') return WINDOWS_ABSOLUTE_PATH.test(payload);
  if (Array.isArray(payload)) return payload.some(containsSensitiveData);
  if (!isRecord(payload)) return false;
  for (const [key, value] of Object.entries(payload)) {
    const normalized = key
      .replaceAll('_', '')
      .replaceAll('-', '')
      .toLowerCase();
    if (FORBIDDEN_RESPONSE_KEYS.has(normalized)) return true;
    // Owner-typed names may contain text that looks like a path; they are
    // display strings, never storage details.
    if (typeof value === 'string' && FREE_TEXT_KEYS.has(normalized)) continue;
    if (containsSensitiveData(value)) return true;
  }
  return false;
}

function readCookie(header: string | null, name: string): string | null {
  if (header === null) return null;
  for (const rawPart of header.split(';')) {
    const separator = rawPart.indexOf('=');
    if (separator < 0 || rawPart.slice(0, separator).trim() !== name) continue;
    return rawPart.slice(separator + 1).trim();
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function jsonHeaders(): Headers {
  return new Headers({
    'Cache-Control': 'no-store',
    'Content-Type': 'application/json',
  });
}

function withClearedCookie(response: Response): Response {
  response.headers.append(
    'Set-Cookie',
    `${BOARD_SEARCH_SHARE_COOKIE}=; Max-Age=0; Path=${BOARD_SEARCH_SHARE_COOKIE_PATH}; ` +
      'HttpOnly; Secure; SameSite=Strict',
  );
  return response;
}

function errorResponse(
  status: number,
  code: string,
  message: string,
): Response {
  return new Response(JSON.stringify({ code, message }), {
    headers: jsonHeaders(),
    status,
  });
}

function forbidden(): Response {
  return errorResponse(
    403,
    'BOARD_SEARCH_SHARE_ROUTE_FORBIDDEN',
    'Route is not public.',
  );
}

function originForbidden(): Response {
  return errorResponse(
    403,
    'BOARD_SEARCH_SHARE_ORIGIN_FORBIDDEN',
    'The request origin is not allowed.',
  );
}

function tooLarge(): Response {
  return errorResponse(
    413,
    'BOARD_SEARCH_SHARE_REQUEST_TOO_LARGE',
    'The request is too large.',
  );
}

function invalidUpstream(): Response {
  return errorResponse(
    502,
    'BOARD_SEARCH_SHARE_UPSTREAM_INVALID',
    'The shared board search returned an invalid response.',
  );
}

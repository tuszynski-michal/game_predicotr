import { remoteSelectionProxyTarget } from './reviewer-proxy-policy.ts';

export const REMOTE_SELECTION_PUBLIC_COOKIE = 'gp_remote_selection_token';
export const REMOTE_SELECTION_PUBLIC_COOKIE_PATH = '/selection-api';
export const REMOTE_SELECTION_PROXY_INTENT = 'reviewer-v1';
export const REMOTE_SELECTION_MAX_CONTROL_BYTES = 128 * 1024;

const INTERNAL_COOKIE = 'remote_manual_selection_access';
const DEFAULT_INTERNAL_API = 'http://127.0.0.1:8000';
const PUBLIC_PREFIX = '/selection-api';
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);
const TOKEN = /^[A-Za-z0-9_-]{32,256}$/;

type RemoteSelectionProxyOptions = {
  readonly fetchImplementation?: typeof globalThis.fetch;
  readonly internalApiOrigin?: string;
  readonly remoteSelectionEnabled?: boolean;
};

export function isRemoteManualSelectionEnabled(
  configured = process.env.GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED,
): boolean {
  if (configured === undefined) return true;
  const normalized = configured.trim().toLowerCase();
  if (['1', 'true', 'yes', 'on'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off'].includes(normalized)) return false;
  return false;
}

export async function proxyRemoteSelectionRequest(
  request: Request,
  options: RemoteSelectionProxyOptions = {},
): Promise<Response> {
  if (!(options.remoteSelectionEnabled ?? isRemoteManualSelectionEnabled())) {
    return errorResponse(
      404,
      'REMOTE_SELECTION_ROUTE_DISABLED',
      'Remote manual selection is disabled.',
    );
  }

  const requestUrl = new URL(request.url);
  const incomingPath = publicPathToApiPath(requestUrl.pathname);
  const targetPath = remoteSelectionProxyTarget(request.method, incomingPath);
  if (targetPath === null) return forbidden();
  if (
    !isAllowedControlQuery(request.method, targetPath, requestUrl.searchParams)
  ) {
    return forbidden();
  }

  const originError = validateRequestOrigin(request);
  if (originError !== null) return originError;

  const declaredLength = Number(request.headers.get('content-length') ?? '0');
  if (
    !Number.isFinite(declaredLength) ||
    declaredLength < 0 ||
    declaredLength > REMOTE_SELECTION_MAX_CONTROL_BYTES
  ) {
    return tooLarge();
  }

  const isUnlock = targetPath.endsWith('/unlock');
  const publicToken = readCookie(
    request.headers.get('cookie'),
    REMOTE_SELECTION_PUBLIC_COOKIE,
  );
  if (!isUnlock && (publicToken === null || !TOKEN.test(publicToken))) {
    return errorResponse(
      401,
      'REMOTE_SELECTION_TOKEN_REQUIRED',
      'Remote selection access token is required.',
    );
  }

  let body: ArrayBuffer | undefined;
  if (request.method !== 'GET') {
    const contentType = request.headers.get('content-type')?.split(';', 1)[0];
    if (contentType?.trim().toLowerCase() !== 'application/json') {
      return errorResponse(
        415,
        'REMOTE_SELECTION_CONTENT_TYPE_INVALID',
        'Remote selection control requests must use application/json.',
      );
    }
    body = await request.arrayBuffer();
    if (body.byteLength > REMOTE_SELECTION_MAX_CONTROL_BYTES) return tooLarge();
  }

  const headers = new Headers({
    Accept: 'application/json',
    'X-Remote-Selection-Proxy': REMOTE_SELECTION_PROXY_INTENT,
  });
  const clientInstanceId = request.headers.get('x-remote-selection-client');
  if (clientInstanceId !== null) {
    headers.set('X-Remote-Selection-Client', clientInstanceId);
  }
  if (body !== undefined) headers.set('Content-Type', 'application/json');
  if (!isUnlock && publicToken !== null) {
    headers.set('Cookie', `${INTERNAL_COOKIE}=${publicToken}`);
  }

  let upstream: Response;
  try {
    upstream = await (options.fetchImplementation ?? globalThis.fetch)(
      new URL(
        `${targetPath}${requestUrl.search}`,
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
      'REMOTE_SELECTION_UPSTREAM_UNAVAILABLE',
      'Remote selection API is unavailable.',
    );
  }

  if (isUnlock && upstream.ok) {
    return unlockedResponse(upstream);
  }

  const response = await filteredUpstreamResponse(upstream);
  if (upstream.status === 401) clearPublicCookie(response.headers);
  return response;
}

function isAllowedControlQuery(
  method: string,
  path: string,
  parameters: URLSearchParams,
): boolean {
  if (parameters.size === 0) return true;
  if (method !== 'GET' || !path.endsWith('/state')) return false;
  const allowed = new Set(['sinceRevision', 'limit']);
  for (const [key, value] of parameters) {
    if (!allowed.has(key) || !/^\d{1,16}$/.test(value)) return false;
    if (parameters.getAll(key).length !== 1) return false;
  }
  return true;
}

function publicPathToApiPath(pathname: string): string {
  if (!pathname.startsWith(`${PUBLIC_PREFIX}/`)) return '';
  return pathname.slice(PUBLIC_PREFIX.length);
}

function validateRequestOrigin(request: Request): Response | null {
  const fetchSite = request.headers.get('sec-fetch-site');
  if (fetchSite !== null && fetchSite !== 'same-origin') {
    return originForbidden();
  }
  const origin = request.headers.get('origin');
  if (request.method !== 'GET' && origin === null) return originForbidden();
  if (origin === null) return null;
  try {
    if (new URL(origin).origin !== expectedPublicOrigin(request)) {
      return originForbidden();
    }
  } catch {
    return originForbidden();
  }
  return null;
}

function expectedPublicOrigin(request: Request): string {
  const requestUrl = new URL(request.url);
  const forwardedHost = firstForwardedValue(
    request.headers.get('x-forwarded-host'),
  );
  const host = forwardedHost ?? request.headers.get('host') ?? requestUrl.host;
  const forwardedProtocol = firstForwardedValue(
    request.headers.get('x-forwarded-proto'),
  );
  const protocol = forwardedProtocol ?? requestUrl.protocol.replace(':', '');
  if (!/^[A-Za-z0-9.:[\]-]+(?::\d{1,5})?$/.test(host)) {
    throw new Error('Invalid public host.');
  }
  const hostname = new URL(`${protocol}://${host}`).hostname;
  if (
    protocol !== 'https' &&
    !(protocol === 'http' && LOOPBACK_HOSTS.has(hostname))
  ) {
    throw new Error('Remote selection requires HTTPS or HTTP loopback.');
  }
  return `${protocol}://${host}`;
}

function firstForwardedValue(value: string | null): string | null {
  const first = value?.split(',', 1)[0]?.trim();
  return first === undefined || first === '' ? null : first;
}

function internalApiOrigin(configured: string | undefined): string {
  const parsed = new URL((configured ?? DEFAULT_INTERNAL_API).trim());
  if (parsed.protocol !== 'http:' || !LOOPBACK_HOSTS.has(parsed.hostname)) {
    throw new Error('Reviewer internal API must remain on HTTP loopback.');
  }
  return parsed.origin;
}

async function unlockedResponse(upstream: Response): Promise<Response> {
  const body = await boundedUpstreamBody(upstream);
  if (body === null || !isJsonResponse(upstream)) return invalidUpstream();
  let payload: unknown;
  try {
    payload = JSON.parse(new TextDecoder().decode(body));
  } catch {
    return invalidUpstream();
  }
  if (!isRecord(payload) || containsPublicSecretField(payload)) {
    return invalidUpstream();
  }
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
    `${REMOTE_SELECTION_PUBLIC_COOKIE}=${token}; Max-Age=${maxAge}; ` +
      `Expires=${expiry.toUTCString()}; Path=${REMOTE_SELECTION_PUBLIC_COOKIE_PATH}; ` +
      'HttpOnly; Secure; SameSite=Strict',
  );
  return new Response(JSON.stringify(payload), {
    headers,
    status: upstream.status,
  });
}

function upstreamCookie(value: string | null): string | null {
  const match = value?.match(
    new RegExp(`(?:^|[,;]\\s*)${INTERNAL_COOKIE}=([^;,\\s]+)`),
  );
  const token = match?.[1] ?? null;
  return token !== null && TOKEN.test(token) ? token : null;
}

async function filteredUpstreamResponse(upstream: Response): Promise<Response> {
  const body = await boundedUpstreamBody(upstream);
  if (body === null || !isJsonResponse(upstream)) return invalidUpstream();
  const headers = new Headers({ 'Cache-Control': 'no-store' });
  for (const name of ['content-type', 'etag']) {
    const value = upstream.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  return new Response(body, { headers, status: upstream.status });
}

async function boundedUpstreamBody(
  upstream: Response,
): Promise<Uint8Array<ArrayBuffer> | null> {
  const declaredLength = Number(upstream.headers.get('content-length') ?? '0');
  if (
    !Number.isFinite(declaredLength) ||
    declaredLength < 0 ||
    declaredLength > REMOTE_SELECTION_MAX_CONTROL_BYTES
  ) {
    return null;
  }
  if (upstream.body === null) return new Uint8Array();
  const reader = upstream.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      total += chunk.value.byteLength;
      if (total > REMOTE_SELECTION_MAX_CONTROL_BYTES) {
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

function isJsonResponse(upstream: Response): boolean {
  return (
    upstream.headers
      .get('content-type')
      ?.split(';', 1)[0]
      ?.trim()
      .toLowerCase() === 'application/json'
  );
}

function clearPublicCookie(headers: Headers): void {
  headers.append(
    'Set-Cookie',
    `${REMOTE_SELECTION_PUBLIC_COOKIE}=; Max-Age=0; ` +
      `Path=${REMOTE_SELECTION_PUBLIC_COOKIE_PATH}; HttpOnly; Secure; SameSite=Strict`,
  );
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

function containsPublicSecretField(payload: Record<string, unknown>): boolean {
  return [
    'accessToken',
    'access_token',
    'token',
    'hostBasePath',
    'host_base_path',
  ].some((key) => key in payload);
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
    'REMOTE_SELECTION_ROUTE_FORBIDDEN',
    'Route is not public.',
  );
}

function originForbidden(): Response {
  return errorResponse(
    403,
    'REMOTE_SELECTION_ORIGIN_FORBIDDEN',
    'Remote selection request origin is not allowed.',
  );
}

function tooLarge(): Response {
  return errorResponse(
    413,
    'REMOTE_SELECTION_REQUEST_TOO_LARGE',
    'Remote selection control request is too large.',
  );
}

function invalidUpstream(): Response {
  return errorResponse(
    502,
    'REMOTE_SELECTION_UPSTREAM_INVALID',
    'Remote selection unlock response is invalid.',
  );
}

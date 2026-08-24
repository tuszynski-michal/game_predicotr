import { remoteSelectionProxyTarget } from './reviewer-proxy-policy.ts';

export const REMOTE_SELECTION_PUBLIC_COOKIE = 'gp_remote_selection_token';
export const REMOTE_SELECTION_PUBLIC_COOKIE_PATH = '/selection-api';
export const REMOTE_SELECTION_PROXY_INTENT = 'reviewer-v1';
export const REMOTE_SELECTION_MAX_CONTROL_BYTES = 128 * 1024;
export const REMOTE_SELECTION_MAX_BINARY_BYTES = 32 * 1024 * 1024;

const INTERNAL_COOKIE = 'remote_manual_selection_access';
const DEFAULT_INTERNAL_API = 'http://127.0.0.1:8000';
const PUBLIC_PREFIX = '/selection-api';
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);
const TOKEN = /^[A-Za-z0-9_-]{32,256}$/;
const STRICT_UUID =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$/;
const WINDOWS_ABSOLUTE_PATH = /(?:^|[\s"'])(?:[a-zA-Z]:[\\/]|[\\/]{2})[^\s"']+/;
const FORBIDDEN_PUBLIC_RESPONSE_KEYS = new Set([
  'accesscode',
  'accesstoken',
  'absolutepath',
  'authorization',
  'basepath',
  'codehash',
  'codesalt',
  'cookie',
  'hostbasepath',
  'hostpath',
  'leasetoken',
  'secret',
  'temppath',
  'token',
  'tokenhash',
  'verifiedrelativepath',
  'verifiedpath',
]);

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

  const isBinaryTransfer =
    request.method === 'PUT' && targetPath.endsWith('/content');

  const declaredLength = Number(request.headers.get('content-length') ?? '0');
  if (
    !Number.isFinite(declaredLength) ||
    declaredLength < 0 ||
    declaredLength >
      (isBinaryTransfer
        ? REMOTE_SELECTION_MAX_BINARY_BYTES
        : REMOTE_SELECTION_MAX_CONTROL_BYTES) ||
    (isBinaryTransfer && declaredLength < 1)
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

  let body: ArrayBuffer | ReadableStream<Uint8Array> | undefined;
  if (request.method !== 'GET') {
    const contentType = request.headers.get('content-type')?.split(';', 1)[0];
    const expectedContentType = isBinaryTransfer
      ? 'application/octet-stream'
      : 'application/json';
    if (contentType?.trim().toLowerCase() !== expectedContentType) {
      return errorResponse(
        415,
        'REMOTE_SELECTION_CONTENT_TYPE_INVALID',
        `Remote selection requests must use ${expectedContentType}.`,
      );
    }
    if (isBinaryTransfer) {
      if (request.body === null) return tooLarge();
      body = request.body;
    } else {
      body = await request.arrayBuffer();
      if (body.byteLength > REMOTE_SELECTION_MAX_CONTROL_BYTES)
        return tooLarge();
    }
  }

  const headers = new Headers({
    Accept: 'application/json',
    'X-Remote-Selection-Proxy': REMOTE_SELECTION_PROXY_INTENT,
  });
  const clientInstanceId = request.headers.get('x-remote-selection-client');
  if (clientInstanceId !== null) {
    if (!STRICT_UUID.test(clientInstanceId)) {
      return errorResponse(
        422,
        'REMOTE_SELECTION_CLIENT_INVALID',
        'The remote selection client identifier is invalid.',
      );
    }
    headers.set('X-Remote-Selection-Client', clientInstanceId);
  }
  if (body !== undefined) {
    headers.set(
      'Content-Type',
      isBinaryTransfer ? 'application/octet-stream' : 'application/json',
    );
  }
  if (isBinaryTransfer) {
    headers.set('Content-Length', String(declaredLength));
    const transferHeaders = [
      'x-remote-selection-transfer-id',
      'x-remote-selection-generation',
      'x-remote-selection-source-mtime',
      'x-remote-selection-checksum-sha256',
    ] as const;
    const patterns: Record<(typeof transferHeaders)[number], RegExp> = {
      'x-remote-selection-transfer-id':
        /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$/,
      'x-remote-selection-generation': /^[1-9]\d{0,15}$/,
      'x-remote-selection-source-mtime': /^\d{1,16}$/,
      'x-remote-selection-checksum-sha256': /^[0-9a-f]{64}$/,
    };
    for (const name of transferHeaders) {
      const value = request.headers.get(name);
      if (value === null || !patterns[name].test(value)) {
        return errorResponse(
          422,
          'REMOTE_SELECTION_TRANSFER_HEADER_INVALID',
          `The ${name} header is missing or invalid.`,
        );
      }
      headers.set(name, value);
    }
  }
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
        ...(isBinaryTransfer ? { duplex: 'half' } : {}),
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
  if (parameters.size === 0) {
    return !(method === 'GET' && path.endsWith('/transfer'));
  }
  if (method !== 'GET') return false;
  const allowed = path.endsWith('/state')
    ? new Set(['sinceRevision', 'limit'])
    : path.endsWith('/transfer')
      ? new Set(['generation', 'transferId'])
      : new Set<string>();
  if (allowed.size === 0) return false;
  for (const [key, value] of parameters) {
    if (!allowed.has(key)) return false;
    if (key === 'transferId') {
      if (!STRICT_UUID.test(value)) return false;
    } else if (!/^\d{1,16}$/.test(value)) return false;
    if (parameters.getAll(key).length !== 1) return false;
  }
  if (path.endsWith('/transfer') && parameters.get('generation') === null) {
    return false;
  }
  return true;
}

function publicPathToApiPath(pathname: string): string {
  if (!pathname.startsWith(`${PUBLIC_PREFIX}/`)) return '';
  return pathname.slice(PUBLIC_PREFIX.length);
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
    if (!originMatchesRequestHost(origin, request)) {
      return originForbidden();
    }
  } catch {
    return originForbidden();
  }
  return null;
}

function originMatchesRequestHost(origin: string, request: Request): boolean {
  const parsedOrigin = new URL(origin);
  const requestHost = (request.headers.get('host') ?? new URL(request.url).host)
    .trim()
    .toLowerCase();
  if (requestHost === '' || parsedOrigin.host.toLowerCase() !== requestHost) {
    return false;
  }
  if (parsedOrigin.protocol === 'https:') return true;
  return (
    parsedOrigin.protocol === 'http:' &&
    LOOPBACK_HOSTS.has(parsedOrigin.hostname)
  );
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
  if (!isRecord(payload) || containsSensitivePublicData(payload)) {
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
  try {
    const payload: unknown = JSON.parse(new TextDecoder().decode(body));
    if (containsSensitivePublicData(payload)) return invalidUpstream();
  } catch {
    return invalidUpstream();
  }
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

function containsSensitivePublicData(payload: unknown): boolean {
  if (typeof payload === 'string') return WINDOWS_ABSOLUTE_PATH.test(payload);
  if (Array.isArray(payload)) return payload.some(containsSensitivePublicData);
  if (!isRecord(payload)) return false;
  for (const [key, value] of Object.entries(payload)) {
    const normalized = key
      .replaceAll('_', '')
      .replaceAll('-', '')
      .toLowerCase();
    if (FORBIDDEN_PUBLIC_RESPONSE_KEYS.has(normalized)) return true;
    if (containsSensitivePublicData(value)) return true;
  }
  return false;
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

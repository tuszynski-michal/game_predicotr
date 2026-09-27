const hosts = new Set(['127.0.0.1:3102', 'localhost:3102']);
const origins = new Set(['http://127.0.0.1:3102', 'http://localhost:3102']);

export function boundary(request: Request): Response | null {
  if (!hosts.has(request.headers.get('host') ?? ''))
    return new Response('HOST_FORBIDDEN', { status: 403 });
  const origin = request.headers.get('origin');
  if (origin !== null && !origins.has(origin))
    return new Response('ORIGIN_FORBIDDEN', { status: 403 });
  if (!['GET', 'HEAD'].includes(request.method)) {
    if (!origins.has(origin ?? ''))
      return new Response('ORIGIN_REQUIRED', { status: 403 });
    if (
      request.headers.get('content-type')?.split(';')[0].trim() !==
      'application/json'
    )
      return new Response('JSON_REQUIRED', { status: 415 });
  }
  return null;
}

export function allowedRoute(method: string, parts: string[]): boolean {
  return (
    (method === 'GET' &&
      parts.length === 1 &&
      [
        'sources',
        'annotations',
        'timings',
        'runs',
        'symbols',
        'symbol-dictionaries',
      ].includes(parts[0])) ||
    (method === 'POST' &&
      parts.length === 1 &&
      [
        'geometry',
        'annotations',
        'families',
        'splits',
        'backups',
        'runs',
        'symbols',
        'symbol-crops',
        'symbol-backups',
      ].includes(parts[0])) ||
    (method === 'GET' &&
      parts.length === 3 &&
      parts[0] === 'symbol-dictionaries' &&
      /^[A-Za-z0-9_-]{1,100}$/.test(parts[1]) &&
      /^[1-9][0-9]*$/.test(parts[2])) ||
    (parts[0] === 'runs' &&
      /^[a-f0-9]{32}$/.test(parts[1] ?? '') &&
      ((method === 'GET' && parts.length === 2) ||
        (method === 'POST' &&
          parts.length === 3 &&
          ['cancel', 'retry'].includes(parts[2])))) ||
    (method === 'GET' &&
      parts.length === 2 &&
      parts[0] === 'assets' &&
      /^[a-f0-9]{64}$/.test(parts[1]))
  );
}

export function allowedQuery(
  parts: string[],
  query: URLSearchParams,
  method = 'GET',
): boolean {
  if (method !== 'GET') return [...query.keys()].length === 0;
  const keys =
    parts.length === 1 && parts[0] === 'sources'
      ? ['offset', 'limit', 'game']
      : parts.length === 1 && parts[0] === 'runs'
        ? ['offset', 'limit']
        : parts.length === 1 && parts[0] === 'symbols'
          ? ['offset', 'limit', 'game_id', 'source_id', 'read_token']
          : parts.length === 1 && parts[0] === 'symbol-dictionaries'
            ? ['offset', 'limit', 'game_id', 'read_token']
            : [];
  return [...query.keys()].every((key) => keys.includes(key));
}

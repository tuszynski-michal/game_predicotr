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
      ['sources', 'annotations', 'timings'].includes(parts[0])) ||
    (method === 'POST' &&
      parts.length === 1 &&
      ['geometry', 'annotations', 'families', 'splits', 'backups'].includes(
        parts[0],
      )) ||
    (method === 'GET' &&
      parts.length === 2 &&
      parts[0] === 'assets' &&
      /^[a-f0-9]{64}$/.test(parts[1]))
  );
}

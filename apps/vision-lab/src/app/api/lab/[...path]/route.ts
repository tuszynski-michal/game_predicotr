import { allowedRoute, boundary } from '../../../../lib/boundary';

async function forward(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const blocked = boundary(request);
  if (blocked) return blocked;
  const { path } = await context.params;
  if (!allowedRoute(request.method, path))
    return new Response('ROUTE_FORBIDDEN', { status: 404 });
  const url = new URL(request.url);
  if (
    [...url.searchParams.keys()].some(
      (key) => !['offset', 'limit', 'game'].includes(key),
    ) ||
    (path[0] !== 'sources' && url.search)
  )
    return new Response('QUERY_FORBIDDEN', { status: 400 });
  const body = request.method === 'POST' ? await request.text() : undefined;
  if (body && body.length > 4096)
    return new Response('BODY_TOO_LARGE', { status: 413 });
  try {
    const response = await fetch(
      `http://127.0.0.1:8102/${path.join('/')}${url.search}`,
      {
        method: request.method,
        body,
        cache: 'no-store',
        redirect: 'error',
        headers: {
          'Content-Type': 'application/json',
          ...(request.headers.get('origin')
            ? { Origin: request.headers.get('origin')! }
            : {}),
        },
        signal: AbortSignal.timeout(60000),
      },
    );
    return new Response(response.body, {
      status: response.status,
      headers: {
        'Content-Type':
          response.headers.get('content-type') ?? 'application/json',
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
      },
    });
  } catch {
    return new Response('LAB_UNAVAILABLE', { status: 502 });
  }
}
export const GET = forward;
export const POST = forward;

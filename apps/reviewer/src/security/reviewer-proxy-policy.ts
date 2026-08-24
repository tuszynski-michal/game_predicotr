const UUID = '[0-9a-fA-F-]{36}';
const STRICT_UUID =
  '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}';

export function remoteSelectionProxyTarget(
  method: string,
  path: string,
): string | null {
  if (
    method === 'POST' &&
    new RegExp(
      `^/api/v1/remote-manual-selections/sessions/${STRICT_UUID}/unlock$`,
    ).test(path)
  ) {
    return path;
  }
  if (method === 'GET' && path === '/api/v1/remote-manual-selections/context') {
    return path;
  }
  if (
    method === 'POST' &&
    new RegExp(
      `^/api/v1/remote-manual-selections/sessions/${STRICT_UUID}/writer-lease/(?:heartbeat|takeover)$`,
    ).test(path)
  ) {
    return path;
  }
  if (
    method === 'POST' &&
    path === '/api/v1/remote-manual-selections/collections'
  ) {
    return path;
  }
  if (
    method === 'POST' &&
    new RegExp(
      `^/api/v1/remote-manual-selections/collections/${STRICT_UUID}/batches$`,
    ).test(path)
  ) {
    return path;
  }
  if (
    method === 'POST' &&
    new RegExp(
      `^/api/v1/remote-manual-selections/batches/${STRICT_UUID}/(?:source-items|operations)$`,
    ).test(path)
  ) {
    return path;
  }
  if (
    method === 'GET' &&
    new RegExp(
      `^/api/v1/remote-manual-selections/batches/${STRICT_UUID}/state$`,
    ).test(path)
  ) {
    return path;
  }
  return null;
}

export function reviewerProxyTarget(
  method: string,
  path: string,
): string | null {
  if (
    method === 'POST' &&
    new RegExp(`^/api/v1/reviewer/sessions/${UUID}/unlock$`).test(path)
  ) {
    return path;
  }
  if (method === 'GET' && path === '/api/v1/admin/games') {
    return '/api/v1/reviewer/context/games';
  }
  if (method === 'GET' && path === '/api/v1/admin/jobs') {
    return '/api/v1/reviewer/context/jobs';
  }
  const symbolMatch = path.match(
    new RegExp(`^/api/v1/admin/games/(${UUID})/symbols$`),
  );
  if (method === 'GET' && symbolMatch?.[1] !== undefined) {
    return `/api/v1/reviewer/context/games/${symbolMatch[1]}/symbols`;
  }
  const pendingGeometryCollectionPattern = new RegExp(
    `^/api/v1/admin/games/${UUID}/image-imports/${UUID}/board-cell-geometry-pending$`,
  );
  const pendingGeometryItemPattern = new RegExp(
    `${pendingGeometryCollectionPattern.source.slice(0, -1)}/${UUID}$`,
  );
  if (
    method === 'GET' &&
    (pendingGeometryCollectionPattern.test(path) ||
      pendingGeometryItemPattern.test(path))
  ) {
    return path;
  }
  if (
    method === 'GET' &&
    new RegExp(
      `${pendingGeometryItemPattern.source.slice(0, -1)}/(?:correction-context|source)$`,
    ).test(path)
  ) {
    return path;
  }
  if (
    method === 'POST' &&
    new RegExp(
      `${pendingGeometryItemPattern.source.slice(0, -1)}/(?:geometry-preview|manual-resolution)$`,
    ).test(path)
  ) {
    return path;
  }
  if (!path.startsWith('/api/v1/admin/image-review-items')) {
    return null;
  }
  if (
    method === 'GET' &&
    new RegExp(
      `^/api/v1/admin/image-review-items(?:/${UUID}(?:/resolution-events|/assets/(?:source|board|cells/\\d+))?)?$`,
    ).test(path)
  ) {
    return path;
  }
  if (
    method === 'POST' &&
    new RegExp(
      `^/api/v1/admin/image-review-items/${UUID}/(?:geometry-preview|geometry-revisions|resolution)$`,
    ).test(path)
  ) {
    return path;
  }
  return null;
}

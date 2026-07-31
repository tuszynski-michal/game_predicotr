const UUID = '[0-9a-fA-F-]{36}';

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

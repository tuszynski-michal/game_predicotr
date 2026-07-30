const DEFAULT_ADMIN_API_BASE_URL = 'http://127.0.0.1:8000';
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);

export class AdminConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AdminConfigurationError';
  }
}

export function resolveAdminApiBaseUrl(
  configuredValue: string | undefined,
): string {
  const candidate = configuredValue?.trim() || DEFAULT_ADMIN_API_BASE_URL;

  let url: URL;
  try {
    url = new URL(candidate);
  } catch {
    throw new AdminConfigurationError(
      'NEXT_PUBLIC_ADMIN_API_BASE_URL must be a valid absolute URL.',
    );
  }

  if (url.protocol !== 'http:') {
    throw new AdminConfigurationError(
      'Local Admin API must use the http protocol.',
    );
  }

  if (!LOOPBACK_HOSTS.has(url.hostname)) {
    throw new AdminConfigurationError(
      'Local Admin API must use localhost or a loopback address.',
    );
  }

  if (
    url.username ||
    url.password ||
    (url.pathname !== '' && url.pathname !== '/') ||
    url.search ||
    url.hash
  ) {
    throw new AdminConfigurationError(
      'Admin API base URL cannot contain credentials, a path, query, or fragment.',
    );
  }

  return url.origin;
}

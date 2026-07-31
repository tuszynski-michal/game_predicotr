const DEFAULT_ADMIN_API_BASE_URL = '/review-api';
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);

export function resolveAdminApiBaseUrl(value: string | undefined): string {
  const candidate = (value ?? DEFAULT_ADMIN_API_BASE_URL).trim();
  if (candidate === '/review-api') return candidate;
  const parsed = new URL(candidate);
  if (parsed.protocol !== 'http:' || !LOOPBACK_HOSTS.has(parsed.hostname)) {
    throw new Error('Reviewer API must use a local HTTP loopback address.');
  }
  return parsed.origin;
}

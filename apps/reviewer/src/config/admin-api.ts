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

export function resolveLocalAdminApiBaseUrl(value: string | undefined): string {
  const candidate = (value ?? 'http://127.0.0.1:8000').trim();
  const parsed = new URL(candidate);
  if (parsed.protocol !== 'http:' || !LOOPBACK_HOSTS.has(parsed.hostname)) {
    throw new Error('Local Reviewer API must use an HTTP loopback address.');
  }
  return parsed.origin;
}

export function isLoopbackReviewerHost(value: string | null): boolean {
  if (value === null || value.trim() === '') return false;
  const host = value.trim().toLowerCase();
  return (
    host === '127.0.0.1:3001' ||
    host === 'localhost:3001' ||
    host === '[::1]:3001'
  );
}

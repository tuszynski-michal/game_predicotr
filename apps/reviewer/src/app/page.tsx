import { resolveAdminApiBaseUrl } from '@/config/admin-api';
import { ReviewerAccessGate } from '@/features/access/reviewer-access-gate';

export default async function HomePage({
  searchParams,
}: {
  readonly searchParams: Promise<{ readonly session?: string | string[] }>;
}) {
  const apiBaseUrl = resolveAdminApiBaseUrl(
    process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL,
  );
  const rawSessionId = (await searchParams).session;
  const sessionId =
    typeof rawSessionId === 'string' ? rawSessionId : (rawSessionId?.[0] ?? '');
  return <ReviewerAccessGate apiBaseUrl={apiBaseUrl} sessionId={sessionId} />;
}

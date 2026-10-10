import '@game-predictor/board-search-ui/board-search.css';
import '@game-predictor/board-search-ui/management.css';
import { ManagementGate } from '@/features/management/management-gate';
import { MANAGEMENT_SESSION_ID } from '@/features/management/management-access-state';

export default async function ManagementPage({
  searchParams,
}: {
  searchParams: Promise<{ share?: string | readonly string[] }>;
}) {
  const value = (await searchParams).share;
  const candidate = typeof value === 'string' ? value : (value?.[0] ?? '');
  return (
    <ManagementGate
      key={candidate}
      sessionId={MANAGEMENT_SESSION_ID.test(candidate) ? candidate : ''}
    />
  );
}

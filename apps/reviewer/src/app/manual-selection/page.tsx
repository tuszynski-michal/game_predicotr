import { notFound } from 'next/navigation';

import { RemoteManualSelectionAccessGate } from '@/features/manual-selection/remote-manual-selection-access-gate';
import { isRemoteManualSelectionEnabled } from '@/security/remote-selection-proxy';

const SESSION_ID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default async function ManualSelectionPage({
  searchParams,
}: {
  readonly searchParams: Promise<{
    readonly session?: string | readonly string[];
  }>;
}) {
  if (!isRemoteManualSelectionEnabled()) notFound();
  const params = await searchParams;
  const rawSession = params.session;
  const candidate =
    typeof rawSession === 'string' ? rawSession : (rawSession?.[0] ?? '');
  const sessionId = SESSION_ID.test(candidate) ? candidate : '';
  return <RemoteManualSelectionAccessGate sessionId={sessionId} />;
}

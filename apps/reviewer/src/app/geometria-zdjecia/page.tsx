import { headers } from 'next/headers';
import { notFound } from 'next/navigation';

import {
  isLoopbackReviewerHost,
  resolveLocalAdminApiBaseUrl,
} from '@/config/admin-api';
import { ReviewerAccessGate } from '@/features/access/reviewer-access-gate';

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default async function PhotoGeometryPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { gameId, importJobId, sourceImageId } = await searchParams;
  const host = (await headers()).get('host');
  if (
    !isLoopbackReviewerHost(host) ||
    typeof gameId !== 'string' ||
    !UUID.test(gameId) ||
    typeof importJobId !== 'string' ||
    !UUID.test(importJobId) ||
    typeof sourceImageId !== 'string' ||
    !UUID.test(sourceImageId)
  )
    notFound();

  return (
    <ReviewerAccessGate
      apiBaseUrl={resolveLocalAdminApiBaseUrl(
        process.env.REVIEWER_INTERNAL_API_ORIGIN,
      )}
      localScope={{ gameId, importJobId, sourceImageId }}
      sessionId=""
    />
  );
}

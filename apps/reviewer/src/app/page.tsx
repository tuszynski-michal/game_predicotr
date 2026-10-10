import { headers } from 'next/headers';

import {
  isLoopbackReviewerHost,
  resolveAdminApiBaseUrl,
  resolveLocalAdminApiBaseUrl,
} from '@/config/admin-api';
import { ReviewerAccessGate } from '@/features/access/reviewer-access-gate';

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default async function HomePage({
  searchParams,
}: {
  readonly searchParams: Promise<{
    readonly gameId?: string | string[];
    readonly importJobId?: string | string[];
    readonly mode?: string | string[];
    readonly queue?: string | string[];
    readonly resultId?: string | string[];
    readonly positionIndex?: string | string[];
    readonly session?: string | string[];
  }>;
}) {
  const params = await searchParams;
  const requestHeaders = await headers();
  const value = (candidate: string | readonly string[] | undefined) =>
    typeof candidate === 'string' ? candidate : (candidate?.[0] ?? '');
  const gameId = value(params.gameId);
  const importJobId = value(params.importJobId);
  const loopbackLocal =
    value(params.mode) === 'local' &&
    isLoopbackReviewerHost(requestHeaders.get('host')) &&
    UUID.test(gameId);
  // TASK-0840: the grid-audit list spans imports, so it is scoped by game only.
  const gridAuditMode = loopbackLocal && value(params.queue) === 'grid-audit';
  const resultId = value(params.resultId);
  const rawPositionIndex = value(params.positionIndex);
  const positionIndex = Number(rawPositionIndex);
  const gridShadowMode =
    loopbackLocal &&
    value(params.queue) === 'grid-shadow' &&
    UUID.test(resultId) &&
    /^\d$/.test(rawPositionIndex) &&
    positionIndex <= 8;
  const localMode =
    loopbackLocal &&
    !gridAuditMode &&
    !gridShadowMode &&
    // TASK-0962: the import is optional; a present but malformed one is not
    // a local scope.
    (importJobId === '' || UUID.test(importJobId));
  const apiBaseUrl =
    localMode || gridAuditMode || gridShadowMode
      ? resolveLocalAdminApiBaseUrl(process.env.REVIEWER_INTERNAL_API_ORIGIN)
      : resolveAdminApiBaseUrl(process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL);
  const rawSessionId = params.session;
  const sessionId =
    typeof rawSessionId === 'string' ? rawSessionId : (rawSessionId?.[0] ?? '');
  return (
    <ReviewerAccessGate
      apiBaseUrl={apiBaseUrl}
      gridAuditScope={gridAuditMode ? { gameId } : null}
      gridShadowScope={
        gridShadowMode ? { gameId, resultId, positionIndex } : null
      }
      gridValidationEnabled={localMode}
      localScope={
        localMode
          ? {
              gameId,
              importJobId: importJobId === '' ? undefined : importJobId,
            }
          : null
      }
      sessionId={sessionId}
    />
  );
}

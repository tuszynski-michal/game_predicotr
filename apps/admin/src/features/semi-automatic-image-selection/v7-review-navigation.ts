import type { SemiAutomaticSelectionRangeResponse } from '@game-predictor/admin-api-client';

/** A link opens an existing run; it never starts analysis or publishes a photo. */
export function reviewRunId(
  href: string,
  savedRunId: string | null,
): string | null {
  const requested = new URL(href).searchParams.get('semiAutomaticRunId');
  if (requested === null) return savedRunId;
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    requested,
  )
    ? requested
    : null;
}

export function preferredV7Source(
  row: SemiAutomaticSelectionRangeResponse | null,
): number | null {
  return (
    (row?.status === 'output_synced' ? row.sourceIndex : null) ??
    row?.v7Review?.candidate?.sourceIndex ??
    row?.v7Review?.draft?.sourceIndex ??
    null
  );
}

export function v7ReviewUrl(href: string, runId: string): string {
  const url = new URL(href);
  url.searchParams.set('workspace', 'semi-automatic-image-selection');
  url.searchParams.set('semiAutomaticRunId', runId);
  return url.toString();
}

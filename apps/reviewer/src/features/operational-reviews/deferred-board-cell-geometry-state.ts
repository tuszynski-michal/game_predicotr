import type {
  BoardCellGeometryCorrectionContextResponse,
  BoardCellGeometryManualPreviewCommand,
  BoardCellGeometryManualResolutionCommand,
  BoardCellGeometryPendingReason,
  BoardCellGeometryPendingResponse,
  OperationalImageReviewGeometryPoint,
} from '@game-predictor/admin-api-client';

import type { OperationalReviewGeometryCorners } from './operational-review-state.ts';

const REASON_LABELS: Readonly<Record<BoardCellGeometryPendingReason, string>> =
  {
    incomplete_lattice: 'Niepełna siatka symboli',
    insufficient_centers: 'Za mało pewnych środków symboli',
    residual_too_high: 'Dopasowanie siatki jest zbyt niedokładne',
    source_unavailable: 'Źródło było niedostępne podczas przetwarzania',
  };

export interface DeferredBoardCellGeometryIdempotency {
  readonly commandKey: string;
  readonly idempotencyKey: string;
}

export function deferredBoardCellGeometryReasonLabel(
  reason: BoardCellGeometryPendingReason,
): string {
  return REASON_LABELS[reason];
}

export function deferredBoardCellGeometryCorners(
  context: BoardCellGeometryCorrectionContextResponse,
): OperationalReviewGeometryCorners {
  return context.suggestedCorners.map(
    copyPoint,
  ) as OperationalReviewGeometryCorners;
}

export function deferredBoardCellGeometryPreviewCommand(
  context: BoardCellGeometryCorrectionContextResponse,
  corners: OperationalReviewGeometryCorners,
): BoardCellGeometryManualPreviewCommand {
  return {
    corners,
    expectedGeometryRevision: context.item.expectedGeometryRevision,
    expectedManifestChecksumSha256:
      context.item.processingManifestChecksumSha256,
    expectedResolutionRevision: context.item.expectedReviewResolutionRevision,
  };
}

export function deferredBoardCellGeometryResolutionCommand(
  context: BoardCellGeometryCorrectionContextResponse,
  corners: OperationalReviewGeometryCorners,
  idempotencyKey: string,
): BoardCellGeometryManualResolutionCommand {
  return {
    ...deferredBoardCellGeometryPreviewCommand(context, corners),
    correctedBy: 'reviewer-operator',
    idempotencyKey,
  };
}

export function deferredBoardCellGeometryCommandKey(
  context: BoardCellGeometryCorrectionContextResponse,
  corners: OperationalReviewGeometryCorners,
): string {
  return JSON.stringify(
    deferredBoardCellGeometryPreviewCommand(context, corners),
  );
}

export function deferredBoardCellGeometryIdempotency(
  current: DeferredBoardCellGeometryIdempotency | null,
  commandKey: string,
  createKey: () => string,
): DeferredBoardCellGeometryIdempotency {
  return current?.commandKey === commandKey
    ? current
    : { commandKey, idempotencyKey: createKey() };
}

export function deferredBoardCellGeometrySourceUrl(
  apiBaseUrl: string,
  item: BoardCellGeometryPendingResponse,
): string {
  const base = apiBaseUrl.endsWith('/') ? apiBaseUrl : `${apiBaseUrl}/`;
  const path = [
    'api/v1/admin/games',
    encodeURIComponent(item.gameId),
    'image-imports',
    encodeURIComponent(item.importJobId),
    'board-cell-geometry-pending',
    encodeURIComponent(item.id),
    'source',
  ].join('/');
  const query = new URLSearchParams({ v: item.sourceChecksumSha256 });
  if (base.startsWith('/')) return `${base}${path}?${query.toString()}`;
  const url = new URL(path, base);
  url.search = query.toString();
  return url.toString();
}

function copyPoint(
  point: OperationalImageReviewGeometryPoint,
): OperationalImageReviewGeometryPoint {
  return { x: point.x, y: point.y };
}

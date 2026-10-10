import type {
  ImageGridReviewGeometryPreviewCommand,
  GridAuditQueueCountsResponse,
  OperationalImageReviewGeometryPoint,
} from '@game-predictor/admin-api-client';

import type { OperationalReviewGeometryCorners } from './operational-review-state.ts';

/** Object key order is transport detail; every preview value still has to match. */
export function gridAuditPreviewCommandsEqual(
  left: ImageGridReviewGeometryPreviewCommand,
  right: ImageGridReviewGeometryPreviewCommand,
): boolean {
  return (
    JSON.stringify(sortedValue(left)) === JSON.stringify(sortedValue(right))
  );
}

function sortedValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortedValue);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, entry]) => [key, sortedValue(entry)]),
    );
  }
  return value;
}

/**
 * Pure helpers of the grid-audit correction queue (TASK-0840). The audit
 * proposal is the network grid in `exif-normalized-rgb-pixels-v1` pixels of
 * the source photo — the same space as the stored board geometry and the
 * editor — so its four outer corners are used as they are.
 */

const AUDIT_CLASS_LABELS: Readonly<Record<string, string>> = {
  column_shift: 'przesunięcie o kolumnę',
  diagonal_shift: 'przesunięcie po przekątnej',
  row_shift: 'przesunięcie o rząd',
  scale_rotation: 'skala / obrót',
};

export function gridAuditClassLabel(auditClass: string): string {
  return AUDIT_CLASS_LABELS[auditClass] ?? auditClass;
}

/**
 * The proposal corners for the editor. A board that is not explicitly partial
 * cannot be saved with corners outside the photo, so such corners are moved
 * to the nearest photo edge (and the operator is told so).
 */
export function gridAuditSuggestedCorners(
  corners: readonly OperationalImageReviewGeometryPoint[],
  sourceWidth: number,
  sourceHeight: number,
  allowOutsideSource: boolean,
): {
  readonly clamped: boolean;
  readonly corners: OperationalReviewGeometryCorners;
} {
  if (corners.length !== 4) {
    throw new Error('Propozycja siatki musi mieć cztery narożniki.');
  }
  let clamped = false;
  const fitted = corners.map((point) => {
    const x = Math.round(point.x);
    const y = Math.round(point.y);
    if (allowOutsideSource) return { x, y };
    const inside = {
      x: Math.min(Math.max(x, 0), sourceWidth - 1),
      y: Math.min(Math.max(y, 0), sourceHeight - 1),
    };
    if (inside.x !== x || inside.y !== y) clamped = true;
    return inside;
  });
  return {
    clamped,
    corners: fitted as unknown as OperationalReviewGeometryCorners,
  };
}

/** One line of queue progress; every number is derived on each read. */
export function gridAuditProgressText(
  counts: GridAuditQueueCountsResponse,
): string {
  const parts = [
    `Do poprawy: ${counts.open.toLocaleString('pl-PL')}`,
    `poprawione: ${counts.corrected.toLocaleString('pl-PL')} z ${counts.total.toLocaleString('pl-PL')}`,
  ];
  if (counts.openWithSymbolDecisions > 0) {
    parts.push(
      `z decyzjami symboli: ${counts.openWithSymbolDecisions.toLocaleString('pl-PL')}`,
    );
  }
  const skipped = counts.stale + counts.removed + counts.noProposal;
  if (skipped > 0) {
    parts.push(
      `nieaktualne (bez propozycji): ${skipped.toLocaleString('pl-PL')}`,
    );
  }
  return parts.join(' · ');
}

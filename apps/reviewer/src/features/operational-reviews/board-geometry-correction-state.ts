import type {
  GeometryQualificationPayload,
  ImageGridReviewGeometryPreviewCommand,
  ImageGridReviewItemResponse,
  OperationalImageReviewGeometryPoint,
} from '@game-predictor/admin-api-client';

import { manualGridCellPolygons } from '@game-predictor/manual-image-selection-core/manual-grid-qualification';

import type { OperationalReviewGeometryCorners } from './operational-review-state.ts';

/**
 * Pure helpers for a board from the correction queue (moved from the removed
 * whole-photo grid validation, TASK-0727).
 */

/** Initial corners: an unsaved draft or lattice first, then the current geometry. */
export function gridReviewCorners(
  item: ImageGridReviewItemResponse,
): OperationalReviewGeometryCorners {
  const allowSignedCoordinates =
    gridReviewQualification(item)?.completenessStatus === 'pending_partial';
  if (item.geometryRevision === 0) {
    const reviewDraft = parseTypedCorners(item.reviewDraftQuad, false);
    if (reviewDraft !== null) return reviewDraft;
    const symbolGrid = parseTypedCorners(
      item.symbolGridQuad,
      allowSignedCoordinates,
    );
    if (symbolGrid !== null) return symbolGrid;
  }
  const parsed = parseGeometryCorners(item.geometry, allowSignedCoordinates);
  if (parsed !== null) return parsed;
  const insetX = Math.max(1, Math.round(item.sourceWidth * 0.1));
  const insetY = Math.max(1, Math.round(item.sourceHeight * 0.1));
  return [
    { x: insetX, y: insetY },
    { x: item.sourceWidth - insetX - 1, y: insetY },
    {
      x: item.sourceWidth - insetX - 1,
      y: item.sourceHeight - insetY - 1,
    },
    { x: insetX, y: item.sourceHeight - insetY - 1 },
  ];
}

/** The persisted qualification, else the one of an automatic proposal. */
export function gridReviewQualification(
  item: ImageGridReviewItemResponse,
): GeometryQualificationPayload | undefined {
  return (
    item.geometryQualification ??
    item.automaticFrameProposal?.geometryQualification ??
    item.automaticPartialProposal?.geometryQualification ??
    undefined
  );
}

/** Binds a preview or save to the exact board, source and topology read. */
export function gridReviewGeometryPreviewCommand(
  item: ImageGridReviewItemResponse,
  corners: OperationalReviewGeometryCorners,
): ImageGridReviewGeometryPreviewCommand {
  return {
    corners,
    expectedGeometryRevision: item.geometryRevision,
    expectedGridColumns: item.gridColumns,
    expectedGridRows: item.gridRows,
    expectedResolutionRevision: item.resolutionRevision,
    expectedSourceChecksumSha256: item.sourceChecksumSha256,
    expectedSourceHeight: item.sourceHeight,
    expectedSourceWidth: item.sourceWidth,
  };
}

/**
 * Corners of a persisted board geometry (lattice bounds first). Signed
 * coordinates are accepted only for a board that is explicitly partial.
 */
export function parseGeometryCorners(
  geometry: Readonly<Record<string, unknown>>,
  allowSignedCoordinates = false,
): OperationalReviewGeometryCorners | null {
  const raw =
    geometry.latticeBoundsQuad ??
    geometry.sourceQuad ??
    geometry.quad ??
    geometry.corners;
  return parseTypedCorners(raw, allowSignedCoordinates);
}

function parseTypedCorners(
  value: unknown,
  allowSignedCoordinates = false,
): OperationalReviewGeometryCorners | null {
  if (!Array.isArray(value) || value.length !== 4) return null;
  const parsed = value.map((point) =>
    parsePoint(point, allowSignedCoordinates),
  );
  return parsed.every((point) => point !== null)
    ? (parsed as OperationalReviewGeometryCorners)
    : null;
}

function parsePoint(
  value: unknown,
  allowSignedCoordinates = false,
): OperationalImageReviewGeometryPoint | null {
  if (Array.isArray(value) && value.length === 2) {
    return finitePoint(value[0], value[1], allowSignedCoordinates);
  }
  if (typeof value !== 'object' || value === null) return null;
  const candidate = value as { readonly x?: unknown; readonly y?: unknown };
  return finitePoint(candidate.x, candidate.y, allowSignedCoordinates);
}

function finitePoint(x: unknown, y: unknown, allowSignedCoordinates = false) {
  return typeof x === 'number' &&
    Number.isFinite(x) &&
    (allowSignedCoordinates || x >= 0) &&
    typeof y === 'number' &&
    Number.isFinite(y) &&
    (allowSignedCoordinates || y >= 0)
    ? { x: Math.round(x), y: Math.round(y) }
    : null;
}

/**
 * Cells whose footprint has no area inside the photo: they have no crop and
 * cannot receive an operator symbol (D-486). A cell that only partly leaves
 * the photo keeps real pixels and stays assignable.
 */
export function gridCellsWithoutPixels(
  corners: OperationalReviewGeometryCorners,
  sourceWidth: number,
  sourceHeight: number,
): readonly number[] {
  const right = sourceWidth - 1;
  const bottom = sourceHeight - 1;
  return manualGridCellPolygons(corners).flatMap((polygon, index) =>
    clippedArea(polygon, right, bottom) > 1e-6 ? [] : [index],
  );
}

type Point = { readonly x: number; readonly y: number };

/** Area of a convex polygon clipped to `[0, right] x [0, bottom]`. */
function clippedArea(
  polygon: readonly Point[],
  right: number,
  bottom: number,
): number {
  if (polygon.some((point) => !Number.isFinite(point.x + point.y))) return 0;
  const edges: readonly {
    readonly inside: (point: Point) => boolean;
    readonly cut: (from: Point, to: Point) => Point;
  }[] = [
    {
      cut: (a, b) => atX(a, b, 0),
      inside: (point) => point.x >= 0,
    },
    {
      cut: (a, b) => atX(a, b, right),
      inside: (point) => point.x <= right,
    },
    {
      cut: (a, b) => atY(a, b, 0),
      inside: (point) => point.y >= 0,
    },
    {
      cut: (a, b) => atY(a, b, bottom),
      inside: (point) => point.y <= bottom,
    },
  ];
  let clipped: readonly Point[] = polygon;
  for (const edge of edges) {
    const next: Point[] = [];
    clipped.forEach((point, index) => {
      const previous = clipped[(index + clipped.length - 1) % clipped.length]!;
      const inside = edge.inside(point);
      if (inside !== edge.inside(previous))
        next.push(edge.cut(previous, point));
      if (inside) next.push(point);
    });
    clipped = next;
    if (clipped.length === 0) return 0;
  }
  const doubled = clipped.reduce((sum, point, index) => {
    const following = clipped[(index + 1) % clipped.length]!;
    return sum + point.x * following.y - following.x * point.y;
  }, 0);
  return Math.abs(doubled) / 2;
}

function atX(from: Point, to: Point, x: number): Point {
  const ratio = (x - from.x) / (to.x - from.x);
  return { x, y: from.y + ratio * (to.y - from.y) };
}

function atY(from: Point, to: Point, y: number): Point {
  const ratio = (y - from.y) / (to.y - from.y);
  return { x: from.x + ratio * (to.x - from.x), y };
}

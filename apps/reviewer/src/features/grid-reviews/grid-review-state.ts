import type {
  ImageGridReviewApprovalCommand,
  ImageGridReviewGeometryCommand,
  ImageGridReviewGeometryPreviewCommand,
  ImageGridReviewItemResponse,
  ImageGridReviewState,
  ImageGridReviewView,
  OperationalImageReviewGeometryPoint,
} from '@game-predictor/admin-api-client';

import {
  clampOperationalReviewGeometryPoint,
  type OperationalReviewGeometryCorners,
} from '../operational-reviews/operational-review-state.ts';

export const GRID_REVIEW_PAGE_LIMIT = 1;
export const GRID_REVIEW_SOURCE_PAGE_LIMIT = 9;

export const GRID_REVIEW_VIEWS: readonly {
  readonly label: string;
  readonly value: ImageGridReviewView;
}[] = [
  { label: 'Do walidacji', value: 'needs_validation' },
  { label: 'Do poprawy', value: 'needs_correction' },
  { label: 'Wszystkie', value: 'all' },
];

export const GRID_CORNER_LABELS = ['LT', 'PT', 'PD', 'LD'] as const;

export interface GridReviewNavigation {
  readonly afterCursor?: string;
  readonly beforeCursor?: string;
}

export type GridGeometryDraft = readonly OperationalImageReviewGeometryPoint[];
export type GridGeometrySourceDrafts = ReadonlyMap<string, GridGeometryDraft>;

export type GridGeometryDragTarget =
  | { readonly kind: 'corner'; readonly index: number }
  | { readonly kind: 'grid' }
  | null;

export interface GridReviewSourceStats {
  readonly approvedBoards: number;
  readonly imageState: ImageGridReviewState;
  readonly manualBoards: number;
  readonly needsCorrectionBoards: number;
  readonly needsValidationBoards: number;
  readonly totalBoards: number;
}

export function gridReviewSourceStats(
  items: readonly ImageGridReviewItemResponse[],
): GridReviewSourceStats {
  const approvedBoards = items.filter(
    (item) => item.state === 'approved',
  ).length;
  const needsCorrectionBoards = items.filter(
    (item) => item.state === 'needs_correction',
  ).length;
  const needsValidationBoards = items.filter(
    (item) => item.state === 'needs_validation',
  ).length;
  return {
    approvedBoards,
    imageState:
      needsCorrectionBoards > 0
        ? 'needs_correction'
        : needsValidationBoards > 0
          ? 'needs_validation'
          : 'approved',
    manualBoards: items.filter((item) => item.geometryRevision > 0).length,
    needsCorrectionBoards,
    needsValidationBoards,
    totalBoards: items.length,
  };
}

export function orderGridReviewSourceItems(
  items: readonly ImageGridReviewItemResponse[],
): readonly ImageGridReviewItemResponse[] {
  return [...items].sort(
    (left, right) =>
      left.positionIndex - right.positionIndex ||
      left.sequenceNumber - right.sequenceNumber ||
      left.reviewItemId.localeCompare(right.reviewItemId),
  );
}

export function gridReviewCorners(
  item: ImageGridReviewItemResponse,
): OperationalReviewGeometryCorners {
  const parsed = parseCorners(item.geometry);
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

export function addGridGeometryPoint(
  draft: GridGeometryDraft,
  point: OperationalImageReviewGeometryPoint,
  imageWidth: number,
  imageHeight: number,
): GridGeometryDraft {
  if (draft.length >= 4) return draft;
  return [
    ...draft,
    clampOperationalReviewGeometryPoint(point, imageWidth, imageHeight),
  ];
}

export function emptyGridGeometrySourceDrafts(
  items: readonly ImageGridReviewItemResponse[],
): GridGeometrySourceDrafts {
  return new Map(items.map((item) => [item.reviewItemId, []] as const));
}

export function gridGeometrySourceDraft(
  drafts: GridGeometrySourceDrafts,
  reviewItemId: string,
): GridGeometryDraft {
  return drafts.get(reviewItemId) ?? [];
}

/**
 * A source-wide manual edit intentionally starts with an empty draft.  Canvas
 * code must use this optional anchor instead of assuming that a first point
 * already exists before the operator makes the LT click.
 */
export function gridGeometryDraftAnchor(
  draft: GridGeometryDraft,
): OperationalImageReviewGeometryPoint | null {
  return draft[0] ?? null;
}

export function replaceGridGeometrySourceDraft(
  drafts: GridGeometrySourceDrafts,
  reviewItemId: string,
  draft: GridGeometryDraft,
): GridGeometrySourceDrafts {
  const next = new Map(drafts);
  next.set(reviewItemId, draft);
  return next;
}

export function completeGridGeometrySourceDrafts(
  items: readonly ImageGridReviewItemResponse[],
  drafts: GridGeometrySourceDrafts,
):
  | readonly {
      readonly item: ImageGridReviewItemResponse;
      readonly corners: OperationalReviewGeometryCorners;
    }[]
  | null {
  const values = orderGridReviewSourceItems(items).map((item) => {
    const draft = gridGeometrySourceDraft(drafts, item.reviewItemId);
    return {
      corners:
        draft.length === 4 ? (draft as OperationalReviewGeometryCorners) : null,
      item,
    };
  });
  return values.every((value) => value.corners !== null)
    ? (values as readonly {
        readonly item: ImageGridReviewItemResponse;
        readonly corners: OperationalReviewGeometryCorners;
      }[])
    : null;
}

export function nextIncompleteGridGeometrySourceItem(
  items: readonly ImageGridReviewItemResponse[],
  drafts: GridGeometrySourceDrafts,
  afterReviewItemId: string,
): ImageGridReviewItemResponse | null {
  const ordered = orderGridReviewSourceItems(items);
  const startIndex = ordered.findIndex(
    (item) => item.reviewItemId === afterReviewItemId,
  );
  if (startIndex < 0) return null;
  for (let offset = 1; offset <= ordered.length; offset += 1) {
    const candidate = ordered[(startIndex + offset) % ordered.length];
    if (
      candidate !== undefined &&
      gridGeometrySourceDraft(drafts, candidate.reviewItemId).length < 4
    ) {
      return candidate;
    }
  }
  return null;
}

export function firstIncompleteGridGeometrySourceItem(
  items: readonly ImageGridReviewItemResponse[],
  drafts: GridGeometrySourceDrafts,
): ImageGridReviewItemResponse | null {
  return (
    orderGridReviewSourceItems(items).find(
      (candidate) =>
        gridGeometrySourceDraft(drafts, candidate.reviewItemId).length < 4,
    ) ?? null
  );
}

export function undoGridGeometryPoint(
  draft: GridGeometryDraft,
): GridGeometryDraft {
  return draft.slice(0, -1);
}

export function moveGridGeometryCorner(
  draft: GridGeometryDraft,
  index: number,
  point: OperationalImageReviewGeometryPoint,
  imageWidth: number,
  imageHeight: number,
): GridGeometryDraft {
  if (draft.length !== 4 || index < 0 || index >= 4) return draft;
  return draft.map((candidate, candidateIndex) =>
    candidateIndex === index
      ? clampOperationalReviewGeometryPoint(point, imageWidth, imageHeight)
      : candidate,
  );
}

export function moveGridGeometry(
  draft: GridGeometryDraft,
  delta: OperationalImageReviewGeometryPoint,
  imageWidth: number,
  imageHeight: number,
): GridGeometryDraft {
  if (draft.length !== 4) return draft;
  const minX = Math.min(...draft.map((point) => point.x));
  const maxX = Math.max(...draft.map((point) => point.x));
  const minY = Math.min(...draft.map((point) => point.y));
  const maxY = Math.max(...draft.map((point) => point.y));
  const boundedDelta = {
    x: Math.max(-minX, Math.min(imageWidth - 1 - maxX, delta.x)),
    y: Math.max(-minY, Math.min(imageHeight - 1 - maxY, delta.y)),
  };
  return draft.map((point) => ({
    x: Math.round(point.x + boundedDelta.x),
    y: Math.round(point.y + boundedDelta.y),
  }));
}

export function gridGeometryDragTarget(
  draft: GridGeometryDraft,
  point: OperationalImageReviewGeometryPoint,
  cornerThreshold: number,
): GridGeometryDragTarget {
  if (draft.length !== 4) return null;
  const nearest = draft
    .map((corner, index) => ({
      distance: Math.hypot(corner.x - point.x, corner.y - point.y),
      index,
    }))
    .sort((left, right) => left.distance - right.distance)[0];
  if (nearest !== undefined && nearest.distance <= cornerThreshold) {
    return { index: nearest.index, kind: 'corner' };
  }
  return pointInPolygon(point, draft) ? { kind: 'grid' } : null;
}

export function gridGeometrySourceItemAtPoint(
  items: readonly ImageGridReviewItemResponse[],
  drafts: GridGeometrySourceDrafts,
  activeReviewItemId: string,
  activeDraft: GridGeometryDraft,
  point: OperationalImageReviewGeometryPoint,
): ImageGridReviewItemResponse | null {
  return (
    [...items].reverse().find((candidate) => {
      const storedDraft = gridGeometrySourceDraft(
        drafts,
        candidate.reviewItemId,
      );
      const visibleCorners =
        candidate.reviewItemId === activeReviewItemId
          ? activeDraft
          : storedDraft.length > 0
            ? storedDraft
            : gridReviewCorners(candidate);
      return (
        visibleCorners.length === 4 && pointInPolygon(point, visibleCorners)
      );
    }) ?? null
  );
}

export function gridReviewApprovalCommand(
  item: ImageGridReviewItemResponse,
): ImageGridReviewApprovalCommand {
  return expectedGridReviewIdentity(item);
}

export function gridReviewGeometryPreviewCommand(
  item: ImageGridReviewItemResponse,
  corners: OperationalReviewGeometryCorners,
): ImageGridReviewGeometryPreviewCommand {
  return { corners, ...expectedGridReviewIdentity(item) };
}

export function gridReviewGeometryCommand(
  item: ImageGridReviewItemResponse,
  corners: OperationalReviewGeometryCorners,
  idempotencyKey: string,
): ImageGridReviewGeometryCommand {
  return {
    ...gridReviewGeometryPreviewCommand(item, corners),
    idempotencyKey,
  };
}

export function isGridReviewTypingTarget(target: unknown): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName)
  );
}

function expectedGridReviewIdentity(item: ImageGridReviewItemResponse) {
  return {
    expectedGeometryRevision: item.geometryRevision,
    expectedGridColumns: item.gridColumns,
    expectedGridRows: item.gridRows,
    expectedResolutionRevision: item.resolutionRevision,
    expectedSourceChecksumSha256: item.sourceChecksumSha256,
    expectedSourceHeight: item.sourceHeight,
    expectedSourceWidth: item.sourceWidth,
  };
}

function parseCorners(
  geometry: Readonly<Record<string, unknown>>,
): OperationalReviewGeometryCorners | null {
  const raw =
    geometry.latticeBoundsQuad ??
    geometry.sourceQuad ??
    geometry.quad ??
    geometry.corners;
  if (!Array.isArray(raw) || raw.length !== 4) return null;
  const parsed = raw.map(parsePoint);
  return parsed.every((point) => point !== null)
    ? (parsed as OperationalReviewGeometryCorners)
    : null;
}

function parsePoint(
  value: unknown,
): OperationalImageReviewGeometryPoint | null {
  if (Array.isArray(value) && value.length === 2) {
    return finitePoint(value[0], value[1]);
  }
  if (typeof value !== 'object' || value === null) return null;
  const candidate = value as { readonly x?: unknown; readonly y?: unknown };
  return finitePoint(candidate.x, candidate.y);
}

function finitePoint(x: unknown, y: unknown) {
  return typeof x === 'number' &&
    Number.isFinite(x) &&
    x >= 0 &&
    typeof y === 'number' &&
    Number.isFinite(y) &&
    y >= 0
    ? { x: Math.round(x), y: Math.round(y) }
    : null;
}

function pointInPolygon(
  point: OperationalImageReviewGeometryPoint,
  polygon: GridGeometryDraft,
): boolean {
  let inside = false;
  for (
    let index = 0, previous = polygon.length - 1;
    index < polygon.length;
    previous = index++
  ) {
    const currentPoint = polygon[index];
    const previousPoint = polygon[previous];
    if (currentPoint === undefined || previousPoint === undefined) continue;
    const crosses =
      currentPoint.y > point.y !== previousPoint.y > point.y &&
      point.x <
        ((previousPoint.x - currentPoint.x) * (point.y - currentPoint.y)) /
          (previousPoint.y - currentPoint.y) +
          currentPoint.x;
    if (crosses) inside = !inside;
  }
  return inside;
}

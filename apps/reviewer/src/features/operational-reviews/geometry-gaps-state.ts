import type {
  ImageGeometryCompletenessResponse,
  ImageGridReviewItemResponse,
  IncompleteGeometryImageResponse,
  ListIncompleteGeometryImagesOptions,
} from '@game-predictor/admin-api-client';

/**
 * Pure helpers of the "Braki zdjęć" tab of the local Reviewer (TASK-0963).
 * The state of an image and of its positions is the D-484 classification
 * returned by `incomplete-images`; the tab never classifies on its own. The
 * labels and the SVG helpers were copied from the Admin diagnostics section,
 * whose list disappears in TASK-0964.
 */

/** The four real-gap states of decision 1 of the plan (`gapsOnly`). */
export type GeometryGapStateName =
  | 'incomplete_missing'
  | 'incomplete_partial'
  | 'import_failed'
  | 'no_source_geometry';

export type GeometryGapsFilter = 'all' | GeometryGapStateName;

export const GEOMETRY_GAPS_FILTERS: readonly GeometryGapsFilter[] = [
  'all',
  'incomplete_missing',
  'incomplete_partial',
  'import_failed',
  'no_source_geometry',
];

/** Images of these states show the import hint and never the editor. */
export const GEOMETRY_GAP_STATES_WITHOUT_EDITOR: ReadonlySet<string> = new Set([
  'import_failed',
  'no_source_geometry',
]);

/** Pages of the gap list; the next one is fetched near the end of the queue. */
export const GEOMETRY_GAPS_PAGE_LIMIT = 25;
export const GEOMETRY_GAPS_PREFETCH_THRESHOLD = 3;
/** Rows of one image: nine positions at most, well under the API cap of 100. */
export const GEOMETRY_GAPS_ROWS_LIMIT = 100;

export const GEOMETRY_GAPS_NO_TARGET_HINT =
  'Brak planszy i slotu do ręcznej korekty — przetwórz zdjęcie ponownie w Imporcie plansz';

/** A live board exists, but it has no review-queue row to open the editor on. */
export const GEOMETRY_GAPS_BOARD_WITHOUT_ROW_HINT =
  'Plansza istnieje, ale nie ma wpisu w kolejce do ręcznej korekty — przetwórz zdjęcie ponownie w Imporcie plansz';

const FILTER_LABELS: Readonly<Record<GeometryGapsFilter, string>> = {
  all: 'Wszystkie braki',
  incomplete_missing: 'Brakuje plansz',
  incomplete_partial: 'Plansza częściowa',
  import_failed: 'Import nieudany',
  no_source_geometry: 'Bez geometrii źródła',
};

const IMAGE_STATE_LABELS: Readonly<Record<string, string>> = {
  complete: 'Kompletne',
  incomplete_missing: 'Brakuje plansz',
  incomplete_partial: 'Plansza częściowa',
  incomplete_uncertain: 'Siatka niepotwierdzona',
  no_source_geometry: 'Bez geometrii źródła',
  import_failed: 'Import nieudany',
  superseded: 'Zastąpione nowszym importem',
};

const POSITION_STATE_LABELS: Readonly<Record<string, string>> = {
  ok: 'Poprawna siatka',
  uncertain: 'Siatka niepotwierdzona',
  partial: 'Plansza częściowa',
  missing: 'Brak siatki',
  deferred: 'Siatka odroczona',
  superseded: 'Zastąpiona (numer jest w innym zdjęciu)',
};

const IMPORT_ERROR_LABELS: Readonly<Record<string, string>> = {
  IMAGE_STAGE_EXECUTION_FAILED: 'etap przetwarzania zakończył się błędem',
  IMAGE_STAGE_RESULT_INVALID: 'etap przetwarzania zwrócił nieprawidłowy wynik',
  IMAGE_VIRTUAL_CELL_SOURCE_SUPPORT_INCOMPLETE:
    'niepełne wsparcie źródła pól planszy',
};

const DEFERRED_REASON_LABELS: Readonly<Record<string, string>> = {
  insufficient_centers: 'za mało środków symboli',
  incomplete_lattice: 'niepełna siatka',
  residual_too_high: 'zbyt duży błąd dopasowania',
  source_unavailable: 'źródło niedostępne',
};

const SOURCE_STATUS_LABELS: Readonly<Record<string, string>> = {
  discovered: 'wykryte',
  processing: 'w przetwarzaniu',
  waiting_for_review: 'czeka na przegląd',
  accepted: 'zaakceptowane',
  rejected: 'odrzucone',
  completed: 'zakończone',
  failed: 'błąd',
};

export function geometryGapsFilterLabel(filter: GeometryGapsFilter): string {
  return FILTER_LABELS[filter];
}

export function geometryImageStateLabel(state: string): string {
  return IMAGE_STATE_LABELS[state] ?? state;
}

export function geometryPositionStateLabel(state: string): string {
  return POSITION_STATE_LABELS[state] ?? state;
}

export function geometryReasonLabel(reason: string): string {
  return DEFERRED_REASON_LABELS[reason] ?? reason;
}

export function geometrySourceStatusLabel(status: string): string {
  return SOURCE_STATUS_LABELS[status] ?? status;
}

/** Error code of a failed import file with its meaning, when the code is known. */
export function geometryImportErrorLabel(code: string): string {
  const label = IMPORT_ERROR_LABELS[code];
  return label === undefined ? code : `${label} (${code})`;
}

/** Label of one position state, with the deferral reason when there is one. */
export function geometryPositionLabel(
  state: string,
  reasonCode: string | null,
): string {
  const label = geometryPositionStateLabel(state);
  return reasonCode === null
    ? label
    : `${label} (${geometryReasonLabel(reasonCode)})`;
}

export type GeometryPositionTone = 'ok' | 'warning' | 'danger' | 'muted';

/**
 * Tone of a position in the preview: positions without a grid are `danger`;
 * superseded ones are covered by another image, so they are only `muted`.
 */
export function geometryPositionTone(state: string): GeometryPositionTone {
  if (state === 'ok') return 'ok';
  if (state === 'superseded') return 'muted';
  if (state === 'uncertain' || state === 'partial') return 'warning';
  return 'danger';
}

export function geometryImageTone(state: string): GeometryPositionTone {
  if (state === 'superseded') return 'muted';
  return state === 'incomplete_uncertain' || state === 'incomplete_partial'
    ? 'warning'
    : 'danger';
}

/** Counter of one filter button from the completeness report. */
export function geometryGapsFilterCount(
  report: ImageGeometryCompletenessResponse,
  filter: GeometryGapsFilter,
): number {
  const images = report.images;
  switch (filter) {
    case 'all':
      return (
        images.incompleteMissing +
        images.incompletePartial +
        images.importFailed +
        images.noSourceGeometry
      );
    case 'incomplete_missing':
      return images.incompleteMissing;
    case 'incomplete_partial':
      return images.incompletePartial;
    case 'import_failed':
      return images.importFailed;
    case 'no_source_geometry':
      return images.noSourceGeometry;
  }
}

/**
 * Query of one page of the tab: `gapsOnly` for the default filter, else the
 * single state; the server refuses both together (TASK-0961).
 */
export function geometryGapsListQuery(
  gameId: string,
  filter: GeometryGapsFilter,
  afterCursor: string | null,
  limit: number = GEOMETRY_GAPS_PAGE_LIMIT,
): ListIncompleteGeometryImagesOptions {
  return {
    gameId,
    ...(filter === 'all' ? { gapsOnly: true } : { imageState: filter }),
    ...(afterCursor === null ? {} : { afterCursor }),
    limit,
  };
}

/**
 * Decision 8 of the plan: a partial board has no final state, so an image
 * whose every `partial` position is already approved by a human is hidden
 * unless the operator asks for it. An image without partial positions is
 * never hidden by this rule.
 */
export function allPartialPositionsHumanApproved(
  image: Pick<IncompleteGeometryImageResponse, 'positions'>,
): boolean {
  const partial = image.positions.filter(
    (position) => position.state === 'partial',
  );
  return (
    partial.length > 0 &&
    partial.every((position) => position.humanApproved === true)
  );
}

export function visibleGapImages<
  T extends Pick<IncompleteGeometryImageResponse, 'positions'>,
>(images: readonly T[], showHumanApproved: boolean): readonly T[] {
  return showHumanApproved
    ? images
    : images.filter((image) => !allPartialPositionsHumanApproved(image));
}

/** The next page is fetched when at most `threshold` images remain after `index`. */
export function shouldPrefetchNextPage(
  index: number,
  visibleCount: number,
  hasNextPage: boolean,
  threshold: number = GEOMETRY_GAPS_PREFETCH_THRESHOLD,
): boolean {
  return hasNextPage && visibleCount - index - 1 <= threshold;
}

export type GeometryGapPositionTarget =
  | {
      readonly kind: 'deferred';
      readonly pendingId: string;
      readonly row: ImageGridReviewItemResponse;
    }
  | { readonly kind: 'reported'; readonly row: ImageGridReviewItemResponse };

/**
 * The editing target of one position is the `grid-reviews` row of the pair
 * `(sourceImageId, positionIndex)` (plan, "Reguły danych"): a current board
 * first (it is the slot's single queue entry), else a deferred slot. No row
 * means nothing to edit.
 */
export function geometryGapPositionTarget(
  rows: readonly ImageGridReviewItemResponse[],
  positionIndex: number,
): GeometryGapPositionTarget | null {
  const candidates = rows.filter((row) => row.positionIndex === positionIndex);
  const board = candidates.find(
    (row) => row.slotKind === 'current_review' && row.reviewItemId !== null,
  );
  if (board !== undefined) return { kind: 'reported', row: board };
  const deferred = candidates.find(
    (row) =>
      row.slotKind === 'deferred_geometry' && row.pendingGeometryId !== null,
  );
  if (deferred !== undefined && deferred.pendingGeometryId !== null) {
    return {
      kind: 'deferred',
      pendingId: deferred.pendingGeometryId,
      row: deferred,
    };
  }
  return null;
}

export interface GeometryQuadPoint {
  readonly x: number;
  readonly y: number;
}

/** `points` attribute of an SVG polygon, or `null` for anything but four finite points. */
export function quadSvgPoints(
  quad: readonly GeometryQuadPoint[] | null | undefined,
): string | null {
  if (
    quad === null ||
    quad === undefined ||
    quad.length !== 4 ||
    !quad.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y))
  ) {
    return null;
  }
  return quad.map((point) => `${point.x},${point.y}`).join(' ');
}

/** Centre of a quad, used to place the position number. */
export function quadCentre(
  quad: readonly GeometryQuadPoint[],
): GeometryQuadPoint {
  const count = Math.max(quad.length, 1);
  return {
    x: quad.reduce((sum, point) => sum + point.x, 0) / count,
    y: quad.reduce((sum, point) => sum + point.y, 0) / count,
  };
}

/** Sequence range and expected boards of an image, as one line. */
export function geometryImageSummary(
  image: Pick<
    IncompleteGeometryImageResponse,
    'expectedBoardCount' | 'sequenceRangeEnd' | 'sequenceRangeStart'
  >,
): string {
  const range =
    image.sequenceRangeStart !== null && image.sequenceRangeEnd !== null
      ? `numery ${image.sequenceRangeStart.toLocaleString('pl-PL')}–${image.sequenceRangeEnd.toLocaleString('pl-PL')}`
      : 'brak geometrii źródła, oczekiwana liczba plansz nieznana';
  return image.expectedBoardCount === null
    ? range
    : `${range} · oczekiwane plansze: ${image.expectedBoardCount}`;
}

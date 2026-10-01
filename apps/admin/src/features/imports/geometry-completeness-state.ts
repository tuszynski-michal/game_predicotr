/** Pure state helpers of the D-484 geometry completeness section (TASK-0806, 0808). */

export type GeometryImageStateName =
  | 'complete'
  | 'incomplete_missing'
  | 'incomplete_partial'
  | 'incomplete_uncertain'
  | 'no_source_geometry'
  | 'import_failed'
  | 'superseded';

export type GeometryPositionStateName =
  'ok' | 'uncertain' | 'partial' | 'missing' | 'deferred' | 'superseded';

/** States that still need attention: the "all incomplete" list (never `superseded`). */
export type IncompleteImageStateName = Exclude<
  GeometryImageStateName,
  'complete' | 'superseded'
>;

/** States the list can be filtered by: the incomplete ones and `superseded`. */
export type ListedImageStateName = IncompleteImageStateName | 'superseded';

const IMAGE_STATE_LABELS: Readonly<Record<GeometryImageStateName, string>> = {
  complete: 'Kompletne',
  incomplete_missing: 'Brakuje plansz',
  incomplete_partial: 'Plansza częściowa',
  incomplete_uncertain: 'Siatka niepotwierdzona',
  no_source_geometry: 'Bez geometrii źródła',
  import_failed: 'Import nieudany',
  superseded: 'Zastąpione nowszym importem',
};

const POSITION_STATE_LABELS: Readonly<
  Record<GeometryPositionStateName, string>
> = {
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

export const INCOMPLETE_IMAGE_STATES: readonly IncompleteImageStateName[] = [
  'incomplete_missing',
  'incomplete_partial',
  'incomplete_uncertain',
  'import_failed',
  'no_source_geometry',
];

/** Filter tabs of the list: the incomplete states, then the replaced images. */
export const LISTED_IMAGE_STATES: readonly ListedImageStateName[] = [
  ...INCOMPLETE_IMAGE_STATES,
  'superseded',
];

export function geometryImageStateLabel(state: string): string {
  return IMAGE_STATE_LABELS[state as GeometryImageStateName] ?? state;
}

export function geometryPositionStateLabel(state: string): string {
  return POSITION_STATE_LABELS[state as GeometryPositionStateName] ?? state;
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

export type GeometrySectionState =
  'loading' | 'error' | 'no-images' | 'all-complete' | 'incomplete';

export interface GeometrySectionInput {
  readonly loading: boolean;
  readonly error: string | null;
  readonly hasStaleData: boolean;
  readonly totalImages: number;
  /** Images that still need attention; superseded and complete ones are not counted. */
  readonly incompleteImages: number;
}

export function geometrySectionState(
  input: GeometrySectionInput,
): GeometrySectionState {
  if (input.loading) return 'loading';
  if (input.error !== null && !input.hasStaleData) return 'error';
  if (input.totalImages === 0) return 'no-images';
  if (input.incompleteImages === 0) return 'all-complete';
  return 'incomplete';
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

export const DEFAULT_LOW_QUALITY_MAX_CONFIDENCE = 0.8;
export const DEFAULT_LOW_QUALITY_MIN_CELLS = 5;
export const MAX_LOW_QUALITY_MIN_CELLS = 15;

export type LowQualityThresholdsResult =
  | {
      readonly ok: true;
      readonly maxConfidence: number;
      readonly minCells: number;
    }
  | { readonly ok: false; readonly error: string };

/** Parse the two thresholds of the low-quality query (percent and a cell count). */
export function parseLowQualityThresholds(
  maxConfidencePercent: string,
  minCells: string,
): LowQualityThresholdsResult {
  const percentText = maxConfidencePercent.trim().replace(',', '.');
  const cellsText = minCells.trim();
  const percent = percentText === '' ? Number.NaN : Number(percentText);
  if (!Number.isFinite(percent) || percent < 0 || percent > 100) {
    return {
      ok: false,
      error: 'Próg pewności musi być liczbą od 0 do 100 (%).',
    };
  }
  if (!/^\d+$/.test(cellsText)) {
    return {
      ok: false,
      error: `Minimalna liczba pól musi być liczbą całkowitą od 1 do ${MAX_LOW_QUALITY_MIN_CELLS}.`,
    };
  }
  const cells = Number(cellsText);
  if (cells < 1 || cells > MAX_LOW_QUALITY_MIN_CELLS) {
    return {
      ok: false,
      error: `Minimalna liczba pól musi być liczbą całkowitą od 1 do ${MAX_LOW_QUALITY_MIN_CELLS}.`,
    };
  }
  return {
    ok: true,
    maxConfidence: Math.round(percent * 100) / 10000,
    minCells: cells,
  };
}

/** Domain error codes of the low-quality query mapped to operator text. */
export function lowQualityErrorMessage(code: string | null): string {
  if (code === 'IMAGE_GEOMETRY_LOW_QUALITY_TIMEOUT') {
    return 'Zapytanie przekroczyło limit czasu. Zawęź je do jednego importu.';
  }
  return 'Nie udało się sprawdzić jakości symboli.';
}

export function formatPercent(value: number): string {
  return `${(value * 100).toLocaleString('pl-PL', {
    maximumFractionDigits: 1,
  })}%`;
}

export function errorCodeOf(error: unknown): string | null {
  return typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string'
    ? error.code
    : null;
}

export interface GeometryImportOption {
  readonly id: string;
  readonly label: string;
}

/** Whole game or one selected import (empty selection means the whole game). */
export function geometryScopeImportId(
  scope: 'game' | 'import',
  importId: string,
  imports: readonly GeometryImportOption[],
): string | undefined {
  if (scope !== 'import') return undefined;
  return imports.some((option) => option.id === importId)
    ? importId
    : undefined;
}

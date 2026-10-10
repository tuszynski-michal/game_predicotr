/** Pure state helpers of the D-484 geometry completeness diagnostics (TASK-0806, 0808, 0964). */

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

const DEFERRED_REASON_LABELS: Readonly<Record<string, string>> = {
  insufficient_centers: 'za mało środków symboli',
  incomplete_lattice: 'niepełna siatka',
  residual_too_high: 'zbyt duży błąd dopasowania',
  source_unavailable: 'źródło niedostępne',
};

export const INCOMPLETE_IMAGE_STATES: readonly IncompleteImageStateName[] = [
  'incomplete_missing',
  'incomplete_partial',
  'incomplete_uncertain',
  'import_failed',
  'no_source_geometry',
];

const GATE_REASON_LABELS: Readonly<Record<string, string>> = {
  SOURCE_IMAGE_GEOMETRY_INCOMPLETE:
    'zdjęcie nie ma kompletu potwierdzonych siatek; w V3 poprawne pełne siatki mogą być już dostępne w weryfikacji symboli',
};

export function geometryGateReasonLabel(code: string): string {
  const label = GATE_REASON_LABELS[code];
  return label === undefined ? code : `${label} (${code})`;
}

export function geometryImageStateLabel(state: string): string {
  return IMAGE_STATE_LABELS[state as GeometryImageStateName] ?? state;
}

export function geometryPositionStateLabel(state: string): string {
  return POSITION_STATE_LABELS[state as GeometryPositionStateName] ?? state;
}

export function geometryReasonLabel(reason: string): string {
  return DEFERRED_REASON_LABELS[reason] ?? reason;
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

/** Image counters of a completeness report that the heading reads. */
export interface GeometryImageCounters {
  readonly incompleteMissing: number;
  readonly incompletePartial: number;
  readonly incompleteUncertain: number;
  readonly importFailed: number;
  readonly noSourceGeometry: number;
}

/**
 * Real gaps need a human (missing or partial boards, failed import, no source
 * geometry); an unconfirmed grid is an automatic grid without manual approval,
 * not a cutting error.
 */
export function geometryGapCounts(images: GeometryImageCounters): {
  readonly realGaps: number;
  readonly unconfirmed: number;
} {
  return {
    realGaps:
      images.incompleteMissing +
      images.incompletePartial +
      images.importFailed +
      images.noSourceGeometry,
    unconfirmed: images.incompleteUncertain,
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

/**
 * Sequence numbers of the import report (D-543, TASK-0971): the API sends a
 * sorted, capped list with the exact count, so a cut list says how many are
 * not shown.
 */
export function formatSequenceNumbers(
  numbers: readonly number[],
  count: number,
): string {
  if (count === 0 || numbers.length === 0) return '—';
  const shown = numbers.map((value) => `#${value}`).join(', ');
  const hidden = count - numbers.length;
  return hidden > 0
    ? `${shown} i jeszcze ${hidden.toLocaleString('pl-PL')}`
    : shown;
}

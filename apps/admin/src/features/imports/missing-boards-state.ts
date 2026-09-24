const MISSING_REASON_LABELS: Readonly<Record<string, string>> = {
  import_in_progress: 'W trakcie importu',
  waiting_for_geometry: 'Oczekuje na siatkę/cięcie',
  partial_source: 'Niepełne zdjęcie',
  failed: 'Błąd importu',
  rejected: 'Odrzucona w weryfikacji',
  unknown: 'Niekompletna — przyczyna nieustalona',
  no_source: 'Brak źródła w systemie',
};

export function missingReasonLabel(reason: string): string {
  return MISSING_REASON_LABELS[reason] ?? reason;
}

export function formatSegmentRange(start: number, end: number): string {
  const formattedStart = start.toLocaleString('pl-PL');
  if (start === end) return formattedStart;
  return `${formattedStart}–${end.toLocaleString('pl-PL')}`;
}

export interface ParsedSequenceRange {
  readonly from: number;
  readonly to: number;
}

export type SequenceRangeQueryResult =
  | { readonly ok: true; readonly range: ParsedSequenceRange | null }
  | { readonly ok: false; readonly error: string };

const SINGLE_NUMBER_PATTERN = /^(\d+)$/;
const RANGE_PATTERN = /^(\d+)\s*[-–—]\s*(\d+)$/;

export function parseSequenceRangeQuery(
  rawQuery: string,
  expectedLayoutCount: number,
): SequenceRangeQueryResult {
  const query = rawQuery.trim();
  if (query.length === 0) return { ok: true, range: null };

  const singleMatch = SINGLE_NUMBER_PATTERN.exec(query);
  const rangeMatch = singleMatch === null ? RANGE_PATTERN.exec(query) : null;
  if (singleMatch === null && rangeMatch === null) {
    return {
      ok: false,
      error: 'Wpisz liczbę lub zakres, np. „120” albo „100-200”.',
    };
  }

  const from = Number(singleMatch ? singleMatch[1] : rangeMatch![1]);
  const to = Number(singleMatch ? singleMatch[1] : rangeMatch![2]);
  if (from < 1 || to < 1) {
    return { ok: false, error: 'Numer musi być liczbą całkowitą ≥ 1.' };
  }
  if (from > to) {
    return {
      ok: false,
      error: 'Początek zakresu musi być mniejszy lub równy końcowi.',
    };
  }
  if (to > expectedLayoutCount) {
    return {
      ok: false,
      error: `Numer przekracza oczekiwaną liczbę plansz (${expectedLayoutCount.toLocaleString(
        'pl-PL',
      )}).`,
    };
  }
  return { ok: true, range: { from, to } };
}

export type MissingBoardsSummaryState =
  | 'loading'
  | 'error'
  | 'unknown-target'
  | 'empty'
  | 'all-added'
  | 'no-results'
  | 'list';

export interface MissingBoardsSummaryInput {
  readonly loading: boolean;
  readonly error: string | null;
  readonly hasStaleData: boolean;
  readonly expectedLayoutCount: number | null;
  readonly countsAdded: number;
  readonly countsMissing: number;
  readonly missingByReason: Readonly<Record<string, number>>;
  readonly segmentCount: number;
}

export function summaryState(
  input: MissingBoardsSummaryInput,
): MissingBoardsSummaryState {
  if (input.loading) return 'loading';
  if (input.error !== null && !input.hasStaleData) return 'error';
  if (
    input.expectedLayoutCount === null ||
    !Number.isInteger(input.expectedLayoutCount) ||
    input.expectedLayoutCount < 1
  ) {
    return 'unknown-target';
  }
  const hasOnlyNoSourceSignal = Object.entries(input.missingByReason).every(
    ([reason, count]) => reason === 'no_source' || count === 0,
  );
  if (input.countsAdded === 0 && hasOnlyNoSourceSignal) return 'empty';
  if (input.countsMissing === 0) return 'all-added';
  if (input.segmentCount === 0) return 'no-results';
  return 'list';
}

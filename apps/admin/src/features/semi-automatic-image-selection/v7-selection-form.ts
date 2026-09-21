export type V7SelectionDirection = 'ascending' | 'descending';
export type V7SelectionMode = 'semi_automatic' | 'automatic';
export type V7BorderStyle =
  'top_and_sides' | 'full_frame' | 'irregular_or_none';

export type V7SelectionFormErrorCode =
  | 'V7_BOUNDARY_INVALID'
  | 'V7_BOUNDARY_NOT_FULL_PAGE'
  | 'V7_DIRECTION_MISMATCH'
  | 'V7_PAGE_GAP_INVALID';

export interface V7PageBoundary {
  readonly end: number;
  readonly start: number;
}

export interface V7SelectionFormInput {
  readonly borderStyle: V7BorderStyle;
  readonly direction: V7SelectionDirection;
  readonly firstPage: string;
  readonly lastPage: string;
  readonly mode: V7SelectionMode;
}

export interface V7NormalizedSelectionForm {
  readonly borderStyle: V7BorderStyle;
  readonly direction: V7SelectionDirection;
  readonly expectedRangeCount: number;
  readonly firstPage: V7PageBoundary;
  readonly firstSequenceNumber: number;
  readonly lastPage: V7PageBoundary;
  readonly lastSequenceNumber: number;
  readonly mode: V7SelectionMode;
}

export interface V7SelectionCreatePayload {
  readonly direction: V7SelectionDirection;
  readonly firstSequenceNumber: number;
  readonly lastSequenceNumber: number;
  readonly mode: 'v7_selection';
  readonly selectionToken: string;
  readonly v7: {
    readonly borderStyle: V7BorderStyle;
    readonly mode: V7SelectionMode;
  };
}

export type V7SelectionFormNormalization =
  | { readonly code: V7SelectionFormErrorCode; readonly ok: false }
  | { readonly ok: true; readonly value: V7NormalizedSelectionForm };

const PAGE_SIZE = 9;
const PAGE_BOUNDARY = /^\s*([1-9][0-9]*)(?:\s*[-–]\s*([1-9][0-9]*))?\s*$/u;

/**
 * Parses one V7 page boundary. A single number deliberately means the first
 * number of a full 3×3 page; it is never inferred from a neighbouring page.
 */
export function parseV7PageBoundary(
  value: string,
):
  | { readonly ok: true; readonly value: V7PageBoundary }
  | { readonly code: V7SelectionFormErrorCode; readonly ok: false } {
  const match = PAGE_BOUNDARY.exec(value);
  if (match === null) return { code: 'V7_BOUNDARY_INVALID', ok: false };
  const start = Number(match[1]);
  const explicitEnd = match[2] === undefined ? null : Number(match[2]);
  if (!Number.isSafeInteger(start) || start < 1) {
    return { code: 'V7_BOUNDARY_INVALID', ok: false };
  }
  const end = explicitEnd ?? start + PAGE_SIZE - 1;
  if (!Number.isSafeInteger(end) || end < start) {
    return { code: 'V7_BOUNDARY_INVALID', ok: false };
  }
  if (end - start + 1 !== PAGE_SIZE) {
    return { code: 'V7_BOUNDARY_NOT_FULL_PAGE', ok: false };
  }
  return { ok: true, value: { end, start } };
}

/**
 * Normalizes display order to canonical increasing API bounds. Direction
 * controls only the order pages occur in a recording.
 */
export function normalizeV7SelectionForm(
  input: V7SelectionFormInput,
): V7SelectionFormNormalization {
  const first = parseV7PageBoundary(input.firstPage);
  if (!first.ok) return first;
  const last = parseV7PageBoundary(input.lastPage);
  if (!last.ok) return last;

  const orderMatches =
    input.direction === 'ascending'
      ? first.value.start <= last.value.start
      : first.value.start >= last.value.start;
  if (!orderMatches) return { code: 'V7_DIRECTION_MISMATCH', ok: false };

  const firstSequenceNumber = Math.min(first.value.start, last.value.start);
  const lastSequenceNumber = Math.max(first.value.end, last.value.end);
  const span = lastSequenceNumber - firstSequenceNumber + 1;
  if (span % PAGE_SIZE !== 0) {
    return { code: 'V7_PAGE_GAP_INVALID', ok: false };
  }
  return {
    ok: true,
    value: {
      borderStyle: input.borderStyle,
      direction: input.direction,
      expectedRangeCount: span / PAGE_SIZE,
      firstPage: first.value,
      firstSequenceNumber,
      lastPage: last.value,
      lastSequenceNumber,
      mode: input.mode,
    },
  };
}

export function formatV7PageBoundary(boundary: V7PageBoundary): string {
  return `${boundary.start}–${boundary.end}`;
}

export function deriveV7OutputDirectory(sourcePath: string): string {
  const normalized = sourcePath.trim().replace(/[\\/]+$/u, '');
  return normalized === '' ? '' : `${normalized} cut`;
}

export function createV7SelectionPayload(
  configuration: V7NormalizedSelectionForm,
  selectionToken: string,
): V7SelectionCreatePayload {
  return {
    direction: configuration.direction,
    firstSequenceNumber: configuration.firstSequenceNumber,
    lastSequenceNumber: configuration.lastSequenceNumber,
    mode: 'v7_selection',
    selectionToken,
    v7: {
      borderStyle: configuration.borderStyle,
      mode: configuration.mode,
    },
  };
}

export function v7SelectionFormErrorMessage(
  code: V7SelectionFormErrorCode,
): string {
  switch (code) {
    case 'V7_BOUNDARY_INVALID':
      return 'Podaj dodatni numer albo pełny zakres, np. 10 lub 10-18.';
    case 'V7_BOUNDARY_NOT_FULL_PAGE':
      return 'V7 automatycznie analizuje tylko pełne strony z 9 planszami.';
    case 'V7_DIRECTION_MISMATCH':
      return 'Kolejność pierwszego i ostatniego zakresu nie pasuje do wybranego kierunku.';
    case 'V7_PAGE_GAP_INVALID':
      return 'Granice nie wyznaczają pełnej liczby stron po 9 plansz.';
  }
}

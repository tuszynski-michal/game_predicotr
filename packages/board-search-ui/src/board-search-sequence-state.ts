import type {
  BoardSearchPattern,
  BoardSearchScope,
} from '@game-predictor/admin-api-client';
import {
  createBoardSearchEditorState,
  patternBoardSearchCells,
  type BoardSearchEditorState,
  type BoardSearchEntryOrder,
} from './board-search-editor-state.ts';

export type BoardSearchSubmittedSequence = {
  readonly patterns: BoardSearchPattern[];
  readonly scope: BoardSearchScope;
  readonly limit: number;
};

export type BoardSearchSequenceLocalState = {
  readonly version: 1;
  readonly scope: string;
  readonly patterns: readonly (readonly (string | null)[])[];
  readonly activeIndex: number;
  readonly entryOrder: BoardSearchEntryOrder;
  readonly lastSubmitted: BoardSearchSubmittedSequence | null;
  readonly selectedStartSequenceNumber: number | null;
};

export const boardSearchSequenceStorageKey = (scope: string) =>
  `board-search-sequence:v1:${scope}`;

/** Preserve inactive codes: validation must ask the operator to fix them. */
export function boardSearchSequenceEditor(
  cells: readonly (string | null)[],
): BoardSearchEditorState {
  return { ...createBoardSearchEditorState(), cells: [...cells] };
}

export function boardSearchSequenceEditorsFromPatterns(
  patterns: readonly BoardSearchPattern[],
): BoardSearchEditorState[] {
  return patterns.map((pattern) => {
    const cells: (string | null)[] = Array<string | null>(15).fill(null);
    for (const cell of pattern.cells)
      cells[cell.cellIndex] = cell.symbolCode ?? '?';
    return boardSearchSequenceEditor(cells);
  });
}

export function boardSearchSequenceInput(
  editors: readonly BoardSearchEditorState[],
  activeCodes: ReadonlySet<string>,
): { readonly patterns: BoardSearchPattern[]; readonly error: string | null } {
  let last = editors.length - 1;
  while (last >= 0 && editors[last].cells.every((cell) => cell === null))
    last--;
  if (last < 0) return { patterns: [], error: 'Uzupełnij układ 1.' };
  const patterns: BoardSearchPattern[] = [];
  for (let index = 0; index <= last; index++) {
    const cells = patternBoardSearchCells(editors[index]);
    if (!cells.some((cell) => cell.symbolCode !== null))
      return {
        patterns: [],
        error: `Uzupełnij układ ${index + 1}: potrzebny jest przynajmniej jeden znany symbol.`,
      };
    const invalid = cells.find(
      (cell) => cell.symbolCode !== null && !activeCodes.has(cell.symbolCode),
    );
    if (invalid)
      return {
        patterns: [],
        error: `Układ ${index + 1}: symbol „${invalid.symbolCode}” nie jest już aktywny. Popraw wzór.`,
      };
    patterns.push({ cells: [...cells] });
  }
  return { patterns, error: null };
}

export function boardSearchSequenceKey(
  patterns: readonly BoardSearchPattern[],
): string {
  return JSON.stringify(
    patterns.map((pattern) =>
      [...pattern.cells]
        .sort((a, b) => a.cellIndex - b.cellIndex)
        .map((cell) => [cell.cellIndex, cell.symbolCode]),
    ),
  );
}

function validPattern(value: unknown): value is BoardSearchPattern {
  if (
    value === null ||
    typeof value !== 'object' ||
    !('cells' in value) ||
    !Array.isArray(value.cells) ||
    value.cells.length < 1 ||
    value.cells.length > 15
  )
    return false;
  const seen = new Set<number>();
  return value.cells.every((cell: unknown) => {
    if (
      cell === null ||
      typeof cell !== 'object' ||
      !('cellIndex' in cell) ||
      !('symbolCode' in cell)
    )
      return false;
    const index = cell.cellIndex;
    if (
      typeof index !== 'number' ||
      !Number.isInteger(index) ||
      index < 0 ||
      index > 14 ||
      seen.has(index)
    )
      return false;
    seen.add(index);
    return (
      cell.symbolCode === null ||
      (typeof cell.symbolCode === 'string' &&
        cell.symbolCode.length > 0 &&
        cell.symbolCode.length <= 64 &&
        cell.symbolCode !== '?')
    );
  });
}

/** Strict versioned hydration. Ignore extra properties when writing the next record. */
export function readBoardSearchSequenceLocalState(
  raw: string,
  scope: string,
): BoardSearchSequenceLocalState {
  const value = JSON.parse(raw);
  const fail = () => {
    throw new Error('Nieprawidłowy zapis wyszukiwania.');
  };
  if (
    value === null ||
    typeof value !== 'object' ||
    value.version !== 1 ||
    value.scope !== scope
  )
    return fail();
  if (
    !Array.isArray(value.patterns) ||
    value.patterns.length < 1 ||
    value.patterns.length > 4 ||
    !value.patterns.every(
      (cells: unknown) =>
        Array.isArray(cells) &&
        cells.length === 15 &&
        cells.every(
          (cell: unknown) =>
            cell === null ||
            (typeof cell === 'string' && cell.length > 0 && cell.length <= 64),
        ),
    )
  )
    return fail();
  if (
    !Number.isInteger(value.activeIndex) ||
    value.activeIndex < 0 ||
    value.activeIndex >= value.patterns.length ||
    !['rows', 'columns'].includes(value.entryOrder)
  )
    return fail();
  const submitted = value.lastSubmitted;
  if (
    submitted !== null &&
    (typeof submitted !== 'object' ||
      !Array.isArray(submitted.patterns) ||
      submitted.patterns.length < 1 ||
      submitted.patterns.length > 4 ||
      !submitted.patterns.every(validPattern) ||
      !['all_searchable', 'approved_only'].includes(submitted.scope) ||
      !Number.isInteger(submitted.limit) ||
      submitted.limit < 1 ||
      submitted.limit > 100)
  )
    return fail();
  const selected = value.selectedStartSequenceNumber;
  if (selected !== null && (!Number.isSafeInteger(selected) || selected < 1))
    return fail();
  return {
    version: 1,
    scope,
    patterns: value.patterns.map((cells: (string | null)[]) => [...cells]),
    activeIndex: value.activeIndex,
    entryOrder: value.entryOrder,
    lastSubmitted:
      submitted === null
        ? null
        : {
            patterns: submitted.patterns.map((pattern: BoardSearchPattern) => ({
              cells: pattern.cells.map((cell) => ({
                cellIndex: cell.cellIndex,
                symbolCode: cell.symbolCode,
              })),
            })),
            scope: submitted.scope,
            limit: submitted.limit,
          },
    selectedStartSequenceNumber: selected,
  };
}

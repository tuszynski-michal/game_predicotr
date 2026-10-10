export const BOARD_SEARCH_ROWS = 3;
export const BOARD_SEARCH_COLUMNS = 5;
export const BOARD_SEARCH_CELL_COUNT = BOARD_SEARCH_ROWS * BOARD_SEARCH_COLUMNS;
export const BOARD_SEARCH_UNKNOWN = '?';

export type BoardSearchEntryOrder = 'columns' | 'rows';

export interface BoardSearchEditorSnapshot {
  readonly cells: readonly (string | null)[];
  readonly selectedCellIndex: number;
}

export interface BoardSearchEditorState extends BoardSearchEditorSnapshot {
  readonly history: readonly BoardSearchEditorSnapshot[];
}

function emptyCells(): readonly null[] {
  return Object.freeze(Array<null>(BOARD_SEARCH_CELL_COUNT).fill(null));
}

function requireCellIndex(cellIndex: number): void {
  if (
    !Number.isInteger(cellIndex) ||
    cellIndex < 0 ||
    cellIndex >= BOARD_SEARCH_CELL_COUNT
  ) {
    throw new RangeError('Board-search cell index must be between 0 and 14.');
  }
}

function freezeSnapshot(
  snapshot: BoardSearchEditorSnapshot,
): BoardSearchEditorSnapshot {
  return Object.freeze({
    cells: Object.freeze([...snapshot.cells]),
    selectedCellIndex: snapshot.selectedCellIndex,
  });
}

function createState(
  cells: readonly (string | null)[],
  selectedCellIndex: number,
  history: readonly BoardSearchEditorSnapshot[],
): BoardSearchEditorState {
  requireCellIndex(selectedCellIndex);
  if (cells.length !== BOARD_SEARCH_CELL_COUNT) {
    throw new RangeError('Board-search editor must contain exactly 15 cells.');
  }
  return Object.freeze({
    cells: Object.freeze([...cells]),
    history: Object.freeze(history.map(freezeSnapshot)),
    selectedCellIndex,
  });
}

function currentSnapshot(
  state: BoardSearchEditorState,
): BoardSearchEditorSnapshot {
  return freezeSnapshot({
    cells: state.cells,
    selectedCellIndex: state.selectedCellIndex,
  });
}

function orderedCellIndexes(
  entryOrder: BoardSearchEntryOrder,
): readonly number[] {
  if (entryOrder === 'rows') {
    return Array.from({ length: BOARD_SEARCH_CELL_COUNT }, (_, index) => index);
  }
  return Array.from(
    { length: BOARD_SEARCH_CELL_COUNT },
    (_, index) =>
      (index % BOARD_SEARCH_ROWS) * BOARD_SEARCH_COLUMNS +
      Math.floor(index / BOARD_SEARCH_ROWS),
  );
}

function firstEmptyAfter(
  cells: readonly (string | null)[],
  currentCellIndex: number,
  entryOrder: BoardSearchEntryOrder,
): number {
  const indexes = orderedCellIndexes(entryOrder);
  const currentPosition = indexes.indexOf(currentCellIndex);
  for (let offset = 1; offset <= indexes.length; offset += 1) {
    const candidate = indexes[(currentPosition + offset) % indexes.length];
    if (cells[candidate] === null) {
      return candidate;
    }
  }
  return currentCellIndex;
}

export function createBoardSearchEditorState(): BoardSearchEditorState {
  return createState(emptyCells(), 0, []);
}

export function selectBoardSearchCell(
  state: BoardSearchEditorState,
  cellIndex: number,
): BoardSearchEditorState {
  requireCellIndex(cellIndex);
  if (cellIndex === state.selectedCellIndex) {
    return state;
  }
  return createState(state.cells, cellIndex, state.history);
}

export function placeBoardSearchSymbol(
  state: BoardSearchEditorState,
  symbolCode: string,
  entryOrder: BoardSearchEntryOrder = 'columns',
): BoardSearchEditorState {
  const normalizedSymbolCode = symbolCode.trim();
  if (!normalizedSymbolCode || normalizedSymbolCode === '?') {
    throw new Error('Board-search symbol must be a known catalog code.');
  }
  const cells = [...state.cells];
  cells[state.selectedCellIndex] = normalizedSymbolCode;
  return createState(
    cells,
    firstEmptyAfter(cells, state.selectedCellIndex, entryOrder),
    [...state.history, currentSnapshot(state)],
  );
}

export function placeBoardSearchUnknown(
  state: BoardSearchEditorState,
  entryOrder: BoardSearchEntryOrder = 'columns',
): BoardSearchEditorState {
  const cells = [...state.cells];
  cells[state.selectedCellIndex] = BOARD_SEARCH_UNKNOWN;
  return createState(
    cells,
    firstEmptyAfter(cells, state.selectedCellIndex, entryOrder),
    [...state.history, currentSnapshot(state)],
  );
}

export function selectBoardSearchEntryStart(
  state: BoardSearchEditorState,
  entryOrder: BoardSearchEntryOrder,
): BoardSearchEditorState {
  const firstEmptyCell = orderedCellIndexes(entryOrder).find(
    (cellIndex) => state.cells[cellIndex] === null,
  );
  if (
    firstEmptyCell === undefined ||
    firstEmptyCell === state.selectedCellIndex
  ) {
    return state;
  }
  return createState(state.cells, firstEmptyCell, state.history);
}

export function undoBoardSearchEdit(
  state: BoardSearchEditorState,
): BoardSearchEditorState {
  const previous = state.history.at(-1);
  if (previous === undefined) {
    return state;
  }
  return createState(
    previous.cells,
    previous.selectedCellIndex,
    state.history.slice(0, -1),
  );
}

export function resetBoardSearchEditor(
  state: BoardSearchEditorState,
): BoardSearchEditorState {
  if (
    state.history.length === 0 &&
    state.cells.every((cell) => cell === null)
  ) {
    return state;
  }
  return createBoardSearchEditorState();
}

export function selectedBoardSearchCells(
  state: BoardSearchEditorState,
): readonly { readonly cellIndex: number; readonly symbolCode: string }[] {
  return state.cells.flatMap((symbolCode, cellIndex) =>
    symbolCode === null || symbolCode === BOARD_SEARCH_UNKNOWN
      ? []
      : [{ cellIndex, symbolCode }],
  );
}

export function boardSearchPatternCellCount(
  state: BoardSearchEditorState,
): number {
  return state.cells.filter((symbolCode) => symbolCode !== null).length;
}

/**
 * Every filled cell of the pattern for a search request: known symbols and
 * `?` cells (as `null`). `?` carries no evidence and is ignored by scoring,
 * but a share link's query log keeps the whole pattern (D-472).
 */
export function patternBoardSearchCells(
  state: BoardSearchEditorState,
): readonly {
  readonly cellIndex: number;
  readonly symbolCode: string | null;
}[] {
  return state.cells.flatMap((symbolCode, cellIndex) =>
    symbolCode === null
      ? []
      : [
          {
            cellIndex,
            symbolCode: symbolCode === BOARD_SEARCH_UNKNOWN ? null : symbolCode,
          },
        ],
  );
}

/**
 * An editor holding a recorded pattern (replay, D-472). Codes outside
 * `activeSymbolCodes` become `?` and are reported, never dropped silently.
 */
export function boardSearchEditorFromPattern(
  cells: readonly {
    readonly cellIndex: number;
    readonly symbolCode: string | null;
  }[],
  activeSymbolCodes: ReadonlySet<string>,
): {
  readonly state: BoardSearchEditorState;
  readonly inactiveCodes: readonly string[];
} {
  const next: (string | null)[] = Array<string | null>(
    BOARD_SEARCH_CELL_COUNT,
  ).fill(null);
  const inactive = new Set<string>();
  for (const cell of cells) {
    requireCellIndex(cell.cellIndex);
    if (cell.symbolCode === null) {
      next[cell.cellIndex] = BOARD_SEARCH_UNKNOWN;
    } else if (activeSymbolCodes.has(cell.symbolCode)) {
      next[cell.cellIndex] = cell.symbolCode;
    } else {
      next[cell.cellIndex] = BOARD_SEARCH_UNKNOWN;
      inactive.add(cell.symbolCode);
    }
  }
  const firstEmpty = next.indexOf(null);
  return {
    inactiveCodes: [...inactive].sort(),
    state: createState(next, firstEmpty < 0 ? 0 : firstEmpty, []),
  };
}

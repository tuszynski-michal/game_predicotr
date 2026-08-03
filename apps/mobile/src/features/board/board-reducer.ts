export type BoardCell = number | null;

export interface BoardSnapshot {
  readonly anchorSequenceNumber: number | null;
  readonly cells: readonly BoardCell[];
}

export interface BoardState {
  readonly anchorSequenceNumber: number | null;
  readonly cells: readonly BoardCell[];
  readonly columns: number;
  readonly history: readonly BoardSnapshot[];
  readonly rejectedSuggestionPrefix: string | null;
  readonly rows: number;
  readonly selectedGameId: string | null;
}

export type BoardAction =
  | {
      readonly columns: number;
      readonly gameId: string;
      readonly rows: number;
      readonly type: 'select_game';
    }
  | {
      readonly mobileCode: number;
      readonly type: 'append_symbol';
    }
  | {
      readonly type: 'undo';
    }
  | {
      readonly type: 'reset';
    }
  | {
      readonly cells: readonly number[];
      readonly type: 'complete_board';
    }
  | {
      readonly cells: readonly number[];
      readonly sequenceNumber: number;
      readonly type: 'load_anchored_layout';
    }
  | {
      readonly signaturePrefix: string;
      readonly type: 'reject_suggestion';
    };

export class BoardStateError extends Error {
  readonly code = 'invalid_board_state';

  constructor(message: string) {
    super(message);
    this.name = 'BoardStateError';
  }
}

function requireDimensions(rows: number, columns: number): void {
  if (
    !Number.isSafeInteger(rows) ||
    !Number.isSafeInteger(columns) ||
    rows < 1 ||
    columns < 1
  ) {
    throw new BoardStateError(
      'Board dimensions must be positive safe integers.',
    );
  }
}

function requireGameId(gameId: string): void {
  if (gameId.trim().length === 0) {
    throw new BoardStateError('Selected game id must not be empty.');
  }
}

function requireMobileCode(mobileCode: number): void {
  if (!Number.isSafeInteger(mobileCode) || mobileCode < 1) {
    throw new BoardStateError(
      'Symbol mobile code must be a positive safe integer.',
    );
  }
}

function emptyCells(rows: number, columns: number): readonly null[] {
  return Object.freeze(Array<null>(rows * columns).fill(null));
}

function freezeHistory(
  history: readonly BoardSnapshot[],
): readonly BoardSnapshot[] {
  return Object.freeze(
    history.map((snapshot) =>
      Object.freeze({
        anchorSequenceNumber: snapshot.anchorSequenceNumber,
        cells: Object.freeze([...snapshot.cells]),
      }),
    ),
  );
}

function snapshot(state: BoardState): BoardSnapshot {
  return Object.freeze({
    anchorSequenceNumber: state.anchorSequenceNumber,
    cells: state.cells,
  });
}

function createState(
  selectedGameId: string | null,
  rows: number,
  columns: number,
  cells: readonly BoardCell[],
  history: readonly BoardSnapshot[],
  rejectedSuggestionPrefix: string | null,
  anchorSequenceNumber: number | null,
): BoardState {
  return Object.freeze({
    anchorSequenceNumber,
    cells: Object.freeze([...cells]),
    columns,
    history: freezeHistory(history),
    rejectedSuggestionPrefix,
    rows,
    selectedGameId,
  });
}

export function createEmptyBoardState(): BoardState {
  return createState(null, 0, 0, [], [], null, null);
}

export function createBoardState(
  gameId: string,
  rows: number,
  columns: number,
): BoardState {
  requireGameId(gameId);
  requireDimensions(rows, columns);
  return createState(
    gameId,
    rows,
    columns,
    emptyCells(rows, columns),
    [],
    null,
    null,
  );
}

export function enteredCellCount(state: BoardState): number {
  const firstEmptyIndex = state.cells.findIndex((cell) => cell === null);
  return firstEmptyIndex === -1 ? state.cells.length : firstEmptyIndex;
}

export function isBoardFull(state: BoardState): boolean {
  return (
    state.cells.length > 0 && enteredCellCount(state) === state.cells.length
  );
}

export function canUndo(state: BoardState): boolean {
  return state.history.length > 0;
}

function appendSymbol(state: BoardState, mobileCode: number): BoardState {
  requireMobileCode(mobileCode);
  const emptyIndex = state.cells.findIndex((cell) => cell === null);
  if (emptyIndex === -1) {
    return state;
  }

  const nextCells = [...state.cells];
  nextCells[emptyIndex] = mobileCode;
  return createState(
    state.selectedGameId,
    state.rows,
    state.columns,
    nextCells,
    [...state.history, snapshot(state)],
    null,
    null,
  );
}

function completeBoard(
  state: BoardState,
  completedCells: readonly number[],
): BoardState {
  if (
    state.selectedGameId === null ||
    completedCells.length !== state.cells.length
  ) {
    throw new BoardStateError(
      'Completed board must match the selected game dimensions.',
    );
  }

  completedCells.forEach(requireMobileCode);
  for (const [index, currentCell] of state.cells.entries()) {
    if (currentCell !== null && currentCell !== completedCells[index]) {
      throw new BoardStateError(
        'Completed board must preserve the manually entered prefix.',
      );
    }
  }
  if (state.cells.every((cell, index) => cell === completedCells[index])) {
    return state;
  }

  return createState(
    state.selectedGameId,
    state.rows,
    state.columns,
    completedCells,
    [...state.history, snapshot(state)],
    null,
    null,
  );
}

function loadAnchoredLayout(
  state: BoardState,
  cells: readonly number[],
  sequenceNumber: number,
): BoardState {
  if (state.selectedGameId === null || cells.length !== state.cells.length) {
    throw new BoardStateError(
      'Anchored layout must match the selected game dimensions.',
    );
  }
  cells.forEach(requireMobileCode);
  if (!Number.isSafeInteger(sequenceNumber) || sequenceNumber < 1) {
    throw new BoardStateError(
      'Anchor sequence number must be a positive safe integer.',
    );
  }
  if (
    state.anchorSequenceNumber === sequenceNumber &&
    state.cells.every((cell, index) => cell === cells[index])
  ) {
    return state;
  }

  return createState(
    state.selectedGameId,
    state.rows,
    state.columns,
    cells,
    [...state.history, snapshot(state)],
    null,
    sequenceNumber,
  );
}

function undo(state: BoardState): BoardState {
  const previous = state.history.at(-1);
  if (previous === undefined) {
    return state;
  }
  return createState(
    state.selectedGameId,
    state.rows,
    state.columns,
    previous.cells,
    state.history.slice(0, -1),
    null,
    previous.anchorSequenceNumber,
  );
}

function reset(state: BoardState): BoardState {
  if (state.selectedGameId === null) {
    return createEmptyBoardState();
  }
  return createBoardState(state.selectedGameId, state.rows, state.columns);
}

export function boardReducer(
  state: BoardState,
  action: BoardAction,
): BoardState {
  switch (action.type) {
    case 'select_game':
      if (
        state.selectedGameId === action.gameId &&
        state.rows === action.rows &&
        state.columns === action.columns
      ) {
        return state;
      }
      return createBoardState(action.gameId, action.rows, action.columns);
    case 'append_symbol':
      return appendSymbol(state, action.mobileCode);
    case 'complete_board':
      return completeBoard(state, action.cells);
    case 'load_anchored_layout':
      return loadAnchoredLayout(state, action.cells, action.sequenceNumber);
    case 'reject_suggestion':
      return createState(
        state.selectedGameId,
        state.rows,
        state.columns,
        state.cells,
        state.history,
        action.signaturePrefix,
        state.anchorSequenceNumber,
      );
    case 'undo':
      return undo(state);
    case 'reset':
      return reset(state);
  }
}

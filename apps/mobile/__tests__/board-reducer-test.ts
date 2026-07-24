import {
  boardReducer,
  BoardStateError,
  canUndo,
  createBoardState,
  enteredCellCount,
  isBoardFull,
} from '@/features/board/board-reducer';

describe('board reducer', () => {
  test('creates a fixed row-major board for the selected game', () => {
    const state = createBoardState('game-1', 2, 3);

    expect(state).toEqual({
      cells: [null, null, null, null, null, null],
      columns: 3,
      history: [],
      rejectedSuggestionPrefix: null,
      rows: 2,
      selectedGameId: 'game-1',
    });
    expect(enteredCellCount(state)).toBe(0);
    expect(isBoardFull(state)).toBe(false);
  });

  test('appends symbols to the first empty cell in row-major order', () => {
    const initial = createBoardState('game-1', 2, 3);
    const first = boardReducer(initial, {
      mobileCode: 4,
      type: 'append_symbol',
    });
    const second = boardReducer(first, {
      mobileCode: 2,
      type: 'append_symbol',
    });

    expect(second.cells).toEqual([4, 2, null, null, null, null]);
    expect(enteredCellCount(second)).toBe(2);
    expect(second.history).toHaveLength(2);
    expect(initial.cells).toEqual([null, null, null, null, null, null]);
  });

  test('undo removes one manually appended symbol', () => {
    const initial = createBoardState('game-1', 1, 2);
    const entered = boardReducer(initial, {
      mobileCode: 4,
      type: 'append_symbol',
    });
    const undone = boardReducer(entered, { type: 'undo' });

    expect(undone.cells).toEqual([null, null]);
    expect(canUndo(undone)).toBe(false);
  });

  test('undo treats automatic completion as one operation', () => {
    const initial = createBoardState('game-1', 2, 2);
    const prefix = boardReducer(initial, {
      mobileCode: 1,
      type: 'append_symbol',
    });
    const completed = boardReducer(prefix, {
      cells: [1, 2, 3, 4],
      type: 'complete_board',
    });

    expect(completed.cells).toEqual([1, 2, 3, 4]);
    expect(isBoardFull(completed)).toBe(true);
    expect(boardReducer(completed, { type: 'undo' }).cells).toEqual([
      1,
      null,
      null,
      null,
    ]);
  });

  test('reset preserves the game and clears all input context', () => {
    let state = createBoardState('game-1', 1, 3);
    state = boardReducer(state, {
      mobileCode: 2,
      type: 'append_symbol',
    });
    state = boardReducer(state, {
      signaturePrefix: '02',
      type: 'reject_suggestion',
    });

    const reset = boardReducer(state, { type: 'reset' });

    expect(reset).toEqual({
      cells: [null, null, null],
      columns: 3,
      history: [],
      rejectedSuggestionPrefix: null,
      rows: 1,
      selectedGameId: 'game-1',
    });
  });

  test('changing game replaces dimensions and clears previous context', () => {
    const entered = boardReducer(createBoardState('game-1', 1, 2), {
      mobileCode: 1,
      type: 'append_symbol',
    });

    const changed = boardReducer(entered, {
      columns: 3,
      gameId: 'game-2',
      rows: 2,
      type: 'select_game',
    });

    expect(changed.selectedGameId).toBe('game-2');
    expect(changed.cells).toEqual([null, null, null, null, null, null]);
    expect(changed.history).toEqual([]);
    expect(changed.rejectedSuggestionPrefix).toBeNull();
  });

  test('does not append beyond a full board', () => {
    let state = createBoardState('game-1', 1, 2);
    state = boardReducer(state, {
      mobileCode: 1,
      type: 'append_symbol',
    });
    state = boardReducer(state, {
      mobileCode: 2,
      type: 'append_symbol',
    });

    expect(boardReducer(state, { mobileCode: 3, type: 'append_symbol' })).toBe(
      state,
    );
    expect(state.cells).toEqual([1, 2]);
  });

  test('changing the board clears a rejected suggestion prefix', () => {
    const rejected = boardReducer(createBoardState('game-1', 1, 2), {
      signaturePrefix: '01',
      type: 'reject_suggestion',
    });

    const changed = boardReducer(rejected, {
      mobileCode: 1,
      type: 'append_symbol',
    });

    expect(changed.rejectedSuggestionPrefix).toBeNull();
  });

  test('rejects an invalid completion or symbol code', () => {
    const state = boardReducer(createBoardState('game-1', 1, 2), {
      mobileCode: 1,
      type: 'append_symbol',
    });

    expect(() =>
      boardReducer(state, {
        cells: [2, 1],
        type: 'complete_board',
      }),
    ).toThrow(BoardStateError);
    expect(() =>
      boardReducer(state, {
        mobileCode: 0,
        type: 'append_symbol',
      }),
    ).toThrow(BoardStateError);
  });
});

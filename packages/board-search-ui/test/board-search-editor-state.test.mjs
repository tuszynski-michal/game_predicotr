import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createBoardSearchEditorState,
  boardSearchPatternCellCount,
  placeBoardSearchSymbol,
  placeBoardSearchUnknown,
  resetBoardSearchEditor,
  selectBoardSearchCell,
  selectBoardSearchEntryStart,
  selectedBoardSearchCells,
  undoBoardSearchEdit,
} from '../src/board-search-editor-state.ts';

test('places symbols by columns by default and preserves canonical cell indexes', () => {
  let state = createBoardSearchEditorState();
  state = placeBoardSearchSymbol(state, 'lemon');
  state = placeBoardSearchSymbol(state, 'bell');

  assert.deepEqual(selectedBoardSearchCells(state), [
    { cellIndex: 0, symbolCode: 'lemon' },
    { cellIndex: 5, symbolCode: 'bell' },
  ]);
  assert.equal(state.selectedCellIndex, 10);
});

test('can place symbols by rows when the operator selects row order', () => {
  let state = createBoardSearchEditorState();
  state = placeBoardSearchSymbol(state, 'lemon', 'rows');
  state = placeBoardSearchSymbol(state, 'bell', 'rows');

  assert.deepEqual(selectedBoardSearchCells(state), [
    { cellIndex: 0, symbolCode: 'lemon' },
    { cellIndex: 1, symbolCode: 'bell' },
  ]);
  assert.equal(state.selectedCellIndex, 2);
});

test('lets the operator replace an explicitly selected cell and undo that exact change', () => {
  let state = createBoardSearchEditorState();
  state = placeBoardSearchSymbol(state, 'lemon');
  state = placeBoardSearchSymbol(state, 'bell');
  state = selectBoardSearchCell(state, 0);
  state = placeBoardSearchSymbol(state, 'seven');
  state = undoBoardSearchEdit(state);

  assert.deepEqual(selectedBoardSearchCells(state), [
    { cellIndex: 0, symbolCode: 'lemon' },
    { cellIndex: 5, symbolCode: 'bell' },
  ]);
  assert.equal(state.selectedCellIndex, 0);
});

test('resets the partial pattern and its history without a search request', () => {
  let state = createBoardSearchEditorState();
  state = placeBoardSearchSymbol(state, 'lemon');
  state = resetBoardSearchEditor(state);

  assert.deepEqual(selectedBoardSearchCells(state), []);
  assert.equal(state.history.length, 0);
  assert.equal(state.selectedCellIndex, 0);
});

test('keeps logical unknown in the editor but omits it from search evidence', () => {
  let state = createBoardSearchEditorState();
  state = placeBoardSearchUnknown(state);
  state = placeBoardSearchSymbol(state, 'bell');

  assert.equal(state.cells[0], '?');
  assert.equal(state.cells[5], 'bell');
  assert.equal(boardSearchPatternCellCount(state), 2);
  assert.deepEqual(selectedBoardSearchCells(state), [
    { cellIndex: 5, symbolCode: 'bell' },
  ]);

  state = undoBoardSearchEdit(state);
  assert.equal(state.cells[0], '?');
  assert.equal(state.cells[5], null);
  state = resetBoardSearchEditor(state);
  assert.equal(boardSearchPatternCellCount(state), 0);
});

test('changing entry order preserves values and selects its first empty cell', () => {
  let state = createBoardSearchEditorState();
  state = placeBoardSearchSymbol(state, 'lemon');
  state = placeBoardSearchSymbol(state, 'bell');
  state = selectBoardSearchEntryStart(state, 'rows');

  assert.deepEqual(selectedBoardSearchCells(state), [
    { cellIndex: 0, symbolCode: 'lemon' },
    { cellIndex: 5, symbolCode: 'bell' },
  ]);
  assert.equal(state.selectedCellIndex, 1);
});

test('pattern cells include unknown cells as null for the request', async () => {
  const { patternBoardSearchCells, placeBoardSearchUnknown } =
    await import('../src/board-search-editor-state.ts');
  let state = createBoardSearchEditorState();
  state = placeBoardSearchSymbol(state, 'A', 'rows');
  state = placeBoardSearchUnknown(state, 'rows');
  state = placeBoardSearchSymbol(state, 'B', 'rows');
  assert.deepEqual(patternBoardSearchCells(state), [
    { cellIndex: 0, symbolCode: 'A' },
    { cellIndex: 1, symbolCode: null },
    { cellIndex: 2, symbolCode: 'B' },
  ]);
});

test('a recorded pattern becomes an editor; inactive symbols turn into ?', async () => {
  const { boardSearchEditorFromPattern } =
    await import('../src/board-search-editor-state.ts');
  const { state, inactiveCodes } = boardSearchEditorFromPattern(
    [
      { cellIndex: 4, symbolCode: 'A' },
      { cellIndex: 0, symbolCode: null },
      { cellIndex: 7, symbolCode: 'OLD' },
    ],
    new Set(['A', 'B']),
  );
  assert.equal(state.cells[0], '?');
  assert.equal(state.cells[4], 'A');
  assert.equal(state.cells[7], '?');
  assert.deepEqual(inactiveCodes, ['OLD']);
  assert.equal(state.selectedCellIndex, 1);
  assert.deepEqual(state.history, []);
});

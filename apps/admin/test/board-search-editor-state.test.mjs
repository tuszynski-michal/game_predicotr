import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createBoardSearchEditorState,
  boardSearchPatternCellCount,
  placeBoardSearchSymbol,
  placeBoardSearchUnknown,
  resetBoardSearchEditor,
  selectBoardSearchCell,
  selectedBoardSearchCells,
  undoBoardSearchEdit,
} from '../src/features/board-search/board-search-editor-state.ts';

test('places symbols sequentially and advances to the next empty board-search cell', () => {
  let state = createBoardSearchEditorState();
  state = placeBoardSearchSymbol(state, 'lemon');
  state = placeBoardSearchSymbol(state, 'bell');

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
    { cellIndex: 1, symbolCode: 'bell' },
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

  assert.deepEqual(state.cells.slice(0, 2), ['?', 'bell']);
  assert.equal(boardSearchPatternCellCount(state), 2);
  assert.deepEqual(selectedBoardSearchCells(state), [
    { cellIndex: 1, symbolCode: 'bell' },
  ]);

  state = undoBoardSearchEdit(state);
  assert.deepEqual(state.cells.slice(0, 2), ['?', null]);
  state = resetBoardSearchEditor(state);
  assert.equal(boardSearchPatternCellCount(state), 0);
});

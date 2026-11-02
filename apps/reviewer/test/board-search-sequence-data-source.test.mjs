import assert from 'node:assert/strict';
import test from 'node:test';
import { createBoardSearchShareDataSource } from '../src/features/board-search-share/board-search-share-data-source.ts';
test('share adapter exposes single search only', () => {
  const source = createBoardSearchShareDataSource({});
  assert.equal(source.searchGameBoardSequence, undefined);
  assert.equal(typeof source.searchGameBoards, 'function');
});

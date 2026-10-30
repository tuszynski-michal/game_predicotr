import assert from 'node:assert/strict';
import test from 'node:test';
import {
  boardSearchSequenceInput,
  boardSearchSequenceEditorsFromPatterns,
  readBoardSearchSequenceLocalState,
  boardSearchSequenceStorageKey,
} from '../src/board-search-local-state.ts';

const pattern = (code) => ({ cells: [{ cellIndex: 0, symbolCode: code }] });
const active = new Set(['A', 'B']);
test('local v1 preserves dirty draft separately from submitted patterns and keeps scope keys isolated', () => {
  const record = {
    version: 1,
    scope: 'share:one',
    patterns: boardSearchSequenceEditorsFromPatterns([pattern('archived')]).map(
      (editor) => editor.cells,
    ),
    activeIndex: 0,
    entryOrder: 'rows',
    lastSubmitted: {
      patterns: [pattern('A')],
      scope: 'approved_only',
      limit: 7,
    },
    selectedStartSequenceNumber: 6,
    searchContextId: 'secret',
    results: [1],
  };
  const read = readBoardSearchSequenceLocalState(
    JSON.stringify(record),
    'share:one',
  );
  assert.equal(read.patterns[0][0], 'archived');
  assert.deepEqual(read.lastSubmitted.patterns, [pattern('A')]);
  assert.equal(read.searchContextId, undefined);
  assert.equal(read.results, undefined);
  assert.throws(() =>
    readBoardSearchSequenceLocalState(JSON.stringify(record), 'panel:one:one'),
  );
  assert.notEqual(
    boardSearchSequenceStorageKey('admin:one'),
    boardSearchSequenceStorageKey('share:one'),
  );
  assert.notEqual(
    boardSearchSequenceStorageKey('panel:a:one'),
    boardSearchSequenceStorageKey('panel:b:one'),
  );
});
test('invalid versions, cells, selected identity and submitted requests never hydrate', () => {
  const valid = {
    version: 1,
    scope: 'admin:g',
    patterns: [Array(15).fill(null)],
    activeIndex: 0,
    entryOrder: 'columns',
    lastSubmitted: null,
    selectedStartSequenceNumber: null,
  };
  for (const change of [
    { version: 2 },
    { patterns: [] },
    { patterns: [[]] },
    { activeIndex: 1 },
    { entryOrder: 'diagonal' },
    { selectedStartSequenceNumber: 0 },
    {
      lastSubmitted: {
        patterns: [{ cells: [{ cellIndex: 15, symbolCode: 'A' }] }],
        scope: 'all_searchable',
        limit: 15,
      },
    },
  ])
    assert.throws(() =>
      readBoardSearchSequenceLocalState(
        JSON.stringify({ ...valid, ...change }),
        'admin:g',
      ),
    );
  assert.throws(() => readBoardSearchSequenceLocalState('{', 'admin:g'));
});

test('single input validates evidence and refuses multiple editors', () => {
  assert.equal(
    boardSearchSequenceInput(
      boardSearchSequenceEditorsFromPatterns([pattern('A')]),
      active,
    ).error,
    null,
  );
  assert.match(
    boardSearchSequenceInput(
      boardSearchSequenceEditorsFromPatterns([pattern('A'), pattern('B')]),
      active,
    ).error,
    /zostało usunięte/,
  );
  assert.match(
    boardSearchSequenceInput(
      boardSearchSequenceEditorsFromPatterns([pattern(null)]),
      active,
    ).error,
    /znany symbol/,
  );
});

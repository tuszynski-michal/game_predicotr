import assert from 'node:assert/strict';
import test from 'node:test';
import {
  boardSearchSequenceInput,
  boardSearchSequenceEditorsFromPatterns,
  boardSearchSequenceEditor,
  boardSearchSequenceKey,
  readBoardSearchSequenceLocalState,
  boardSearchSequenceStorageKey,
} from '../src/board-search-sequence-state.ts';

const pattern = (code) => ({ cells: [{ cellIndex: 0, symbolCode: code }] });
const active = new Set(['A', 'B']);
test('trailing empty slots are ignored; interior gaps and only-unknown slots block without shifting spins', () => {
  const filled = boardSearchSequenceEditorsFromPatterns([
    pattern('A'),
    pattern('B'),
  ]);
  const empty = boardSearchSequenceEditor(Array(15).fill(null));
  assert.deepEqual(
    boardSearchSequenceInput([...filled, empty, empty], active).patterns,
    [pattern('A'), pattern('B')],
  );
  assert.match(
    boardSearchSequenceInput([filled[0], empty, filled[1]], active).error,
    /układ 2/,
  );
  assert.match(
    boardSearchSequenceInput(
      boardSearchSequenceEditorsFromPatterns([pattern(null)]),
      active,
    ).error,
    /znany symbol/,
  );
  assert.match(
    boardSearchSequenceInput(
      boardSearchSequenceEditorsFromPatterns([pattern('archived')]),
      active,
    ).error,
    /nie jest już aktywny/,
  );
  assert.notEqual(
    boardSearchSequenceKey([pattern('A'), pattern('B')]),
    boardSearchSequenceKey([pattern('B'), pattern('A')]),
  );
});
test('local v1 preserves dirty draft separately from submitted patterns and keeps scope keys isolated', () => {
  const record = {
    version: 1,
    scope: 'share:one',
    patterns: boardSearchSequenceEditorsFromPatterns([
      pattern('archived'),
      pattern(null),
    ]).map((editor) => editor.cells),
    activeIndex: 1,
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
  assert.equal(read.patterns[1][0], '?');
  assert.equal(read.patterns[1][1], null);
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

import assert from 'node:assert/strict';
import test from 'node:test';
import { boardSearchReplayPlan } from '../src/features/board-search/board-search-replay-state.ts';
import {
  boardSearchQueryPatterns,
  describeBoardSearchQueryEntry,
} from '../src/features/board-search/board-search-share-query-log-state.ts';
const entry = {
  id: 'search',
  kind: 'search',
  request: {
    version: 2,
    patterns: [{ cells: ['0:A', '14:?'] }, { cells: ['5:B'] }],
    scope: 'approved_only',
    limit: 7,
  },
  resultSummary: {
    patternCount: 2,
    resultCount: 1,
    firstEndSequenceNumbers: [1],
  },
  outcomeCode: 'ok',
};
test('v2 replay preserves every ordered pattern and follow-up end anchor', () => {
  const approximateWin = {
    id: 'range',
    kind: 'approximate_win',
    request: { startSequenceNumber: 1, spinCount: 50 },
  };
  const event = {
    id: 'detail',
    kind: 'board_detail',
    request: { sequenceNumber: 3 },
  };
  const result = boardSearchReplayPlan(
    { search: entry, event, approximateWin },
    'nonce',
  );
  assert.equal(result.kind, 'plan');
  assert.deepEqual(result.plan.patterns, [
    {
      cells: [
        { cellIndex: 0, symbolCode: 'A' },
        { cellIndex: 14, symbolCode: null },
      ],
    },
    { cells: [{ cellIndex: 5, symbolCode: 'B' }] },
  ]);
  assert.deepEqual(result.plan.approximateWin, {
    startSequenceNumber: 1,
    spinCount: 50,
  });
  assert.equal(result.plan.boardSequenceNumber, 3);
  assert.equal(result.plan.scope, 'approved_only');
  const invalid = {
    ...entry,
    request: {
      ...entry.request,
      patterns: [{ cells: ['0:A'] }, { cells: ['15:B'] }],
      cells: ['0:legacy'],
    },
  };
  assert.equal(
    boardSearchReplayPlan(
      { search: invalid, event: invalid, approximateWin: null },
      'x',
    ).kind,
    'no_search',
  );
});
test('v2 log shows all grids and end numbers, legacy still shows board numbers', () => {
  const patterns = boardSearchQueryPatterns(entry);
  assert.equal(patterns.length, 2);
  assert.equal(patterns[0][14], '?');
  assert.equal(patterns[1][5], 'B');
  assert.match(
    describeBoardSearchQueryEntry(entry).details,
    /Ciąg: 2 układów.*końce ciągów: #1/,
  );
  const legacy = {
    ...entry,
    request: { cells: ['0:A'], scope: 'all_searchable', limit: 15 },
    resultSummary: { firstSequenceNumbers: [6], resultCount: 1 },
  };
  assert.equal(boardSearchQueryPatterns(legacy).length, 1);
  assert.match(describeBoardSearchQueryEntry(legacy).details, /\(#6\)/);
  assert.doesNotMatch(
    describeBoardSearchQueryEntry(legacy).details,
    /końce ciągów/,
  );
  assert.deepEqual(
    boardSearchQueryPatterns({
      ...entry,
      request: { version: 2, cells: ['0:legacy'] },
    }),
    [],
  );
});

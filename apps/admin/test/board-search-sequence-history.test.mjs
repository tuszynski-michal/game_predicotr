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
test('multi history and its follow-up are readable but cannot replay', () => {
  for (const event of [
    entry,
    { id: 'detail', kind: 'board_detail', request: { sequenceNumber: 3 } },
  ]) {
    const result = boardSearchReplayPlan(
      { search: entry, event, approximateWin: null },
      'new',
    );
    assert.equal(result.kind, 'no_search');
    assert.match(result.message, /zostało usunięte/);
  }
  const one = {
    ...entry,
    request: { ...entry.request, patterns: [entry.request.patterns[0]] },
  };
  assert.equal(
    boardSearchReplayPlan(
      { search: one, event: one, approximateWin: null },
      'one',
    ).kind,
    'plan',
  );
});

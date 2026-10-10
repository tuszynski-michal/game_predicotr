import assert from 'node:assert/strict';
import test from 'node:test';

import { approximateWinRequestKey } from '../src/board-search-approximate-win-state.ts';
import {
  boardCountMatches,
  boardCountedCells,
  boardLinesConsistency,
} from '../src/board-search-board-lines-state.ts';
import {
  LATEST_PUBLISHED_RULES_VALUE,
  boardCountMatchLabel,
  boardSearchRulesVersionLabel,
  rulesVersionFromSelectValue,
  selectableBoardSearchRulesVersions,
} from '../src/board-search-rules-versions.ts';

test('only draft and published rules versions are offered, newest first', () => {
  assert.deepEqual(
    selectableBoardSearchRulesVersions([
      { id: 'v1', status: 'archived', version: 1 },
      { id: 'v2', status: 'published', version: 2 },
      { id: 'v3', status: 'draft', version: 3 },
    ]),
    [
      { id: 'v3', status: 'draft', version: 3 },
      { id: 'v2', status: 'published', version: 2 },
    ],
  );
  assert.equal(
    boardSearchRulesVersionLabel({ id: 'v3', status: 'draft', version: 3 }),
    'v3 · draft',
  );
  assert.equal(
    boardSearchRulesVersionLabel({ id: 'v2', status: 'published', version: 2 }),
    'v2 · opublikowana',
  );
  assert.equal(rulesVersionFromSelectValue(LATEST_PUBLISHED_RULES_VALUE), null);
  assert.equal(rulesVersionFromSelectValue('v3'), 'v3');
});

test('a chosen rules version is part of the approximate-win request key', () => {
  const base = { gameId: 'g', resultIdentity: 'r', spinCount: 10 };
  // The default key is unchanged, so earlier cached results stay valid.
  assert.equal(approximateWinRequestKey(base), 'g|r|10');
  assert.equal(
    approximateWinRequestKey({ ...base, rulesVersionId: null }),
    'g|r|10',
  );
  assert.equal(
    approximateWinRequestKey({ ...base, rulesVersionId: 'draft-1' }),
    'g|r|10|rules:draft-1',
  );
});

test('count payouts take part in the line check and are labelled per symbol', () => {
  const detail = {
    countMatches: [
      { cells: [1, 7, 10], count: 3, payoutCredits: 20, symbolCode: 'M' },
    ],
    matches: [{ payoutCredits: 25 }],
    payoutCredits: 45,
    rules: { rulesVersionId: 'draft-1' },
  };
  assert.deepEqual(boardLinesConsistency(detail, 45, 'draft-1'), {
    kind: 'consistent',
  });
  assert.deepEqual(
    boardLinesConsistency({ ...detail, countMatches: [] }, 45, 'draft-1'),
    { kind: 'inconsistent', reason: 'lines' },
  );
  // An older response without the field still reads as "no count payouts".
  assert.deepEqual(boardCountMatches({}), []);
  assert.deepEqual([...boardCountedCells(detail.countMatches)], [1, 7, 10]);
  assert.equal(
    boardCountMatchLabel(detail.countMatches[0], [
      { code: 'M', name: 'Mumia' },
    ]),
    'Mumia ×3',
  );
  assert.equal(boardCountMatchLabel(detail.countMatches[0], []), 'M ×3');
});

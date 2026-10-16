import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import {
  evaluationCommand,
  metricChange,
  needsCurrentnessCheck,
  parseExtraCohorts,
} from '../src/features/model-quality/grid-model-evaluation-state.ts';

const metrics = (overrides = {}) => ({
  photos: 5,
  photo_complete_correct: 3,
  photo_complete_correct_rate: 0.6,
  boards_expected: 45,
  boards_correct: 40,
  board_correct_rate: 40 / 45,
  boards_matched: 44,
  detection_recall: 44 / 45,
  false_boards: 0,
  duplicate_predictions: 0,
  image_macro: 0.05,
  nme_p95: 0.01,
  max_node_error_p95: 0.03,
  ...overrides,
});

test('comparison direction treats missing quality as the worst value', () => {
  assert.equal(
    metricChange(
      metrics(),
      metrics({ boards_correct: 41 }),
      'boards_correct',
      'higher',
    ),
    'better',
  );
  assert.equal(
    metricChange(
      metrics(),
      metrics({ false_boards: 1 }),
      'false_boards',
      'lower',
    ),
    'worse',
  );
  assert.equal(
    metricChange(
      metrics(),
      metrics({ image_macro: null }),
      'image_macro',
      'lower',
    ),
    'worse',
  );
  assert.equal(metricChange(metrics(), metrics(), 'photos', null), 'info');
  assert.equal(
    metricChange(metrics(), metrics(), 'boards_matched', 'higher'),
    'same',
  );
});

test('extra cohorts are exact game and cohort UUID pairs', () => {
  const game = '11111111-1111-4111-8111-111111111111';
  const cohort = '22222222-2222-4222-8222-222222222222';
  assert.deepEqual(parseExtraCohorts(`\n${game} ${cohort}\n`), [
    { gameId: game, cohortId: cohort },
  ]);
  assert.equal(parseExtraCohorts(`${game}`), null);
  assert.equal(parseExtraCohorts('a b'), null);
});

test('a retry reuses its key only for exactly the same command', () => {
  let next = 0;
  const key = () => `key-${(next += 1)}`;
  const body = {
    versionId: 'v',
    cohorts: [
      { gameId: 'b', cohortId: '2' },
      { gameId: 'a', cohortId: '1' },
    ],
  };
  const first = evaluationCommand(null, body, key);
  const retry = evaluationCommand(
    first,
    { ...body, cohorts: [...body.cohorts].reverse() },
    key,
  );
  assert.equal(retry, first);
  const changed = evaluationCommand(
    first,
    { ...body, cohorts: [{ gameId: 'a', cohortId: '1' }] },
    key,
  );
  assert.notEqual(changed.key, first.key);
  assert.notEqual(
    evaluationCommand(first, { ...body, versionId: 'w' }, key).key,
    first.key,
  );
});

test('stale or missing proofs ask for a currentness check', () => {
  assert.equal(needsCurrentnessCheck([{ state: 'current' }]), false);
  assert.equal(
    needsCurrentnessCheck([{ state: 'current' }, { state: 'stale' }]),
    true,
  );
});

test('the comparison panel never publishes and is part of the V3 workspace', async () => {
  const panel = await readFile(
    new URL(
      '../src/features/model-quality/grid-model-comparison.tsx',
      import.meta.url,
    ),
    'utf8',
  );
  const workspace = await readFile(
    new URL(
      '../src/features/model-quality/model-quality-workspace.tsx',
      import.meta.url,
    ),
    'utf8',
  );
  assert.match(workspace, /<GridModelComparison/);
  assert.match(panel, /Sprawdź aktualność/);
  // An answer for an earlier candidate or detail request never replaces the view.
  assert.match(panel, /currentVersion\.current !== versionId/);
  assert.match(panel, /token !== openRequest\.current/);
  assert.match(panel, /disabled=\{busy\}\s+onChange=\{\(event\) => setRunId/);
  assert.equal(panel.match(/token !== openRequest\.current/g).length, 2);
  assert.match(panel, /REGRESSION \(tylko końcowa kontrola\)/);
  assert.doesNotMatch(
    panel,
    /publishGridModelVersion|activateGameGridModel|setGridModelDefault/,
  );
});

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  compatibleDatasets,
  compatibleRules,
  createInitialSelections,
  formatReleaseTimestamp,
  hasCompatibleReleasePair,
  releaseStatusLabel,
  upsertRelease,
  validateReleaseDraft,
} from '../src/features/releases/release-state.ts';

const game = {
  code: 'game-1',
  createdAt: '2026-07-27T10:00:00Z',
  id: 'game-1',
  name: 'Game One',
  status: 'active',
  updatedAt: '2026-07-27T10:00:00Z',
};

function dataset(overrides = {}) {
  return {
    columns: 5,
    createdAt: '2026-07-27T10:00:00Z',
    gameId: game.id,
    generationSeed: 1,
    generatorVersion: 'mock-v1',
    id: 'dataset-1',
    layoutCount: 1000,
    publishedAt: '2026-07-27T10:05:00Z',
    rows: 3,
    signatureCellWidth: 2,
    sourceJobId: null,
    status: 'published',
    version: 1,
    ...overrides,
  };
}

function rules(overrides = {}) {
  return {
    columns: 5,
    createdAt: '2026-07-27T10:00:00Z',
    gameId: game.id,
    id: 'rules-1',
    publishedAt: '2026-07-27T10:05:00Z',
    rows: 3,
    spinCost: 10,
    status: 'published',
    version: 1,
    ...overrides,
  };
}

const source = {
  datasets: [
    dataset(),
    dataset({ id: 'dataset-wrong', columns: 6, version: 2 }),
    dataset({ id: 'dataset-draft', status: 'staging', version: 3 }),
  ],
  game,
  rulesVersions: [
    rules(),
    rules({ id: 'rules-wrong', rows: 4, version: 2 }),
    rules({ id: 'rules-draft', status: 'draft', version: 3 }),
  ],
};

test('selects only published sources with identical non-empty dimensions', () => {
  assert.deepEqual(
    compatibleRules(source, 'dataset-1').map((item) => item.id),
    ['rules-1'],
  );
  assert.deepEqual(
    compatibleDatasets(source, 'rules-1').map((item) => item.id),
    ['dataset-1'],
  );
  assert.equal(hasCompatibleReleasePair(source), true);
  assert.equal(
    hasCompatibleReleasePair({
      ...source,
      datasets: [dataset({ layoutCount: 0 })],
    }),
    false,
  );
});

test('builds a typed immutable selection and rejects incomplete drafts', () => {
  const [selection] = createInitialSelections([source]);
  assert.deepEqual(selection, {
    datasetVersionId: 'dataset-1',
    gameId: 'game-1',
    included: false,
    rulesVersionId: 'rules-1',
  });

  assert.equal(
    validateReleaseDraft(
      { selections: [{ ...selection, included: true }], version: 'm3.4.1' },
      [source],
    ).valid,
    true,
  );
  assert.equal(
    validateReleaseDraft({ selections: [selection], version: 'm3.4.1' }, [
      source,
    ]).valid,
    false,
  );
  assert.equal(
    validateReleaseDraft(
      { selections: [{ ...selection, included: true }], version: '../bad' },
      [source],
    ).valid,
    false,
  );
});

test('presents release history deterministically', () => {
  const older = {
    createdAt: '2026-07-27T10:00:00Z',
    id: 'release-1',
  };
  const newer = {
    createdAt: '2026-07-27T11:00:00Z',
    id: 'release-2',
  };
  assert.deepEqual(
    upsertRelease([older], newer).map((item) => item.id),
    ['release-2', 'release-1'],
  );
  assert.equal(releaseStatusLabel('ready'), 'Gotowe');
  assert.equal(formatReleaseTimestamp(null), '—');
});

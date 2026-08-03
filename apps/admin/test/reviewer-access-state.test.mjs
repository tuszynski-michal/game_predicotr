import assert from 'node:assert/strict';
import test from 'node:test';

import {
  hasImageImport,
  reviewableGames,
  reviewReadyImports,
  selectReviewImportId,
} from '../src/features/reviewer-access/reviewer-access-state.ts';

const gameId = 'game-1';

test('keeps draft and active games available for review', () => {
  const game = {
    code: 'game',
    createdAt: '2026-08-01T10:00:00Z',
    expectedLayoutCount: 500000,
    id: gameId,
    name: 'Game',
    updatedAt: '2026-08-01T10:00:00Z',
  };

  assert.deepEqual(
    reviewableGames([
      { ...game, status: 'active' },
      { ...game, id: 'game-draft', status: 'draft' },
      { ...game, id: 'game-archived', status: 'archived' },
    ]).map((item) => item.id),
    [gameId, 'game-draft'],
  );
});

function imageJob(overrides = {}) {
  return {
    createdAt: '2026-08-01T10:00:00Z',
    gameId,
    id: 'job-ready',
    inputPayload: {
      importKind: 'image_directory',
      pipelineFingerprint: 'a'.repeat(64),
      schemaVersion: 1,
    },
    jobType: 'import',
    status: 'waiting_for_review',
    ...overrides,
  };
}

test('selects the newest ready image import and preserves an explicit choice', () => {
  const older = imageJob({
    createdAt: '2026-08-01T08:00:00Z',
    id: 'job-older',
    status: 'completed',
  });
  const newest = imageJob();
  const processing = imageJob({
    createdAt: '2026-08-01T11:00:00Z',
    id: 'job-processing',
    status: 'processing',
  });
  const otherGame = imageJob({ gameId: 'game-2', id: 'job-other' });

  assert.deepEqual(
    reviewReadyImports([processing, older, otherGame, newest], gameId).map(
      (job) => job.id,
    ),
    ['job-ready', 'job-older'],
  );
  assert.equal(selectReviewImportId([older, newest], gameId, ''), newest.id);
  assert.equal(
    selectReviewImportId([older, newest], gameId, older.id),
    older.id,
  );
});

test('distinguishes an unfinished image import from no image import', () => {
  const processing = imageJob({ status: 'processing' });
  const fileImport = imageJob({
    inputPayload: {
      contractVersion: 1,
      fileFormat: 'csv',
      importKind: 'layout_file',
      schemaVersion: 1,
      sourceChecksum: 'b'.repeat(64),
      sourcePath: 'layouts.csv',
      sourceSizeBytes: 100,
    },
  });

  assert.equal(hasImageImport([processing], gameId), true);
  assert.equal(hasImageImport([fileImport], gameId), false);
  assert.equal(reviewReadyImports([processing], gameId).length, 0);
});

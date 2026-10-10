import assert from 'node:assert/strict';
import test from 'node:test';

import {
  hasImageImport,
  readyBoardImportStaging,
  reviewableGames,
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
      sourceDisplayName: '19810 - 45162',
    },
    jobType: 'import',
    status: 'waiting_for_review',
    ...overrides,
  };
}

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
  assert.equal(hasImageImport([processing], 'game-2'), false);
});

test('scopes ready staging to the game', () => {
  const staging = {
    createdAt: '2026-08-01T10:00:00Z',
    displayName: '19810 - 45162',
    expectedFileCount: 2817,
    expectedTotalBytes: 744_900_000,
    gameId,
    manifestChecksumSha256: 'a'.repeat(64),
    purpose: 'layout_import',
    uploadId: 'staging-newest',
    uploadedBytes: 744_900_000,
    uploadedFileCount: 2817,
  };

  assert.deepEqual(
    readyBoardImportStaging(
      [
        { ...staging, gameId: 'game-2', uploadId: 'other-game' },
        { ...staging, createdAt: '2026-08-01T09:00:00Z', uploadId: 'older' },
        { ...staging, purpose: 'image_selection', uploadId: 'wrong-purpose' },
        staging,
      ],
      gameId,
    ).map((item) => item.uploadId),
    ['staging-newest', 'older'],
  );
});

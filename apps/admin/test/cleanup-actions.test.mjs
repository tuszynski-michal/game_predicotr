import assert from 'node:assert/strict';
import test from 'node:test';

import {
  executeCleanup,
  loadCleanupPreview,
} from '../src/features/cleanup/cleanup-actions.ts';

const preview = {
  artifactPaths: ['snapshots/v-test'],
  blockers: [],
  confirmationTarget: 'release-1',
  counts: [{ count: 1, name: 'mobile_releases' }],
  kind: 'mobile_release',
  previewToken: 'a'.repeat(64),
  retainedSharedArtifactCount: 0,
  targetId: 'release-1',
  targetLabel: 'v-test',
};

test('loads the preview for the exact cleanup kind and target', async () => {
  const calls = [];
  const api = {
    previewMobileReleaseDeletion: async (id) => {
      calls.push(['release', id]);
      return { data: preview };
    },
    previewGameLayoutDataReset: async (id) => {
      calls.push(['game', id]);
      return { data: { ...preview, targetId: id } };
    },
  };

  const releaseResult = await loadCleanupPreview(api, {
    id: 'release-1',
    kind: 'mobile-release',
  });
  const gameResult = await loadCleanupPreview(api, {
    id: 'game-1',
    kind: 'game-layout-data',
  });

  assert.equal(releaseResult.ok, true);
  assert.equal(gameResult.ok, true);
  assert.deepEqual(calls, [
    ['release', 'release-1'],
    ['game', 'game-1'],
  ]);
});

test('executes with the immutable token and exact confirmation from preview', async () => {
  let captured;
  const api = {
    deleteMobileRelease: async () => ({ error: { code: 'not-used' } }),
    resetGameLayoutData: async (id, body) => {
      captured = { body, id };
      return {
        data: {
          alreadyCompleted: false,
          deletedArtifactCount: 1,
          deletedCounts: preview.counts,
          kind: 'game_layout_data',
          previewToken: preview.previewToken,
          retainedSharedArtifactCount: 0,
          targetId: id,
          targetLabel: 'Game One',
        },
      };
    },
  };

  const result = await executeCleanup(
    api,
    { id: 'game-1', kind: 'game-layout-data' },
    { ...preview, confirmationTarget: 'game-1', targetId: 'game-1' },
  );

  assert.equal(result.ok, true);
  assert.deepEqual(captured, {
    body: {
      confirmationTarget: 'game-1',
      confirmed: true,
      previewToken: preview.previewToken,
    },
    id: 'game-1',
  });
});

test('returns a stable message when preview request fails', async () => {
  const result = await loadCleanupPreview(
    {
      previewMobileReleaseDeletion: async () => ({
        error: { code: 'CLEANUP_BLOCKED', message: 'Active workflow' },
      }),
    },
    { id: 'release-1', kind: 'mobile-release' },
  );

  assert.deepEqual(result, {
    error: 'Active workflow (CLEANUP_BLOCKED)',
    ok: false,
  });
});

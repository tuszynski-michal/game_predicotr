import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createRelease,
  downloadReleaseApk,
  loadReleaseWorkspace,
  refreshRelease,
  retryReleaseBuild,
  startReleaseBuild,
} from '../src/features/releases/release-actions.ts';

const game = {
  code: 'game-1',
  createdAt: '2026-07-27T10:00:00Z',
  id: 'game-1',
  name: 'Game One',
  status: 'active',
  updatedAt: '2026-07-27T10:00:00Z',
};

const release = {
  algorithmVersion: 'payout-v2',
  apk: null,
  buildJobId: null,
  createdAt: '2026-07-27T10:00:00Z',
  games: [],
  id: 'release-1',
  readyAt: null,
  snapshot: null,
  snapshotSchemaVersion: 2,
  status: 'draft',
  version: 'm3.4.1',
};

const job = {
  attemptCount: 1,
  cancelRequestedAt: null,
  createdAt: '2026-07-27T10:00:00Z',
  error: null,
  finishedAt: null,
  gameId: null,
  heartbeatAt: null,
  id: 'job-1',
  inputPayload: {
    schemaVersion: 1,
    mobileReleaseId: release.id,
  },
  jobType: 'android_build',
  leaseExpiresAt: null,
  progress: {
    current: 0,
    failed: 0,
    review: 0,
    stage: null,
    succeeded: 0,
    total: null,
  },
  startedAt: null,
  status: 'created',
  updatedAt: '2026-07-27T10:00:00Z',
  workerVersion: null,
};

test('loads active games, exact source histories and releases', async () => {
  const result = await loadReleaseWorkspace({
    listGames: async () => ({
      data: [game, { ...game, id: 'archived', status: 'archived' }],
    }),
    listMobileReleases: async () => ({ data: [release] }),
    listDatasetVersions: async (gameId) => {
      assert.equal(gameId, game.id);
      return { data: [{ id: 'dataset-1', status: 'published' }] };
    },
    listRulesVersions: async (gameId) => {
      assert.equal(gameId, game.id);
      return { data: [{ id: 'rules-1', status: 'published' }] };
    },
  });

  assert.equal(result.ok, true);
  assert.deepEqual(
    result.sources.map((source) => source.game.id),
    [game.id],
  );
  assert.deepEqual(result.releases, [release]);
});

test('creates, starts, refreshes and retries through typed operations', async () => {
  const body = {
    games: [
      {
        datasetVersionId: 'dataset-1',
        gameId: game.id,
        rulesVersionId: 'rules-1',
      },
    ],
    version: release.version,
  };
  assert.deepEqual(
    await createRelease(
      {
        createMobileRelease: async (received) => {
          assert.deepEqual(received, body);
          return { data: release };
        },
      },
      body,
    ),
    { ok: true, release },
  );
  assert.deepEqual(
    await startReleaseBuild(
      {
        buildMobileRelease: async (releaseId) => {
          assert.equal(releaseId, release.id);
          return { data: { jobId: job.id, status: 'created' } };
        },
      },
      release.id,
    ),
    { build: { jobId: job.id, status: 'created' }, ok: true },
  );

  const building = {
    ...release,
    buildJobId: job.id,
    status: 'building',
  };
  assert.deepEqual(
    await refreshRelease(
      {
        getMobileRelease: async () => ({ data: building }),
        getJob: async () => ({ data: job }),
      },
      release.id,
    ),
    { job, ok: true, release: building },
  );
  assert.deepEqual(
    await retryReleaseBuild(
      {
        retryJob: async (jobId) => {
          assert.equal(jobId, job.id);
          return { data: job };
        },
      },
      job.id,
    ),
    { job, ok: true },
  );
  const artifact = new Blob(['apk']);
  assert.deepEqual(
    await downloadReleaseApk(
      {
        downloadMobileReleaseApk: async (releaseId) => {
          assert.equal(releaseId, release.id);
          return { data: artifact };
        },
      },
      release.id,
    ),
    { artifact, ok: true },
  );
});

test('preserves stable API errors and hides transport details', async () => {
  const conflict = await startReleaseBuild(
    {
      buildMobileRelease: async () => ({
        error: {
          code: 'MOBILE_RELEASE_BUILD_ALREADY_STARTED',
          details: {},
          message: 'Build already started.',
        },
      }),
    },
    release.id,
  );
  assert.deepEqual(conflict, {
    error: 'Build already started. (MOBILE_RELEASE_BUILD_ALREADY_STARTED)',
    ok: false,
  });

  const transport = await refreshRelease(
    {
      getMobileRelease: async () => {
        throw new Error('sensitive transport detail');
      },
    },
    release.id,
  );
  assert.deepEqual(transport, {
    error: 'Połączenie z lokalnym Admin API zostało przerwane.',
    ok: false,
  });
});

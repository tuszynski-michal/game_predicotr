import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

import {
  confirmGridActivation,
  createGridCandidate,
  confirmModelActivation,
  freezeModelQualityCohort,
  loadModelQuality,
  loadGridQuality,
  previewGridActivation,
  previewModelActivation,
} from '../src/features/model-quality/model-quality-actions.ts';

const workspaceSource = await readFile(
  new URL(
    '../src/features/model-quality/model-quality-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);

const gameId = 'game-1';
const checksum = 'a'.repeat(64);
const quality = {
  activeHeavyJob: false,
  activeModel: null,
  advisoryThresholds: [
    { layoutCount: 100, reached: true },
    { layoutCount: 1000, reached: false },
  ],
  canFreeze: true,
  cellSampleCount: 1500,
  gameId,
  incompleteItemCount: 0,
  latestCohort: null,
  manifestChecksumSha256: checksum,
  newVerifiedLayoutCount: 100,
  pendingItemCount: 2,
  protectedItemCount: 101,
  rejectedItemCount: 1,
  resolvedLayoutCount: 100,
  sourceImageCount: 12,
  symbolCoverage: [{ sampleCount: 150, symbolCode: 'lemon' }],
  warnings: [],
};
const preview = {
  cellSampleCount: 1500,
  gameId,
  incompleteItemCount: 0,
  manifestChecksumSha256: checksum,
  manifestSchemaVersion: 1,
  pendingItemCount: 2,
  protectedItemCount: 101,
  rejectedItemCount: 1,
  resolvedLayoutCount: 100,
  sourceImageCount: 12,
  warnings: [],
};

test('loads one summary and derives its checksum-bound preview without a duplicate request', async () => {
  let previewCalls = 0;
  const result = await loadModelQuality(
    {
      getModelQuality: async (requestedGameId) => {
        assert.equal(requestedGameId, gameId);
        return { data: quality };
      },
      previewVerifiedTrainingCohort: async (requestedGameId) => {
        assert.equal(requestedGameId, gameId);
        previewCalls += 1;
        return { data: preview };
      },
      listSymbolModelIterations: async (requestedGameId) => {
        assert.equal(requestedGameId, gameId);
        return { data: [] };
      },
      listSymbolModelActivations: async (requestedGameId) => {
        assert.equal(requestedGameId, gameId);
        return { data: [] };
      },
    },
    gameId,
  );

  assert.equal(result.ok, true);
  assert.equal(result.quality.newVerifiedLayoutCount, 100);
  assert.equal(result.preview.manifestChecksumSha256, checksum);
  assert.deepEqual(result.iterations, []);
  assert.deepEqual(result.activations, []);
  assert.equal(previewCalls, 0);
});

test('does not start the heavy grid panel while the primary quality request is loading', () => {
  const loadingBranch = workspaceSource.slice(
    workspaceSource.indexOf('if (loading && quality === null)'),
    workspaceSource.indexOf('if (quality === null || preview === null)'),
  );

  assert.doesNotMatch(loadingBranch, /GridQualityPanel/);
});

test('rejects a response from another game', async () => {
  const result = await loadModelQuality(
    {
      getModelQuality: async () => ({ data: { ...quality, gameId: 'other' } }),
      listSymbolModelIterations: async () => ({ data: [] }),
      listSymbolModelActivations: async () => ({ data: [] }),
    },
    gameId,
  );

  assert.deepEqual(result, {
    error: 'Odpowiedź API nie należy do wybranej gry.',
    ok: false,
  });
});

test('previews and activates an exact checksum-bound model candidate', async () => {
  const activationPreview = {
    action: 'activate',
    canActivate: true,
    candidateManifestChecksumSha256: checksum,
    currentModelIterationId: null,
    gameId,
    modelIterationId: 'iteration-1',
  };
  const client = {
    previewSymbolModelActivation: async (
      requestedGameId,
      iterationId,
      action,
    ) => {
      assert.equal(requestedGameId, gameId);
      assert.equal(iterationId, 'iteration-1');
      assert.equal(action, 'activate');
      return { data: activationPreview };
    },
    activateSymbolModel: async (requestedGameId, iterationId, command) => {
      assert.equal(requestedGameId, gameId);
      assert.equal(iterationId, 'iteration-1');
      assert.deepEqual(command, {
        actor: 'local-owner',
        expectedCurrentModelIterationId: null,
        expectedManifestChecksumSha256: checksum,
        idempotencyKey: 'activation-key',
        reason:
          'Owner-confirmed activation from Admin model quality workspace.',
      });
      return {
        data: {
          activation: { id: 'activation-1', modelIterationId: iterationId },
          created: true,
        },
      };
    },
  };

  const previewResult = await previewModelActivation(client, {
    action: 'activate',
    gameId,
    iterationId: 'iteration-1',
  });
  assert.equal(previewResult.ok, true);

  const activationResult = await confirmModelActivation(client, {
    action: 'activate',
    actor: 'local-owner',
    gameId,
    idempotencyKey: 'activation-key',
    preview: activationPreview,
  });
  assert.equal(activationResult.ok, true);
  assert.equal(activationResult.response.created, true);
});

test('uses the dedicated rollback endpoint for a prior active model', async () => {
  let rollbackCalled = false;
  const result = await confirmModelActivation(
    {
      rollbackSymbolModel: async (_requestedGameId, _iterationId, command) => {
        rollbackCalled = true;
        assert.equal(command.expectedCurrentModelIterationId, 'iteration-2');
        return {
          data: {
            activation: { id: 'activation-2', modelIterationId: 'iteration-1' },
            created: true,
          },
        };
      },
    },
    {
      action: 'rollback',
      actor: 'local-owner',
      gameId,
      idempotencyKey: 'rollback-key',
      preview: {
        action: 'rollback',
        canActivate: true,
        candidateManifestChecksumSha256: checksum,
        currentModelIterationId: 'iteration-2',
        gameId,
        modelIterationId: 'iteration-1',
      },
    },
  );
  assert.equal(result.ok, true);
  assert.equal(rollbackCalled, true);
});

test('freezes exactly the confirmed manifest with a stable idempotency key', async () => {
  let command;
  const result = await freezeModelQualityCohort(
    {
      createSymbolTraining: async (requestedGameId, body) => {
        assert.equal(requestedGameId, gameId);
        assert.deepEqual(body, {
          cohortId: 'cohort-1',
          idempotencyKey: 'idempotency-1',
        });
        return {
          data: {
            created: true,
            iteration: { id: 'iteration-1', iterationNumber: 1 },
            job: { id: 'job-1', jobType: 'symbol_training', status: 'created' },
          },
        };
      },
      freezeVerifiedTrainingCohort: async (requestedGameId, body) => {
        assert.equal(requestedGameId, gameId);
        command = body;
        return {
          data: {
            cohort: {
              artifactRelativePath: 'training/game/cohort.json',
              cellSampleCount: 1500,
              createdAt: '2026-08-08T12:00:00Z',
              createdBy: 'local-owner',
              gameId,
              id: 'cohort-1',
              incompleteItemCount: 0,
              iterationNumber: 1,
              manifestChecksumSha256: checksum,
              manifestSchemaVersion: 1,
              pendingItemCount: 2,
              rejectedItemCount: 1,
              resolvedLayoutCount: 100,
              sourceImageCount: 12,
            },
            created: true,
          },
        };
      },
    },
    {
      actor: 'local-owner',
      gameId,
      idempotencyKey: 'idempotency-1',
      manifestChecksumSha256: checksum,
    },
  );

  assert.equal(result.ok, true);
  assert.deepEqual(command, {
    createdBy: 'local-owner',
    expectedManifestChecksumSha256: checksum,
    idempotencyKey: 'idempotency-1',
  });
});

test('loads, creates and explicitly activates grid quality independently', async () => {
  const profile = {
    id: 'profile-1',
    gameId,
    profileChecksumSha256: checksum,
    profileNumber: 1,
    status: 'candidate_ready',
  };
  const activationPreview = {
    action: 'activate',
    canActivate: true,
    currentProfileId: null,
    gameId,
    profileChecksumSha256: checksum,
    profileId: profile.id,
  };
  const client = {
    listGridCalibrationProfiles: async () => ({ data: [profile] }),
    listGridProfileActivations: async () => ({ data: [] }),
    getGridCalibrationCohortDiagnostics: async () => ({
      data: {
        acceptedGeometryCount: 0,
        correctedGeometryCount: 0,
        firstSequenceNumber: null,
        gameId,
        incompleteGeometryCount: 0,
        lastSequenceNumber: null,
        missingDetectionCount: 0,
        sourceImageCount: 0,
      },
    }),
    createGridCalibrationCandidate: async () => ({
      data: { created: true, profile },
    }),
    previewGridProfileActivation: async (_gameId, _profileId, action) => {
      assert.equal(action, 'activate');
      return { data: activationPreview };
    },
    activateGridProfile: async (_gameId, _profileId, command) => {
      assert.equal(command.expectedProfileChecksumSha256, checksum);
      assert.equal(command.expectedCurrentProfileId, null);
      return { data: { activation: { id: 'activation-1' }, created: true } };
    },
  };

  assert.equal((await loadGridQuality(client, gameId)).ok, true);
  assert.equal((await createGridCandidate(client, gameId)).ok, true);
  assert.equal(
    (
      await previewGridActivation(client, {
        action: 'activate',
        gameId,
        profileId: profile.id,
      })
    ).ok,
    true,
  );
  assert.equal(
    (
      await confirmGridActivation(client, {
        action: 'activate',
        actor: 'local-owner',
        gameId,
        idempotencyKey: 'grid-key',
        preview: activationPreview,
      })
    ).ok,
    true,
  );
});

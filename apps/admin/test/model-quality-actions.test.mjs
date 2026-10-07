import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

import {
  confirmGridActivation,
  createGridCandidate,
  confirmModelActivation,
  freezeModelQualityCohort,
  loadModelQuality,
  prepareModelQualityCohort,
  previewPendingSymbolReinference,
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
  manifestSchemaVersion: 3,
  manifestChecksumSha256: checksum,
  newVerifiedLayoutCount: 100,
  pendingItemCount: 2,
  protectedItemCount: 101,
  rejectedItemCount: 1,
  resolvedLayoutCount: 100,
  sourceImageCount: 12,
  symbolCoverage: [{ sampleCount: 150, symbolCode: 'lemon' }],
  trainingExclusions: {
    changedCrop: 3,
    gridIssue: 2,
    missingAsset: 1,
    unknown: 4,
    unreadable: 5,
  },
  warnings: [],
};
const preview = {
  cellSampleCount: 1500,
  gameId,
  incompleteItemCount: 0,
  manifestChecksumSha256: checksum,
  manifestSchemaVersion: 3,
  pendingItemCount: 2,
  protectedItemCount: 101,
  rejectedItemCount: 1,
  resolvedLayoutCount: 100,
  sourceImageCount: 12,
  trainingExclusions: quality.trainingExclusions,
  warnings: [],
};

const overview = {
  view: 'overview',
  gameId,
  activeHeavyJob: false,
  latestCohort: null,
  approvedCellCount: 1500,
  approvedLayoutCount: 100,
  sourceImageCount: 12,
  symbolCoverage: quality.symbolCoverage,
};

test('loads only SQL overview on entry without preparing a training cohort', async () => {
  let previewCalls = 0;
  const result = await loadModelQuality(
    {
      getModelQuality: async (requestedGameId, options) => {
        assert.equal(requestedGameId, gameId);
        assert.equal(options.view, 'overview');
        return { data: overview };
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
  assert.equal(result.quality.approvedCellCount, 1500);
  assert.equal(result.preview, undefined);
  assert.deepEqual(result.iterations, []);
  assert.deepEqual(result.activations, []);
  assert.equal(previewCalls, 0);
});

test('mounts grid independently from conditional symbol loading', () => {
  const workspace = workspaceSource.slice(
    workspaceSource.indexOf('export function ModelQualityWorkspace'),
  );
  assert.match(workspace, /SymbolQualityWorkspace/);
  assert.match(workspace, /GridQualityPanel/);
  assert.doesNotMatch(workspace, /if \(loading/);
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

test('does not create an artificial timeout for a pending overview', async () => {
  const controller = new AbortController();
  const signals = [];
  const lost = (_game, { signal }) => {
    signals.push(signal);
    return new Promise(() => {});
  };
  const reading = loadModelQuality(
    {
      getModelQuality: lost,
      listSymbolModelIterations: lost,
      listSymbolModelActivations: lost,
    },
    gameId,
    controller.signal,
  );
  controller.abort();
  assert.deepEqual(await reading, { ok: false, error: 'REQUEST_ABORTED' });
  assert.equal(signals.length, 3);
  assert.ok(signals.every((signal) => signal.aborted));
});

test('cancels a hanging request without waiting for its network response', async () => {
  const controller = new AbortController();
  let childSignal;
  const loading = loadModelQuality(
    {
      getModelQuality: (_game, { signal }) => {
        childSignal = signal;
        return new Promise(() => {});
      },
      listSymbolModelIterations: async () => ({ data: [] }),
      listSymbolModelActivations: async () => ({ data: [] }),
    },
    gameId,
    controller.signal,
  );
  controller.abort();
  assert.deepEqual(await loading, { ok: false, error: 'REQUEST_ABORTED' });
  assert.equal(childSignal.aborted, true);
});

test('cancels and validates pending preview separately', async () => {
  const controller = new AbortController();
  let signal;
  const api = {
    previewPendingSymbolReinference: (_game, options) => {
      signal = options.signal;
      return new Promise(() => {});
    },
  };
  const reading = previewPendingSymbolReinference(
    api,
    gameId,
    controller.signal,
  );
  controller.abort();
  assert.deepEqual(await reading, { ok: false, error: 'REQUEST_ABORTED' });
  assert.equal(signal.aborted, true);
  assert.deepEqual(
    await previewPendingSymbolReinference(
      {
        previewPendingSymbolReinference: async () => ({
          data: { gameId: 'other' },
        }),
      },
      gameId,
    ),
    { ok: false, error: 'Odpowiedź API nie należy do wybranej gry.' },
  );
});

test('explicit preparation derives a checksum-bound preview from the unchanged full report', async () => {
  let calls = 0;
  const result = await prepareModelQualityCohort(
    {
      getModelQuality: async (id, options) => {
        calls++;
        assert.equal(id, gameId);
        assert.equal(options.view, undefined);
        return { data: quality };
      },
    },
    gameId,
  );
  assert.equal(calls, 1);
  assert.equal(result.ok, true);
  assert.equal(result.preview.manifestChecksumSha256, checksum);
  assert.equal(result.quality.newVerifiedLayoutCount, 100);
});

test('overview cannot masquerade as an attested training preview', async () => {
  const result = await prepareModelQualityCohort(
    {
      getModelQuality: async () => ({ data: overview }),
    },
    gameId,
  );
  assert.equal(result.ok, false);
  assert.match(result.error, /sprawdzonego manifestu/);
});

test('explicit preparation rejects the full report of a different game', async () => {
  const result = await prepareModelQualityCohort(
    {
      getModelQuality: async () => ({ data: { ...quality, gameId: 'other' } }),
    },
    gameId,
  );
  assert.deepEqual(result, {
    ok: false,
    error: 'Odpowiedź API nie należy do wybranej gry.',
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

import assert from 'node:assert/strict';
import test from 'node:test';
import {
  geometryPreflightMatchesReport,
  replayGeometryPreflightProgress,
} from '../src/features/imports/image-folder-import-actions.ts';
import {
  canStartReadyImport,
  readyBoardImportLifecycleLabel,
} from '../src/features/imports/image-folder-import-state.ts';
import {
  canResumeNeuralImport,
  readySelectionHasNeuralImport,
} from '../src/features/imports/neural-import-preflight-state.ts';

export const snapshot = {
  contractVersion: 'neural-grid-proposal-snapshot-v1',
  expectedLayoutCount: 500000,
  model: {
    profile: 'grid_profile_mumie_v1',
    modelKind: 'neural_grid',
    schemaVersion: 'grid-engine-model-manifest-v1',
    weightsSha256: 'a'.repeat(64),
    snapshotId: 'frozen',
  },
};
export const geometry = {
  id: 'nn-geometry',
  gameId: 'game',
  jobType: 'validate',
  status: 'completed',
  createdAt: '2026-10-06',
  inputPayload: {
    schemaVersion: 2,
    validationKind: 'page_geometry_preflight',
    preflightPolicyVersion: 'page-geometry-preflight-v13-neural-mumie-pilot',
    neuralGridProposal: snapshot,
    sourceSelectionId: 'selection',
    sourceManifestSha256: 'b'.repeat(64),
    managedSourceJobId: null,
  },
  progress: {
    current: 100,
    total: 100,
    succeeded: 1,
    failed: 0,
    review: 99,
    pageGeometryPreflight: {
      complete: true,
      geometryManifestChecksumSha256: 'c'.repeat(64),
      provisionalReviewRequired: 99,
    },
  },
};
export const report = {
  gameId: 'game',
  uploadId: 'selection',
  geometryEngineVariant: null,
  geometryEngineVariantEnabled: true,
  manifestChecksumSha256: 'b'.repeat(64),
  geometryPreflightJob: geometry,
  geometryPreflightArtifactReady: false,
};
export const previous = {
  id: 'previous-import',
  gameId: 'game',
  jobType: 'import',
  status: 'completed',
  inputPayload: {
    importKind: 'image_directory',
    neuralGridProposal: snapshot,
    sourceSelectionId: 'selection',
    sourceManifestSha256: 'b'.repeat(64),
    pageGeometryManifest: {
      preflightJobId: 'previous-geometry',
      checksumSha256: 'd'.repeat(64),
      relativePath: 'manifest.json',
    },
  },
  progress: { current: 200, total: 200, succeeded: 0, failed: 0, review: 100 },
};

test('completed frozen neural manifest permits import with 99 review sources, including source-only pending', () => {
  assert.equal(geometryPreflightMatchesReport(geometry, report), true);
  const ready = replayGeometryPreflightProgress(report, geometry, geometry.id);
  assert.equal(ready.geometryPreflightArtifactReady, true);
  assert.equal(ready.geometryPreflightArtifactBlockerCode, null);
  assert.equal(
    canStartReadyImport({
      symbolModelAvailable: true,
      geometryPreflightRequired: true,
      geometryPreflightCompleted: true,
      geometryManifestAvailable: true,
      geometryPreflightArtifactReady: ready.geometryPreflightArtifactReady,
      geometryGuardResolutionRequired: false,
    }),
    true,
  );
  assert.match(
    readyBoardImportLifecycleLabel({
      geometryPreflightJobs: [geometry],
      reportPrepared: true,
      selection: {
        uploadId: report.uploadId,
        manifestChecksumSha256: report.manifestChecksumSha256,
        boardImportStatus: 'ready',
      },
    }),
    /gotowe do importu · propozycje sieci dla zdjęć 99/,
  );
});

test('neural proposal counts preserve durable import stages without declaring manual errors', () => {
  for (const boardImportStatus of ['boards_imported', 'importing', 'failed']) {
    const label = readyBoardImportLifecycleLabel({
      geometryPreflightJobs: [geometry],
      reportPrepared: true,
      selection: {
        uploadId: report.uploadId,
        manifestChecksumSha256: report.manifestChecksumSha256,
        boardImportStatus,
      },
    });
    assert.match(label, /propozycje sieci dla zdjęć 99/);
    assert.doesNotMatch(label, /wymaga korekty|odroczone zdjęcia/);
    if (boardImportStatus === 'boards_imported')
      assert.match(label, /import zakończony.*weryfikacja symboli/);
    if (boardImportStatus === 'importing')
      assert.match(label, /trwa import plansz/);
    if (boardImportStatus === 'failed')
      assert.match(label, /błąd przetwarzania importu/);
  }
});

test('neural identity rejects foreign snapshot, managed owner, manifest and unversioned policy', () => {
  for (const inputPayload of [
    {
      ...geometry.inputPayload,
      neuralGridProposal: {
        ...snapshot,
        model: { ...snapshot.model, weightsSha256: 'e'.repeat(64) },
      },
    },
    { ...geometry.inputPayload, managedSourceJobId: 'foreign' },
    { ...geometry.inputPayload, sourceManifestSha256: 'e'.repeat(64) },
    { ...geometry.inputPayload, preflightPolicyVersion: null },
  ])
    assert.equal(
      geometryPreflightMatchesReport({ ...geometry, inputPayload }, report),
      false,
    );
  for (const progress of [
    {
      ...geometry.progress,
      pageGeometryPreflight: {
        ...geometry.progress.pageGeometryPreflight,
        complete: false,
      },
    },
    {
      ...geometry.progress,
      pageGeometryPreflight: {
        complete: true,
        geometryManifestChecksumSha256: null,
      },
    },
  ]) {
    assert.equal(
      replayGeometryPreflightProgress(
        report,
        { ...geometry, progress },
        geometry.id,
      ).geometryPreflightArtifactReady,
      false,
    );
  }
});

test('managed restart and a changed frozen descriptor permit a new neural run, never a duplicate or active run', () => {
  const managed = {
    ...geometry,
    inputPayload: { ...geometry.inputPayload, managedSourceJobId: previous.id },
  };
  const resumed = {
    ...report,
    existingImportJob: previous,
    geometryPreflightJob: managed,
  };
  assert.equal(geometryPreflightMatchesReport(managed, resumed), true);
  assert.equal(
    canResumeNeuralImport(JSON.parse(JSON.stringify(resumed)), [previous]),
    true,
  );
  assert.equal(
    readySelectionHasNeuralImport([previous], report, report.gameId),
    true,
  );
  assert.equal(
    canResumeNeuralImport(
      {
        ...resumed,
        existingImportJob: {
          ...previous,
          inputPayload: {
            ...previous.inputPayload,
            pageGeometryManifest: {
              preflightJobId: managed.id,
              checksumSha256:
                managed.progress.pageGeometryPreflight
                  .geometryManifestChecksumSha256,
            },
          },
        },
      },
      [],
    ),
    false,
  );
  assert.equal(
    canResumeNeuralImport(resumed, [
      { ...previous, id: 'active', status: 'processing' },
    ]),
    false,
  );
  assert.equal(
    canResumeNeuralImport(
      { ...resumed, existingImportJob: { ...previous, status: 'processing' } },
      [],
    ),
    false,
  );
});

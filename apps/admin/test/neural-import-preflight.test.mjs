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
  neuralImportSnapshot,
  neuralUnboundReasonLabel,
  neuralUnboundSkipConfirmed,
  neuralUnboundSourcesLabel,
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

test('neural snapshot is accepted for each grid engine profile and nothing else (D-544)', () => {
  const withProfile = (profile) => ({
    ...geometry,
    inputPayload: {
      ...geometry.inputPayload,
      neuralGridProposal: {
        ...snapshot,
        model: { ...snapshot.model, profile },
      },
    },
  });
  assert.equal(
    neuralImportSnapshot(withProfile('grid_profile_777_v2'))?.model.profile,
    'grid_profile_777_v2',
  );
  assert.equal(
    neuralImportSnapshot(withProfile('grid_profile_mumie_v1'))?.model.profile,
    'grid_profile_mumie_v1',
  );
  for (const profile of ['framed_full_page_v2', 'requires_clarification', null])
    assert.equal(neuralImportSnapshot(withProfile(profile)), null);
});

test('unbound V3 sources block start until the exact count is confirmed (TASK-1041)', () => {
  const unboundReport = {
    ...report,
    neuralUnboundSourceCount: 1962,
    neuralUnboundAttestedBoardCount: 17658,
  };
  const manifest = 'c'.repeat(64);
  const startState = (confirmed) => ({
    symbolModelAvailable: true,
    geometryPreflightRequired: true,
    geometryPreflightCompleted: true,
    geometryManifestAvailable: true,
    geometryPreflightArtifactReady: true,
    geometryGuardResolutionRequired: false,
    neuralUnboundSourceCount: unboundReport.neuralUnboundSourceCount,
    neuralUnboundSkipConfirmed: confirmed,
  });
  const confirmation = {
    uploadId: report.uploadId,
    geometryManifestChecksumSha256: manifest,
    sourceCount: 1962,
  };

  assert.equal(
    neuralUnboundSkipConfirmed(unboundReport, manifest, null),
    false,
  );
  assert.equal(canStartReadyImport(startState(false)), false);
  assert.equal(
    neuralUnboundSkipConfirmed(unboundReport, manifest, confirmation),
    true,
  );
  assert.equal(canStartReadyImport(startState(true)), true);
  // A new frozen manifest, another count or another staging needs a new consent.
  for (const stale of [
    { ...confirmation, geometryManifestChecksumSha256: 'd'.repeat(64) },
    { ...confirmation, sourceCount: 1961 },
    { ...confirmation, uploadId: 'other' },
  ])
    assert.equal(
      neuralUnboundSkipConfirmed(unboundReport, manifest, stale),
      false,
    );
  // A fully bound report and a report without the field need no confirmation.
  assert.equal(neuralUnboundSkipConfirmed(report, manifest, null), true);
  assert.equal(
    neuralUnboundSkipConfirmed(
      { ...report, neuralUnboundSourceCount: 0 },
      manifest,
      null,
    ),
    true,
  );
  assert.equal(
    neuralUnboundSourcesLabel(1962, 17658),
    `Pominięte bez przypisania plansz: ${(1962).toLocaleString('pl-PL')} zdjęć (zakresy z nazw plików: ${(17658).toLocaleString('pl-PL')} plansz)`,
  );
  assert.equal(
    neuralUnboundReasonLabel('NEURAL_GRID_SOURCE_TIME_LIMIT'),
    'przekroczony czas analizy zdjęcia',
  );
  assert.equal(neuralUnboundReasonLabel('OTHER_CODE'), 'OTHER_CODE');
});

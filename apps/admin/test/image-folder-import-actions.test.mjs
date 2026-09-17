import assert from 'node:assert/strict';
import test from 'node:test';

import {
  filterImageFolderImportFiles,
  geometryPreflightMatchesReport,
  imageImportJobMatchesReportIdentity,
  listReadyBrowserImageSelections,
  pageRegistrationVariantFromJob,
  persistedGuardContextIdentityStatus,
  persistedGuardContextIdentityStatusFromLatest,
  previewReadyBrowserImageImport,
  replayGeometryPreflightProgress,
  reprocessManagedV4OrPrepare,
  reprocessImageFolderImport,
  retryBrowserPageGeometryPreflight,
  startBrowserPageGeometryPreflight,
  startReadyBrowserImageImport,
  symbolSnapshotMatchesReport,
  uploadImageFolder,
} from '../src/features/imports/image-folder-import-actions.ts';

test('pins the selected page registration variant in the preflight request', async () => {
  const calls = [];
  const result = await startBrowserPageGeometryPreflight(
    {
      startBrowserPageGeometryPreflight: async (uploadId, body) => {
        calls.push([uploadId, body]);
        return { data: { created: true, job: { id: 'masked-job' } } };
      },
    },
    'upload-1',
    'game-1',
    'board_area_test',
  );

  assert.deepEqual(calls, [
    [
      'upload-1',
      { gameId: 'game-1', pageRegistrationVariant: 'board_area_test' },
    ],
  ]);
  assert.equal(result.ok, true);
});

test('pins v0.10.4 only on explicit report, preflight and start requests', async () => {
  const calls = [];
  const api = {
    previewReadyBrowserImageImport: async (uploadId, body) => {
      calls.push(['report', uploadId, body]);
      return { data: { uploadId } };
    },
    startBrowserPageGeometryPreflight: async (uploadId, body) => {
      calls.push(['preflight', uploadId, body]);
      return { data: { created: true, job: { id: 'preflight-v4' } } };
    },
    startReadyBrowserImageImport: async (uploadId, body) => {
      calls.push(['start', uploadId, body]);
      return { data: { created: true, job: { id: 'run-v4' }, preflight: {} } };
    },
  };
  const variant = 'structured_lattice_v4_partial_sides';

  await previewReadyBrowserImageImport(api, 'upload-v4', 'game-1', variant);
  assert.equal(calls.length, 1, 'opening the report must not create a job');
  await startBrowserPageGeometryPreflight(
    api,
    'upload-v4',
    'game-1',
    'board_area_test',
    variant,
  );
  await startReadyBrowserImageImport(
    api,
    'upload-v4',
    'game-1',
    'a'.repeat(64),
    'b'.repeat(64),
    'preflight-v4',
    'c'.repeat(64),
    'structured_lattice_v3',
    4,
    undefined,
    'd'.repeat(64),
    undefined,
    undefined,
    variant,
  );

  assert.deepEqual(calls, [
    [
      'report',
      'upload-v4',
      { gameId: 'game-1', geometryEngineVariant: variant },
    ],
    [
      'preflight',
      'upload-v4',
      {
        gameId: 'game-1',
        geometryEngineVariant: variant,
        pageRegistrationVariant: 'board_area_test',
      },
    ],
    [
      'start',
      'upload-v4',
      {
        boardCellProcessingMode: 'structured_lattice_v3',
        gameId: 'game-1',
        geometryEngineVariant: variant,
        geometryManifestChecksumSha256: 'c'.repeat(64),
        geometryPreflightJobId: 'preflight-v4',
        gridProfileInferenceFingerprint: 'd'.repeat(64),
        imageEnginePolicy: 'structured_lattice_v3',
        imageEnginePolicyRevision: 4,
        manifestChecksumSha256: 'a'.repeat(64),
        preflightChecksumSha256: 'b'.repeat(64),
      },
    ],
  ]);
});

test('pins v0.10.4 evidence on managed-original reprocessing', async () => {
  let args;
  await reprocessImageFolderImport(
    {
      reprocessManagedImageImport: async (...values) => {
        args = values;
        return { data: { job: { id: 'run-v4' } } };
      },
    },
    'source-run',
    false,
    {
      geometryEngineVariant: 'structured_lattice_v4_partial_sides',
      geometryManifestChecksumSha256: 'a'.repeat(64),
      geometryPreflightJobId: 'preflight-v4',
    },
  );
  assert.deepEqual(args, [
    'source-run',
    false,
    {
      geometryEngineVariant: 'structured_lattice_v4_partial_sides',
      geometryManifestChecksumSha256: 'a'.repeat(64),
      geometryPreflightJobId: 'preflight-v4',
    },
  ]);
});

const managedSourceJob = {
  gameId: 'game-1',
  id: 'source-run',
  inputPayload: {
    importKind: 'image_directory',
    sourceManifestSha256: 'a'.repeat(64),
    sourceSelectionId: 'upload-deleted-from-browser',
  },
  jobType: 'import',
  progress: {},
  status: 'completed',
};

function managedV4Preflight(
  status = 'completed',
  policyVersion = 'structured-lattice-v4-lateral-partial-v1',
) {
  return {
    gameId: 'game-1',
    id: 'preflight-managed-v4',
    inputPayload: {
      lateralPartialGeometry: {
        policyVersion,
        variant: 'structured_lattice_v4_partial_sides',
      },
      managedSourceJobId: 'source-run',
      preflightPolicyVersion: 'page-geometry-preflight-v2-auto-anchor',
      sourceManifestSha256: 'a'.repeat(64),
      sourceSelectionId: 'upload-deleted-from-browser',
      validationKind: 'page_geometry_preflight',
    },
    jobType: 'validate',
    progress: {
      pageGeometryPreflight: {
        geometryManifestChecksumSha256: 'b'.repeat(64),
      },
    },
    status,
  };
}

test('prepares v0.10.4 from managed originals after browser staging was deleted', async () => {
  const calls = [];
  const result = await reprocessManagedV4OrPrepare(
    {
      startBrowserPageGeometryPreflight: async (uploadId, body) => {
        calls.push([uploadId, body]);
        return {
          data: { created: true, job: managedV4Preflight('created') },
        };
      },
    },
    managedSourceJob,
    [],
    'standard_v0_10',
  );

  assert.equal(result.kind, 'preflight_created');
  assert.deepEqual(calls, [
    [
      'upload-deleted-from-browser',
      {
        gameId: 'game-1',
        geometryEngineVariant: 'structured_lattice_v4_partial_sides',
        managedSourceJobId: 'source-run',
        pageRegistrationVariant: 'standard_v0_10',
      },
    ],
  ]);
});

test('starts managed v0.10.4 only with the exact completed preflight manifest', async () => {
  const calls = [];
  const result = await reprocessManagedV4OrPrepare(
    {
      reprocessManagedImageImport: async (...args) => {
        calls.push(args);
        return { data: { job: { id: 'new-run' } } };
      },
    },
    managedSourceJob,
    [
      {
        ...managedV4Preflight(),
        gameId: 'another-game',
        id: 'foreign-preflight',
      },
      managedV4Preflight(
        'completed',
        'structured-lattice-v4-lateral-partial-v2',
      ),
    ],
    'standard_v0_10',
  );

  assert.equal(result.kind, 'reprocessed');
  assert.deepEqual(calls, [
    [
      'source-run',
      false,
      {
        geometryEngineVariant: 'structured_lattice_v4_partial_sides',
        geometryManifestChecksumSha256: 'b'.repeat(64),
        geometryPreflightJobId: 'preflight-managed-v4',
      },
    ],
  ]);
});

test('refreshes a cached managed preflight before starting the reprocess', async () => {
  const calls = [];
  const completed = managedV4Preflight('completed');
  const result = await reprocessManagedV4OrPrepare(
    {
      getJob: async (jobId) => {
        calls.push(['get', jobId]);
        return { data: completed };
      },
      reprocessManagedImageImport: async (...args) => {
        calls.push(['reprocess', ...args]);
        return { data: { job: { id: 'new-run' } } };
      },
    },
    managedSourceJob,
    [managedV4Preflight('created')],
    'standard_v0_10',
  );

  assert.equal(result.kind, 'reprocessed');
  assert.deepEqual(calls, [
    ['get', 'preflight-managed-v4'],
    [
      'reprocess',
      'source-run',
      false,
      {
        geometryEngineVariant: 'structured_lattice_v4_partial_sides',
        geometryManifestChecksumSha256: 'b'.repeat(64),
        geometryPreflightJobId: 'preflight-managed-v4',
      },
    ],
  ]);
});

test('does not mutate browser report state when managed preflight refresh fails', async () => {
  let reprocessCalled = false;
  const result = await reprocessManagedV4OrPrepare(
    {
      getJob: async () => ({
        error: {
          code: 'JOB_READ_FAILED',
          message: 'Nie udało się pobrać joba.',
        },
      }),
      reprocessManagedImageImport: async () => {
        reprocessCalled = true;
        return { data: { job: { id: 'unexpected-run' } } };
      },
    },
    managedSourceJob,
    [managedV4Preflight('processing')],
    'standard_v0_10',
  );

  assert.equal(result.ok, false);
  assert.match(result.error, /JOB_READ_FAILED/);
  assert.equal(reprocessCalled, false);
});

test('completed preflight replay unlocks the current report and ignores a stale response', () => {
  const managed = managedV4Preflight();
  const browserPayload = { ...managed.inputPayload };
  // The API serializes the optional source as null for a browser staging.
  // It must remain distinct from a non-null managed-original job id.
  browserPayload.managedSourceJobId = null;
  const completed = {
    ...managed,
    inputPayload: browserPayload,
  };
  const report = {
    gameId: 'game-1',
    geometryPreflightArtifactBlockerCode:
      'IMAGE_PAGE_GEOMETRY_PREFLIGHT_REQUIRED',
    geometryPreflightArtifactBlockerMessage: 'Przygotuj preflight.',
    geometryPreflightArtifactReady: false,
    geometryEngineVariant: 'structured_lattice_v4_partial_sides',
    manifestChecksumSha256: 'a'.repeat(64),
    uploadId: 'upload-deleted-from-browser',
  };
  const unlocked = replayGeometryPreflightProgress(
    report,
    completed,
    completed.id,
  );
  assert.equal(unlocked.geometryPreflightArtifactReady, true);
  assert.equal(unlocked.geometryPreflightArtifactBlockerCode, null);
  assert.equal(unlocked.geometryPreflightJob.status, 'completed');
  const deferred = replayGeometryPreflightProgress(
    report,
    {
      ...completed,
      progress: {
        pageGeometryPreflight: {
          ...completed.progress.pageGeometryPreflight,
          provisionalReviewRequired: 2,
        },
      },
    },
    completed.id,
  );
  assert.equal(deferred.geometryPreflightArtifactReady, false);
  assert.equal(
    deferred.geometryPreflightArtifactBlockerCode,
    'IMAGE_PAGE_GEOMETRY_REVIEW_REQUIRED',
  );
  assert.strictEqual(
    replayGeometryPreflightProgress(report, completed, 'newer-preflight'),
    report,
  );
  assert.equal(geometryPreflightMatchesReport(managed, report), false);
  assert.strictEqual(
    replayGeometryPreflightProgress(report, managed, managed.id),
    report,
    'managed preflight B must not replace browser report A',
  );
});

test('browser preflight identity accepts every released lateral policy', () => {
  const report = {
    gameId: 'game-1',
    geometryEngineVariant: 'structured_lattice_v4_partial_sides',
    manifestChecksumSha256: 'a'.repeat(64),
    uploadId: 'upload-deleted-from-browser',
  };
  const browserPreflight = (policyVersion) => {
    const managed = managedV4Preflight('processing', policyVersion);
    return {
      ...managed,
      inputPayload: {
        ...managed.inputPayload,
        managedSourceJobId: null,
      },
    };
  };

  assert.equal(
    geometryPreflightMatchesReport(
      browserPreflight('structured-lattice-v4-lateral-partial-v1'),
      report,
    ),
    true,
  );
  assert.equal(
    geometryPreflightMatchesReport(
      browserPreflight('structured-lattice-v4-lateral-partial-v2'),
      report,
    ),
    true,
  );
  assert.equal(
    geometryPreflightMatchesReport(
      browserPreflight('structured-lattice-v4-lateral-partial-v3'),
      report,
    ),
    true,
  );
  assert.equal(
    geometryPreflightMatchesReport(
      browserPreflight('structured-lattice-v4-lateral-partial-v4'),
      report,
    ),
    false,
  );
  assert.equal(
    geometryPreflightMatchesReport(
      browserPreflight('structured-lattice-v4-lateral-partial-v2'),
      { ...report, geometryEngineVariant: undefined },
    ),
    false,
  );
});

test('guard replay requires exact job identity and cannot rebind v3 into v0.10.4', () => {
  const report = {
    gridProfileInferenceFingerprint: 'g'.repeat(64),
    imageEnginePolicy: 'verified_v19',
    imageEnginePolicyRevision: 0,
    manifestChecksumSha256: 'a'.repeat(64),
    symbolModelInferenceFingerprint: 's'.repeat(64),
    symbolModelSnapshotFingerprint: 's'.repeat(64),
  };
  const identity = {
    browserSelectionId: 'upload-1',
    gameId: 'game-1',
    guardJobId: 'guard-1',
    pageGeometryManifestChecksumSha256: 'p'.repeat(64),
    sourceManifestChecksumSha256: 'a'.repeat(64),
  };
  const manifest = {
    guardJobId: 'guard-1',
    pageGeometryManifestChecksumSha256: 'p'.repeat(64),
    sourceManifestChecksumSha256: 'a'.repeat(64),
  };
  const base = {
    currentGameId: 'game-1',
    currentGuardJobId: 'guard-1',
    currentUploadId: 'upload-1',
    identity,
    manifest,
    pageGeometryPreflightJob: {
      gameId: 'game-1',
      inputPayload: {
        sourceManifestSha256: 'a'.repeat(64),
        sourceSelectionId: 'upload-1',
      },
      progress: {
        pageGeometryPreflight: {
          geometryManifestChecksumSha256: 'p'.repeat(64),
        },
      },
    },
    report,
  };

  assert.equal(persistedGuardContextIdentityStatus(base), 'match');
  assert.equal(
    persistedGuardContextIdentityStatus({
      ...base,
      currentGuardJobId: 'new-guard',
    }),
    'stale',
  );
  assert.equal(
    persistedGuardContextIdentityStatus({
      ...base,
      geometryEngineVariant: 'structured_lattice_v4_partial_sides',
      report: {
        ...report,
        geometryEngineVariant: 'structured_lattice_v4_partial_sides',
      },
    }),
    'v4_rebind_forbidden',
  );
  assert.equal(
    persistedGuardContextIdentityStatus({
      ...base,
      manifest: { ...manifest, sourceManifestChecksumSha256: 'x'.repeat(64) },
    }),
    'foreign',
  );
});

test('the wired guard callback reads the latest guard generation instead of its creation closure', () => {
  const report = {
    geometryEngineVariant: null,
    manifestChecksumSha256: 'a'.repeat(64),
  };
  const activeGuardJobIdRef = { current: 'guard-revision-1' };
  const activeReportIdentityRef = {
    current: {
      gameId: 'game-1',
      geometryEngineVariant: undefined,
      preflight: report,
      readyUploadId: 'upload-1',
    },
  };
  const identity = {
    browserSelectionId: 'upload-1',
    gameId: 'game-1',
    guardJobId: 'guard-revision-1',
    pageGeometryManifestChecksumSha256: 'p'.repeat(64),
    sourceManifestChecksumSha256: 'a'.repeat(64),
  };
  const staleCallback = () =>
    persistedGuardContextIdentityStatusFromLatest({
      activeGuardJobIdRef,
      activeReportIdentityRef,
      identity,
      manifest: null,
      pageGeometryPreflightJob: null,
    });

  assert.equal(staleCallback(), 'match');
  activeGuardJobIdRef.current = 'guard-revision-2';
  assert.equal(staleCallback(), 'stale');
});

test('run identity and history registration use exact pinned snapshots', () => {
  const report = {
    gridProfileInferenceFingerprint: 'g'.repeat(64),
    imageEnginePolicy: 'structured_lattice_v3',
    imageEnginePolicyRevision: 4,
    manifestChecksumSha256: 'a'.repeat(64),
    symbolModelInferenceFingerprint: 's'.repeat(64),
    symbolModelSnapshotFingerprint: 's'.repeat(64),
  };
  const job = {
    gameId: 'game-1',
    inputPayload: {
      gridProfile: { inferenceFingerprint: 'g'.repeat(64) },
      imageGeometryRollout: { rolloutRevision: 4 },
      sourceManifestSha256: 'a'.repeat(64),
      sourceSelectionId: 'upload-1',
      symbolModel: { inferenceFingerprint: 's'.repeat(64) },
    },
  };
  assert.equal(
    imageImportJobMatchesReportIdentity(
      job,
      'game-1',
      'upload-1',
      report,
      undefined,
    ),
    true,
  );
  assert.equal(
    imageImportJobMatchesReportIdentity(
      {
        ...job,
        inputPayload: {
          ...job.inputPayload,
          imageGeometryRollout: { rolloutRevision: 3 },
        },
      },
      'game-1',
      'upload-1',
      report,
      undefined,
    ),
    false,
  );
  const lateralJob = {
    ...job,
    inputPayload: {
      ...job.inputPayload,
      imageGeometryRollout: {
        lateralPartialGeometry: {
          policyVersion: 'structured-lattice-v4-lateral-partial-v2',
          variant: 'structured_lattice_v4_partial_sides',
        },
        rolloutRevision: 4,
      },
    },
  };
  assert.equal(
    imageImportJobMatchesReportIdentity(
      lateralJob,
      'game-1',
      'upload-1',
      report,
      'structured_lattice_v4_partial_sides',
    ),
    true,
  );
  assert.equal(
    imageImportJobMatchesReportIdentity(
      {
        ...lateralJob,
        inputPayload: {
          ...lateralJob.inputPayload,
          imageGeometryRollout: {
            ...lateralJob.inputPayload.imageGeometryRollout,
            lateralPartialGeometry: {
              policyVersion: 'structured-lattice-v4-lateral-partial-v4',
              variant: 'structured_lattice_v4_partial_sides',
            },
          },
        },
      },
      'game-1',
      'upload-1',
      report,
      'structured_lattice_v4_partial_sides',
    ),
    false,
  );
  assert.equal(
    pageRegistrationVariantFromJob({
      inputPayload: {
        preflightPolicyVersion: 'page-geometry-preflight-v3-board-area-mask',
        validationKind: 'page_geometry_preflight',
      },
    }),
    'board_area_test',
  );
});

test('cold-start replay matches only the pinned unclassified snapshot', () => {
  const fingerprint = 'c'.repeat(64);
  const report = {
    gridProfileInferenceFingerprint: 'g'.repeat(64),
    imageEnginePolicy: 'verified_v19',
    imageEnginePolicyRevision: 0,
    manifestChecksumSha256: 'a'.repeat(64),
    symbolModelInferenceFingerprint: null,
    symbolModelSnapshotFingerprint: fingerprint,
    unclassifiedColdStartAllowed: true,
  };
  const coldStart = {
    classCodes: ['CYTRYNA', 'WISNIA'],
    inferenceFingerprint: fingerprint,
    inferenceMode: 'unclassified',
    inputSize: 64,
    manifestChecksumSha256: 'a'.repeat(64),
    modelVersion: 'cold-start-unclassified-v1',
    onnxChecksumSha256: 'b'.repeat(64),
    onnxRelativePath: 'unclassified/cold-start-unclassified-v1.no-onnx',
    storageRoot: 'repository',
    temperature: 1,
  };

  assert.equal(symbolSnapshotMatchesReport(coldStart, report), true);
  const coldRun = {
    gameId: 'game-1',
    inputPayload: {
      gridProfile: { inferenceFingerprint: 'g'.repeat(64) },
      sourceManifestSha256: 'a'.repeat(64),
      sourceSelectionId: 'upload-1',
      symbolModel: coldStart,
    },
  };
  assert.equal(
    imageImportJobMatchesReportIdentity(
      coldRun,
      'game-1',
      'upload-1',
      report,
      undefined,
    ),
    true,
  );
  assert.equal(
    symbolSnapshotMatchesReport(
      { ...coldStart, inferenceMode: 'model' },
      report,
    ),
    false,
  );
  assert.equal(
    symbolSnapshotMatchesReport({ inferenceFingerprint: fingerprint }, report),
    false,
  );
  assert.equal(
    imageImportJobMatchesReportIdentity(
      {
        ...coldRun,
        inputPayload: {
          ...coldRun.inputPayload,
          symbolModel: { inferenceFingerprint: fingerprint },
        },
      },
      'game-1',
      'upload-1',
      report,
      undefined,
    ),
    false,
  );
});

test('retries the existing failed page geometry preflight job', async () => {
  const calls = [];
  const job = {
    id: 'preflight-job-1',
    inputPayload: { validationKind: 'page_geometry_preflight' },
    jobType: 'validate',
    status: 'created',
  };

  const result = await retryBrowserPageGeometryPreflight(
    {
      retryJob: async (jobId) => {
        calls.push(jobId);
        return { data: job };
      },
    },
    'preflight-job-1',
  );

  assert.deepEqual(calls, ['preflight-job-1']);
  assert.deepEqual(result, { data: job, ok: true });
});

test('board import accepts cropped seq JPEGs and ignores the local crop manifest', () => {
  const files = [
    new File(['a'], 'seq_1-9.jpg', { type: 'image/jpeg' }),
    new File(['b'], 'seq_10-18.jpeg', { type: 'image/jpeg' }),
    new File(['{}'], 'manual-image-crop-output-v1.json', {
      type: 'application/json',
    }),
  ];
  assert.deepEqual(
    filterImageFolderImportFiles(files).map((file) => file.name),
    ['seq_1-9.jpg', 'seq_10-18.jpeg'],
  );
});

test('uploads a browser-native folder and returns a validated selection', async () => {
  const selection = {
    expiresAt: '2026-07-31T12:15:00Z',
    path: 'C:\\photos',
    selectionToken: 'token',
    status: 'selected',
    supportedFileCount: 12,
  };
  const file = new File(['jpeg'], 'layout.jpg', { type: 'image/jpeg' });
  Object.defineProperty(file, 'webkitRelativePath', {
    value: 'photos/layout.jpg',
  });
  const calls = [];
  const progress = [];

  const result = await uploadImageFolder(
    {
      cancelBrowserImageSelection: async () => ({ data: undefined }),
      createBrowserImageSelection: async (body) => {
        calls.push(['create', body]);
        return {
          data: {
            expectedFileCount: 1,
            expectedTotalBytes: file.size,
            uploadId: 'upload-1',
            uploadedBytes: 0,
            uploadedFileCount: 0,
          },
        };
      },
      finalizeBrowserImageSelection: async (uploadId) => {
        calls.push(['finalize', uploadId]);
        return { data: selection };
      },
      uploadBrowserImageSelectionFile: async (...args) => {
        calls.push(['upload', ...args]);
        return {
          data: {
            expectedFileCount: 1,
            expectedTotalBytes: file.size,
            uploadId: 'upload-1',
            uploadedBytes: file.size,
            uploadedFileCount: 1,
          },
        };
      },
    },
    [file],
    (uploaded, total) => progress.push([uploaded, total]),
  );

  assert.deepEqual(result, {
    displayName: 'photos',
    kind: 'uploaded',
    ok: true,
    selection,
    uploadId: 'upload-1',
    uploadPlan: null,
  });
  assert.deepEqual(calls[0], [
    'create',
    {
      displayName: 'photos',
      expectedFileCount: 1,
      expectedTotalBytes: file.size,
    },
  ]);
  assert.deepEqual(calls[1].slice(0, 5), [
    'upload',
    'upload-1',
    0,
    'photos/layout.jpg',
    file,
  ]);
  assert.deepEqual(calls[2], ['finalize', 'upload-1']);
  assert.deepEqual(progress, [[1, 1]]);
});

test('filters fully imported seq ranges before uploading browser JPEG bytes', async () => {
  const existing = new File(['old'], 'seq_1-9.jpg', { type: 'image/jpeg' });
  const missing = new File(['new'], 'seq_10-18.jpg', { type: 'image/jpeg' });
  const calls = [];
  const result = await uploadImageFolder(
    {
      cancelBrowserImageSelection: async () => ({ data: undefined }),
      createBrowserImageSelection: async (body) => {
        calls.push(['create', body]);
        return {
          data: {
            expectedFileCount: 1,
            expectedTotalBytes: missing.size,
            uploadId: 'upload-1',
            uploadedBytes: 0,
            uploadedFileCount: 0,
          },
        };
      },
      finalizeBrowserImageSelection: async () => ({
        data: { status: 'selected', supportedFileCount: 1 },
      }),
      planBrowserImageSelectionUpload: async (body) => {
        calls.push(['plan', body]);
        return {
          data: {
            filesToUpload: [
              {
                relativePath: 'seq_10-18.jpg',
                sizeBytes: missing.size,
                sourceIndex: 1,
                uploadIndex: 0,
              },
            ],
            missingSequenceCount: 9,
            partialSourceCount: 0,
            planChecksumSha256: 'a'.repeat(64),
            reusedSequenceCount: 9,
            selectedFileCount: 2,
            selectedTotalBytes: existing.size + missing.size,
            skippedCompleteSources: [
              {
                relativePath: 'seq_1-9.jpg',
                sequenceRangeEnd: 9,
                sequenceRangeStart: 1,
                sourceIndex: 0,
              },
            ],
            skippedCompleteSourceCount: 1,
            uploadFileCount: 1,
            uploadTotalBytes: missing.size,
            gameId: 'game-1',
          },
        };
      },
      uploadBrowserImageSelectionFile: async (...args) => {
        calls.push(['upload', ...args]);
        return {
          data: {
            expectedFileCount: 1,
            expectedTotalBytes: missing.size,
            uploadedBytes: missing.size,
            uploadedFileCount: 1,
          },
        };
      },
    },
    [existing, missing],
    'game-1',
  );

  assert.equal(result.ok, true);
  assert.equal(calls[0][0], 'plan');
  assert.deepEqual(calls[1], [
    'create',
    {
      displayName: 'seq_1-9.jpg',
      expectedFileCount: 1,
      expectedTotalBytes: missing.size,
      gameId: 'game-1',
      skippedCanonicalRanges: [{ sequenceRangeEnd: 9, sequenceRangeStart: 1 }],
      uploadPlanChecksumSha256: 'a'.repeat(64),
    },
  ]);
  assert.equal(calls[2][3], 'seq_10-18.jpg');
});

test('reprocesses an import from its managed originals', async () => {
  const job = {
    id: 'job-2',
    inputPayload: { importKind: 'image_directory', schemaVersion: 4 },
    jobType: 'import',
    status: 'created',
  };
  let sourceJobId;

  const result = await reprocessImageFolderImport(
    {
      reprocessManagedImageImport: async (value) => {
        sourceJobId = value;
        return { data: { job } };
      },
    },
    'job-1',
  );

  assert.equal(sourceJobId, 'job-1');
  assert.deepEqual(result, { job, ok: true });
});

test('manual continuation is an explicit flag on the managed reprocess action', async () => {
  let args;
  const result = await reprocessImageFolderImport(
    {
      reprocessManagedImageImport: async (...values) => {
        args = values;
        return { data: { job: { id: 'continued' } } };
      },
    },
    'failed-import',
    true,
  );
  assert.deepEqual(args, ['failed-import', true]);
  assert.equal(result.job.id, 'continued');
});

test('preserves a stable browser folder validation error', async () => {
  const file = new File(['jpeg'], 'layout.jpg', { type: 'image/jpeg' });
  const result = await uploadImageFolder(
    {
      createBrowserImageSelection: async () => ({
        error: {
          code: 'IMAGE_FOLDER_EMPTY',
          details: {},
          message: 'No supported files.',
        },
      }),
    },
    [file],
  );

  assert.deepEqual(result, {
    error: 'No supported files. (IMAGE_FOLDER_EMPTY)',
    ok: false,
  });
});

test('previews and starts a recovered browser staging idempotently', async () => {
  const calls = [];
  const api = {
    listReadyBrowserImageSelections: async () => ({
      data: [{ uploadId: 'upload-1', displayName: '1-18' }],
    }),
    previewReadyBrowserImageImport: async (uploadId, body) => {
      calls.push(['preview', uploadId, body]);
      return {
        data: {
          uploadId,
          gameId: body.gameId,
          manifestChecksumSha256: 'a'.repeat(64),
          preflightChecksumSha256: 'b'.repeat(64),
          sourceFileCount: 2,
          attestedFileCount: 2,
          newSequenceCount: 9,
          reusedSequenceCount: 9,
          skippedSourceCount: 1,
          partialSourceCount: 0,
          alternativeSourceCount: 0,
          firstUnresolvedSequence: 10,
          lastUnresolvedSequence: 18,
          warnings: [],
          displayName: '1-18',
        },
      };
    },
    startReadyBrowserImageImport: async (uploadId, body) => {
      calls.push(['start', uploadId, body]);
      return {
        data: {
          created: false,
          job: { id: 'job-1' },
          preflight: {},
        },
      };
    },
  };

  assert.equal((await listReadyBrowserImageSelections(api)).ok, true);
  const preview = await previewReadyBrowserImageImport(
    api,
    'upload-1',
    'game-1',
  );
  assert.equal(preview.ok, true);
  const started = await startReadyBrowserImageImport(
    api,
    'upload-1',
    'game-1',
    'a'.repeat(64),
    'b'.repeat(64),
    'geometry-job-1',
    'c'.repeat(64),
    'verified_v19',
  );

  assert.equal(started.ok, true);
  assert.deepEqual(calls, [
    ['preview', 'upload-1', { gameId: 'game-1' }],
    [
      'start',
      'upload-1',
      {
        gameId: 'game-1',
        boardCellProcessingMode: 'verified_v19',
        imageEnginePolicy: 'verified_v19',
        geometryManifestChecksumSha256: 'c'.repeat(64),
        geometryPreflightJobId: 'geometry-job-1',
        manifestChecksumSha256: 'a'.repeat(64),
        preflightChecksumSha256: 'b'.repeat(64),
      },
    ],
  ]);
});

test('pins the game engine policy for a ready browser staging', async () => {
  let command;
  const result = await startReadyBrowserImageImport(
    {
      startReadyBrowserImageImport: async (_uploadId, body) => {
        command = body;
        return {
          data: {
            created: true,
            job: { id: 'job-v20' },
            preflight: {},
          },
        };
      },
    },
    'upload-v20',
    'game-1',
    'a'.repeat(64),
    'b'.repeat(64),
    'geometry-job-v20',
    'c'.repeat(64),
    'verified_v19',
  );

  assert.equal(result.ok, true);
  assert.equal(command.boardCellProcessingMode, 'verified_v19');
});

test('pins the cold-start geometry manifest for structured shadow', async () => {
  let command;
  const result = await startReadyBrowserImageImport(
    {
      startReadyBrowserImageImport: async (_uploadId, body) => {
        command = body;
        return {
          data: {
            created: true,
            job: { id: 'job-shadow' },
            preflight: {},
          },
        };
      },
    },
    'upload-shadow',
    'game-1',
    'a'.repeat(64),
    'b'.repeat(64),
    'geometry-job-shadow',
    'c'.repeat(64),
    'structured_shadow',
    2,
  );

  assert.equal(result.ok, true);
  assert.equal(command.imageEnginePolicy, 'structured_shadow');
  assert.equal(command.imageEnginePolicyRevision, 2);
  assert.equal(command.geometryPreflightJobId, 'geometry-job-shadow');
  assert.equal(command.geometryManifestChecksumSha256, 'c'.repeat(64));
});

test('pins an explicitly sealed geometry guard resolution manifest', async () => {
  let command;
  const result = await startReadyBrowserImageImport(
    {
      startReadyBrowserImageImport: async (_uploadId, body) => {
        command = body;
        return {
          data: { created: true, job: { id: 'job-v7' }, preflight: {} },
        };
      },
    },
    'upload-v7',
    'game-1',
    'a'.repeat(64),
    'b'.repeat(64),
    'geometry-job-v7',
    'c'.repeat(64),
    'structured_lattice_v3',
    3,
    'd'.repeat(64),
    'e'.repeat(64),
    'resolution-manifest-1',
    'f'.repeat(64),
  );

  assert.equal(result.ok, true);
  assert.equal(
    command.geometryGuardResolutionManifestId,
    'resolution-manifest-1',
  );
  assert.equal(
    command.geometryGuardResolutionManifestChecksumSha256,
    'f'.repeat(64),
  );
});

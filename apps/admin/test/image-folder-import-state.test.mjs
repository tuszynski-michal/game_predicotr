import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canStartReadyImport,
  pageGeometryPreflightOutcomeLabel,
  readyBoardImportGeometryVariant,
  readyBoardImportHasImport,
  readyBoardImportLifecycleLabel,
  sortReadyBoardImports,
} from '../src/features/imports/image-folder-import-state.ts';

function staging(displayName, uploadId) {
  return {
    completedAt: '2026-08-22T00:00:00Z',
    createdAt: '2026-08-22T00:00:00Z',
    displayName,
    expectedFileCount: 1,
    expectedTotalBytes: 1,
    gameId: 'game-1',
    manifestChecksumSha256: 'a'.repeat(64),
    purpose: 'layout_import',
    uploadId,
    uploadedBytes: 1,
    uploadedFileCount: 1,
  };
}

function job({
  checksum = 'a'.repeat(64),
  geometryManifestChecksum,
  provisionalReviewRequired,
  id = 'job-1',
  jobType,
  variant,
  createdAt = '2026-09-16T10:00:00Z',
  sourceSelectionId = 'upload-1',
  status,
}) {
  return {
    createdAt,
    gameId: 'game-1',
    id,
    inputPayload: {
      importKind: jobType === 'import' ? 'image_directory' : undefined,
      sourceManifestSha256: checksum,
      sourceSelectionId,
      lateralPartialGeometry: variant === undefined ? undefined : { variant },
      validationKind:
        jobType === 'validate' ? 'page_geometry_preflight' : undefined,
    },
    jobType,
    progress: {
      pageGeometryPreflight:
        geometryManifestChecksum === undefined
          ? undefined
          : {
              geometryManifestChecksumSha256: geometryManifestChecksum,
              ...(provisionalReviewRequired === undefined
                ? {}
                : { provisionalReviewRequired }),
            },
    },
    status,
  };
}

test('reopens a completed v1.1 staging in its pinned variant', () => {
  const selection = staging('200575 - 222912 cut', 'upload-1');
  const completedV11 = job({
    geometryManifestChecksum: 'g'.repeat(64),
    id: 'v11-completed',
    jobType: 'validate',
    status: 'completed',
    variant: 'selective_board_review_v1_1',
  });
  const laterV10 = job({
    createdAt: '2026-09-16T11:00:00Z',
    id: 'v10-created',
    jobType: 'validate',
    status: 'created',
    variant: 'structured_lattice_v4_partial_sides',
  });
  assert.equal(
    readyBoardImportGeometryVariant([], selection),
    'selective_board_review_v1_1',
  );
  assert.equal(
    readyBoardImportGeometryVariant([laterV10], selection),
    'structured_lattice_v4_partial_sides',
  );
  assert.equal(
    readyBoardImportGeometryVariant([laterV10, completedV11], selection),
    'selective_board_review_v1_1',
  );
  assert.equal(
    readyBoardImportGeometryVariant(
      [{ ...laterV10, status: 'cancelled' }, completedV11],
      selection,
    ),
    'selective_board_review_v1_1',
  );
  assert.equal(
    readyBoardImportGeometryVariant(
      [
        {
          ...completedV11,
          inputPayload: {
            ...completedV11.inputPayload,
            sourceSelectionId: 'other-upload',
          },
        },
      ],
      selection,
    ),
    'selective_board_review_v1_1',
  );
});

function lifecycle(overrides = {}) {
  return readyBoardImportLifecycleLabel({
    geometryPreflightJobs: [],
    reportPrepared: false,
    selection: staging('1-10', 'upload-1'),
    ...overrides,
  });
}

test('orders ready board imports by the leading numeric range', () => {
  const ordered = sortReadyBoardImports([
    staging('100000-150000', 'large'),
    staging('Katalog testowy', 'named'),
    staging('20000 - 99999', 'small'),
    staging('1-19809', 'first'),
  ]);

  assert.deepEqual(
    ordered.map((item) => item.uploadId),
    ['first', 'small', 'large', 'named'],
  );
});

test('uses a deterministic name and id fallback for equal or non-range names', () => {
  const ordered = sortReadyBoardImports([
    staging('Test 10', 'b'),
    staging('20000-30000 B', 'range-b'),
    staging('Test 2', 'c'),
    staging('20000-30000 A', 'range-a'),
    staging('Test 2', 'a'),
  ]);

  assert.deepEqual(
    ordered.map((item) => item.uploadId),
    ['range-a', 'range-b', 'a', 'c', 'b'],
  );
});

test('allows a guarded ready import only after both durable manifests are restored', () => {
  const restored = {
    geometryGuardResolutionManifestAvailable: true,
    geometryGuardResolutionRequired: true,
    geometryManifestAvailable: true,
    geometryPreflightArtifactReady: true,
    geometryPreflightCompleted: true,
    geometryPreflightRequired: true,
    symbolModelAvailable: true,
  };

  assert.equal(canStartReadyImport(restored), true);
  assert.equal(
    canStartReadyImport({
      ...restored,
      geometryGuardResolutionManifestAvailable: false,
    }),
    false,
  );
  assert.equal(
    canStartReadyImport({ ...restored, geometryPreflightCompleted: false }),
    false,
  );
  assert.equal(
    canStartReadyImport({ ...restored, geometryPreflightArtifactReady: false }),
    false,
  );
});

test('labels a staging by its highest durable import stage', () => {
  assert.equal(lifecycle(), 'oczekuje na operację · załadowano folder');
  assert.equal(
    lifecycle({ reportPrepared: true }),
    'oczekuje na operację · przygotowano preflight',
  );
  assert.equal(
    lifecycle({
      geometryPreflightJobs: [
        job({ jobType: 'validate', status: 'processing' }),
      ],
    }),
    'oczekuje na operację · przygotowano preflight',
  );
  assert.equal(
    lifecycle({
      geometryPreflightJobs: [
        job({ jobType: 'validate', status: 'completed' }),
      ],
    }),
    'oczekuje na operację · przygotowano preflight',
  );
  assert.equal(
    lifecycle({
      geometryPreflightJobs: [
        job({
          geometryManifestChecksum: 'g'.repeat(64),
          jobType: 'validate',
          status: 'completed',
        }),
      ],
    }),
    'oczekuje na operację · przygotowano siatkę',
  );
});

test('keeps a completed board import independent from symbol verification', () => {
  assert.equal(
    lifecycle({
      selection: {
        ...staging('1-10', 'upload-1'),
        boardImportStatus: 'boards_imported',
      },
    }),
    'plansze utworzone · weryfikacja symboli poza importem',
  );
  assert.equal(
    lifecycle({
      selection: {
        ...staging('1-10', 'upload-1'),
        boardImportStatus: 'importing',
      },
    }),
    'trwa import plansz',
  );
});

test('shows a completed preflight with deferred geometry as requiring correction', () => {
  assert.equal(
    lifecycle({
      geometryPreflightJobs: [
        job({
          geometryManifestChecksum: 'g'.repeat(64),
          jobType: 'validate',
          provisionalReviewRequired: 2,
          status: 'completed',
        }),
      ],
    }),
    'wymaga korekty geometrii · odroczone zdjęcia 2',
  );
});

test('does not advance a staging from a foreign id or manifest checksum', () => {
  assert.equal(
    lifecycle({
      geometryPreflightJobs: [
        job({
          geometryManifestChecksum: 'g'.repeat(64),
          jobType: 'validate',
          sourceSelectionId: 'upload-2',
          status: 'completed',
        }),
      ],
    }),
    'oczekuje na operację · załadowano folder',
  );
});

test('labels an active auto-anchor result as provisional', () => {
  assert.equal(
    pageGeometryPreflightOutcomeLabel(
      {
        status: 'processing',
        progress: {
          pageGeometryPreflight: {
            phase: 'auto_anchor_retry',
            provisionalReviewRequired: 7,
          },
        },
      },
      0,
    ),
    'jeszcze nierozstrzygnięte zdjęcia 7',
  );
});

test('labels the correction queue as final only after preflight completion', () => {
  assert.equal(
    pageGeometryPreflightOutcomeLabel(
      {
        status: 'completed',
        progress: {
          pageGeometryPreflight: {
            phase: 'complete',
            provisionalReviewRequired: 4,
          },
        },
      },
      4,
    ),
    'odroczone zdjęcia 4',
  );
});

test('does not claim a final count for a legacy active checkpoint', () => {
  assert.equal(
    pageGeometryPreflightOutcomeLabel(
      {
        status: 'processing',
        progress: {},
      },
      0,
    ),
    'wynik końcowy jeszcze niegotowy',
  );
});

test('uses the durable staging status instead of job history', () => {
  const selection = {
    ...staging('1-10', 'upload-1'),
    boardImportStatus: 'boards_imported',
  };
  assert.equal(readyBoardImportHasImport(selection), true);
  assert.equal(
    lifecycle({ selection }),
    'plansze utworzone · weryfikacja symboli poza importem',
  );
  assert.equal(readyBoardImportHasImport(staging('1-10', 'upload-1')), false);
});

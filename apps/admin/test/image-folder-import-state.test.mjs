import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canStartReadyImport,
  pageGeometryPreflightOutcomeLabel,
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

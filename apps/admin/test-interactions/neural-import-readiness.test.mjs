import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'Element',
  'Event',
  'MouseEvent',
  'localStorage',
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { ImageFolderImportPanel } =
  await import('../src/features/imports/image-folder-import-panel.tsx');
after(() => dom.window.close());
const snapshot = {
  contractVersion: 'neural-grid-proposal-snapshot-v1',
  expectedLayoutCount: 500000,
  model: {
    profile: 'grid_profile_mumie_v1',
    modelKind: 'neural_grid',
    schemaVersion: 'grid-engine-model-manifest-v1',
  },
};
const progress = {
  current: 100,
  total: 100,
  failed: 0,
  succeeded: 1,
  review: 99,
  pageGeometryPreflight: {
    complete: true,
    provisionalReviewRequired: 99,
    geometryManifestChecksumSha256: 'c'.repeat(64),
  },
};
const geometry = {
  id: 'geometry',
  gameId: 'game',
  jobType: 'validate',
  status: 'completed',
  createdAt: '2026-10-06',
  inputPayload: {
    validationKind: 'page_geometry_preflight',
    preflightPolicyVersion: 'page-geometry-preflight-v13-neural-mumie-pilot',
    neuralGridProposal: snapshot,
    sourceSelectionId: 'selection',
    sourceManifestSha256: 'b'.repeat(64),
    managedSourceJobId: null,
  },
  progress,
};
const previous = {
  id: 'previous',
  gameId: 'game',
  jobType: 'import',
  status: 'completed',
  createdAt: '2026-10-06',
  startedAt: null,
  finishedAt: null,
  inputPayload: {
    importKind: 'image_directory',
    neuralGridProposal: snapshot,
    sourceSelectionId: 'selection',
    sourceManifestSha256: 'b'.repeat(64),
    pageGeometryManifest: {
      preflightJobId: 'old',
      checksumSha256: 'd'.repeat(64),
      relativePath: 'manifest.json',
    },
  },
  progress: { current: 200, total: 200, failed: 0, succeeded: 0, review: 100 },
};
const button = (text) =>
  [...document.querySelectorAll('button')].find((b) => b.textContent === text);
async function mount(prior = null, processing = false) {
  const calls = [];
  const currentGeometry = processing
    ? {
        ...geometry,
        status: 'processing',
        progress: {
          ...progress,
          pageGeometryPreflight: {
            ...progress.pageGeometryPreflight,
            complete: false,
            geometryManifestChecksumSha256: null,
          },
        },
      }
    : geometry;
  const source = {
    uploadId: 'selection',
    gameId: 'game',
    manifestChecksumSha256: 'b'.repeat(64),
    displayName: 'Mumie',
    uploadedFileCount: 100,
    expectedTotalBytes: 1000,
    boardImportStatus: prior ? 'boards_imported' : 'ready',
    createdAt: '2026-10-06',
  };
  const report = {
    gameId: 'game',
    uploadId: 'selection',
    manifestChecksumSha256: source.manifestChecksumSha256,
    preflightChecksumSha256: 'e'.repeat(64),
    gridProfileInferenceFingerprint: 'grid',
    imageEnginePolicyRevision: 1,
    imageEnginePolicy: 'structured_lattice_v3',
    geometryEngineVariant: null,
    geometryEngineVariantEnabled: true,
    geometryPreflightJob: currentGeometry,
    geometryPreflightArtifactReady: !processing,
    geometryPreflightRequired: true,
    unclassifiedColdStartAllowed: true,
    symbolModelReady: false,
    sourceFileCount: 100,
    newSequenceCount: 900,
    reusedSequenceCount: 0,
    skippedSourceCount: 0,
    warnings: [],
    existingImportJob: prior,
  };
  const unavailable = async () => ({
    error: { message: 'fixture unrelated section' },
  });
  const api = {
    listJobs: async ({ jobType }) => ({
      data: jobType === 'validate' ? [geometry] : prior ? [prior] : [],
    }),
    getJob: async () => ({ data: geometry }),
    listCuratedImageImportSources: async () => ({ data: [] }),
    listReadyBrowserImageSelections: async () => ({ data: [source] }),
    getImageImportEnginePolicy: async () => ({
      data: { policy: 'structured_lattice_v3', geometryEngineVariants: [] },
    }),
    getBoardImportCoverage: unavailable,
    getImageGeometryCompleteness: unavailable,
    listIncompleteGeometryImages: unavailable,
    previewReadyBrowserImageImport: async () => ({ data: report }),
    listBrowserPageGeometryReviewSources: async () => ({
      data: {
        sources: [],
        reviewRequiredSourceCount: 99,
        geometryManifestChecksumSha256: 'c'.repeat(64),
        managedSourceJobId: prior?.id ?? null,
      },
    }),
    startReadyBrowserImageImport: async (...args) => {
      calls.push(args);
      return { error: { message: 'fixture stops before execution' } };
    },
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(ImageFolderImportPanel, {
        client: api,
        apiBaseUrl: 'http://fixture',
        gameId: 'game',
      }),
    ),
  );
  await act(async () => button('Pokaż raport').click());
  return { root, calls };
}

test('existing Import button is enabled for a completed 99-review neural report and sends pinned manifest only on explicit click', async () => {
  const { root, calls } = await mount();
  try {
    const start = button('Rozpocznij import Mumii z korektą');
    assert.ok(start);
    assert.equal(start.disabled, false);
    assert.equal(calls.length, 0);
    await act(async () => start.click());
    assert.equal(calls.length, 1);
    assert.equal(calls[0][1].geometryPreflightJobId, geometry.id);
    assert.equal(calls[0][1].geometryManifestChecksumSha256, 'c'.repeat(64));
  } finally {
    await act(async () => root.unmount());
  }
});

test('after restart pending-only neural history keeps source correction/report accessible and enables changed manifest import', async () => {
  const { root, calls } = await mount(JSON.parse(JSON.stringify(previous)));
  try {
    assert.ok(button('Odśwież raport'));
    assert.equal(button('Rozpocznij import Mumii z korektą').disabled, false);
    assert.match(document.body.textContent, /Źródła oczekujące na przypisanie/);
    assert.equal(calls.length, 0);
  } finally {
    await act(async () => root.unmount());
  }
});

test('polling a processing frozen neural preflight unlocks Import when its 99-review manifest completes', async () => {
  const { root, calls } = await mount(null, true);
  try {
    await act(async () => {});
    assert.equal(button('Rozpocznij import Mumii z korektą').disabled, false);
    assert.equal(calls.length, 0);
  } finally {
    await act(async () => root.unmount());
  }
});

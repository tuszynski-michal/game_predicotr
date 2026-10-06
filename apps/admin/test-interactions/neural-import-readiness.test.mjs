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
async function mount(prior = null, processing = false, options = {}) {
  const calls = [];
  const reportCalls = [];
  const preflightCalls = [];
  const currentGeometry = options.noGeometry
    ? null
    : processing
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
  const report = options.report ?? {
    gameId: 'game',
    uploadId: 'selection',
    manifestChecksumSha256: source.manifestChecksumSha256,
    preflightChecksumSha256: 'e'.repeat(64),
    gridProfileInferenceFingerprint: 'grid',
    imageEnginePolicyRevision: 1,
    imageEnginePolicy: 'structured_lattice_v3',
    geometryEngineVariant: options.historyVariant ?? null,
    geometryEngineVariantEnabled: true,
    geometryPreflightJob: options.historyGeometry ?? currentGeometry,
    geometryPreflightArtifactReady: !processing && !options.noGeometry,
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
      data:
        jobType === 'validate'
          ? options.noGeometry
            ? []
            : [options.historyGeometry ?? geometry]
          : prior
            ? [prior]
            : [],
    }),
    getJob: async () => ({ data: geometry }),
    listCuratedImageImportSources: async () => ({ data: [] }),
    listReadyBrowserImageSelections: async () =>
      options.readyResult?.() ?? { data: [source] },
    getImageImportEnginePolicy: async () => ({
      data: {
        policy: 'structured_lattice_v3',
        geometryEngineVariants: [
          { variant: 'selective_board_review_v1_1', enabled: true },
          { variant: 'structured_lattice_v4_partial_sides', enabled: true },
          { variant: 'contrast_frame_grid_v1_2', enabled: true },
        ],
      },
    }),
    getBoardImportCoverage: unavailable,
    getImageGeometryCompleteness: unavailable,
    listIncompleteGeometryImages: unavailable,
    previewReadyBrowserImageImport: async (...args) => {
      reportCalls.push(args);
      return options.previewResult?.() ?? { data: report };
    },
    startBrowserPageGeometryPreflight: async (...args) => {
      preflightCalls.push(args);
      return { data: { created: false, job: geometry } };
    },
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
      return (
        options.startResult ?? {
          error: { message: 'fixture stops before execution' },
        }
      );
    },
    ...options.clientOverrides,
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(ImageFolderImportPanel, {
        client: api,
        apiBaseUrl: 'http://fixture',
        gameId: 'game',
        shapeGeometryConfiguration:
          options.profile === undefined
            ? 'grid_profile_mumie_v1'
            : options.profile,
      }),
    ),
  );
  if (options.openReport !== false)
    await act(async () => button('Pokaż raport').click());
  return { root, calls, reportCalls, preflightCalls, api, source };
}

test('existing Import button is enabled for a completed 99-review neural report and sends pinned manifest only on explicit click', async () => {
  const { root, calls, reportCalls } = await mount();
  try {
    const start = button('Rozpocznij import Mumii z korektą');
    assert.ok(start);
    assert.equal(start.disabled, false);
    assert.equal(calls.length, 0);
    await act(async () => start.click());
    assert.equal(calls.length, 1);
    assert.equal(calls[0][1].geometryPreflightJobId, geometry.id);
    assert.equal(calls[0][1].geometryManifestChecksumSha256, 'c'.repeat(64));
    assert.equal(Object.hasOwn(calls[0][1], 'geometryEngineVariant'), false);
    assert.equal(
      Object.hasOwn(reportCalls[0][1], 'geometryEngineVariant'),
      false,
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('import does not mount or request grid diagnostics', async () => {
  const requests = [];
  const { root } = await mount(null, false, {
    clientOverrides: {
      getImageGeometryCompleteness: async () => {
        requests.push('report');
        return { error: {} };
      },
      listIncompleteGeometryImages: async () => {
        requests.push('images');
        return { error: {} };
      },
    },
  });
  try {
    assert.deepEqual(requests, []);
    assert.doesNotMatch(
      document.body.textContent,
      /Kompletność siatek zdjęć|Diagnostyka siatek zdjęć/,
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('a successful Mumie import reports V3 rather than the undefined classical fallback', async () => {
  const job = {
    ...previous,
    id: 'new-neural-import',
    status: 'created',
    inputPayload: {
      ...previous.inputPayload,
      imageGeometryRollout: { geometryMode: 'structured_lattice_v3' },
    },
  };
  const { root, calls } = await mount(null, false, {
    startResult: { data: { created: true, job } },
  });
  try {
    await act(async () => button('Rozpocznij import Mumii z korektą').click());
    assert.equal(calls.length, 1);
    assert.match(
      document.body.textContent,
      /Import new-neural-import utworzony w V3/,
    );
    assert.doesNotMatch(document.body.textContent, /utworzony w v1.0/);
  } finally {
    await act(async () => root.unmount());
  }
});

test('fresh Mumie mounts show selected V3, hide classical choices and do not start processing', async () => {
  for (let restart = 0; restart < 2; restart++) {
    const { root, calls, reportCalls, preflightCalls } = await mount(
      null,
      false,
      { openReport: false },
    );
    try {
      const radios = [
        ...document.querySelectorAll('input[name="geometry-engine-variant"]'),
      ];
      assert.equal(radios.length, 1);
      assert.equal(radios[0].checked, true);
      assert.match(
        radios[0].closest('label').textContent,
        /V3 — sieć neuronowa/,
      );
      assert.equal(button('Przetwórz w v1.1'), undefined);
      assert.equal(document.querySelector('select'), null);
      assert.match(document.body.textContent, /przeznaczone do usunięcia/);
      assert.equal(reportCalls.length, 0);
      assert.equal(preflightCalls.length, 0);
      assert.equal(calls.length, 0);
    } finally {
      await act(async () => root.unmount());
    }
  }
});

test('Mumie explicit geometry preparation omits the classical variant', async () => {
  const { root, calls, preflightCalls } = await mount(null, false, {
    noGeometry: true,
  });
  try {
    assert.doesNotMatch(
      document.body.textContent,
      /Wariant dopasowania zdjęcia/,
    );
    assert.match(document.body.textContent, /Źródło geometrii neuronowej/);
    const reportVersion = [...document.querySelectorAll('dt')].find(
      (element) => element.textContent === 'Wersja silnika siatki',
    );
    assert.match(
      reportVersion.nextElementSibling.textContent,
      /V3 — sieć neuronowa/,
    );
    await act(async () => button('Przygotuj geometrię stron').click());
    assert.equal(preflightCalls.length, 1);
    assert.equal(
      Object.hasOwn(preflightCalls[0][1], 'geometryEngineVariant'),
      false,
    );
    assert.equal(calls.length, 0);
  } finally {
    await act(async () => root.unmount());
  }
});

test('777 keeps V1.1, classical registration and its selected request value', async () => {
  const { root, reportCalls, preflightCalls } = await mount(null, false, {
    openReport: false,
    profile: 'framed_full_page_v2',
    noGeometry: true,
  });
  try {
    const radios = [
      ...document.querySelectorAll('input[name="geometry-engine-variant"]'),
    ];
    assert.equal(radios.length, 1);
    assert.equal(radios[0].checked, true);
    assert.equal(radios[0].disabled, false);
    assert.match(radios[0].closest('label').textContent, /v1.1/);
    assert.doesNotMatch(document.body.textContent, /V3 — sieć neuronowa/);
    assert.equal(button('Przetwórz w v1.1').disabled, false);
    await act(async () => button('Pokaż raport').click());
    assert.equal(
      reportCalls[0][1].geometryEngineVariant,
      'selective_board_review_v1_1',
    );
    const registration = document.querySelector('select');
    assert.ok(registration);
    await act(async () => {
      registration.value = 'board_area_test';
      registration.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await act(async () => button('Przygotuj geometrię stron').click());
    assert.equal(
      preflightCalls[0][1].pageRegistrationVariant,
      'board_area_test',
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('opening a pinned classical V1.2 report preserves its version while the deprecated picker stays hidden', async () => {
  const historyGeometry = {
    ...geometry,
    inputPayload: {
      validationKind: 'page_geometry_preflight',
      sourceSelectionId: 'selection',
      sourceManifestSha256: 'b'.repeat(64),
      contrastFrameGridV12Profile: { profileVersion: 'historical-fixture' },
    },
  };
  const { root, reportCalls, calls } = await mount(null, false, {
    profile: 'framed_full_page_v2',
    historyVariant: 'contrast_frame_grid_v1_2',
    historyGeometry,
  });
  try {
    assert.equal(
      reportCalls[0][1].geometryEngineVariant,
      'contrast_frame_grid_v1_2',
    );
    assert.match(document.body.textContent, /Wariant dopasowania zdjęcia/);
    assert.match(
      document.body.textContent,
      /Otwarty raport historyczny używa v1.2/,
    );
    const radios = [
      ...document.querySelectorAll('input[name="geometry-engine-variant"]'),
    ];
    assert.equal(radios.length, 1);
    assert.match(radios[0].closest('label').textContent, /v1.1/);
    assert.equal(calls.length, 0);
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

test('folder list failure is visible and refresh recovers the actionable folder after remount', async () => {
  let failed = true;
  const options = {
    openReport: false,
    noGeometry: true,
    readyResult: () =>
      failed
        ? { error: { code: 'LIST_FAILURE', message: 'temporary list failure' } }
        : undefined,
  };
  let { root, calls, preflightCalls } = await mount(null, false, options);
  try {
    assert.match(
      document.body.textContent,
      /Nie udało się wczytać przesłanych folderów/,
    );
    assert.match(document.body.textContent, /temporary list failure/);
    assert.equal(button('Pokaż raport'), undefined);
    failed = false;
    await act(async () => button('Odśwież status').click());
    assert.doesNotMatch(document.body.textContent, /temporary list failure/);
    assert.ok(button('Pokaż raport'));
    assert.equal(calls.length, 0);
    assert.equal(preflightCalls.length, 0);
  } finally {
    await act(async () => root.unmount());
  }
  ({ root, calls, preflightCalls } = await mount(null, false, options));
  try {
    assert.ok(button('Pokaż raport'));
    assert.equal(calls.length, 0);
    assert.equal(preflightCalls.length, 0);
  } finally {
    await act(async () => root.unmount());
  }
});

test('failed folder-list refresh preserves a previously loaded card', async () => {
  let failed = false;
  const { root } = await mount(null, false, {
    openReport: false,
    noGeometry: true,
    readyResult: () =>
      failed
        ? { error: { code: 'LIST_FAILURE', message: 'list offline' } }
        : undefined,
  });
  try {
    assert.ok(button('Pokaż raport'));
    failed = true;
    await act(async () => button('Odśwież status').click());
    assert.ok(button('Pokaż raport'));
    assert.match(document.body.textContent, /list offline/);
  } finally {
    await act(async () => root.unmount());
  }
});

test('empty and loading folder states are explicit', async () => {
  let resolveList;
  const pending = new Promise((resolve) => {
    resolveList = resolve;
  });
  const { root } = await mount(null, false, {
    openReport: false,
    noGeometry: true,
    clientOverrides: { listReadyBrowserImageSelections: () => pending },
  });
  try {
    assert.match(document.body.textContent, /Wczytywanie przesłanych folderów/);
    await act(async () => resolveList({ data: [] }));
    assert.doesNotMatch(
      document.body.textContent,
      /Wczytywanie przesłanych folderów/,
    );
    assert.match(
      document.body.textContent,
      /Brak przesłanych folderów dla tej gry/,
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('late older folder list cannot remove a folder recovered by refresh', async () => {
  let resolveOldList;
  const oldList = new Promise((resolve) => {
    resolveOldList = resolve;
  });
  let listCalls = 0;
  let storedSource;
  const { root, source } = await mount(null, false, {
    openReport: false,
    noGeometry: true,
    clientOverrides: {
      listReadyBrowserImageSelections: () =>
        ++listCalls === 1 ? oldList : Promise.resolve({ data: [storedSource] }),
    },
  });
  storedSource = source;
  try {
    await act(async () => button('Odśwież status').click());
    assert.ok(button('Pokaż raport'));
    await act(async () => resolveOldList({ data: [] }));
    assert.ok(button('Pokaż raport'));
    assert.doesNotMatch(document.body.textContent, /Brak przesłanych folderów/);
  } finally {
    await act(async () => root.unmount());
  }
});

test('finalized upload stays visible and retryable when its report fails', async () => {
  let finalized = false;
  let reportFailed = true;
  let storedSource;
  const file = new File(['jpeg'], 'seq_1-9.jpg', { type: 'image/jpeg' });
  Object.defineProperty(file, 'webkitRelativePath', {
    value: 'Mumie/seq_1-9.jpg',
  });
  const { root, source, calls, preflightCalls } = await mount(null, false, {
    openReport: false,
    noGeometry: true,
    readyResult: () => ({ data: finalized ? [storedSource] : [] }),
    previewResult: () =>
      reportFailed
        ? {
            error: {
              code: 'REPORT_FAILURE',
              message: 'report temporarily unavailable',
            },
          }
        : undefined,
    clientOverrides: {
      planBrowserImageSelectionUpload: async () => ({
        data: {
          filesToUpload: [{ sourceIndex: 0, uploadIndex: 0 }],
          uploadFileCount: 1,
          selectedFileCount: 1,
          skippedCompleteSourceCount: 0,
          skippedCanonicalRanges: [],
          skippedCompleteSources: [],
          planChecksumSha256: 'a'.repeat(64),
        },
      }),
      createBrowserImageSelection: async () => ({
        data: { uploadId: 'selection' },
      }),
      uploadBrowserImageSelectionFile: async () => ({ data: {} }),
      finalizeBrowserImageSelection: async () => {
        finalized = true;
        return { data: { status: 'selected', supportedFileCount: 1 } };
      },
      cancelBrowserImageSelection: async () => {
        assert.fail('finalized upload must remain');
      },
    },
  });
  storedSource = source;
  try {
    const input = document.querySelector('input[type="file"]');
    Object.defineProperty(input, 'files', {
      configurable: true,
      value: [file],
    });
    await act(async () =>
      input.dispatchEvent(new Event('change', { bubbles: true })),
    );
    assert.equal(finalized, true);
    assert.ok(button('Odśwież raport'));
    assert.match(document.body.textContent, /report temporarily unavailable/);
    reportFailed = false;
    await act(async () => button('Odśwież raport').click());
    assert.doesNotMatch(
      document.body.textContent,
      /report temporarily unavailable/,
    );
    assert.ok(button('Przygotuj geometrię stron'));
    assert.equal(calls.length, 0);
    assert.equal(preflightCalls.length, 0);
  } finally {
    await act(async () => root.unmount());
  }
});

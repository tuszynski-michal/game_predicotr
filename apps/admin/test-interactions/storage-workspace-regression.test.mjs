import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import test from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';

// Regression: the photo crop sections must not change the existing inventory
// and garbage-collection behavior of the Storage workspace (TASK-1049).
const bootstrap = new JSDOM('<div></div>');
globalThis.window = bootstrap.window;
globalThis.document = bootstrap.window.document;
const { createRoot } = await import('react-dom/client');
delete globalThis.window;
delete globalThis.document;
bootstrap.window.close();

registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith('.css'))
      return {
        format: 'module',
        shortCircuit: true,
        source: 'export default new Proxy({}, {get: (_, key) => key});',
      };
    if (url.endsWith('/src/api/admin-api-client.ts'))
      return {
        format: 'module',
        shortCircuit: true,
        source:
          'export function createConfiguredAdminApiClient() { return globalThis.__storageTestClient; }',
      };
    return nextLoad(url, context);
  },
});
const { StorageWorkspace } =
  await import('../src/features/storage/storage-workspace.tsx');

const GIB = 1024 ** 3;
const inventory = {
  automaticDeletion: false,
  databaseSizeBytes: 5 * GIB,
  measuredAt: '2026-10-17T10:00:00Z',
  namespaces: [
    {
      fileCount: 12,
      name: 'originals',
      protected: true,
      retentionPolicy: 'keep',
      sizeBytes: 40 * GIB,
    },
    {
      fileCount: 3,
      name: 'working',
      protected: false,
      retentionPolicy: 'ttl',
      sizeBytes: 2 * GIB,
    },
  ],
  totalFileCount: 15,
  totalSizeBytes: 42 * GIB,
  volumes: [
    {
      freeBytes: 20 * GIB,
      key: 'c',
      roots: ['data'],
      totalBytes: 500 * GIB,
    },
  ],
};
const gcPreview = {
  candidateBytes: 2 * GIB,
  candidateCount: 4,
  categoryCounts: { working: { bytes: 2 * GIB, count: 4 } },
  id: 'gc-preview-1',
  manifestChecksumSha256: 'd'.repeat(64),
  policyVersion: 'gc-v1',
  predictedFreeBytes: 22 * GIB,
  previewToken: 'gc-token',
  protectedBytes: 40 * GIB,
  protectedCount: 12,
  protectionReasonCounts: { REFERENCED: { bytes: GIB, count: 2 } },
};

function fixture() {
  const requests = [];
  globalThis.__storageTestClient = {
    async getImageStorageInventory() {
      requests.push(['inventory']);
      return { data: inventory };
    },
    async refreshImageStorageInventory() {
      requests.push(['refresh']);
      return { data: { id: 'inventory-job' } };
    },
    async getJob(jobId) {
      requests.push(['job', jobId]);
      return { data: { id: jobId, status: 'completed' } };
    },
    async createStorageGcPreview() {
      requests.push(['gcPreview']);
      return { data: gcPreview };
    },
    async startStorageGcRun(body) {
      requests.push(['gcStart', body]);
      return {
        data: {
          candidateCount: 4,
          deletedBytes: 0,
          deletedCount: 0,
          id: 'gc-run-1',
          jobId: 'gc-job-1',
          status: 'created',
        },
      };
    },
    async getStorageGcRun(runId) {
      requests.push(['gcRun', runId]);
      return { data: { id: runId, status: 'created' } };
    },
    async listGames() {
      return { data: [] };
    },
    async listSourceCropRuns(limit) {
      requests.push(['cropRuns', limit]);
      return { data: { runs: [] } };
    },
  };
  return requests;
}

async function mount() {
  const dom = new JSDOM('<div id="root"></div>', {
    url: 'http://127.0.0.1:3000',
  });
  const previous = {};
  for (const [key, value] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    previous[key] = globalThis[key];
    globalThis[key] = value;
  }
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(StorageWorkspace, {
        apiBaseUrl: 'http://127.0.0.1:8000',
      }),
    ),
  );
  await settle();
  return {
    async cleanup() {
      await act(async () => root.unmount());
      dom.window.close();
      Object.assign(globalThis, previous);
      delete globalThis.__storageTestClient;
    },
  };
}
async function settle() {
  for (let index = 0; index < 5; index += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 5));
    });
  }
}
const button = (label, root = document) =>
  [...root.querySelectorAll('button')].find(
    (element) => element.textContent.trim() === label,
  );

test('inventory, volume pressure and namespaces render next to the crop sections', async () => {
  const requests = fixture();
  const m = await mount();
  try {
    const page = document.body.textContent;
    assert.match(page, /Pamięć i czyszczenie/);
    assert.match(page, /42 GiB/);
    assert.match(page, /Tryb obserwacji/);
    assert.match(page, /blokada zapisu/);
    assert.match(page, /Oryginały/);
    assert.match(page, /chronione/);
    assert.match(page, /odtwarzalne/);
    assert.ok(requests.some((item) => item[0] === 'inventory'));
    // The new sections load their recent runs read-only and never plan on mount.
    assert.deepEqual(
      requests.filter((item) => item[0] === 'cropRuns'),
      [['cropRuns', 20]],
    );
    assert.match(page, /Przycinanie zdjęć/);
    assert.match(page, /Usuń oryginały przyciętych zdjęć/);
  } finally {
    await m.cleanup();
  }
});

test('garbage collection still requires a preview and a confirmed start', async () => {
  const requests = fixture();
  const m = await mount();
  try {
    assert.equal(requests.filter((item) => item[0] === 'gcStart').length, 0);
    await act(async () => button('Przygotuj raport czyszczenia').click());
    const dialog = document.querySelector('[role="dialog"]');
    assert.ok(dialog);
    assert.match(dialog.textContent, /Bezpieczne dane do usunięcia/);
    assert.match(dialog.textContent, /Operacja jest nieodwracalna/);
    assert.equal(requests.filter((item) => item[0] === 'gcStart').length, 0);
    await act(async () => button('Usuń bezpieczne dane', dialog).click());
    assert.deepEqual(
      requests.filter((item) => item[0] === 'gcStart'),
      [
        [
          'gcStart',
          {
            confirmed: true,
            manifestChecksumSha256: 'd'.repeat(64),
            previewId: 'gc-preview-1',
            previewToken: 'gc-token',
          },
        ],
      ],
    );
    assert.match(document.body.textContent, /Garbage collector · created/);
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(
      requests.filter((item) => item[0] === 'cropRuns').length,
      1,
      'GC never touches the crop runs',
    );
  } finally {
    await m.cleanup();
  }
});

test('inventory refresh still runs as a polled durable job', async () => {
  const requests = fixture();
  const m = await mount();
  try {
    await act(async () => button('Odśwież inwentarz').click());
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1100));
    });
    await settle();
    assert.deepEqual(
      requests.filter((item) => item[0] === 'refresh' || item[0] === 'job'),
      [['refresh'], ['job', 'inventory-job']],
    );
    assert.equal(requests.filter((item) => item[0] === 'inventory').length, 2);
    assert.equal(document.querySelector('[role="alert"]'), null);
  } finally {
    await m.cleanup();
  }
});

import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';

const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'http://localhost',
});
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'HTMLInputElement',
  'Element',
  'Event',
  'MouseEvent',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
dom.window.Element.prototype.getBoundingClientRect = () => ({
  bottom: 200,
  height: 200,
  left: 0,
  right: 200,
  top: 0,
  width: 200,
  x: 0,
  y: 0,
});
Object.defineProperty(globalThis, 'indexedDB', {
  configurable: true,
  value: {},
});
const originalCreateObjectUrl = URL.createObjectURL;
const originalRevokeObjectUrl = URL.revokeObjectURL;
let assetNumber = 0;
URL.createObjectURL = () => `blob:v7-label-geometry-${++assetNumber}`;
URL.revokeObjectURL = () => {};

const { createRoot } = await import('react-dom/client');
const { V7LabelGeometryCalibrationWorkspace } = await import(
  '../src/features/v7-label-geometry/v7-label-geometry-calibration-workspace.tsx'
);

after(() => {
  URL.createObjectURL = originalCreateObjectUrl;
  URL.revokeObjectURL = originalRevokeObjectUrl;
  dom.window.close();
});

const sessionId = '11111111-1111-4111-8111-111111111111';
const sourceA = {
  corpusCaseId: 'small_777',
  sourceChecksumSha256: 'a'.repeat(64),
  sourceId: 'source-a',
};
const sourceB = {
  corpusCaseId: 'occluded_777',
  sourceChecksumSha256: 'b'.repeat(64),
  sourceId: 'source-b',
};

function session(revision, captureGroups = {}) {
  return {
    captureGroups,
    geometryFamilyId: 'standard_3x3_numeric_labels_v1',
    manifestFingerprint: 'f'.repeat(64),
    revision,
    sessionId,
    slots: [],
    sources: [sourceA, sourceB],
    status: 'active',
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((nextResolve) => {
    resolve = nextResolve;
  });
  return { promise, resolve };
}

async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function eventually(predicate, label) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (predicate()) return;
    await settle();
  }
  assert.fail(label);
}

function image() {
  const current = document.querySelector(
    'img[alt="Kanoniczny obraz do kalibracji etykiety"]',
  );
  assert.ok(current);
  return current;
}

function button(text) {
  const current = [...document.querySelectorAll('button')].find((node) =>
    node.textContent.includes(text),
  );
  assert.ok(current);
  return current;
}

test('V7 workspace serializes durable clicks, rejects edge points, and preserves capture-group draft through a receipt', async () => {
  const assetA = deferred();
  const assetB = deferred();
  const firstAppend = deferred();
  const firstMutation = deferred();
  const secondMutation = deferred();
  const thirdMutation = deferred();
  const appended = [];
  const sent = [];
  const initialView = {
    activePositionIndex: 0,
    activeSourceId: sourceA.sourceId,
    cropAssessment: 'contained',
    manifestFingerprint: 'f'.repeat(64),
    queueStoppedReason: null,
    sessionId,
    updatedAt: '2026-09-21T00:00:00.000Z',
  };
  let appendCount = 0;
  const store = {
    appendOperation: async (operation) => {
      appended.push(operation);
      appendCount += 1;
      if (appendCount === 1) await firstAppend.promise;
    },
    discardPending: async () => {},
    load: async () => ({
      queue: { confirmedRevision: 0, pending: [], stoppedReason: null },
      view: initialView,
    }),
    loadMostRecent: async () => initialView,
    removeHead: async () => {},
    saveView: async () => {},
  };
  const client = {
    createV7LabelGeometryCalibrationSession: async () => {
      throw new Error('unexpected create');
    },
    createV7LabelGeometryProfile: async () => {
      throw new Error('unexpected profile');
    },
    exportV7LabelGeometryCalibrationSession: async () => {
      throw new Error('unexpected export');
    },
    getV7LabelGeometryCalibrationSession: async () => ({ data: session(0) }),
    getV7LabelGeometryCalibrationSourceAsset: async (_sessionId, sourceId) =>
      sourceId === sourceA.sourceId ? await assetA.promise : await assetB.promise,
    mutateV7LabelGeometryCalibrationSession: async (_sessionId, body) => {
      sent.push(body);
      if (sent.length === 1) return await firstMutation.promise;
      if (sent.length === 2) return await secondMutation.promise;
      return await thirdMutation.promise;
    },
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(V7LabelGeometryCalibrationWorkspace, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client,
        localStore: store,
      }),
    ),
  );

  await eventually(
    () => document.querySelector('select') !== null,
    'workspace should restore the session',
  );
  assetA.resolve({ data: new Blob(['a']) });
  await eventually(
    () => document.querySelector('img') !== null,
    'first canonical asset should render',
  );

  await act(async () =>
    image().dispatchEvent(
      new dom.window.MouseEvent('click', {
        bubbles: true,
        clientX: 0,
        clientY: 0,
      }),
    ),
  );
  assert.equal(appended.length, 0);

  const sourceSelect = document.querySelector('select');
  sourceSelect.value = sourceB.sourceId;
  await act(async () =>
    sourceSelect.dispatchEvent(new dom.window.Event('change', { bubbles: true })),
  );
  assert.equal(document.querySelector('img'), null);
  assetB.resolve({ data: new Blob(['b']) });
  await eventually(
    () => document.querySelector('img') !== null,
    'a delayed asset for the new source should replace the old one',
  );

  await act(async () =>
    image().dispatchEvent(
      new dom.window.MouseEvent('click', {
        bubbles: true,
        clientX: 40,
        clientY: 40,
      }),
    ),
  );
  await eventually(() => appended.length === 1, 'first click should enter IndexedDB');
  await act(async () =>
    image().dispatchEvent(
      new dom.window.MouseEvent('click', {
        bubbles: true,
        clientX: 80,
        clientY: 80,
      }),
    ),
  );
  firstAppend.resolve();
  await eventually(() => appended.length === 2, 'second click should wait for first append');
  assert.deepEqual(
    appended.map((operation) => [operation.expectedRevision, operation.sequence]),
    [
      [0, 0],
      [1, 1],
    ],
  );

  const captureInput = [...document.querySelectorAll('input')].find(
    (node) => node.placeholder === 'np. przejście-A',
  );
  captureInput.focus();
  Object.getOwnPropertyDescriptor(
    dom.window.HTMLInputElement.prototype,
    'value',
  ).set.call(captureInput, 'operator-draft');
  await act(async () =>
    captureInput.dispatchEvent(new dom.window.Event('input', { bubbles: true })),
  );
  firstMutation.resolve({
    data: { receipt: { revision: 1 }, session: session(1) },
  });
  await eventually(() => sent.length === 2, 'receipt should advance only the head');
  assert.equal(captureInput.value, 'operator-draft');
  assert.equal(document.activeElement, captureInput);
  await act(async () => captureInput.blur());
  await eventually(() => appended.length === 3, 'capture group should become a durable operation');
  assert.equal(appended[2].captureGroupId, 'operator-draft');

  secondMutation.resolve({
    data: { receipt: { revision: 2 }, session: session(2) },
  });
  await eventually(() => sent.length === 3, 'capture group should flush after prior click');
  thirdMutation.resolve({
    data: { receipt: { revision: 3 }, session: session(3) },
  });
  await settle();
  await act(async () => root.unmount());
});

test('discard blocks a delayed local deletion from racing with flush or a new annotation', async () => {
  const discardGate = deferred();
  const appended = [];
  let discarded = false;
  const initialView = {
    activePositionIndex: 0,
    activeSourceId: sourceA.sourceId,
    cropAssessment: 'contained',
    manifestFingerprint: 'f'.repeat(64),
    queueStoppedReason: 'Konflikt rewizji w drugiej zakładce.',
    sessionId,
    updatedAt: '2026-09-21T00:00:00.000Z',
  };
  const queuedOperation = {
    expectedRevision: 0,
    kind: 'unavailable',
    operationId: '00000000-0000-4000-8000-000000000099',
    positionIndex: 0,
    sequence: 0,
    sessionId,
    sourceId: sourceA.sourceId,
  };
  const store = {
    appendOperation: async (operation) => appended.push(operation),
    discardPending: async () => {
      await discardGate.promise;
      discarded = true;
    },
    load: async () => ({
      queue: discarded
        ? { confirmedRevision: 0, pending: [], stoppedReason: null }
        : {
            confirmedRevision: 0,
            pending: [queuedOperation],
            stoppedReason: 'Konflikt rewizji w drugiej zakładce.',
          },
      view: initialView,
    }),
    loadMostRecent: async () => initialView,
    removeHead: async () => {
      throw new Error('flush must not start while discarding');
    },
    saveView: async () => {},
  };
  const client = {
    createV7LabelGeometryCalibrationSession: async () => {
      throw new Error('unexpected create');
    },
    createV7LabelGeometryProfile: async () => {
      throw new Error('unexpected profile');
    },
    exportV7LabelGeometryCalibrationSession: async () => {
      throw new Error('unexpected export');
    },
    getV7LabelGeometryCalibrationSession: async () => ({ data: session(0) }),
    getV7LabelGeometryCalibrationSourceAsset: async () => ({
      data: new Blob(['a']),
    }),
    mutateV7LabelGeometryCalibrationSession: async () => {
      throw new Error('flush must not start while discarding');
    },
  };
  const previousConfirm = globalThis.confirm;
  Object.defineProperty(globalThis, 'confirm', {
    configurable: true,
    value: () => true,
  });
  const root = createRoot(document.getElementById('root'));
  try {
    await act(async () =>
      root.render(
        React.createElement(V7LabelGeometryCalibrationWorkspace, {
          apiBaseUrl: 'http://127.0.0.1:8000',
          client,
          localStore: store,
        }),
      ),
    );
    await eventually(() => document.querySelector('img') !== null, 'asset should render');
    await act(async () =>
      button('Porzuć niepotwierdzone').dispatchEvent(
        new dom.window.MouseEvent('click', { bubbles: true }),
      ),
    );
    await act(async () =>
      image().dispatchEvent(
        new dom.window.MouseEvent('click', {
          bubbles: true,
          clientX: 50,
          clientY: 50,
        }),
      ),
    );
    assert.equal(appended.length, 0);
    discardGate.resolve();
    await eventually(() => discarded, 'discard should finish its delayed local deletion');
    await settle();
  } finally {
    await act(async () => root.unmount());
    Object.defineProperty(globalThis, 'confirm', {
      configurable: true,
      value: previousConfirm,
    });
  }
});

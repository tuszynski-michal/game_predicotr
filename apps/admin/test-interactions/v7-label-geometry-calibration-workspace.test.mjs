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
  'HTMLSelectElement',
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
const createdAssetUrls = [];
const revokedAssetUrls = [];
URL.createObjectURL = () => {
  const url = `blob:v7-label-geometry-${++assetNumber}`;
  createdAssetUrls.push(url);
  return url;
};
URL.revokeObjectURL = (url) => {
  revokedAssetUrls.push(url);
};

const { createRoot } = await import('react-dom/client');
const { V7LabelGeometryCalibrationWorkspace } =
  await import('../src/features/v7-label-geometry/v7-label-geometry-calibration-workspace.tsx');

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

function sessionWithSources(sources, revision = 0) {
  return {
    ...session(revision),
    sources,
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

function sourceSelect() {
  const current = document.querySelector('select');
  assert.ok(current);
  return current;
}

function selectSource(sourceId) {
  const current = sourceSelect();
  Object.getOwnPropertyDescriptor(
    dom.window.HTMLSelectElement.prototype,
    'value',
  ).set.call(current, sourceId);
  return act(async () =>
    current.dispatchEvent(new dom.window.Event('change', { bubbles: true })),
  );
}

function button(text) {
  const current = [...document.querySelectorAll('button')].find((node) =>
    node.textContent.includes(text),
  );
  assert.ok(current);
  return current;
}

function positionButton(position) {
  const current = [...document.querySelectorAll('.v7LabelGeometrySlot')].find(
    (node) => node.querySelector('strong')?.textContent === String(position),
  );
  assert.ok(current);
  return current;
}

function assessmentSelect() {
  const current = document.querySelector('.v7LabelGeometryAssessment select');
  assert.ok(current);
  return current;
}

function activePosition() {
  return Number(
    document.querySelector('.v7LabelGeometrySlot[aria-pressed="true"] strong')
      ?.textContent,
  );
}

function unavailableCheckbox() {
  const current = document.querySelector('.v7LabelGeometryUnavailable input');
  assert.ok(current);
  return current;
}

function selectionFixture({ slots = [] } = {}) {
  const mutation = deferred();
  const pending = [];
  const sent = [];
  let savedView = {
    activePositionIndex: 0,
    activeSourceId: sourceA.sourceId,
    cropAssessment: 'contained',
    manifestFingerprint: 'f'.repeat(64),
    queueStoppedReason: null,
    sessionId,
    updatedAt: '2026-10-05T00:00:00.000Z',
  };
  const store = {
    appendOperation: async (operation) => pending.push(operation),
    discardPending: async () => pending.splice(0),
    load: async () => ({
      queue: {
        confirmedRevision: 0,
        pending: [...pending],
        stoppedReason: null,
      },
      view: savedView,
    }),
    loadMostRecent: async () => savedView,
    removeHead: async () => pending.shift(),
    saveView: async (next) => {
      savedView = next;
    },
  };
  const client = {
    getV7LabelGeometryCalibrationSession: async () => ({
      data: { ...session(0), slots },
    }),
    getV7LabelGeometryCalibrationSourceAsset: async () => ({
      data: new Blob(['canonical-test-asset']),
    }),
    mutateV7LabelGeometryCalibrationSession: async (_id, body) => {
      sent.push(body);
      return await mutation.promise;
    },
  };
  return { client, pending, sent, store };
}

async function renderSelectionFixture(fixture) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(V7LabelGeometryCalibrationWorkspace, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client: fixture.client,
        localStore: fixture.store,
      }),
    ),
  );
  await eventually(
    () => document.querySelector('img') !== null,
    'asset should render',
  );
  return root;
}

test('V2 profile control accepts occlusion and visibly omits a sparse photo without changing annotations', async () => {
  const fixture = selectionFixture();
  const sources = Array.from({ length: 11 }, (_, index) => ({
    ...sourceA,
    sourceId: index === 0 ? sourceA.sourceId : `coverage-${index}`,
    sourceChecksumSha256: (index + 10).toString(16).padStart(64, '0'),
    geometryFamilyId: 'standard_3x3_numeric_labels_v2',
  }));
  const confirmed = {
    ...sessionWithSources(sources, 118),
    geometryFamilyId: 'standard_3x3_numeric_labels_v2',
    captureGroups: Object.fromEntries(
      sources.map((item, index) => [item.sourceId, index < 4 ? 'A' : 'B']),
    ),
    slots: sources.slice(0, 10).flatMap((item, index) =>
      Array.from({ length: 9 }, (_, positionIndex) => ({
        centerX: index < 4 && positionIndex === 6 ? null : 0.2,
        centerY: index < 4 && positionIndex === 6 ? null : 0.3,
        cropAssessment: index < 4 && positionIndex === 6 ? null : 'contained',
        positionIndex,
        sourceId: item.sourceId,
        state: index < 4 && positionIndex === 6 ? 'unavailable' : 'annotated',
      })),
    ),
  };
  confirmed.slots.push({
    centerX: 0.6,
    centerY: 0.7,
    cropAssessment: 'contained',
    positionIndex: 8,
    sourceId: sources[10].sourceId,
    state: 'annotated',
  });
  const original = structuredClone(confirmed);
  const profileRequests = [];
  fixture.client.getV7LabelGeometryCalibrationSession = async () => ({
    data: confirmed,
  });
  fixture.client.createV7LabelGeometryProfile = async (id, request) => {
    profileRequests.push({ id, request });
    return {
      data: {
        profileFingerprint: 'e'.repeat(64),
        revision: 118,
        calibration: { status: 'passed' },
      },
    };
  };
  let root = await renderSelectionFixture(fixture);
  try {
    const readiness = document.querySelector(
      '[aria-label="Gotowość kalibracji profilu"]',
    );
    assert.match(readiness.textContent, /Grupy ujęć z pełną siatką: 2\/2/);
    assert.match(
      readiness.textContent,
      /Pominięte w profilu — niepełna siatka/,
    );
    assert.match(readiness.textContent, /Oznaczenia pozostają zapisane/);
    const seventh = [...readiness.querySelectorAll('strong')].find(
      (e) => e.textContent === 'Pozycja 7',
    ).parentElement;
    assert.match(seventh.textContent, /Zdjęcia: 6\/5/);
    assert.match(seventh.textContent, /Grupy: 1/);
    assert.doesNotMatch(seventh.textContent, /Grupy: 1\/2/);
    assert.match(seventh.textContent, /Gotowa do kontroli serwera/);
    assert.equal(button('Sprawdź i utwórz profil').disabled, false);
    await act(async () => button('Sprawdź i utwórz profil').click());
    assert.deepEqual(profileRequests, [
      { id: sessionId, request: { expectedRevision: 118 } },
    ]);
    assert.deepEqual(fixture.sent, []);
    assert.deepEqual(confirmed, original);
    await act(async () => root.unmount());
    root = await renderSelectionFixture(fixture);
    assert.equal(button('Sprawdź i utwórz profil').disabled, false);
    assert.deepEqual(confirmed, original);
  } finally {
    await act(async () => root.unmount());
  }
});

test('annotations automatically advance 1 through 9 after durable append without waiting for HTTP', async () => {
  const fixture = selectionFixture();
  let root = await renderSelectionFixture(fixture);
  try {
    for (let position = 1; position <= 9; position += 1) {
      assert.equal(activePosition(), position);
      await act(async () =>
        image().dispatchEvent(
          new dom.window.MouseEvent('click', {
            bubbles: true,
            clientX: 40,
            clientY: 40,
          }),
        ),
      );
      await eventually(
        () => fixture.pending.length === position,
        'point must be durable',
      );
      await eventually(
        () => activePosition() === Math.min(position + 1, 9),
        'selection must advance after append',
      );
    }
    assert.deepEqual(
      fixture.pending.map(({ positionIndex, expectedRevision }) => [
        positionIndex,
        expectedRevision,
      ]),
      Array.from({ length: 9 }, (_, index) => [index, index]),
    );
    assert.ok(
      fixture.pending.every(
        ({ sourceId, cropAssessment }) =>
          sourceId === sourceA.sourceId && cropAssessment === 'contained',
      ),
    );
    assert.equal(
      fixture.sent.length,
      1,
      'HTTP stays FIFO while nine positions are marked',
    );
    assert.equal(
      sourceSelect().value,
      sourceA.sourceId,
      'position 9 must not change the photo',
    );
    await act(async () => root.unmount());
    root = await renderSelectionFixture(fixture);
    assert.equal(activePosition(), 9);
    assert.equal(fixture.pending.length, 9);
    assert.ok(
      [...document.querySelectorAll('.v7LabelGeometryReadinessItem')].every(
        (node) => node.textContent.includes('Zdjęcia: 0/5'),
      ),
      'pending points still do not count towards readiness',
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('position shortcuts persist the selection without annotating and ignore editable controls and combinations', async () => {
  const fixture = selectionFixture();
  let root = await renderSelectionFixture(fixture);
  const workspace = () => document.querySelector('.v7LabelGeometryWorkspace');
  const key = (target, value, extra = {}) =>
    act(async () =>
      target.dispatchEvent(
        new dom.window.KeyboardEvent('keydown', {
          key: value,
          bubbles: true,
          cancelable: true,
          ...extra,
        }),
      ),
    );
  try {
    for (let position = 1; position <= 9; position += 1) {
      await key(workspace(), String(position));
      assert.equal(activePosition(), position);
    }
    await key(assessmentSelect(), '2');
    await key(sourceSelect(), '2');
    await key(unavailableCheckbox(), '2');
    for (const extra of [
      { ctrlKey: true },
      { altKey: true },
      { metaKey: true },
      { shiftKey: true },
      { repeat: true },
      { isComposing: true },
    ]) {
      await key(workspace(), '2', extra);
    }
    assert.equal(activePosition(), 9);
    await key(workspace(), '0');
    assert.equal(activePosition(), 9);
    await key(workspace(), '2');
    assert.equal(activePosition(), 2);
    assert.deepEqual(fixture.pending, []);
    assert.deepEqual(fixture.sent, []);
    await act(async () => root.unmount());
    root = await renderSelectionFixture(fixture);
    assert.equal(activePosition(), 2);
  } finally {
    await act(async () => root.unmount());
  }
});

test('a failed durable append does not advance or send an annotation', async () => {
  const fixture = selectionFixture();
  fixture.store.appendOperation = async () => {
    throw new Error('LOCAL_WRITE_FAILED');
  };
  const root = await renderSelectionFixture(fixture);
  try {
    await act(async () =>
      image().dispatchEvent(
        new dom.window.MouseEvent('click', {
          bubbles: true,
          clientX: 40,
          clientY: 40,
        }),
      ),
    );
    await eventually(
      () => document.body.textContent.includes('LOCAL_WRITE_FAILED'),
      'failure must be visible',
    );
    assert.equal(activePosition(), 1);
    assert.deepEqual(fixture.pending, []);
    assert.deepEqual(fixture.sent, []);
  } finally {
    await act(async () => root.unmount());
  }
});

test('a delayed append preserves a later manual position or source selection', async () => {
  for (const switchSource of [false, true]) {
    const fixture = selectionFixture();
    const gate = deferred();
    const append = fixture.store.appendOperation;
    fixture.store.appendOperation = async (operation) => {
      await gate.promise;
      return append(operation);
    };
    const root = await renderSelectionFixture(fixture);
    try {
      await act(async () =>
        image().dispatchEvent(
          new dom.window.MouseEvent('click', {
            bubbles: true,
            clientX: 40,
            clientY: 40,
          }),
        ),
      );
      assert.equal(
        activePosition(),
        1,
        'selection stays until the write is durable',
      );
      if (switchSource) {
        await selectSource(sourceB.sourceId);
      } else {
        await act(async () => positionButton(4).click());
      }
      gate.resolve();
      await eventually(
        () => fixture.pending.length === 1,
        'the original point must still be durable',
      );
      assert.equal(fixture.pending[0].sourceId, sourceA.sourceId);
      assert.equal(fixture.pending[0].positionIndex, 0);
      assert.equal(activePosition(), switchSource ? 1 : 4);
      assert.equal(
        sourceSelect().value,
        switchSource ? sourceB.sourceId : sourceA.sourceId,
      );
    } finally {
      await act(async () => root.unmount());
    }
  }
});

test('a direct session link opens a fresh session instead of another browser recent session', async () => {
  const freshId = '33333333-3333-4333-8333-333333333333';
  const fixture = selectionFixture();
  const loaded = [];
  const pendingReads = [];
  fixture.store.loadMostRecent = async () => {
    assert.fail('a direct session link must not resume the previous session');
  };
  fixture.store.load = async (id) => {
    pendingReads.push(id);
    return null;
  };
  fixture.client.getV7LabelGeometryCalibrationSession = async (id) => {
    loaded.push(id);
    return { data: { ...session(0), sessionId: freshId } };
  };
  dom.window.history.replaceState(
    null,
    '',
    `/?v7CalibrationSession=${freshId}`,
  );
  let root;
  try {
    root = await renderSelectionFixture(fixture);
    assert.deepEqual(loaded, [freshId]);
    assert.deepEqual(pendingReads, [freshId]);
    assert.match(document.body.textContent, /Sesja: 33333333/);
    assert.equal(document.querySelectorAll('.v7LabelGeometrySlot').length, 9);
    assert.ok(
      [...document.querySelectorAll('.v7LabelGeometrySlot')].every((node) =>
        node.textContent.includes('do oznaczenia'),
      ),
    );
    assert.deepEqual(fixture.pending, []);
    assert.deepEqual(fixture.sent, []);
    await act(async () => root.unmount());
    root = await renderSelectionFixture(fixture);
    assert.deepEqual(
      loaded,
      [freshId, freshId],
      'refresh keeps the requested session',
    );
    assert.deepEqual(pendingReads, [freshId, freshId]);
  } finally {
    if (root) await act(async () => root.unmount());
    dom.window.history.replaceState(null, '', '/');
  }
});

test('an invalid direct session link does not silently resume old annotations', async () => {
  const fixture = selectionFixture();
  fixture.store.loadMostRecent = async () =>
    assert.fail('old session must not load');
  dom.window.history.replaceState(null, '', '/?v7CalibrationSession=invalid');
  const root = createRoot(document.getElementById('root'));
  try {
    await act(async () =>
      root.render(
        React.createElement(V7LabelGeometryCalibrationWorkspace, {
          apiBaseUrl: 'http://127.0.0.1:8000',
          client: fixture.client,
          localStore: fixture.store,
        }),
      ),
    );
    assert.match(
      document.body.textContent,
      /nieprawidłowy identyfikator sesji/,
    );
    assert.equal(document.querySelectorAll('.v7LabelGeometrySlot').length, 0);
    assert.deepEqual(fixture.sent, []);
  } finally {
    await act(async () => root.unmount());
    dom.window.history.replaceState(null, '', '/');
  }
});

test('an uncertain assessment belongs to its source and position, including pending points', async () => {
  const fixture = selectionFixture();
  const root = await renderSelectionFixture(fixture);
  try {
    await act(async () => positionButton(8).click());
    const assessment = assessmentSelect();
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLSelectElement.prototype,
      'value',
    ).set.call(assessment, 'uncertain');
    await act(async () =>
      assessment.dispatchEvent(
        new dom.window.Event('change', { bubbles: true }),
      ),
    );
    await act(async () =>
      image().dispatchEvent(
        new dom.window.MouseEvent('click', {
          bubbles: true,
          clientX: 80,
          clientY: 80,
        }),
      ),
    );
    await eventually(
      () => fixture.pending.length === 1,
      'position 8 should be durable',
    );
    assert.equal(fixture.pending[0].positionIndex, 7);
    assert.equal(fixture.pending[0].cropAssessment, 'uncertain');

    await act(async () => positionButton(1).click());
    assert.equal(
      assessmentSelect().value,
      'contained',
      'position 1 must not inherit position 8',
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
    await eventually(
      () => fixture.pending.length === 2,
      'position 1 should be durable',
    );
    assert.equal(fixture.pending[1].positionIndex, 0);
    assert.equal(fixture.pending[1].cropAssessment, 'contained');

    await act(async () => positionButton(8).click());
    assert.equal(
      assessmentSelect().value,
      'uncertain',
      'returning restores the actual pending assessment',
    );
    await selectSource(sourceB.sourceId);
    assert.equal(
      assessmentSelect().value,
      'contained',
      'another source must not inherit an assessment',
    );
    await selectSource(sourceA.sourceId);
    assert.equal(assessmentSelect().value, 'uncertain');
  } finally {
    await act(async () => root.unmount());
  }
});

test('positions 8 and 9 can be marked unavailable during a delayed receipt and survive refresh', async () => {
  const fixture = selectionFixture();
  let root = await renderSelectionFixture(fixture);
  try {
    await act(async () => positionButton(8).click());
    await act(async () => unavailableCheckbox().click());
    await eventually(
      () => fixture.sent.length === 1,
      'the first unavailable operation should start HTTP',
    );
    assert.equal(activePosition(), 9, 'unavailable position 8 advances to 9');
    assert.equal(
      unavailableCheckbox().disabled,
      false,
      'HTTP must not block the next local action',
    );

    await act(async () => positionButton(9).click());
    await act(async () => unavailableCheckbox().click());
    await eventually(
      () => fixture.pending.length === 2,
      'both unavailable operations should be durable',
    );
    assert.equal(activePosition(), 9, 'position 9 stays on the same photo');
    assert.deepEqual(
      fixture.pending.map(({ kind, positionIndex, expectedRevision }) => [
        kind,
        positionIndex,
        expectedRevision,
      ]),
      [
        ['unavailable', 7, 0],
        ['unavailable', 8, 1],
      ],
    );
    assert.equal(
      fixture.sent.length,
      1,
      'HTTP remains sequential while local actions continue',
    );
    const operationIds = fixture.pending.map(({ operationId }) => operationId);
    await act(async () => root.unmount());
    root = await renderSelectionFixture(fixture);
    assert.deepEqual(
      fixture.pending.map(({ operationId }) => operationId),
      operationIds,
    );
    await eventually(
      () => fixture.sent.length === 2,
      'refresh should replay the same head',
    );
    assert.equal(fixture.sent[1].operationId, operationIds[0]);
    assert.match(positionButton(8).textContent, /niewidoczny/);
    assert.match(positionButton(9).textContent, /niewidoczny/);
    assert.doesNotMatch(positionButton(1).textContent, /niewidoczny/);
    assert.doesNotMatch(positionButton(2).textContent, /niewidoczny/);
    assert.ok(
      [...document.querySelectorAll('.v7LabelGeometryReadinessItem')].every(
        (item) => !item.textContent.includes('Niewidoczne:'),
      ),
      'pending unavailable operations never count as server confirmations',
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('selecting an existing label restores its confirmed assessment without changing annotations', async () => {
  const confirmedSlot = {
    centerX: 0.4,
    centerY: 0.4,
    cropAssessment: 'clipped',
    positionIndex: 0,
    sourceId: sourceB.sourceId,
    state: 'annotated',
  };
  const fixture = selectionFixture({ slots: [confirmedSlot] });
  const root = await renderSelectionFixture(fixture);
  try {
    await selectSource(sourceB.sourceId);
    assert.equal(assessmentSelect().value, 'clipped');
    await act(async () => positionButton(2).click());
    assert.equal(assessmentSelect().value, 'contained');
    await act(async () => positionButton(1).click());
    assert.equal(assessmentSelect().value, 'clipped');
    assert.deepEqual(fixture.pending, []);
    assert.equal(confirmedSlot.cropAssessment, 'clipped');
  } finally {
    await act(async () => root.unmount());
  }
});

test('V7 workspace shows durable pending markers before a delayed receipt and keeps fast clicks ordered', async () => {
  const assetA = deferred();
  const assetB = deferred();
  const firstAppend = deferred();
  const firstMutation = deferred();
  const secondMutation = deferred();
  const thirdMutation = deferred();
  const appended = [];
  const sent = [];
  const assetRequests = [];
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
    getV7LabelGeometryCalibrationSourceAsset: async (_sessionId, sourceId) => {
      assetRequests.push(sourceId);
      return sourceId === sourceA.sourceId
        ? await assetA.promise
        : await assetB.promise;
    },
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
  assert.ok(
    document.querySelector('[aria-label="Gotowość kalibracji profilu"]'),
  );
  assert.equal(button('Sprawdź i utwórz profil').disabled, true);
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

  await selectSource(sourceB.sourceId);
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
  await eventually(
    () => appended.length === 1,
    'first click should enter IndexedDB',
  );
  await act(async () =>
    button('2').dispatchEvent(
      new dom.window.MouseEvent('click', { bubbles: true }),
    ),
  );
  await eventually(
    () => button('2').getAttribute('aria-pressed') === 'true',
    'the next fast click should select a different label position',
  );
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
  await eventually(
    () => appended.length === 2,
    'second click should wait for first append',
  );
  assert.deepEqual(
    appended.map((operation) => [
      operation.expectedRevision,
      operation.sequence,
    ]),
    [
      [0, 0],
      [1, 1],
    ],
  );
  await eventually(
    () => document.querySelectorAll('.v7LabelGeometryPoint').length === 2,
    'two durable clicks should be visible before the first HTTP receipt',
  );
  assert.equal(sent.length, 1);

  const captureSelect = [...document.querySelectorAll('select')][1];
  assert.ok(captureSelect);
  Object.getOwnPropertyDescriptor(
    dom.window.HTMLSelectElement.prototype,
    'value',
  ).set.call(captureSelect, 'B');
  await act(async () =>
    captureSelect.dispatchEvent(
      new dom.window.Event('change', { bubbles: true }),
    ),
  );
  await eventually(
    () => appended.length === 3,
    'capture group should become durable',
  );
  assert.equal(captureSelect.value, 'B');
  assert.equal(appended[2].captureGroupId, 'B');
  firstMutation.resolve({
    data: { receipt: { revision: 1 }, session: session(1) },
  });
  await eventually(
    () => sent.length === 2,
    'receipt should advance only the head',
  );

  secondMutation.resolve({
    data: { receipt: { revision: 2 }, session: session(2) },
  });
  await eventually(
    () => sent.length === 3,
    'capture group should flush after prior click',
  );
  thirdMutation.resolve({
    data: { receipt: { revision: 3 }, session: session(3) },
  });
  await settle();
  assert.equal(
    assetRequests.filter((sourceId) => sourceId === sourceB.sourceId).length,
    1,
    'the neighbour prefetch is reused when that source becomes active',
  );
  await act(async () => root.unmount());
});

test('V7 workspace ignores delayed asset responses after unmount', async () => {
  const assetA = deferred();
  const assetB = deferred();
  const initialView = {
    activePositionIndex: 0,
    activeSourceId: sourceA.sourceId,
    cropAssessment: 'contained',
    manifestFingerprint: 'f'.repeat(64),
    queueStoppedReason: null,
    sessionId,
    updatedAt: '2026-09-21T00:00:00.000Z',
  };
  const store = {
    appendOperation: async () => {},
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
      sourceId === sourceA.sourceId
        ? await assetA.promise
        : await assetB.promise,
    mutateV7LabelGeometryCalibrationSession: async () => {
      throw new Error('unexpected mutation');
    },
  };
  const createdBefore = createdAssetUrls.length;
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
    () => sourceSelect() !== null,
    'workspace should restore the session',
  );
  await act(async () => root.unmount());
  assetA.resolve({ data: new Blob(['a']) });
  assetB.resolve({ data: new Blob(['b']) });
  await settle();
  assert.equal(
    createdAssetUrls.length,
    createdBefore,
    'a late response must not create an object URL after workspace cleanup',
  );
});

test('V7 workspace does not repeatedly fetch a source after a stable asset error', async () => {
  const assetRequests = [];
  const initialView = {
    activePositionIndex: 0,
    activeSourceId: sourceA.sourceId,
    cropAssessment: 'contained',
    manifestFingerprint: 'f'.repeat(64),
    queueStoppedReason: null,
    sessionId,
    updatedAt: '2026-09-21T00:00:00.000Z',
  };
  const store = {
    appendOperation: async () => {},
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
    getV7LabelGeometryCalibrationSourceAsset: async (_sessionId, sourceId) => {
      assetRequests.push(sourceId);
      return { error: { code: 'V7_SOURCE_DRIFT' } };
    },
    mutateV7LabelGeometryCalibrationSession: async () => {
      throw new Error('unexpected mutation');
    },
  };
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
    await eventually(
      () => assetRequests.length === 2,
      'both initial requests should run once',
    );
    await settle();
    await settle();
    assert.deepEqual(assetRequests, [sourceA.sourceId, sourceB.sourceId]);
    assert.notEqual(
      document.querySelector('.v7LabelGeometryImageFrame p')?.textContent,
      'Wczytuję kanoniczny PNG…',
      'the stable asset error should remain visible until the source changes',
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('V7 workspace keeps an oversized uncached active asset after scheduler updates', async () => {
  const neighbour = deferred();
  const initialView = {
    activePositionIndex: 0,
    activeSourceId: sourceA.sourceId,
    cropAssessment: 'contained',
    manifestFingerprint: 'f'.repeat(64),
    queueStoppedReason: null,
    sessionId,
    updatedAt: '2026-09-21T00:00:00.000Z',
  };
  const oversized = new Blob(['canonical source']);
  Object.defineProperty(oversized, 'size', { value: 64 * 1024 * 1024 + 1 });
  const store = {
    appendOperation: async () => {},
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
      sourceId === sourceA.sourceId
        ? { data: oversized }
        : await neighbour.promise,
    mutateV7LabelGeometryCalibrationSession: async () => {
      throw new Error('unexpected mutation');
    },
  };
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
    await eventually(
      () => document.querySelector('img') !== null,
      'oversized asset should render',
    );
    const activeUrl = image().getAttribute('src');
    await settle();
    await settle();
    assert.equal(image().getAttribute('src'), activeUrl);
  } finally {
    neighbour.resolve({ data: new Blob(['b']) });
    await act(async () => root.unmount());
  }
});

test('V7 workspace keeps the active asset while delayed neighbours fill the cache', async () => {
  const sources = ['a', 'b', 'c', 'd', 'e'].map((letter) => ({
    corpusCaseId: 'small_777',
    sourceChecksumSha256: letter.repeat(64),
    sourceId: `source-${letter}`,
  }));
  const [sourceOne, sourceTwo, sourceThree, sourceFour, sourceFive] = sources;
  const assets = new Map(
    sources.map((source) => [source.sourceId, deferred()]),
  );
  const initialView = {
    activePositionIndex: 0,
    activeSourceId: sourceOne.sourceId,
    cropAssessment: 'contained',
    manifestFingerprint: 'f'.repeat(64),
    queueStoppedReason: null,
    sessionId,
    updatedAt: '2026-09-21T00:00:00.000Z',
  };
  const store = {
    appendOperation: async () => {},
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
    getV7LabelGeometryCalibrationSession: async () => ({
      data: sessionWithSources(sources),
    }),
    getV7LabelGeometryCalibrationSourceAsset: async (_sessionId, sourceId) =>
      await assets.get(sourceId).promise,
    mutateV7LabelGeometryCalibrationSession: async () => {
      throw new Error('unexpected mutation');
    },
  };
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
    await eventually(
      () => sourceSelect() !== null,
      'workspace should restore the session',
    );
    await settle();
    assets.get(sourceOne.sourceId).resolve({ data: new Blob(['a']) });
    await eventually(
      () => document.querySelector('img') !== null,
      'first asset should render',
    );
    await selectSource(sourceThree.sourceId);
    const createdBeforeThird = createdAssetUrls.length;
    assets.get(sourceThree.sourceId).resolve({ data: new Blob(['c']) });
    await eventually(
      () => createdAssetUrls.length === createdBeforeThird + 1,
      'third source should create its cached asset',
    );
    const thirdUrl = createdAssetUrls.at(-1);
    await eventually(
      () => image().getAttribute('src') === thirdUrl,
      'third source should become active',
    );
    await selectSource(sourceFive.sourceId);
    const createdBeforeFifth = createdAssetUrls.length;
    assets.get(sourceFive.sourceId).resolve({ data: new Blob(['e']) });
    await eventually(
      () => createdAssetUrls.length === createdBeforeFifth + 1,
      'fifth source should create its cached asset',
    );
    const fifthUrl = createdAssetUrls.at(-1);
    await eventually(
      () => image().getAttribute('src') === fifthUrl,
      'fifth source should become active',
    );
    const activeUrl = image().getAttribute('src');
    assets.get(sourceFour.sourceId).resolve({ data: new Blob(['d']) });
    await settle();
    assert.equal(image().getAttribute('src'), activeUrl);
    assert.equal(
      revokedAssetUrls.includes(activeUrl),
      false,
      'a delayed neighbour must not revoke the currently displayed object URL',
    );
  } finally {
    assets.get(sourceTwo.sourceId).resolve({ data: new Blob(['b']) });
    await act(async () => root.unmount());
  }
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
    await eventually(
      () => document.querySelector('img') !== null,
      'asset should render',
    );
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
    await eventually(
      () => discarded,
      'discard should finish its delayed local deletion',
    );
    await settle();
  } finally {
    await act(async () => root.unmount());
    Object.defineProperty(globalThis, 'confirm', {
      configurable: true,
      value: previousConfirm,
    });
  }
});

test('starting a new session forgets only the local view of a drift-blocked V1 session and clears its direct link', async () => {
  const forgotten = [];
  const created = [];
  const initialView = {
    activePositionIndex: 0,
    activeSourceId: sourceA.sourceId,
    cropAssessment: 'contained',
    manifestFingerprint: 'f'.repeat(64),
    queueStoppedReason: null,
    sessionId,
    updatedAt: '2026-09-21T00:00:00.000Z',
  };
  const newSessionId = '22222222-2222-4222-8222-222222222222';
  const store = {
    appendOperation: async () => {},
    discardPending: async () => {},
    forgetSession: async (id) => forgotten.push(id),
    load: async () => ({
      queue: { confirmedRevision: 0, pending: [], stoppedReason: null },
      view: initialView,
    }),
    loadMostRecent: async () => initialView,
    removeHead: async () => {},
    saveView: async () => {},
  };
  const client = {
    createV7LabelGeometryCalibrationSession: async (body) => {
      created.push(body);
      return {
        data: {
          ...session(0),
          geometryFamilyId: 'standard_3x3_numeric_labels_v2',
          sessionId: newSessionId,
        },
      };
    },
    createV7LabelGeometryProfile: async () => {
      throw new Error('unexpected profile');
    },
    exportV7LabelGeometryCalibrationSession: async () => {
      throw new Error('unexpected export');
    },
    getV7LabelGeometryCalibrationSession: async () => ({
      data: { ...session(106), status: 'blocked_source_drift' },
    }),
    getV7LabelGeometryCalibrationSourceAsset: async () => ({
      data: new Blob(['a']),
    }),
    mutateV7LabelGeometryCalibrationSession: async () => {
      throw new Error('unexpected mutation');
    },
  };
  const previousConfirm = globalThis.confirm;
  Object.defineProperty(globalThis, 'confirm', {
    configurable: true,
    value: () => true,
  });
  const root = createRoot(document.getElementById('root'));
  dom.window.history.replaceState(
    null,
    '',
    `/?v7CalibrationSession=${sessionId}`,
  );
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
    await eventually(
      () => document.body.textContent.includes('Rewizja 106 · tryb V1'),
      'the blocked V1 session should be restored',
    );
    await act(async () =>
      button('Zacznij nową sesję').dispatchEvent(
        new dom.window.MouseEvent('click', { bubbles: true }),
      ),
    );
    await eventually(
      () => document.body.textContent.includes('Utwórz sesję kalibracji'),
      'the setup screen should replace the forgotten session',
    );
    assert.deepEqual(forgotten, [sessionId]);
    assert.equal(
      new URL(dom.window.location.href).searchParams.has(
        'v7CalibrationSession',
      ),
      false,
    );
    const checkboxes = [...document.querySelectorAll('input[type="checkbox"]')];
    assert.deepEqual(
      checkboxes.map((node) => node.checked),
      [true, true],
    );
    await act(async () =>
      button('Utwórz sesję kalibracji').dispatchEvent(
        new dom.window.MouseEvent('click', { bubbles: true }),
      ),
    );
    await eventually(
      () => document.body.textContent.includes('Rewizja 0 · tryb V2'),
      'the new V2 session should open',
    );
    assert.deepEqual(created, [
      {
        corpusCaseIds: ['small_777', 'occluded_777'],
        geometryFamilyId: 'standard_3x3_numeric_labels_v2',
      },
    ]);
  } finally {
    await act(async () => root.unmount());
    dom.window.history.replaceState(null, '', '/');
    Object.defineProperty(globalThis, 'confirm', {
      configurable: true,
      value: previousConfirm,
    });
  }
});

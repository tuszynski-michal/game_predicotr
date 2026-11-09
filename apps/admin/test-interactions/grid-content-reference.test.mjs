import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import test from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';
import { contentCommandKey } from '../src/features/model-quality/grid-content-state.ts';

const bootstrap = new JSDOM('<div></div>');
globalThis.window = bootstrap.window;
globalThis.document = bootstrap.window.document;
const { createRoot } = await import('react-dom/client');
delete globalThis.window;
delete globalThis.document;
bootstrap.window.close();
registerHooks({
  load(url, context, next) {
    if (url.endsWith('/src/api/admin-api-client.ts'))
      return {
        format: 'module',
        shortCircuit: true,
        source:
          'export function createConfiguredAdminApiClient(){return globalThis.contentApiFixture;}',
      };
    return next(url, context);
  },
});
const { GridContentReferenceWorkspace } =
  await import('../src/features/model-quality/grid-content-reference-workspace.tsx');
const { GridContentBlind } =
  await import('../src/features/model-quality/grid-content-blind.tsx');
const { GridContentCanvas } =
  await import('../src/features/model-quality/grid-content-canvas.tsx');
const { GridModelWorkspace } =
  await import('../src/features/model-quality/grid-model-workspace.tsx');
const { GridContentReadiness } =
  await import('../src/features/model-quality/grid-content-readiness.tsx');
const game = '11111111-1111-4111-8111-111111111111',
  session = '22222222-2222-4222-8222-222222222222',
  source = '33333333-3333-4333-8333-333333333333',
  cohort = '44444444-4444-4444-8444-444444444444';
const apiBaseUrl = 'http://127.0.0.1:8000',
  sha = 'a'.repeat(64);
const target = {
  source: {
    sourceId: source,
    sourceSha256: sha,
    sourceRepresentativeSha256: 'b'.repeat(64),
    width: 200,
    height: 120,
  },
  positionIndex: 0,
  sequenceNumber: 42,
  role: 'REGRESSION',
  state: 'ready',
  reasonCodes: [],
  displayName: 'Zdjęcie 42',
};
const header = {
  id: cohort,
  gameId: game,
  status: 'frozen',
  mode: 'screen+grid',
  revision: 2,
  manifestSha256: sha,
  createdAt: '2026-11-08T12:00:00Z',
  summary: { roles: [{ materializedPhotos: 10 }] },
};
const status = (phase = 'pass1', revision = 1, completed = 0) => ({
  sessionId: session,
  gameId: game,
  phase,
  revision,
  completed,
  total: 1,
  report: null,
});
function fixture() {
  const calls = [];
  let ref = { annotation: null, revision: 0, contentReferenceSha256: null };
  let current = status();
  let failObservation = false;
  let heldRead = null;
  const api = {
    listGridTrainingCohorts: async () => ({
      data: { items: [header], nextCursor: null },
    }),
    listGridContentTargets: async () => ({
      data: {
        version: 'source-cell-content-targets-v1',
        gameId: game,
        cohortId: cohort,
        manifestSha256: sha,
        items: [target],
        nextOffset: null,
      },
    }),
    gridContentTargetSourceUrl: () => '/ordinary-source',
    getGridCellContentReference: async (...args) => {
      calls.push(['normal-get', ...args]);
      return { data: structuredClone(ref) };
    },
    writeGridCellContentReference: async (_game, body) => {
      calls.push(['reference', structuredClone(body)]);
      ref = {
        revision: ref.revision + 1,
        annotation: {
          source: target.source,
          sequenceNumber: 42,
          origin: 'manual',
          reference: {
            positionIndex: 0,
            cells: body.cells,
            humanApproved: body.humanApproval,
          },
        },
        contentReferenceSha256: sha,
      };
      return { data: { ...ref, idempotencyKey: body.idempotencyKey } };
    },
    listGridContentSessions: async () => ({ data: { items: [current] } }),
    getGridContentSession: async () => {
      calls.push(['session-get']);
      if (heldRead) return heldRead;
      return {
        data: {
          ...current,
          targets: [
            {
              source: target.source,
              positionIndex: 0,
              sequenceNumber: 42,
              completed: current.completed === 1,
            },
          ],
        },
      };
    },
    gridContentSessionSourceUrl: () => '/blind-source',
    writeGridBlindContentObservation: async (_game, id, body) => {
      calls.push(['observe', id, structuredClone(body)]);
      if (failObservation) throw new Error('Utracono odpowiedź');
      current = status(
        body.passNumber === 1 ? 'pass1' : 'pass2',
        current.revision + 1,
        1,
      );
      return {
        data: { idempotencyKey: body.idempotencyKey, session: current },
      };
    },
    advanceGridContentSession: async (_game, _id, body) => {
      calls.push(['advance', structuredClone(body)]);
      current = status('pass2', current.revision + 1, 0);
      return {
        data: { idempotencyKey: body.idempotencyKey, session: current },
      };
    },
    createGridContentSession: async (_game, body) => {
      calls.push(['create', structuredClone(body)]);
      return {
        data: { idempotencyKey: body.idempotencyKey, session: current },
      };
    },
  };
  return {
    api,
    calls,
    fail: (value) => {
      failObservation = value;
    },
    hold: (promise) => {
      heldRead = promise;
    },
  };
}
async function mount(Component, props, saved = {}) {
  const dom = new JSDOM('<div id="root"></div>', { url: apiBaseUrl });
  const previous = {};
  for (const [key, value] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    navigator: dom.window.navigator,
    localStorage: dom.window.localStorage,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    previous[key] = Object.getOwnPropertyDescriptor(globalThis, key);
    Object.defineProperty(globalThis, key, {
      configurable: true,
      writable: true,
      value,
    });
  }
  for (const [key, value] of Object.entries(saved))
    localStorage.setItem(key, value);
  const root = createRoot(document.getElementById('root'));
  async function render(extra = {}) {
    await act(async () =>
      root.render(React.createElement(Component, { ...props, ...extra })),
    );
  }
  await render();
  return {
    render,
    cleanup: async () => {
      await act(async () => root.unmount());
      dom.window.close();
      for (const [key, desc] of Object.entries(previous)) {
        if (desc) Object.defineProperty(globalThis, key, desc);
        else delete globalThis[key];
      }
    },
  };
}
const find = (text) =>
  [...document.querySelectorAll('button')].find((b) => b.textContent === text);
async function click(text) {
  const b = find(text);
  assert.ok(b, text);
  assert.equal(b.disabled, false, text);
  await act(async () => b.click());
}
async function change(label, value) {
  const el = document.querySelector(`[aria-label="${label}"]`);
  assert.ok(el, label);
  await act(async () => {
    const proto =
      el.tagName === 'SELECT'
        ? window.HTMLSelectElement.prototype
        : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
    el.dispatchEvent(new window.Event('change', { bubbles: true }));
    el.dispatchEvent(new window.Event('input', { bubbles: true }));
  });
}
async function checkContaining(text) {
  const label = [...document.querySelectorAll('label')].find((l) =>
    l.textContent.includes(text),
  );
  assert.ok(label, text);
  await act(async () => label.querySelector('input[type="checkbox"]').click());
}
async function imageLoaded() {
  const img = document.querySelector('.gridContentImage img');
  assert.ok(img);
  Object.defineProperty(img, 'naturalWidth', {
    value: 200,
    configurable: true,
  });
  Object.defineProperty(img, 'naturalHeight', {
    value: 120,
    configurable: true,
  });
  await act(async () =>
    img.dispatchEvent(new window.Event('load', { bubbles: true })),
  );
}
async function point(x, y) {
  const svg = document.querySelector('.gridContentImage svg');
  svg.getBoundingClientRect = () => ({
    left: 0,
    top: 0,
    width: 200,
    height: 120,
  });
  await act(async () =>
    svg.dispatchEvent(
      new window.MouseEvent('pointerdown', {
        bubbles: true,
        button: 0,
        clientX: x,
        clientY: y,
      }),
    ),
  );
}
async function annotateBlind() {
  await imageLoaded();
  for (const p of [
    [5, 5],
    [195, 5],
    [195, 115],
    [5, 115],
  ])
    await point(...p);
  await click('Edytuj zawartość 15 pól');
  for (const p of [
    [10, 10],
    [30, 10],
    [30, 30],
    [10, 30],
  ])
    await point(...p);
  await change('Widoczność pola', 'visible');
  await checkContaining('Potwierdzam własny pomiar');
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
const targetPage = (items = [target], id = game, cohortId = cohort) => ({
  data: {
    version: 'source-cell-content-targets-v1',
    gameId: id,
    cohortId,
    manifestSha256: sha,
    items,
    nextOffset: null,
  },
});
const sessionDetail = (
  phase = 'pass1',
  revision = 1,
  targets = [
    {
      source: target.source,
      positionIndex: 0,
      sequenceNumber: 42,
      completed: false,
    },
  ],
) => ({ data: { ...status(phase, revision), total: targets.length, targets } });
function referenceResult(forTarget = target, revision = 2) {
  return {
    data: {
      revision,
      contentReferenceSha256: sha,
      annotation: {
        source: forTarget.source,
        sequenceNumber: forTarget.sequenceNumber,
        origin: 'manual',
        reference: {
          positionIndex: forTarget.positionIndex,
          humanApproved: true,
          cells: Array.from({ length: 15 }, (_, i) =>
            i === 0
              ? {
                  state: 'visible',
                  quad: [
                    [55, 55],
                    [65, 55],
                    [65, 65],
                    [55, 65],
                  ],
                }
              : { state: 'unknown' },
          ),
        },
      },
    },
  };
}
async function resolveRead(read, value) {
  await act(async () => read.resolve(value));
}

test('ordinary B/REG is mounted, reads and approves content with CAS without geometry writes', async () => {
  const f = fixture();
  const m = await mount(GridContentReferenceWorkspace, {
    apiBaseUrl,
    gameId: game,
    mode: 'ordinary',
    client: f.api,
    onClose() {},
  });
  try {
    assert.equal(f.calls.length, 0);
    await change('Zamrożony zestaw etykiet', cohort);
    await click('Oznacz Zdjęcie 42 — pozycja 1');
    assert.equal(f.calls.filter((c) => c[0] === 'normal-get').length, 1);
    await imageLoaded();
    for (const p of [
      [10, 10],
      [30, 10],
      [30, 30],
      [10, 30],
    ])
      await point(...p);
    await change('Widoczność pola', 'visible');
    assert.equal(find('Zapisz i zatwierdź etykiety zawartości').disabled, true);
    await checkContaining('Sprawdziłem zawartość');
    await click('Zapisz i zatwierdź etykiety zawartości');
    const body = f.calls.find((c) => c[0] === 'reference')[1];
    assert.equal(body.sourceId, source);
    assert.equal(body.expectedRevision, 0);
    assert.equal(body.sequenceNumber, 42);
    assert.equal(body.humanApproval, true);
    assert.equal(body.origin, 'manual');
    assert.equal(body.cells.length, 15);
    assert.equal(body.cells[0].quad.length, 4);
    assert.equal('measuredNodes' in body, false);
    assert.equal(f.calls.filter((c) => c[0] === 'normal-get').length, 2);
    assert.match(document.body.textContent, /Rewizja zawartości: 1/);
  } finally {
    await m.cleanup();
  }
});

test('blind saves 24 manual nodes and independent content; advance empties pass2 without normal reads or local drafts', async () => {
  const f = fixture();
  const m = await mount(
    GridContentBlind,
    { api: f.api, apiBaseUrl, gameId: game, initialSessionId: session },
    { 'ordinary-board-draft': JSON.stringify({ nodes: 'PRIVATE-OLD-LABELS' }) },
  );
  try {
    assert.equal(document.querySelectorAll('.gridContentHandle').length, 0);
    assert.doesNotMatch(document.body.textContent, /PRIVATE-OLD-LABELS/);
    await annotateBlind();
    await change('Powiększenie podglądu', '4');
    await click('Przesuwaj podgląd');
    await click('Zapisz ślepy pomiar i dalej');
    const body = f.calls.find((c) => c[0] === 'observe')[2];
    assert.equal(body.measuredNodes.length, 24);
    assert.deepEqual(body.cells[0].quad[0], [10, 10]);
    assert.equal(body.humanApproval, true);
    assert.equal(body.passNumber, 1);
    await click('Zamknij przebieg 1 i rozpocznij pusty przebieg 2');
    assert.match(document.body.textContent, /Przebieg 2/);
    assert.equal(document.querySelectorAll('.gridContentHandle').length, 0);
    assert.equal(document.querySelectorAll('.gridContentQuad').length, 0);
    assert.equal(
      document.querySelector('[aria-label="Widoczność pola"]'),
      null,
    );
    assert.equal(
      find('Edytuj 24 punkty geometrii').getAttribute('aria-pressed'),
      'true',
    );
    assert.equal(find('Edytuj 24 punkty geometrii').className, 'primaryButton');
    assert.equal(
      document.querySelector('[aria-label="Powiększenie podglądu"]').value,
      '1',
    );
    assert.ok(find('Przesuwaj podgląd'));
    assert.equal(
      f.calls.some((c) => c[0] === 'normal-get'),
      false,
    );
  } finally {
    await m.cleanup();
  }
});

test('lost response replays exact UUID/body after reload but never hydrates pending points into canvas', async () => {
  const f = fixture();
  f.fail(true);
  let m = await mount(GridContentBlind, {
    api: f.api,
    apiBaseUrl,
    gameId: game,
    initialSessionId: session,
  });
  let raw, first;
  try {
    await annotateBlind();
    await click('Zapisz ślepy pomiar i dalej');
    first = structuredClone(f.calls.find((c) => c[0] === 'observe')[2]);
    raw = localStorage.getItem(contentCommandKey(apiBaseUrl, game, 'blind'));
    assert.ok(raw);
    assert.match(document.body.textContent, /Utracono odpowiedź/);
  } finally {
    await m.cleanup();
  }
  f.fail(false);
  m = await mount(
    GridContentBlind,
    { api: f.api, apiBaseUrl, gameId: game, initialSessionId: session },
    { [contentCommandKey(apiBaseUrl, game, 'blind')]: raw },
  );
  try {
    assert.equal(document.querySelectorAll('.gridContentHandle').length, 0);
    assert.equal(document.querySelectorAll('.gridContentQuad').length, 0);
    assert.equal(
      document.querySelector('[aria-label="Widoczność pola"]'),
      null,
    );
    await click('Ponów dokładnie zapisane polecenie');
    assert.deepEqual(
      f.calls.filter((c) => c[0] === 'observe').at(-1)[2],
      first,
    );
    assert.equal(
      localStorage.getItem(contentCommandKey(apiBaseUrl, game, 'blind')),
      null,
    );
  } finally {
    await m.cleanup();
  }
});

test('canvas rejects wrong source dimensions and does not move independent content with a lattice edit', async () => {
  const changes = [];
  const m = await mount(GridContentCanvas, {
    sourceUrl: '/source',
    width: 200,
    height: 120,
    measureGeometry: true,
    onChange: (...args) => changes.push(structuredClone(args)),
  });
  try {
    await imageLoaded();
    for (const p of [
      [5, 5],
      [195, 5],
      [195, 115],
      [5, 115],
    ])
      await point(...p);
    await click('Edytuj zawartość 15 pól');
    for (const p of [
      [10, 10],
      [30, 10],
      [30, 30],
      [10, 30],
    ])
      await point(...p);
    const quad = structuredClone(changes.at(-1)[0][0].quad);
    await click('Edytuj 24 punkty geometrii');
    await change('Węzeł X', '8.125');
    assert.deepEqual(changes.at(-1)[0][0].quad, quad);
    assert.equal(changes.at(-1)[1][0][0], 8.125);
    const img = document.querySelector('img');
    Object.defineProperty(img, 'naturalWidth', {
      value: 201,
      configurable: true,
    });
    await act(async () =>
      img.dispatchEvent(new window.Event('load', { bubbles: true })),
    );
    assert.equal(changes.at(-1)[2], false);
    assert.match(document.body.textContent, /Wymiary obrazu/);
  } finally {
    await m.cleanup();
  }
});

test('mounted main workspace hides ordinary tools in blind mode and changes game without keeping its canvas', async () => {
  const f = fixture();
  globalThis.contentApiFixture = new Proxy(f.api, {
    get(object, name) {
      return name in object ? object[name] : async () => ({ error: {} });
    },
  });
  const m = await mount(GridModelWorkspace, { apiBaseUrl, gameId: game });
  try {
    assert.ok(find('Propozycje siatek do ręcznej oceny'));
    await click('Pomiar powtarzalności etykiet');
    assert.equal(find('Propozycje siatek do ręcznej oceny'), undefined);
    assert.equal(
      document.querySelector('[aria-label="Uczenie siatek z korekt"]'),
      null,
    );
    await change('Sesja ślepego pomiaru', session);
    assert.ok(document.querySelector('.gridContentCanvas'));
    assert.equal(
      f.calls.some((c) => c[0] === 'normal-get'),
      false,
    );
    await m.render({ gameId: '55555555-5555-4555-8555-555555555555' });
    assert.equal(document.querySelector('.gridContentCanvas'), null);
    assert.ok(find('Propozycje siatek do ręcznej oceny'));
  } finally {
    await m.cleanup();
    delete globalThis.contentApiFixture;
  }
});

test('setup chooses existing frozen set and exact TRAIN slots; unresolved/B targets cannot enter blind selection', async () => {
  const f = fixture();
  f.api.listGridContentTargets = async () => ({
    data: {
      version: 'source-cell-content-targets-v1',
      gameId: game,
      cohortId: cohort,
      manifestSha256: sha,
      nextOffset: null,
      items: [
        { ...target, role: 'TRAIN' },
        {
          ...target,
          positionIndex: 1,
          role: 'A',
          sequenceNumber: null,
          state: 'unresolved',
          reasonCodes: ['CONTENT_SEQUENCE_UNRESOLVED'],
        },
        { ...target, positionIndex: 2, role: 'B' },
      ],
    },
  });
  const m = await mount(GridContentReferenceWorkspace, {
    apiBaseUrl,
    gameId: game,
    mode: 'blind',
    client: f.api,
    onClose() {},
  });
  try {
    await change('Zamrożony zestaw etykiet', cohort);
    const choices = document.querySelectorAll(
      '[aria-label="Zdjęcia i plansze"] input[type="checkbox"]',
    );
    assert.equal(choices.length, 1);
    await act(async () => choices[0].click());
    const start = find('Rozpocznij dwa ślepe przebiegi wybranych plansz');
    await act(async () => {
      start.click();
      start.click();
    });
    const created = f.calls.filter((c) => c[0] === 'create');
    assert.equal(created.length, 1);
    assert.deepEqual(created[0][1].sourceIds, [source]);
    assert.deepEqual(created[0][1].targetSelection, [
      { sourceId: source, positionIndices: [0] },
    ]);
    assert.equal(created[0][1].cohortId, cohort);
    assert.equal(created[0][1].expectedManifestSha256, sha);
    assert.equal(document.querySelector('textarea'), null);
    assert.equal(
      f.calls.some((c) => c[0] === 'normal-get'),
      false,
    );
  } finally {
    await m.cleanup();
  }
});

test('CAS conflict keeps exact pending command; explicit refresh empties canvas without any automatic write', async () => {
  const f = fixture();
  const writes = [];
  f.api.writeGridBlindContentObservation = async (_game, _session, body) => {
    writes.push(structuredClone(body));
    return {
      error: {
        code: 'CONTENT_SESSION_REVISION_CONFLICT',
        message: 'Zmieniona rewizja sesji',
      },
    };
  };
  const m = await mount(GridContentBlind, {
    api: f.api,
    apiBaseUrl,
    gameId: game,
    initialSessionId: session,
  });
  try {
    await annotateBlind();
    await click('Zapisz ślepy pomiar i dalej');
    assert.equal(writes.length, 1);
    assert.match(document.body.textContent, /Zmieniona rewizja sesji/);
    await click('Odczytaj aktualny stan sesji');
    assert.equal(writes.length, 1);
    assert.equal(document.querySelectorAll('.gridContentQuad').length, 0);
    assert.equal(document.querySelectorAll('.gridContentHandle').length, 0);
    await click('Ponów dokładnie zapisane polecenie');
    assert.equal(writes.length, 2);
    assert.deepEqual(writes[0], writes[1]);
  } finally {
    await m.cleanup();
  }
});

test('live content conflict remains visible beside an independently evaluable frozen coverage', async () => {
  const role = {
    state: 'evaluable',
    reasonCodes: [],
    boards: 1,
    slots: 15,
    unapprovedSlots: 0,
    unresolvedPhotos: 0,
    states: { visible: 15, occluded: 0, out_of_frame: 0, unknown: 0 },
    fullPhotos: 0,
    missingFullPhotos: 0,
  };
  const frozen = {
    version: 'source-cell-content-v1',
    state: 'evaluable',
    games: { [game]: { TRAIN: role } },
  };
  const value = {
    ...frozen,
    basis: 'frozen_content_pins',
    frozenPinCoverage: frozen,
    annotationProgress: {
      ...frozen,
      state: 'not_evaluable',
      games: {
        [game]: {
          TRAIN: {
            ...role,
            state: 'not_evaluable',
            reasonCodes: ['CONTENT_SEQUENCE_CONFLICT'],
            states: { ...role.states, visible: 0, unknown: 15 },
            unapprovedSlots: 15,
          },
        },
      },
    },
  };
  const m = await mount(GridContentReadiness, { value });
  try {
    assert.match(
      document.querySelector('[aria-label="Bieżący postęp etykietowania"]')
        .textContent,
      /innego numeru planszy/,
    );
    assert.match(
      document.querySelector('[aria-label="Bieżący postęp etykietowania"]')
        .textContent,
      /15 \/ 15/,
    );
    assert.match(
      document.querySelector('[aria-label="Etykiety przypięte do kohorty"]')
        .textContent,
      /spełnia wymagania/,
    );
  } finally {
    await m.cleanup();
  }
});

test('zoom, touch pan and resized viewport preserve source coordinates and never annotate while panning', async () => {
  const changes = [];
  const m = await mount(GridContentCanvas, {
    sourceUrl: '/source',
    width: 200,
    height: 120,
    measureGeometry: true,
    onChange: (...args) => changes.push(structuredClone(args)),
  });
  try {
    await imageLoaded();
    for (const p of [
      [50, 50],
      [150, 50],
      [150, 110],
      [50, 110],
    ])
      await point(...p);
    await click('Edytuj zawartość 15 pól');
    for (const p of [
      [55, 55],
      [65, 55],
      [65, 65],
      [55, 65],
    ])
      await point(...p);
    await click('Edytuj 24 punkty geometrii');
    const original = structuredClone(changes.at(-1));
    const before = changes.length;
    await change('Powiększenie podglądu', '4');
    assert.equal(changes.length, before);
    assert.equal(
      document.querySelector('.gridContentImage').style.width,
      '400%',
    );
    const svg = document.querySelector('.gridContentImage svg');
    svg.getBoundingClientRect = () => ({
      left: -80,
      top: -40,
      width: 800,
      height: 480,
    });
    await act(async () =>
      svg.dispatchEvent(
        new window.MouseEvent('pointerdown', {
          bubbles: true,
          button: 0,
          clientX: 120,
          clientY: 160,
        }),
      ),
    );
    assert.deepEqual(changes.at(-1)[1][0], [50, 50]);
    assert.deepEqual(changes.at(-1)[0], original[0]);
    await click('Przesuwaj podgląd');
    const viewport = document.querySelector('.gridContentViewport');
    viewport.scrollLeft = 100;
    viewport.scrollTop = 50;
    const panBefore = changes.length;
    await act(async () => {
      svg.dispatchEvent(
        new window.MouseEvent('pointerdown', {
          bubbles: true,
          button: 0,
          clientX: 120,
          clientY: 160,
        }),
      );
      svg.dispatchEvent(
        new window.MouseEvent('pointermove', {
          bubbles: true,
          clientX: 140,
          clientY: 180,
        }),
      );
      svg.dispatchEvent(new window.MouseEvent('pointerup', { bubbles: true }));
    });
    assert.equal(viewport.scrollLeft, 80);
    assert.equal(viewport.scrollTop, 30);
    assert.equal(changes.length, panBefore);
    await click('Wróć do zaznaczania');
    // Same source point after a resize and a different viewport offset.
    svg.getBoundingClientRect = () => ({
      left: 10,
      top: 20,
      width: 400,
      height: 240,
    });
    await act(async () =>
      svg.dispatchEvent(
        new window.MouseEvent('pointerdown', {
          bubbles: true,
          button: 0,
          clientX: 110,
          clientY: 120,
        }),
      ),
    );
    assert.deepEqual(changes.at(-1)[1][0], [50, 50]);
    assert.deepEqual(changes.at(-1)[0], original[0]);
  } finally {
    await m.cleanup();
  }
});

test('source and mode changes remount a blank viewport without ordinary labels or geometry', async () => {
  const f = fixture();
  const otherSource = {
    ...target.source,
    sourceId: '66666666-6666-4666-8666-666666666666',
    sourceRepresentativeSha256: 'c'.repeat(64),
  };
  f.api.getGridContentSession = async () => ({
    data: {
      ...status(),
      total: 2,
      targets: [
        {
          source: target.source,
          sequenceNumber: 42,
          positionIndex: 0,
          completed: false,
        },
        {
          source: otherSource,
          sequenceNumber: 43,
          positionIndex: 0,
          completed: false,
        },
      ],
    },
  });
  const m = await mount(GridContentBlind, {
    api: f.api,
    apiBaseUrl,
    gameId: game,
    initialSessionId: session,
  });
  try {
    await annotateBlind();
    await change('Powiększenie podglądu', '8');
    await click('Przesuwaj podgląd');
    await change('Cel ślepego pomiaru', '1');
    assert.equal(document.querySelectorAll('.gridContentHandle').length, 0);
    assert.equal(document.querySelectorAll('.gridContentQuad').length, 0);
    assert.equal(
      document.querySelector('[aria-label="Powiększenie podglądu"]').value,
      '1',
    );
    assert.ok(find('Przesuwaj podgląd'));
    assert.equal(
      f.calls.some((c) => c[0] === 'normal-get'),
      false,
    );
  } finally {
    await m.cleanup();
  }
  const ordinary = await mount(GridContentReferenceWorkspace, {
    apiBaseUrl,
    gameId: game,
    mode: 'ordinary',
    client: f.api,
    onClose() {},
  });
  try {
    await change('Zamrożony zestaw etykiet', cohort);
    await click('Oznacz Zdjęcie 42 — pozycja 1');
    await imageLoaded();
    await change('Powiększenie podglądu', '4');
    const normalReads = f.calls.filter((c) => c[0] === 'normal-get').length;
    await ordinary.render({ mode: 'blind' });
    await change('Sesja ślepego pomiaru', session);
    assert.equal(
      document.querySelector('[aria-label="Powiększenie podglądu"]').value,
      '1',
    );
    assert.equal(document.querySelectorAll('.gridContentQuad').length, 0);
    assert.equal(
      f.calls.filter((c) => c[0] === 'normal-get').length,
      normalReads,
    );
  } finally {
    await ordinary.cleanup();
  }
});

test('cohort load exposes loading, error, empty and explicit retry without a mutation', async () => {
  const f = fixture(),
    read = deferred();
  let calls = 0;
  f.api.listGridTrainingCohorts = async () => {
    calls += 1;
    return read.promise;
  };
  const m = await mount(GridContentReferenceWorkspace, {
    apiBaseUrl,
    gameId: game,
    mode: 'ordinary',
    client: f.api,
    onClose() {},
  });
  try {
    assert.equal(find('Odczytywanie…').getAttribute('aria-busy'), 'true');
    assert.equal(
      document.querySelector('[aria-label="Zamrożony zestaw etykiet"]')
        .disabled,
      true,
    );
    assert.equal(document.querySelector('.gridContentCanvas'), null);
    await resolveRead(read, {
      error: { code: 'COHORT_UNAVAILABLE', message: 'Błąd odczytu zestawów' },
    });
    assert.match(document.body.textContent, /Błąd odczytu zestawów/);
    assert.equal(find('Odśwież listę zestawów').disabled, false);
    f.api.listGridTrainingCohorts = async () => {
      calls += 1;
      return { data: { items: [], nextCursor: null } };
    };
    await click('Odśwież listę zestawów');
    assert.match(
      document.body.textContent,
      /Na tej stronie nie ma zamrożonych zestawów/,
    );
    assert.doesNotMatch(document.body.textContent, /Błąd odczytu zestawów/);
    f.api.listGridTrainingCohorts = async () => {
      calls += 1;
      return { data: { items: [header], nextCursor: null } };
    };
    await click('Odśwież listę zestawów');
    assert.equal(
      document.querySelector('[aria-label="Zamrożony zestaw etykiet"]').options
        .length,
      2,
    );
    assert.equal(calls, 3);
    assert.deepEqual(f.calls, []);
  } finally {
    await m.cleanup();
  }
});

test('targets loading and error clear the old editor; empty and retry are readable', async () => {
  const f = fixture(),
    read = deferred();
  let calls = 0;
  f.api.listGridContentTargets = async () => {
    calls += 1;
    return read.promise;
  };
  const m = await mount(GridContentReferenceWorkspace, {
    apiBaseUrl,
    gameId: game,
    mode: 'ordinary',
    client: f.api,
    onClose() {},
  });
  try {
    await change('Zamrożony zestaw etykiet', cohort);
    assert.equal(
      find('Odśwież zdjęcia i plansze').getAttribute('aria-busy'),
      'true',
    );
    assert.equal(find('Odśwież zdjęcia i plansze').disabled, true);
    assert.equal(document.querySelector('.gridContentCanvas'), null);
    await resolveRead(read, {
      error: { code: 'TARGETS_UNAVAILABLE', message: 'Błąd listy plansz' },
    });
    assert.match(document.body.textContent, /Błąd listy plansz/);
    f.api.listGridContentTargets = async () => {
      calls += 1;
      return targetPage([]);
    };
    await click('Odśwież zdjęcia i plansze');
    assert.match(document.body.textContent, /Brak plansz w tym zakresie/);
    assert.equal(
      document.querySelectorAll('[aria-label="Zdjęcia i plansze"] button')
        .length,
      0,
    );
    f.api.listGridContentTargets = async () => {
      calls += 1;
      return targetPage();
    };
    await click('Odśwież zdjęcia i plansze');
    assert.ok(find('Oznacz Zdjęcie 42 — pozycja 1'));
    assert.equal(calls, 3);
    assert.equal(
      f.calls.some((c) => c[0] === 'normal-get'),
      false,
    );
  } finally {
    await m.cleanup();
  }
});

test('ordinary label load, failure, empty annotation and refresh do not approve or save automatically', async () => {
  const f = fixture(),
    read = deferred();
  let calls = 0;
  f.api.getGridCellContentReference = async () => {
    calls += 1;
    return read.promise;
  };
  const m = await mount(GridContentReferenceWorkspace, {
    apiBaseUrl,
    gameId: game,
    mode: 'ordinary',
    client: f.api,
    onClose() {},
  });
  try {
    await change('Zamrożony zestaw etykiet', cohort);
    await click('Oznacz Zdjęcie 42 — pozycja 1');
    assert.equal(
      find('Odczytywanie etykiet…').getAttribute('aria-busy'),
      'true',
    );
    assert.equal(document.querySelector('.gridContentCanvas'), null);
    await resolveRead(read, {
      error: { code: 'REFERENCE_UNAVAILABLE', message: 'Błąd odczytu etykiet' },
    });
    assert.match(document.body.textContent, /Błąd odczytu etykiet/);
    f.api.getGridCellContentReference = async () => {
      calls += 1;
      return {
        data: { annotation: null, revision: 0, contentReferenceSha256: null },
      };
    };
    await click('Odśwież bieżące etykiety');
    assert.match(document.body.textContent, /Brak dotychczasowych etykiet/);
    assert.equal(document.querySelectorAll('.gridContentQuad').length, 0);
    f.api.getGridCellContentReference = async () => {
      calls += 1;
      return referenceResult();
    };
    await click('Odśwież bieżące etykiety');
    await imageLoaded();
    assert.match(document.body.textContent, /Rewizja zawartości: 2/);
    assert.equal(document.querySelectorAll('.gridContentQuad').length, 1);
    assert.equal(find('Zapisz i zatwierdź etykiety zawartości').disabled, true);
    assert.equal(calls, 3);
    assert.equal(
      f.calls.some((c) => c[0] === 'reference'),
      false,
    );
  } finally {
    await m.cleanup();
  }
});

test('session list and selected session expose loading, error, empty and explicit refresh retry', async () => {
  const f = fixture(),
    listRead = deferred();
  let listCalls = 0,
    detailCalls = 0;
  f.api.listGridContentSessions = async () => {
    listCalls += 1;
    return listRead.promise;
  };
  const m = await mount(GridContentBlind, {
    api: f.api,
    apiBaseUrl,
    gameId: game,
  });
  try {
    assert.equal(find('Odczytywanie sesji…').getAttribute('aria-busy'), 'true');
    await resolveRead(listRead, {
      error: { code: 'SESSION_LIST_UNAVAILABLE', message: 'Błąd listy sesji' },
    });
    assert.match(document.body.textContent, /Błąd listy sesji/);
    f.api.listGridContentSessions = async () => {
      listCalls += 1;
      return { data: { items: [] } };
    };
    await click('Odśwież listę sesji');
    assert.match(document.body.textContent, /Brak zapisanych sesji/);
    f.api.listGridContentSessions = async () => {
      listCalls += 1;
      return { data: { items: [status()] } };
    };
    await click('Odśwież listę sesji');
    const detailRead = deferred();
    f.hold(detailRead.promise);
    const originalGet = f.api.getGridContentSession;
    f.api.getGridContentSession = (...args) => {
      detailCalls += 1;
      return originalGet(...args);
    };
    await change('Sesja ślepego pomiaru', session);
    assert.equal(find('Odczytaj aktualny stan sesji').disabled, true);
    assert.equal(document.querySelector('.gridContentCanvas'), null);
    await resolveRead(detailRead, {
      error: { code: 'SESSION_UNAVAILABLE', message: 'Błąd odczytu sesji' },
    });
    assert.match(document.body.textContent, /Błąd odczytu sesji/);
    f.hold(Promise.resolve(sessionDetail('pass1', 1, [])));
    await click('Odczytaj aktualny stan sesji');
    assert.match(document.body.textContent, /Brak plansz w tej sesji/);
    assert.equal(
      find('Zamknij przebieg 1 i rozpocznij pusty przebieg 2').disabled,
      true,
    );
    f.hold(null);
    await click('Odczytaj aktualny stan sesji');
    assert.ok(document.querySelector('.gridContentCanvas'));
    assert.equal(listCalls, 3);
    assert.equal(detailCalls, 3);
    assert.equal(
      f.calls.some(
        (c) =>
          c[0] === 'normal-get' || c[0] === 'observe' || c[0] === 'advance',
      ),
      false,
    );
  } finally {
    await m.cleanup();
  }
});

for (const transition of ['game', 'mode']) {
  test(`late cohort response after ${transition} change cannot populate the new selector`, async () => {
    const f = fixture(),
      stale = deferred();
    const otherGame = '77777777-7777-4777-8777-777777777777';
    f.api.listGridTrainingCohorts = async (id) =>
      id === game ? stale.promise : { data: { items: [], nextCursor: null } };
    const m = await mount(GridContentReferenceWorkspace, {
      apiBaseUrl,
      gameId: game,
      mode: 'ordinary',
      client: f.api,
      onClose() {},
    });
    try {
      assert.equal(find('Odczytywanie…').disabled, true);
      f.api.listGridTrainingCohorts = async () => ({
        data: { items: [], nextCursor: null },
      });
      if (transition === 'game') await m.render({ gameId: otherGame });
      else await m.render({ mode: 'blind' });
      await resolveRead(stale, { data: { items: [header], nextCursor: null } });
      const select = document.querySelector(
        '[aria-label="Zamrożony zestaw etykiet"]',
      );
      if (select) assert.equal(select.options.length, 1);
      assert.equal(document.querySelector('.gridContentCanvas'), null);
      assert.equal(
        f.calls.some((c) => c[0] === 'normal-get' || c[0] === 'reference'),
        false,
      );
    } finally {
      await m.cleanup();
    }
  });

  test(`late target response after ${transition} change cannot restore old targets or label reads`, async () => {
    const f = fixture(),
      stale = deferred();
    const otherGame = '77777777-7777-4777-8777-777777777777';
    f.api.listGridContentTargets = async () => stale.promise;
    f.api.listGridTrainingCohorts = async (id) => ({
      data: { items: [{ ...header, gameId: id }], nextCursor: null },
    });
    const m = await mount(GridContentReferenceWorkspace, {
      apiBaseUrl,
      gameId: game,
      mode: 'ordinary',
      client: f.api,
      onClose() {},
    });
    try {
      await change('Zamrożony zestaw etykiet', cohort);
      assert.equal(find('Odśwież zdjęcia i plansze').disabled, true);
      if (transition === 'game') await m.render({ gameId: otherGame });
      else {
        await m.render({ mode: 'blind' });
        await change('Sesja ślepego pomiaru', session);
      }
      await resolveRead(
        stale,
        targetPage([{ ...target, displayName: 'STARE TAJNE ZDJĘCIE' }]),
      );
      assert.doesNotMatch(document.body.textContent, /STARE TAJNE ZDJĘCIE/);
      assert.equal(
        document.querySelector('[aria-label="Zwykłe etykiety zawartości"]'),
        null,
      );
      assert.equal(
        f.calls.some((c) => c[0] === 'normal-get'),
        false,
      );
      if (transition === 'mode')
        assert.equal(document.querySelectorAll('.gridContentQuad').length, 0);
    } finally {
      await m.cleanup();
    }
  });

  test(`held old session response after ${transition} change never restores that session`, async () => {
    const f = fixture(),
      stale = deferred();
    f.hold(stale.promise);
    const otherGame = '77777777-7777-4777-8777-777777777777';
    const newerSession = '88888888-8888-4888-8888-888888888888';
    const m = await mount(GridContentReferenceWorkspace, {
      apiBaseUrl,
      gameId: game,
      mode: 'blind',
      client: f.api,
      onClose() {},
    });
    try {
      await change('Sesja ślepego pomiaru', session);
      assert.equal(find('Odczytaj aktualny stan sesji').disabled, true);
      if (transition === 'mode') await m.render({ mode: 'ordinary' });
      else {
        f.api.listGridContentSessions = async () => ({
          data: {
            items: [
              {
                ...status('pass2', 4),
                gameId: otherGame,
                sessionId: newerSession,
              },
            ],
          },
        });
        f.api.getGridContentSession = async () => ({
          data: {
            ...sessionDetail('pass2', 4).data,
            gameId: otherGame,
            sessionId: newerSession,
            targets: [
              {
                source: target.source,
                positionIndex: 0,
                sequenceNumber: 84,
                completed: false,
              },
            ],
          },
        });
        await m.render({ gameId: otherGame });
        await change('Sesja ślepego pomiaru', newerSession);
      }
      await resolveRead(stale, sessionDetail('pass1', 1));
      if (transition === 'mode')
        assert.equal(
          document.querySelector('[aria-label="Ślepy pomiar zawartości"]'),
          null,
        );
      else {
        assert.equal(
          document.querySelector('[aria-label="Sesja ślepego pomiaru"]').value,
          newerSession,
        );
        assert.match(document.body.textContent, /Przebieg 2/);
        assert.match(document.body.textContent, /Plansza 84/);
        assert.doesNotMatch(document.body.textContent, /Plansza 42/);
      }
      assert.equal(f.calls.filter((c) => c[0] === 'session-get').length, 1);
      assert.equal(
        f.calls.some((c) => c[0] === 'normal-get'),
        false,
      );
      assert.equal(document.querySelectorAll('.gridContentQuad').length, 0);
    } finally {
      await m.cleanup();
    }
  });
}

test('late ordinary label response after source change cannot overwrite the newer source canvas', async () => {
  const f = fixture(),
    stale = deferred();
  const otherTarget = {
    ...target,
    source: {
      ...target.source,
      sourceId: '66666666-6666-4666-8666-666666666666',
      sourceRepresentativeSha256: 'c'.repeat(64),
    },
    sequenceNumber: 43,
    displayName: 'Zdjęcie 43',
  };
  f.api.listGridContentTargets = async () => targetPage([target, otherTarget]);
  f.api.getGridCellContentReference = async (_game, id) => {
    f.calls.push(['normal-get', id]);
    return id === source ? stale.promise : referenceResult(otherTarget, 2);
  };
  const m = await mount(GridContentReferenceWorkspace, {
    apiBaseUrl,
    gameId: game,
    mode: 'ordinary',
    client: f.api,
    onClose() {},
  });
  try {
    await change('Zamrożony zestaw etykiet', cohort);
    await click('Oznacz Zdjęcie 42 — pozycja 1');
    assert.equal(find('Odczytywanie etykiet…').disabled, true);
    await click('Oznacz Zdjęcie 43 — pozycja 1');
    await imageLoaded();
    assert.match(
      document.querySelector('[aria-label="Zwykłe etykiety zawartości"]')
        .textContent,
      /numer planszy 43/,
    );
    const polygon = document
      .querySelector('.gridContentQuad')
      .getAttribute('points');
    await resolveRead(stale, referenceResult(target, 99));
    assert.doesNotMatch(document.body.textContent, /Rewizja zawartości: 99/);
    assert.match(document.body.textContent, /Rewizja zawartości: 2/);
    assert.equal(
      document.querySelector('.gridContentQuad').getAttribute('points'),
      polygon,
    );
    assert.equal(f.calls.filter((c) => c[0] === 'normal-get').length, 2);
  } finally {
    await m.cleanup();
  }
});

test('late ordinary labels after switching to pass2 remain outside the blind DOM and trigger no new ordinary reads', async () => {
  const f = fixture(),
    stale = deferred();
  f.api.getGridCellContentReference = async () => {
    f.calls.push(['normal-get']);
    return stale.promise;
  };
  f.api.getGridContentSession = async () => sessionDetail('pass2', 3);
  const m = await mount(GridContentReferenceWorkspace, {
    apiBaseUrl,
    gameId: game,
    mode: 'ordinary',
    client: f.api,
    onClose() {},
  });
  try {
    await change('Zamrożony zestaw etykiet', cohort);
    await click('Oznacz Zdjęcie 42 — pozycja 1');
    await m.render({ mode: 'blind' });
    await change('Sesja ślepego pomiaru', session);
    assert.match(document.body.textContent, /Przebieg 2/);
    await resolveRead(stale, referenceResult(target, 99));
    assert.equal(document.querySelectorAll('.gridContentQuad').length, 0);
    assert.equal(document.querySelectorAll('.gridContentHandle').length, 0);
    assert.doesNotMatch(
      document.body.textContent,
      /Rewizja zawartości|Poprzednie etykiety zatwierdził/,
    );
    assert.equal(f.calls.filter((c) => c[0] === 'normal-get').length, 1);
  } finally {
    await m.cleanup();
  }
});

for (const order of ['old-first', 'new-first']) {
  test(`superseded session read ${order} preserves latest pass/source and refresh button ownership`, async () => {
    const f = fixture();
    const stale = deferred(),
      newer = deferred();
    const m = await mount(GridContentBlind, {
      api: f.api,
      apiBaseUrl,
      gameId: game,
      initialSessionId: session,
    });
    try {
      let calls = 0;
      f.api.getGridContentSession = async () =>
        ++calls === 1 ? stale.promise : newer.promise;
      const button = find('Odczytaj aktualny stan sesji');
      await act(async () => {
        button.click();
        button.click();
      });
      assert.equal(calls, 2);
      assert.equal(find('Odczytaj aktualny stan sesji').disabled, true);
      if (order === 'old-first') {
        await resolveRead(stale, sessionDetail('pass1', 1));
        assert.equal(find('Odczytaj aktualny stan sesji').disabled, true);
        assert.equal(document.querySelector('.gridContentCanvas'), null);
      }
      await resolveRead(
        newer,
        sessionDetail('pass2', 3, [
          {
            source: {
              ...target.source,
              sourceId: '66666666-6666-4666-8666-666666666666',
            },
            positionIndex: 0,
            sequenceNumber: 84,
            completed: false,
          },
        ]),
      );
      assert.equal(find('Odczytaj aktualny stan sesji').disabled, false);
      await annotateBlind();
      const polygon = document
        .querySelector('.gridContentQuad')
        .getAttribute('points');
      if (order === 'new-first')
        await resolveRead(stale, sessionDetail('pass1', 1));
      assert.match(document.body.textContent, /Przebieg 2/);
      assert.match(document.body.textContent, /Plansza 84/);
      assert.equal(
        document.querySelector('.gridContentQuad').getAttribute('points'),
        polygon,
      );
      assert.equal(
        f.calls.some((c) => c[0] === 'normal-get'),
        false,
      );
    } finally {
      await m.cleanup();
    }
  });
}

test('an old blind mutation receipt cannot clear a new ordinary pending command or unlock its save button', async () => {
  const f = fixture(),
    oldMutation = deferred(),
    newMutation = deferred();
  let oldBody, newBody;
  f.api.writeGridBlindContentObservation = async (_game, _session, body) => {
    oldBody = structuredClone(body);
    return oldMutation.promise;
  };
  f.api.writeGridCellContentReference = async (_game, body) => {
    newBody = structuredClone(body);
    return newMutation.promise;
  };
  const m = await mount(GridContentReferenceWorkspace, {
    apiBaseUrl,
    gameId: game,
    mode: 'blind',
    client: f.api,
    onClose() {},
  });
  try {
    await change('Sesja ślepego pomiaru', session);
    await annotateBlind();
    await click('Zapisz ślepy pomiar i dalej');
    assert.equal(find('Zapisz ślepy pomiar i dalej').disabled, true);
    const oldKey = contentCommandKey(apiBaseUrl, game, 'blind'),
      newKey = contentCommandKey(apiBaseUrl, game, 'ordinary');
    assert.ok(localStorage.getItem(oldKey));
    await m.render({ mode: 'ordinary' });
    await change('Zamrożony zestaw etykiet', cohort);
    await click('Oznacz Zdjęcie 42 — pozycja 1');
    await imageLoaded();
    await click('Zapisz etykiety bez zatwierdzenia');
    const raw = localStorage.getItem(newKey);
    assert.ok(raw);
    assert.equal(find('Zapisz etykiety bez zatwierdzenia').disabled, true);
    await resolveRead(oldMutation, {
      data: {
        idempotencyKey: oldBody.idempotencyKey,
        session: status('pass1', 2, 1),
      },
    });
    assert.equal(localStorage.getItem(oldKey), null);
    assert.equal(localStorage.getItem(newKey), raw);
    assert.equal(find('Zapisz etykiety bez zatwierdzenia').disabled, true);
    assert.equal(find('Ponów dokładnie zapisane polecenie').disabled, true);
    assert.equal(
      document.querySelector('[aria-label="Ślepy pomiar zawartości"]'),
      null,
    );
    await resolveRead(newMutation, {
      error: {
        code: 'REFERENCE_RETRY_REQUIRED',
        message: 'Potwierdź nowy zapis',
      },
    });
    assert.equal(find('Ponów dokładnie zapisane polecenie').disabled, false);
    assert.equal(
      JSON.parse(localStorage.getItem(newKey)).command.body.idempotencyKey,
      newBody.idempotencyKey,
    );
  } finally {
    await m.cleanup();
  }
});

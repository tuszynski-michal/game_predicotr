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
  'Element',
  'Event',
  'KeyboardEvent',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { createAdminApiClient } =
  await import('@game-predictor/admin-api-client');
const { GeometryCorrectionHistory } =
  await import('../src/features/operational-reviews/geometry-correction-history.tsx');
after(() => dom.window.close());

const row = (id, overrides = {}) => ({
  actor: 'reviewer-session:1',
  blockingReasonCode: null,
  blockingReasonMessage: null,
  boardGeometryRevisionId: id,
  createdAt: '2026-10-09T10:00:00Z',
  geometryRevision: 2,
  kind: 'board_revision',
  pendingGeometryId: null,
  positionIndex: 3,
  recognizedBoardId: 'b-' + id,
  resolutionRevision: 4,
  revertable: true,
  reviewItemId: 'r-' + id,
  sequenceNumber: 100,
  sourceImageId: 's',
  ...overrides,
});

const previewData = {
  correction: row('a'),
  expectedGeometryRevision: 7,
  expectedResolutionRevision: 9,
  removedCellCount: 15,
  removesBoard: false,
  repointedBoardCount: 1,
  restoredCellDecisionCount: 2,
  restoredSourceEngineKind: 'auto_v1',
  restoredSourceGeometryRevisionId: 'x',
  restoredSourceStatus: 'accepted',
  revertedSourceGeometryRevisionId: 'y',
};

function fakeApi(state) {
  const calls = { list: 0, preview: [], revert: [] };
  return {
    calls,
    api: {
      listGeometryCorrections: async () => {
        calls.list += 1;
        return { data: { items: structuredClone(state.items) } };
      },
      previewGeometryCorrectionRevert: async (id, scope) => {
        calls.preview.push({ id, scope });
        return { data: previewData };
      },
      revertGeometryCorrection: async (id, scope, body) => {
        calls.revert.push({ body, id, scope });
        return state.revertResult(calls.revert.length);
      },
    },
  };
}

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50));
  });
const button = (text) =>
  [...document.querySelectorAll('button')].find((b) => b.textContent === text);

async function render(api, onReverted = () => {}) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(GeometryCorrectionHistory, {
        api,
        gameId: 'g',
        importJobId: 'j',
        onReverted,
        refreshToken: 0,
      }),
    ),
  );
  await settle();
  return root;
}

const blocked = row('b', {
  blockingReasonCode: 'GEOMETRY_REVERT_NOT_LATEST',
  blockingReasonMessage: 'Po tej korekcie powstała nowsza.',
  kind: 'pending_slot',
  revertable: false,
});

test('lists corrections and offers "Cofnij" only for revertable rows', async () => {
  const { api } = fakeApi({ items: [row('a'), blocked] });
  const root = await render(api);
  const text = document.body.textContent;
  assert.match(text, /Ostatnie korekty/);
  assert.match(text, /Sekwencja 100/);
  assert.match(text, /Pozycja 3/);
  assert.match(text, /plansza/);
  assert.match(text, /slot/);
  assert.match(text, /reviewer-session:1/);
  assert.match(text, /Po tej korekcie powstała nowsza\./);
  assert.equal(
    [...document.querySelectorAll('button')].filter(
      (b) => b.textContent === 'Cofnij',
    ).length,
    1,
  );
  await act(async () => root.unmount());
});

test('confirming sends one request with CAS tokens and refreshes the list and queue', async () => {
  const state = {
    items: [row('a'), blocked],
    revertResult: () => ({ data: { created: true } }),
  };
  const { api, calls } = fakeApi(state);
  let reverted = 0;
  const root = await render(api, () => {
    reverted += 1;
  });
  await act(async () => button('Cofnij').click());
  await settle();
  assert.equal(calls.preview.length, 1);
  assert.match(document.body.textContent, /Usuwane komórki: 15/);
  const confirm = button('Potwierdź cofnięcie');
  await act(async () => {
    confirm.click();
    confirm.click();
  });
  await settle();
  assert.equal(calls.revert.length, 1);
  assert.equal(calls.revert[0].id, 'a');
  assert.deepEqual(calls.revert[0].scope, { gameId: 'g', importJobId: 'j' });
  assert.equal(calls.revert[0].body.expectedGeometryRevision, 7);
  assert.equal(calls.revert[0].body.expectedResolutionRevision, 9);
  assert.match(calls.revert[0].body.idempotencyKey, /^[0-9a-f-]{36}$/);
  assert.equal(reverted, 1);
  assert.equal(calls.list, 2);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  await act(async () => root.unmount());
});

/** The real generated client over a scripted fetch (no hand-made errors). */
function realClientHarness(revertScript) {
  const calls = { list: 0, revert: [] };
  const json = (status, body) =>
    new Response(JSON.stringify(body), {
      headers: { 'Content-Type': 'application/json' },
      status,
    });
  const fetchStub = async (input, init) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const url = new URL(request.url);
    if (
      request.method === 'GET' &&
      url.pathname.endsWith('/geometry-corrections')
    ) {
      calls.list += 1;
      return json(200, { items: [row('a')] });
    }
    if (request.method === 'GET' && url.pathname.endsWith('/revert-preview')) {
      return json(200, previewData);
    }
    if (request.method === 'POST' && url.pathname.endsWith('/revert')) {
      calls.revert.push(await request.json());
      return revertScript(calls.revert.length);
    }
    return json(404, { code: 'NOT_FOUND', message: 'x' });
  };
  return {
    api: createAdminApiClient({
      baseUrl: 'http://localhost:8000',
      fetch: fetchStub,
    }),
    calls,
    json,
  };
}

const openAndConfirm = async () => {
  await act(async () => button('Cofnij').click());
  await settle();
  await act(async () => button('Potwierdź cofnięcie').click());
  await settle();
};

test('a 4xx refusal with a code closes the dialog and refreshes the list and queue', async () => {
  const { api, calls, json } = realClientHarness(() => json409());
  function json409() {
    return json(409, {
      code: 'GEOMETRY_REVERT_CELLS_CHANGED',
      message: 'Komórki planszy zostały zmienione.',
    });
  }
  let reverted = 0;
  const root = await render(api, () => {
    reverted += 1;
  });
  await openAndConfirm();
  assert.match(document.body.textContent, /Komórki planszy zostały zmienione/);
  assert.match(document.body.textContent, /GEOMETRY_REVERT_CELLS_CHANGED/);
  assert.equal(reverted, 1);
  assert.equal(calls.list, 2);
  assert.equal(calls.revert.length, 1);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  await act(async () => root.unmount());
});

test('a rejected fetch and a 5xx keep the dialog and retry with the same key, then a replay succeeds', async () => {
  const { api, calls, json } = realClientHarness((attempt) => {
    if (attempt === 1) throw new TypeError('fetch failed');
    if (attempt === 2) {
      return json(503, {
        code: 'UNAVAILABLE',
        message: 'Chwilowo niedostępne.',
      });
    }
    return json(200, { created: false });
  });
  let reverted = 0;
  const root = await render(api, () => {
    reverted += 1;
  });
  await openAndConfirm();
  assert.notEqual(document.querySelector('[role="dialog"]'), null);
  assert.match(document.body.textContent, /Wynik cofnięcia jest nieznany/);
  assert.equal(reverted, 0);

  await act(async () => button('Spróbuj ponownie').click());
  await settle();
  // A 5xx may follow a commit, so it is an unknown outcome too.
  assert.notEqual(document.querySelector('[role="dialog"]'), null);
  assert.equal(reverted, 0);

  await act(async () => button('Spróbuj ponownie').click());
  await settle();
  assert.equal(calls.revert.length, 3);
  assert.deepEqual(calls.revert[0], calls.revert[1]);
  assert.deepEqual(calls.revert[0], calls.revert[2]);
  assert.match(calls.revert[0].idempotencyKey, /^[0-9a-f-]{36}$/);
  // A replayed success (created=false) refreshes list and queue as usual.
  assert.equal(reverted, 1);
  assert.equal(calls.list, 2);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  await act(async () => root.unmount());
});

test('the modal takes focus, traps Tab, closes on Escape and returns focus', async () => {
  const { api } = fakeApi({ items: [row('a')], revertResult: () => ({}) });
  const root = await render(api);
  const opener = button('Cofnij');
  opener.focus();
  await act(async () => opener.click());
  await settle();
  const dialog = document.querySelector('[role="dialog"] > div');
  assert.equal(document.activeElement, dialog);

  const press = (target, key, shiftKey = false) =>
    act(async () => {
      target.dispatchEvent(
        new dom.window.KeyboardEvent('keydown', {
          bubbles: true,
          cancelable: true,
          key,
          shiftKey,
        }),
      );
    });
  const confirm = button('Potwierdź cofnięcie');
  confirm.focus();
  await press(confirm, 'Tab');
  assert.equal(document.activeElement, button('Anuluj'));
  await press(button('Anuluj'), 'Tab', true);
  assert.equal(document.activeElement, confirm);

  // Keys typed in the modal never reach window-level shortcut handlers.
  let leaked = 0;
  const probe = () => (leaked += 1);
  dom.window.addEventListener('keydown', probe);
  await press(confirm, 'a');
  dom.window.removeEventListener('keydown', probe);
  assert.equal(leaked, 0);

  await press(confirm, 'Escape');
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(document.activeElement, opener);
  await act(async () => root.unmount());
});

test('a late preview of a closed opening never overwrites the reopened one', async () => {
  const { api: base, calls } = fakeApi({
    items: [row('a')],
    revertResult: (attempt) =>
      attempt === 1 ? null : { data: { created: true } },
  });
  const pendingPreviews = [];
  const api = {
    ...base,
    previewGeometryCorrectionRevert: (id, scope) =>
      new Promise((resolve) => pendingPreviews.push({ id, resolve, scope })),
    revertGeometryCorrection: async (...args) => {
      const result = await base.revertGeometryCorrection(...args);
      if (result === null) throw new Error('lost response');
      return result;
    },
  };
  const preview = (expectedGeometryRevision) => ({
    data: { ...previewData, expectedGeometryRevision },
  });
  const root = await render(api);

  await act(async () => button('Cofnij').click());
  await act(async () => button('Anuluj').click());
  await act(async () => button('Cofnij').click());
  assert.equal(pendingPreviews.length, 2);

  // Reversed order: the second opening answers first, the first one late.
  await act(async () => pendingPreviews[1].resolve(preview(22)));
  await act(async () => pendingPreviews[0].resolve(preview(11)));
  await settle();

  await act(async () => button('Potwierdź cofnięcie').click());
  await settle();
  await act(async () => button('Spróbuj ponownie').click());
  await settle();
  assert.equal(calls.revert.length, 2);
  assert.equal(calls.revert[0].body.expectedGeometryRevision, 22);
  assert.deepEqual(calls.revert[0].body, calls.revert[1].body);
  await act(async () => root.unmount());
});

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
const { GeometryCorrectionHistory } =
  await import('../src/features/operational-reviews/geometry-correction-history.tsx');
const { RejectBoardControl } =
  await import('../src/features/operational-reviews/reject-board-control.tsx');
after(() => dom.window.close());

const rejectionRow = (id, overrides = {}) => ({
  actor: 'reviewer-session:1',
  blockingReasonCode: null,
  blockingReasonMessage: null,
  boardGeometryRevisionId: id,
  createdAt: '2026-10-09T10:00:00Z',
  geometryRevision: 0,
  kind: 'rejection',
  pendingGeometryId: id,
  positionIndex: 2,
  recognizedBoardId: null,
  rejectionNote: null,
  rejectionReason: 'cropped',
  rejectionTarget: 'pending_slot',
  resolutionRevision: 0,
  revertable: true,
  reviewItemId: null,
  sequenceNumber: 69004,
  sourceImageId: 's',
  ...overrides,
});

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50));
  });
const button = (text) =>
  [...document.querySelectorAll('button')].find((b) => b.textContent === text);

async function renderHistory(api, onReverted = () => {}) {
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

function historyApi(items) {
  const calls = { preview: [], revert: [] };
  return {
    calls,
    api: {
      listGeometryCorrections: async () => ({
        data: { items: structuredClone(items) },
      }),
      previewGeometryCorrectionRevert: async (id, scope) => {
        calls.preview.push({ id, scope });
        // No `correction` in the preview: the dialog uses the listed row.
        return {
          data: {
            expectedGeometryRevision: 0,
            expectedResolutionRevision: 0,
            removedCellCount: 0,
            removesBoard: false,
            repointedBoardCount: 0,
            restoredCellDecisionCount: 0,
            restoredSourceEngineKind: null,
            restoredSourceStatus: null,
            revertedSourceGeometryRevisionId: null,
          },
        };
      },
      revertGeometryCorrection: async (id, scope, body) => {
        calls.revert.push({ body, id, scope });
        return { data: { created: true, kind: 'rejection' } };
      },
    },
  };
}

test('the list shows rejections with their reason and offers "Cofnij" only while revertable', async () => {
  const { api } = historyApi([
    rejectionRow('slot-1', {
      rejectionNote: 'Ucięty górny rząd',
      rejectionReason: 'other',
    }),
    rejectionRow('board-1', {
      pendingGeometryId: null,
      recognizedBoardId: 'b',
      rejectionReason: 'blurred',
      rejectionTarget: 'review_item',
      reviewItemId: 'r',
    }),
    rejectionRow('slot-2', {
      blockingReasonCode: 'GEOMETRY_REVERT_REPLACED',
      blockingReasonMessage: 'Tę sekwencję przejęła już inna plansza.',
      revertable: false,
    }),
  ]);
  const root = await renderHistory(api);

  const text = document.body.textContent;
  assert.match(text, /odrzucony slot/);
  assert.match(text, /odrzucona plansza/);
  assert.match(text, /Inny: Ucięty górny rząd/);
  assert.match(text, /Rozmyta/);
  assert.match(text, /Plansza przycięta/);
  assert.match(text, /Tę sekwencję przejęła już inna plansza\./);
  assert.equal(
    [...document.querySelectorAll('button')].filter(
      (b) => b.textContent === 'Cofnij',
    ).length,
    2,
  );
  await act(async () => root.unmount());
});

test('undoing a rejection previews it as a return to the queue and sends one request', async () => {
  const { api, calls } = historyApi([rejectionRow('slot-1')]);
  let reverted = 0;
  const root = await renderHistory(api, () => {
    reverted += 1;
  });

  await act(async () => button('Cofnij').click());
  await settle();
  const dialog = document.querySelector('[role="dialog"]').textContent;
  assert.match(dialog, /Cofnięcie odrzucenia/);
  assert.match(dialog, /Cofnąć odrzucenie sekwencji 69004, pozycja 2\?/);
  assert.match(dialog, /Slot wróci do kolejki korekty cięcia siatki/);
  assert.doesNotMatch(dialog, /Usuwane komórki/);
  await act(async () => button('Potwierdź cofnięcie').click());
  await settle();

  assert.equal(calls.revert.length, 1);
  assert.equal(calls.revert[0].id, 'slot-1');
  assert.equal(calls.revert[0].body.expectedGeometryRevision, 0);
  assert.equal(calls.revert[0].body.expectedResolutionRevision, 0);
  assert.equal(reverted, 1);
  assert.match(document.body.textContent, /Odrzucenie zostało cofnięte/);
  await act(async () => root.unmount());
});

test('the board rejection preview says the item returns to verification', async () => {
  const { api } = historyApi([
    rejectionRow('board-1', {
      pendingGeometryId: null,
      recognizedBoardId: 'b',
      rejectionTarget: 'review_item',
      reviewItemId: 'r',
    }),
  ]);
  const root = await renderHistory(api);

  await act(async () => button('Cofnij').click());
  await settle();

  assert.match(
    document.querySelector('[role="dialog"]').textContent,
    /Plansza wróci do weryfikacji jako oczekująca/,
  );
  await act(async () => root.unmount());
});

test('the control confirms once, hands a done result over and closes', async () => {
  const requests = [];
  const done = [];
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(RejectBoardControl, {
        consequences: ['Plansza wypadnie z weryfikacji.'],
        onDone: (data) => done.push(data),
        onRefused: () => assert.fail('not refused'),
        subject: 'układ #100',
        submit: async (request) => {
          requests.push(request);
          return { data: { id: 'resolved' }, kind: 'done' };
        },
      }),
    ),
  );

  await act(async () => button('Odrzuć planszę').click());
  const dialog = document.querySelector('[role="dialog"]');
  assert.match(dialog.textContent, /Odrzucić planszę \(układ #100\)\?/);
  assert.match(dialog.textContent, /Plansza wypadnie z weryfikacji\./);
  // Neither a reason nor a confirmation is implied.
  assert.equal(button('Potwierdź odrzucenie').disabled, true);
  await act(async () =>
    document
      .querySelector('input[name="board-rejection-reason"][value="blurred"]')
      .click(),
  );
  await act(async () => {
    button('Potwierdź odrzucenie').click();
    button('Potwierdź odrzucenie').click();
  });
  await settle();

  assert.equal(requests.length, 1);
  assert.equal(requests[0].reason, 'blurred');
  assert.match(requests[0].idempotencyKey, /^[0-9a-f-]{36}$/);
  assert.deepEqual(done, [{ id: 'resolved' }]);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  await act(async () => root.unmount());
});

test('a new opening of the dialog gets a new idempotency key', async () => {
  const keys = [];
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(RejectBoardControl, {
        consequences: [],
        onDone: () => {},
        onRefused: () => {},
        subject: 's',
        submit: async (request) => {
          keys.push(request.idempotencyKey);
          return { data: {}, kind: 'done' };
        },
      }),
    ),
  );
  for (let opening = 0; opening < 2; opening += 1) {
    await act(async () => button('Odrzuć planszę').click());
    await act(async () =>
      document
        .querySelector('input[name="board-rejection-reason"][value="cropped"]')
        .click(),
    );
    await act(async () => button('Potwierdź odrzucenie').click());
    await settle();
  }

  assert.equal(keys.length, 2);
  assert.notEqual(keys[0], keys[1]);
  await act(async () => root.unmount());
});

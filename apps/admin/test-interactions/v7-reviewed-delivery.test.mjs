import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'http://localhost',
  pretendToBeVisual: true,
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
  'KeyboardEvent',
  'Image',
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
dom.window.HTMLImageElement.prototype.decode = async () => undefined;
dom.window.HTMLElement.prototype.scrollTo = () => undefined;
dom.window.HTMLElement.prototype.getBoundingClientRect = () => ({
  x: 0,
  y: 0,
  left: 0,
  top: 0,
  right: 900,
  bottom: 500,
  width: 900,
  height: 500,
});
const oldCreate = URL.createObjectURL,
  oldRevoke = URL.revokeObjectURL;
let imageUrlSequence = 0;
URL.createObjectURL = () => `blob:test-v7-delivery-${imageUrlSequence++}`;
URL.revokeObjectURL = () => undefined;
const { createRoot } = await import('react-dom/client');
const { V7SelectionReviewWorkspace } =
  await import('../src/features/semi-automatic-image-selection/v7-selection-review-workspace.tsx');
after(() => {
  URL.createObjectURL = oldCreate;
  URL.revokeObjectURL = oldRevoke;
  dom.window.close();
});
const run = {
  id: '11111111-1111-4111-8111-111111111111',
  status: 'analysis_complete',
  revision: 1,
  direction: 'ascending',
  firstSequenceNumber: 1,
  lastSequenceNumber: 9,
};
const diagnostics = {
  version: 'v7-source-diagnostics-v1',
  sourceIndex: 0,
  sourceId: 'b'.repeat(64),
  sourceChecksumSha256: 'a'.repeat(64),
  sourceErrorCode: null,
  proof: { kind: 'none', supportingSourceIds: [], reasonCodes: ['NO_LABELS'] },
  slots: Array.from({ length: 9 }, (_, positionIndex) => ({
    positionIndex,
    state: positionIndex === 0 ? 'observed_without_number' : 'not_observed',
    sequenceNumber: null,
    readability: 'unknown',
    visibility: 'unknown',
    blur: 'unknown',
    occlusion: 'unknown',
    symbolContentLoss: 'unknown',
    decoration: 'unknown',
  })),
};
const range = {
  id: '22222222-2222-4222-8222-222222222222',
  expectedIndex: 0,
  rangeStart: 1,
  rangeEnd: 9,
  revision: 1,
  status: 'proposed',
  sourceIndex: 0,
  outputChecksumSha256: null,
  v7Review: { candidate: { sourceIndex: 0 }, provenSources: [] },
  outputOperation: null,
  acknowledgementReceipt: null,
};
async function renderFixture({
  feedbackTraceReady = true,
  failStorage = false,
  failInitialLoad = false,
  failFirstRanges = false,
  failFirstSource = false,
  restored = null,
  deferNeighbour = false,
  sourceDiagnostics = diagnostics,
  imageState = 'loaded',
  runState = run,
  rangeRows = [range],
  initialUi = {
    activeExpectedIndex: 0,
    mode: 'review',
    scanSourceIndex: 2,
    sequenceExpectedIndex: 0,
    viewSourceIndex: 0,
    zoomPercent: 125,
    scrollLeft: 4,
    scrollTop: 5,
  },
  acknowledge = null,
  deferFirstViewWrite = false,
  failRunRefresh = false,
  sourceFileCount = 2,
} = {}) {
  const sends = [],
    saves = [],
    ui = [];
  const assetReads = new Map();
  let command = restored;
  let loadCount = 0;
  let rangeCount = 0;
  let sourceCount = 0;
  let assetCount = 0;
  let getRunCount = 0;
  let resolveNeighbour;
  let resolveViewWrite;
  let viewWriteCount = 0;
  const store = {
    load: async () => {
      if (failInitialLoad && loadCount++ === 0)
        throw new Error('IndexedDB unavailable');
      return command;
    },
    save: async (value) => {
      if (failStorage) throw new Error('Storage failed');
      command = value;
      saves.push(value);
    },
    clear: async () => {
      command = null;
    },
  };
  const client = {
    listSemiAutomaticImageSelectionRanges: async (
      _id,
      afterIndex,
      limit = 50,
    ) => {
      if (failFirstRanges && rangeCount++ === 0)
        return { error: { code: 'TEMPORARY_FAILURE' } };
      const items = rangeRows
        .filter((row) => row.expectedIndex > (afterIndex ?? -1))
        .slice(0, limit);
      return {
        data: {
          items,
          nextAfterExpectedIndex:
            items.length === limit ? items.at(-1).expectedIndex : null,
        },
      };
    },
    listSemiAutomaticImageSelectionSources: async (_runId, afterIndex) => {
      if (failFirstSource && sourceCount++ === 0)
        return { error: { code: 'TEMPORARY_FAILURE' } };
      const sourceIndex = afterIndex === undefined ? 0 : afterIndex + 1;
      const sha = sourceIndex === 0 ? 'a'.repeat(64) : 'c'.repeat(64);
      const result = {
        data: {
          items: [
            {
              sourceIndex,
              checksumSha256: sha,
              v7Diagnostics: {
                ...sourceDiagnostics,
                sourceIndex,
                sourceChecksumSha256: sha,
              },
            },
          ],
        },
      };
      if (sourceIndex === 1 && deferNeighbour)
        return new Promise((resolve) => {
          resolveNeighbour = () => resolve(result);
        });
      return result;
    },
    getSemiAutomaticImageSelection: async () => {
      getRunCount += 1;
      if (failRunRefresh) throw new Error('Summary transport failed');
      return { data: runState };
    },
    acknowledgeSemiAutomaticImageSelectionOutput: async (_id, _index, body) => {
      assert.equal(saves.at(-1)?.body.operationId, body.operationId);
      sends.push(body);
      if (acknowledge !== null) return acknowledge(_index, body);
      throw new Error('Lost HTTP response');
    },
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(V7SelectionReviewWorkspace, {
        feedbackTraceReady,
        client,
        decisionStore: store,
        run: runState,
        initialUi,
        onPersistUi: async (value) => {
          if (deferFirstViewWrite && viewWriteCount++ === 0)
            await new Promise((resolve) => {
              resolveViewWrite = resolve;
            });
          ui.push(value);
        },
        sourceFiles: Array.from({ length: sourceFileCount }, (_, index) => ({
          relativePath: index + '.jpg',
          handle: {
            getFile: async () => {
              assetReads.set(index, (assetReads.get(index) ?? 0) + 1);
              if (imageState === 'failed_once' && assetCount++ === 0)
                throw new Error('Asset transport failed once');
              if (imageState === 'failed')
                throw new Error('Asset transport failed');
              return new Blob(['source']);
            },
          },
        })),
      }),
    ),
  );
  if (imageState === 'loaded') await loadVisibleImage();
  return {
    root,
    sends,
    saves,
    ui,
    assetReads,
    command: () => command,
    getRunCount: () => getRunCount,
    releaseViewWrite: () => resolveViewWrite(),
    resolveNeighbour: () => resolveNeighbour(),
  };
}
async function loadVisibleImage() {
  const image = document.querySelector('img');
  assert.ok(image);
  Object.defineProperty(image, 'naturalWidth', {
    configurable: true,
    value: 1000,
  });
  Object.defineProperty(image, 'naturalHeight', {
    configurable: true,
    value: 1200,
  });
  await act(async () =>
    image.dispatchEvent(new Event('load', { bubbles: true })),
  );
}
async function clickLabel(text) {
  const label = [...document.querySelectorAll('label')].find((node) =>
    node.textContent.includes(text),
  );
  assert.ok(label, text);
  await act(async () => label.querySelector('input').click());
}
async function clickButton(text) {
  const button = [...document.querySelectorAll('button')].find(
    (node) => node.textContent === text,
  );
  assert.ok(button, text);
  await act(async () => button.click());
}
test('explicit confirmation persists body before HTTP; lost response/remount retries exact UUID', async () => {
  const fixture = await renderFixture();
  assert.equal(
    document.querySelector('[aria-label="Dziewięć pozycji etykiet"]').children
      .length,
    9,
  );
  assert.match(document.body.textContent, /nieustalone/);
  assert.ok(
    [...document.querySelectorAll('button')].find(
      (node) => node.textContent === 'Zapisz potwierdzone zdjęcie',
    ).disabled,
  );
  await clickLabel('Znam zakres');
  await clickLabel('Sprawdziłem zdjęcie');
  await clickButton('Zapisz potwierdzone zdjęcie');
  assert.equal(fixture.sends.length, 1);
  assert.match(document.body.textContent, /Zapis w toku/);
  const body = fixture.sends[0],
    saved = fixture.command();
  await act(async () => fixture.root.unmount());
  const restarted = await renderFixture({ restored: saved });
  await clickButton('Ponów tę samą decyzję');
  assert.deepEqual(restarted.sends[0], body);
  assert.equal(restarted.command().body.operationId, body.operationId);
  await act(async () => restarted.root.unmount());
});
test('numeric recognition and position confidence are distinct from UNKNOWN symbol quality', async () => {
  const fixture = await renderFixture({
    sourceDiagnostics: {
      ...diagnostics,
      slots: diagnostics.slots.map((slot, index) => ({
        ...slot,
        sequenceNumber: index === 0 ? 6154 : null,
        state: index === 0 ? 'observed_with_number' : 'not_observed',
        recognitionConfidence: index === 0 ? 0.783381 : null,
        positionConfidence: index === 0 ? 0.95 : null,
      })),
    },
  });
  const cards = document.querySelector(
    '[aria-label="Dziewięć pozycji etykiet"]',
  ).children;
  assert.match(cards[0].textContent, /6154/);
  assert.match(cards[0].textContent, /Pewność odczytu numeru: 78,3%/);
  assert.match(cards[0].textContent, /przypisania pozycji: 95,0%/);
  assert.match(
    cards[0].textContent,
    /Jakość symboli — czytelność: nieustalone/,
  );
  assert.match(cards[1].textContent, /Pewność odczytu numeru: brak pomiaru/);
  assert.match(cards[1].textContent, /przypisania pozycji: brak pomiaru/);
  assert.equal(fixture.sends.length, 0);
  await act(async () => fixture.root.unmount());
});

test('optional correction reason survives lost response and remount as part of the exact decision', async () => {
  const fixture = await renderFixture();
  const select = [...document.querySelectorAll('label')]
    .find((label) => label.textContent.includes('Powód wyboru'))
    .querySelector('select');
  await act(async () => {
    select.value = 'occlusion';
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await clickLabel('Znam zakres');
  await clickLabel('Sprawdziłem zdjęcie');
  await clickButton('Zapisz potwierdzone zdjęcie');
  const body = fixture.sends[0],
    saved = fixture.command();
  assert.equal(body.correctionReason, 'occlusion');
  assert.equal(saved.body.correctionReason, 'occlusion');
  await act(async () => fixture.root.unmount());
  const restarted = await renderFixture({ restored: saved });
  await clickButton('Ponów tę samą decyzję');
  assert.deepEqual(restarted.sends[0], body);
  await act(async () => restarted.root.unmount());
});

test('older server retains historical confirmation without sending unsupported feedback reason', async () => {
  const fixture = await renderFixture({ feedbackTraceReady: false });
  assert.match(document.body.textContent, /Pełny ślad uczenia oczekuje/);
  assert.equal(
    [...document.querySelectorAll('label')].some((node) =>
      node.textContent.includes('Powód wyboru'),
    ),
    false,
  );
  await clickLabel('Znam zakres');
  await clickLabel('Sprawdziłem zdjęcie');
  await clickButton('Zapisz potwierdzone zdjęcie');
  assert.equal(fixture.sends.length, 1);
  assert.equal(Object.hasOwn(fixture.sends[0], 'correctionReason'), false);
  await act(async () => fixture.root.unmount());
});
test('failed durable save never sends', async () => {
  const fixture = await renderFixture({ failStorage: true });
  await clickLabel('Znam zakres');
  await clickLabel('Sprawdziłem zdjęcie');
  await clickButton('Zapisz potwierdzone zdjęcie');
  assert.equal(fixture.sends.length, 0);
  assert.match(document.body.textContent, /Storage failed/);
  await clickButton('Odśwież stan');
  assert.match(document.body.textContent, /Storage failed/);
  assert.ok(
    [...document.querySelectorAll('button')].find(
      (node) => node.textContent === 'Zapisz potwierdzone zdjęcie',
    ).disabled,
  );
  await act(async () => fixture.root.unmount());
});

test('successful ranges refresh clears transient request error', async () => {
  const fixture = await renderFixture({ failFirstRanges: true });
  assert.match(
    document.querySelector('[role=alert]').textContent,
    /odświeżyć zakresów/,
  );
  await clickButton('Odśwież stan');
  assert.equal(document.querySelector('[role=alert]'), null);
  assert.match(document.body.textContent, /1–9/);
  assert.equal(fixture.sends.length, 0);
  await act(async () => fixture.root.unmount());
});

test('ranges refresh cannot mask failed IndexedDB restoration or enable output', async () => {
  const fixture = await renderFixture({ failInitialLoad: true });
  await clickButton('Odśwież stan');
  assert.match(
    document.querySelector('[role=alert]').textContent,
    /Zapis jest zablokowany/,
  );
  await clickLabel('Znam zakres');
  await clickLabel('Sprawdziłem zdjęcie');
  await clickButton('Zapisz potwierdzone zdjęcie');
  assert.equal(fixture.sends.length, 0);
  assert.ok(
    [...document.querySelectorAll('button')].find(
      (node) => node.textContent === 'Zapisz potwierdzone zdjęcie',
    ).disabled,
  );
  await act(async () => fixture.root.unmount());
});

test('successful same-source metadata retry clears only its own failure', async () => {
  for (const failInitialLoad of [false, true]) {
    const fixture = await renderFixture({
      failFirstSource: true,
      failInitialLoad,
    });
    assert.match(
      document.querySelector('[role=alert]').textContent,
      failInitialLoad ? /Zapis jest zablokowany/ : /badanego zdjęcia/,
    );
    await clickButton('Odśwież stan');
    assert.ok(
      document.querySelector('[aria-label="Dziewięć pozycji etykiet"]'),
    );
    if (failInitialLoad)
      assert.match(
        document.querySelector('[role=alert]').textContent,
        /Zapis jest zablokowany/,
      );
    else assert.equal(document.querySelector('[role=alert]'), null);
    assert.equal(fixture.sends.length, 0);
    await act(async () => fixture.root.unmount());
  }
});
test('neighbour and proposal navigation reset confirmations; async metadata remains bound to source', async () => {
  const fixture = await renderFixture({ deferNeighbour: true });
  await clickLabel('Znam zakres');
  await clickLabel('Sprawdziłem zdjęcie');
  assert.equal(document.querySelector('input[type=checkbox]').checked, true);
  await act(async () =>
    document.querySelector('[aria-label="Następne zdjęcie"]').click(),
  );
  assert.ok(
    [...document.querySelectorAll('input[type=checkbox]')].every(
      (input) => !input.checked,
    ),
  );
  const save = () =>
    [...document.querySelectorAll('button')].find(
      (node) => node.textContent === 'Zapisz potwierdzone zdjęcie',
    );
  assert.ok(save().disabled);
  await clickLabel('Znam zakres');
  await clickLabel('Sprawdziłem zdjęcie');
  assert.ok(save().disabled);
  await act(async () => fixture.resolveNeighbour());
  await loadVisibleImage();
  assert.equal(
    [...document.querySelectorAll('input[type=checkbox]')].at(-1).checked,
    false,
  );
  assert.ok(save().disabled);
  await clickLabel('Sprawdziłem zdjęcie');
  assert.equal(save().disabled, false);
  await clickButton('Pokaż proponowane zdjęcie');
  assert.ok(
    [...document.querySelectorAll('input[type=checkbox]')].every(
      (input) => !input.checked,
    ),
  );
  assert.ok(save().disabled);
  assert.equal(fixture.sends.length, 0);
  assert.equal(fixture.ui.at(-1).viewSourceIndex, 0);
  assert.equal(fixture.ui.at(-1).scanSourceIndex, 2);
  assert.equal(fixture.ui.at(-1).sequenceExpectedIndex, 0);
  await act(async () => fixture.root.unmount());
});

test('diagnostics and confirmation cannot authorize an unloaded or failed photo', async () => {
  for (const imageState of ['loading', 'failed']) {
    const fixture = await renderFixture({ imageState });
    await clickLabel('Znam zakres');
    await clickLabel('Sprawdziłem zdjęcie');
    await clickButton('Zapisz potwierdzone zdjęcie');
    assert.equal(fixture.sends.length, 0);
    assert.ok(
      [...document.querySelectorAll('button')].find(
        (node) => node.textContent === 'Zapisz potwierdzone zdjęcie',
      ).disabled,
    );
    if (imageState === 'failed')
      assert.match(
        document.querySelector('[role=alert]').textContent,
        /bieżącego zdjęcia/,
      );
    else {
      await loadVisibleImage();
      assert.equal(
        [...document.querySelectorAll('button')].find(
          (node) => node.textContent === 'Zapisz potwierdzone zdjęcie',
        ).disabled,
        false,
      );
    }
    await act(async () => fixture.root.unmount());
  }
});

test('explicit photo retry reloads bytes and requires fresh confirmation after decode', async () => {
  const fixture = await renderFixture({ imageState: 'failed_once' });
  await clickLabel('Znam zakres');
  await clickLabel('Sprawdziłem zdjęcie');
  assert.match(
    document.querySelector('[role=alert]').textContent,
    /bieżącego zdjęcia/,
  );
  await clickButton('Ponów wczytanie zdjęcia');
  const save = () =>
    [...document.querySelectorAll('button')].find(
      (node) => node.textContent === 'Zapisz potwierdzone zdjęcie',
    );
  assert.ok(save().disabled);
  assert.equal(document.querySelector('[role=alert]'), null);
  await loadVisibleImage();
  assert.ok(save().disabled);
  assert.equal(
    [...document.querySelectorAll('input[type=checkbox]')].at(-1).checked,
    false,
  );
  await clickLabel('Sprawdziłem zdjęcie');
  assert.equal(save().disabled, false);
  assert.equal(fixture.sends.length, 0);
  await act(async () => fixture.root.unmount());
});

function provenRanges(count = 2) {
  return Array.from({ length: count }, (_, index) => ({
    ...range,
    id: `22222222-2222-4222-8222-${String(index).padStart(12, '0')}`,
    expectedIndex: index,
    rangeStart: 1 + index * 9,
    rangeEnd: 9 + index * 9,
    sourceIndex: index % 2,
    v7Review: {
      candidate: { sourceIndex: index % 2 },
      provenSources: [{ sourceIndex: index % 2 }],
    },
  }));
}
function committedRow(row, body, state = 'committed') {
  return {
    ...row,
    revision: row.revision + 1,
    status: state === 'committed' ? 'output_synced' : 'conflict',
    sourceIndex: body.sourceIndex,
    v7OutputOwnerOperationId: state === 'committed' ? body.operationId : null,
    v7ConfirmedRange: body.confirmedRange,
    outputChecksumSha256:
      state === 'committed' ? body.expectedSourceChecksumSha256 : null,
    outputOperation: { operationId: body.operationId, state },
    acknowledgementReceipt: {
      operationId: body.operationId,
      state,
      targetName: `seq_${body.confirmedRange.start}-${body.confirmedRange.end}.jpg`,
      errorCode: state === 'committed' ? null : 'V7_OUTPUT_TARGET_CONFLICT',
    },
  };
}
function quickSave() {
  return document.querySelector('[aria-label="Szybkie zatwierdzanie"] button');
}

test('estimated drafts open their indexed neighbour and remain a manual no OCR approval', async () => {
  const row = {
    ...range,
    status: 'missing',
    sourceIndex: null,
    v7Review: {
      candidate: null,
      provenSources: [],
      draft: {
        sourceIndex: 1,
        estimated: true,
        directory: 'C:\\blazing\\propozycje',
      },
    },
  };
  const fixture = await renderFixture({ rangeRows: [row], initialUi: null });
  assert.match(document.body.textContent, /Numer oszacowany/);
  assert.match(document.body.textContent, /Kopia propozycji jest już zapisana/);
  assert.doesNotMatch(document.body.textContent, /Brak gotowej propozycji/);
  assert.ok(fixture.assetReads.get(1) >= 1);
  await loadVisibleImage();
  assert.equal(quickSave().disabled, false);
  await act(async () => quickSave().click());
  assert.equal(fixture.sends[0].kind, 'manual_no_ocr');
  assert.equal(fixture.sends[0].sourceIndex, 1);
  await act(async () => fixture.root.unmount());
});

test('range navigation retains the distant warmed proposal across the intermediate source effect', async () => {
  const rows = provenRanges();
  rows[1] = {
    ...rows[1],
    sourceIndex: 15,
    v7Review: {
      candidate: { sourceIndex: 15 },
      provenSources: [{ sourceIndex: 15 }],
    },
  };
  const fixture = await renderFixture({
    rangeRows: rows,
    sourceFileCount: 20,
    runState: { ...run, lastSequenceNumber: 18 },
  });
  assert.equal(fixture.assetReads.get(15), 1);
  await clickButton('Następny zakres');
  assert.equal(activeRange(), 1);
  assert.equal(fixture.assetReads.get(15), 1);
  assert.ok(document.querySelector('img'));
  await loadVisibleImage();
  assert.equal(quickSave().disabled, false);
  assert.equal(fixture.sends.length, 0);
  await act(async () => fixture.root.unmount());
});
function activeRange() {
  return Number(document.querySelector('label select').value);
}
async function press(key, options = {}, target = window) {
  await act(async () =>
    target.dispatchEvent(
      new KeyboardEvent('keydown', {
        key,
        bubbles: true,
        cancelable: true,
        ...options,
      }),
    ),
  );
}

test('entering a new range shows its proposal; returning uses the saved owner; exact restore keeps neighbour', async () => {
  const rows = provenRanges();
  rows[0].v7Review.candidate.sourceIndex = 1;
  let fixture = await renderFixture({
    rangeRows: rows,
    initialUi: null,
    runState: { ...run, lastSequenceNumber: 18 },
  });
  assert.match(
    document.querySelector('[aria-label="Szybkie zatwierdzanie"]').textContent,
    /Zdjęcie 2/,
  );
  await clickButton('Następny zakres');
  assert.equal(activeRange(), 1);
  const body = {
    operationId: 'owner',
    sourceIndex: 0,
    expectedSourceChecksumSha256: 'a'.repeat(64),
    confirmedRange: { start: 10, end: 18 },
  };
  rows[1] = committedRow(rows[1], body);
  await clickButton('Poprzedni zakres');
  await clickButton('Odśwież stan');
  await clickButton('Następny zakres');
  assert.match(
    document.querySelector('[aria-label="Szybkie zatwierdzanie"]').textContent,
    /Zdjęcie 1/,
  );
  await act(async () => fixture.root.unmount());
  fixture = await renderFixture({ rangeRows: rows });
  assert.match(
    document.querySelector('[aria-label="Szybkie zatwierdzanie"]').textContent,
    /Zdjęcie 1/,
  );
  assert.equal(fixture.sends.length, 0);
  await act(async () => fixture.root.unmount());
});

test('one explicit approval saves full proven photo, advances after committed receipt and prevents double submit', async () => {
  const rows = provenRanges();
  const fixture = await renderFixture({
    rangeRows: rows,
    runState: { ...run, lastSequenceNumber: 18 },
    acknowledge: async (index, body) => ({
      data: (rows[index] = committedRow(rows[index], body)),
    }),
  });
  assert.equal(quickSave().disabled, false);
  assert.equal(document.querySelector('input[type=checkbox]').checked, false);
  await act(async () => {
    quickSave().click();
    quickSave().click();
  });
  assert.equal(fixture.sends.length, 1);
  assert.equal(fixture.sends[0].operatorConfirmedRange, true);
  assert.equal(fixture.sends[0].kind, 'manual_first');
  assert.equal(activeRange(), 1);
  assert.equal(fixture.command(), null);
  assert.equal(fixture.getRunCount(), 1); // one summary refresh after receipt, never polling the full checkpoint
  assert.match(document.body.textContent, /Zapisano na dysku: seq_1-9.jpg/);
  assert.match(
    document.querySelector('[aria-label="Szybkie zatwierdzanie"]').textContent,
    /Zdjęcie 2 → zakres 10–18/,
  );
  assert.equal(quickSave().disabled, true); // next photo has not decoded yet
  await loadVisibleImage();
  assert.equal(quickSave().disabled, false);
  assert.equal(fixture.ui.at(-1).activeExpectedIndex, 1);
  await act(async () => fixture.root.unmount());
});

test('ordinary quick save stays on range and exposes saved owner for explicit replacement', async () => {
  const rows = provenRanges();
  const fixture = await renderFixture({
    rangeRows: rows,
    acknowledge: async (index, body) => ({
      data: (rows[index] = committedRow(rows[index], body)),
    }),
  });
  await clickButton('Zapisz i pozostań');
  assert.equal(activeRange(), 0);
  assert.match(document.body.textContent, /Zdjęcie zapisane/);
  assert.ok(quickSave().disabled); // replacement still requires explicit confirmation
  await clickLabel('Sprawdziłem zdjęcie');
  assert.equal(quickSave().disabled, false);
  await act(async () => quickSave().click());
  assert.equal(fixture.sends[1].kind, 'manual_replace');
  assert.equal(
    fixture.sends[1].expectedOwnerOperationId,
    fixture.sends[0].operationId,
  );
  assert.equal(fixture.sends[1].expectedTargetChecksumSha256, 'a'.repeat(64));
  await act(async () => fixture.root.unmount());
});

test('lost response keeps exact save-and-next intent; restart advances once at page boundary on matching receipt', async () => {
  const rows = provenRanges(51);
  const runState = { ...run, lastSequenceNumber: 459 };
  const initialUi = {
    activeExpectedIndex: 49,
    viewSourceIndex: 1,
    mode: 'review',
  };
  const fixture = await renderFixture({ rangeRows: rows, runState, initialUi });
  await act(async () => quickSave().click());
  assert.equal(fixture.sends.length, 1);
  assert.equal(activeRange(), 49);
  const command = fixture.command();
  assert.equal(command.advanceAfterCommit, true);
  rows[49] = committedRow(rows[49], command.body);
  await act(async () => fixture.root.unmount());
  const restarted = await renderFixture({
    rangeRows: rows,
    runState,
    initialUi,
    restored: command,
  });
  assert.equal(activeRange(), 50);
  assert.equal(restarted.sends.length, 0);
  assert.equal(restarted.command(), null);
  await clickButton('Odśwież stan');
  assert.equal(activeRange(), 50);
  assert.match(document.body.textContent, /451–459/);
  await act(async () => restarted.root.unmount());
});

test('a quickly committed reservation advances within the first second without another click', async () => {
  const rows = provenRanges();
  const fixture = await renderFixture({
    rangeRows: rows,
    runState: { ...run, lastSequenceNumber: 18 },
    acknowledge: async (index, body) => ({
      data: {
        ...rows[index],
        outputOperation: { operationId: body.operationId, state: 'reserved' },
      },
    }),
  });
  try {
    await act(async () => quickSave().click());
    assert.equal(activeRange(), 0);
    assert.ok(quickSave().disabled);
    rows[0] = committedRow(rows[0], fixture.command().body);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 800));
    });
    assert.equal(activeRange(), 1);
    assert.equal(fixture.sends.length, 1);
    assert.equal(fixture.command(), null);
  } finally {
    await act(async () => fixture.root.unmount());
  }
});

test('pending or mismatched receipt cannot advance; exact retry keeps UUID; conflict stays on range', async () => {
  const rows = provenRanges();
  const fixture = await renderFixture({
    rangeRows: rows,
    runState: { ...run, lastSequenceNumber: 18 },
    acknowledge: async (index, body) => ({
      data: {
        ...rows[index],
        outputOperation: { operationId: body.operationId, state: 'reserved' },
        acknowledgementReceipt: {
          operationId: 'another-operation',
          state: 'committed',
        },
      },
    }),
  });
  await act(async () => quickSave().click());
  assert.equal(activeRange(), 0);
  assert.ok(quickSave().disabled);
  const command = fixture.command();
  await clickButton('Następny zakres');
  await press('PageDown');
  await press('Enter');
  assert.equal(activeRange(), 0);
  assert.equal(fixture.sends.length, 1);
  await clickButton('Ponów tę samą decyzję');
  assert.deepEqual(fixture.sends[1], command.body);
  await clickButton('Odśwież stan');
  assert.equal(fixture.getRunCount(), 0); // pending refresh reads only the current ranges page
  rows[0] = committedRow(rows[0], command.body, 'conflict');
  await clickButton('Odśwież stan');
  assert.equal(activeRange(), 0);
  assert.equal(fixture.command(), null);
  assert.match(document.body.textContent, /V7_OUTPUT_TARGET_CONFLICT/);
  assert.doesNotMatch(document.body.textContent, /Zapisano na dysku/);
  await act(async () => fixture.root.unmount());
});

test('keyboard ignores typing and repeated Enter; neighbours invalidate source and range navigation preserves order', async () => {
  const rows = provenRanges();
  const fixture = await renderFixture({
    rangeRows: rows,
    runState: { ...run, lastSequenceNumber: 18 },
  });
  await press('Enter', {}, document.querySelector('input'));
  await press('Enter', { repeat: true });
  assert.equal(fixture.sends.length, 0);
  await press('ArrowRight');
  assert.match(
    document.querySelector('[aria-label="Szybkie zatwierdzanie"]').textContent,
    /Zdjęcie 2/,
  );
  assert.ok(quickSave().disabled);
  await press('PageDown');
  assert.equal(activeRange(), 1);
  await loadVisibleImage();
  await press('Enter');
  assert.equal(fixture.sends.length, 1);
  assert.deepEqual(fixture.sends[0].confirmedRange, { start: 10, end: 18 });
  assert.equal(fixture.sends[0].sourceIndex, 1);
  assert.equal(fixture.saves[0].advanceAfterCommit, true);
  await act(async () => fixture.root.unmount());
});

test('quick approval stays blocked for unloaded photo and failed storage', async () => {
  for (const options of [{ imageState: 'loading' }, { failStorage: true }]) {
    const fixture = await renderFixture({
      rangeRows: provenRanges(),
      ...options,
    });
    await act(async () => quickSave().click());
    assert.equal(fixture.sends.length, 0);
    assert.equal(activeRange(), 0);
    await act(async () => fixture.root.unmount());
  }
});

test('full unproven range needs one explicit approval, records no-OCR and advances only after commit', async () => {
  const rows = provenRanges().map((row) => ({
    ...row,
    v7Review: {
      ...row.v7Review,
      provenSources: [],
      manualConfirmationRequired: true,
    },
  }));
  const fixture = await renderFixture({
    rangeRows: rows,
    runState: {
      ...run,
      lastSequenceNumber: 18,
      outputDirectory: 'C:\\v7-output\\test-run',
    },
    acknowledge: async (index, body) => ({
      data: (rows[index] = committedRow(rows[index], body)),
    }),
  });
  assert.match(document.body.textContent, /C:\\v7-output\\test-run/);
  assert.match(document.body.textContent, /Bez dowodu OCR/);
  assert.match(document.body.textContent, /nieustalone/);
  assert.equal(quickSave().disabled, false);
  assert.equal(
    [...document.querySelectorAll('input[type=checkbox]')].some(
      (e) => e.checked,
    ),
    false,
  );
  await act(async () => quickSave().click());
  assert.equal(fixture.sends.length, 1);
  assert.equal(fixture.sends[0].kind, 'manual_no_ocr');
  assert.equal(fixture.sends[0].operatorConfirmedRange, true);
  assert.equal(fixture.sends[0].operatorConfirmedIncompletePage, false);
  assert.equal(Object.hasOwn(fixture.sends[0], 'correctionReason'), false);
  assert.equal(activeRange(), 1);
  await act(async () => fixture.root.unmount());
});

test('no-OCR approval failure does not advance, remains retryable with a fresh explicit command and shows disk error', async () => {
  const rows = [range];
  const fixture = await renderFixture({
    rangeRows: rows,
    acknowledge: async (index, body) => ({
      data: (rows[index] = {
        ...committedRow(rows[index], body, 'failed'),
        acknowledgementReceipt: {
          ...committedRow(rows[index], body, 'failed').acknowledgementReceipt,
          errorCode: 'V7_OUTPUT_FILESYSTEM_UNSUPPORTED',
        },
      }),
    }),
  });
  await act(async () => quickSave().click());
  assert.equal(activeRange(), 0);
  assert.equal(fixture.command(), null);
  assert.match(document.body.textContent, /V7_OUTPUT_FILESYSTEM_UNSUPPORTED/);
  assert.equal(quickSave().disabled, false);
  const firstId = fixture.sends[0].operationId;
  await act(async () => quickSave().click());
  assert.equal(fixture.sends.length, 2);
  assert.notEqual(fixture.sends[1].operationId, firstId);
  assert.equal(activeRange(), 0);
  await act(async () => fixture.root.unmount());
});

test('slow view storage coalesces navigation and ends with the newest range/photo for restart', async () => {
  const fixture = await renderFixture({
    rangeRows: provenRanges(),
    runState: { ...run, lastSequenceNumber: 18 },
    deferFirstViewWrite: true,
  });
  await clickButton('Następny zakres');
  assert.equal(fixture.ui.length, 0);
  await act(async () => fixture.releaseViewWrite());
  assert.equal(fixture.ui.length, 2); // one in flight plus the latest, no growing navigation queue
  assert.equal(fixture.ui.at(-1).activeExpectedIndex, 1);
  assert.equal(fixture.ui.at(-1).viewSourceIndex, 1);
  assert.equal(fixture.ui.at(-1).scanSourceIndex, 2);
  await act(async () => fixture.root.unmount());
});

test('summary failure after receipt cannot turn a committed file into a pending or failed save', async () => {
  const rows = provenRanges();
  const fixture = await renderFixture({
    rangeRows: rows,
    failRunRefresh: true,
    acknowledge: async (index, body) => ({
      data: (rows[index] = committedRow(rows[index], body)),
    }),
  });
  await clickButton('Zapisz i pozostań');
  assert.equal(fixture.command(), null);
  assert.match(document.body.textContent, /Zapisano na dysku: seq_1-9.jpg/);
  assert.match(
    document.querySelector('[role=alert]').textContent,
    /podsumowania/,
  );
  assert.doesNotMatch(document.body.textContent, /Zapis w toku/);
  assert.equal(
    [...document.querySelectorAll('button')].some(
      (node) => node.textContent === 'Ponów tę samą decyzję',
    ),
    false,
  );
  await act(async () => fixture.root.unmount());
});

test('descending review starts at the highest canonical range and save-and-next crosses the page boundary downwards', async () => {
  const rows = provenRanges(51);
  const fixture = await renderFixture({
    rangeRows: rows,
    initialUi: null,
    runState: { ...run, direction: 'descending', lastSequenceNumber: 459 },
    acknowledge: async (index, body) => ({
      data: (rows[index] = committedRow(rows[index], body)),
    }),
  });
  assert.equal(activeRange(), 50);
  await act(async () => quickSave().click());
  assert.deepEqual(fixture.sends[0].confirmedRange, { start: 451, end: 459 });
  assert.equal(activeRange(), 49);
  assert.match(document.body.textContent, /442–450/);
  await press('PageUp');
  assert.equal(activeRange(), 50);
  await press('PageDown');
  assert.equal(activeRange(), 49);
  assert.equal(fixture.sends.length, 1);
  await act(async () => fixture.root.unmount());
});

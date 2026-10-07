import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import {
  createPartialReviewClient,
  partialReviewItem,
} from './fixtures/symbol-review-partial-client.mjs';

const appReactUrl = import.meta.resolve('react');
registerHooks({
  // Shared hoisted libraries must use the app's React instance in Node tests,
  // just as Next resolves React for the browser bundle.
  resolve(specifier, context, nextResolve) {
    if (specifier === 'react') {
      return nextResolve(appReactUrl, context);
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith('.css'))
      return {
        format: 'module',
        shortCircuit: true,
        source: 'export default new Proxy({}, {get: (_, key) => key});',
      };
    return nextLoad(url, context);
  },
});
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
  'HTMLDialogElement',
  'Element',
  'Event',
  'MouseEvent',
  'KeyboardEvent',
  'Image',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
Object.defineProperty(dom.window.HTMLElement.prototype, 'offsetWidth', {
  get: () => 900,
});
Object.defineProperty(dom.window.HTMLElement.prototype, 'clientWidth', {
  get: () => 900,
});
Object.defineProperty(dom.window.HTMLElement.prototype, 'offsetHeight', {
  get: () => 500,
});
dom.window.HTMLElement.prototype.getBoundingClientRect = () => ({
  x: 0,
  y: 0,
  top: 0,
  left: 0,
  right: 900,
  bottom: 500,
  width: 900,
  height: 500,
});
dom.window.HTMLElement.prototype.scrollTo = () => {};
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '');
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open');
};
globalThis.ResizeObserver = dom.window.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
const { createRoot } = await import('react-dom/client');
const { SymbolReviewWorkspace } =
  await import('../src/features/symbol-reviews/symbol-review-workspace.tsx');
after(() => dom.window.close());
async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}
async function eventually(predicate) {
  const deadline = performance.now() + 5_000;
  while (performance.now() < deadline) {
    if (predicate()) return;
    await act(async () => new Promise((resolve) => setTimeout(resolve, 20)));
    await settle();
  }
  assert.fail('Expected UI state did not appear');
}
const buttons = () => [...document.querySelectorAll('button')];
const button = (text) => {
  const found = buttons().find((x) => x.textContent.trim() === text);
  assert.ok(found, text);
  return found;
};
async function click(node) {
  await act(async () => node.click());
}
async function choose(index, value) {
  await chooseSymbolField(index === 0 ? 'Gra' : 'Symbol', value);
}
function symbolField(label) {
  const node = [...document.querySelectorAll('label')]
    .find((node) => node.firstChild?.textContent.trim() === label)
    ?.querySelector('select');
  assert.ok(node, label);
  return node;
}
async function chooseSymbolField(label, value) {
  await act(async () => {
    const node = symbolField(label);
    node.value = value;
    node.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await settle();
}
async function mount(customFixture) {
  const fixture = customFixture ?? (await createPartialReviewClient());
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(SymbolReviewWorkspace, {
        apiBaseUrl: '',
        client: fixture.api,
      }),
    ),
  );
  await eventually(() => document.querySelector('option[value="game-1"]'));
  await choose(0, 'game-1');
  await eventually(() => document.querySelector('option[value="cherry"]'));
  return { ...fixture, root };
}

test('orphan preparation starts a durable job once and is recoverable on a cold mount', async () => {
  const fixture = await createPartialReviewClient();
  let starts = 0;
  let status = {
    gameId: 'game-1',
    status: 'rebuilding',
    activeJobId: null,
    processedBoardCount: 0,
    expectedBoardCount: 1,
    expectedCellCount: 15,
    persistedCellCount: 15,
    sampleProblemReviewItemIds: [],
    failureMessage: null,
  };
  fixture.api.getSymbolCellReviewProjectionStatus = async () => ({
    data: status,
  });
  fixture.api.startSymbolCellReviewProjectionBackfill = async () => {
    starts++;
    status = { ...status, activeJobId: 'backfill-1' };
    return { data: { projection: status, job: { id: 'backfill-1' } } };
  };
  const { root } = await mount(fixture);
  try {
    await eventually(() => starts === 1);
    await settle();
    assert.equal(starts, 1);
    assert.match(document.body.textContent, /Trwa przygotowanie/);
  } finally {
    await act(async () => root.unmount());
  }
  // New process/view attaches to the active durable job, not a second start.
  const cold = await mount(fixture);
  try {
    await settle();
    assert.equal(starts, 1);
  } finally {
    await act(async () => cold.root.unmount());
  }
});

test('failed orphan start leaves an explicit resume button without automatic retry loops', async () => {
  const fixture = await createPartialReviewClient();
  const status = {
    gameId: 'game-1',
    status: 'rebuilding',
    activeJobId: null,
    processedBoardCount: 0,
    expectedBoardCount: 1,
    expectedCellCount: 15,
    persistedCellCount: 15,
    sampleProblemReviewItemIds: [],
    failureMessage: null,
  };
  let starts = 0;
  fixture.api.getSymbolCellReviewProjectionStatus = async () => ({
    data: status,
  });
  fixture.api.startSymbolCellReviewProjectionBackfill = async () => {
    starts++;
    return {
      error: { code: 'TEST_UNAVAILABLE', message: 'Próba wymaga wznowienia' },
    };
  };
  const { root } = await mount(fixture);
  try {
    await eventually(() => starts === 1);
    await settle();
    assert.equal(starts, 1);
    await click(button('Wznów przygotowanie'));
    assert.equal(starts, 2);
  } finally {
    await act(async () => root.unmount());
  }
});

test('orphan start in a previous game cannot disable or overwrite preparation in the next game', async () => {
  const fixture = await createPartialReviewClient();
  fixture.api.listGames = async () => ({
    data: [
      { id: 'game-1', name: 'Mumie', code: 'mumie', status: 'draft' },
      { id: 'game-2', name: 'Second', code: 'second', status: 'draft' },
    ],
  });
  const status = (gameId, state) => ({
    gameId,
    status: state,
    activeJobId: null,
    processedBoardCount: 0,
    expectedBoardCount: 1,
    expectedCellCount: 15,
    persistedCellCount: 0,
    sampleProblemReviewItemIds: [],
    failureMessage: null,
  });
  fixture.api.getSymbolCellReviewProjectionStatus = async (gameId) => ({
    data: status(gameId, gameId === 'game-1' ? 'rebuilding' : 'not_started'),
  });
  let completeOld;
  fixture.api.startSymbolCellReviewProjectionBackfill = () =>
    new Promise((resolve) => {
      completeOld = resolve;
    });
  const { root } = await mount(fixture);
  try {
    await eventually(() => completeOld !== undefined);
    await choose(0, 'game-2');
    await eventually(() =>
      buttons().some(
        (node) => node.textContent === 'Przygotuj weryfikację symboli',
      ),
    );
    assert.equal(button('Przygotuj weryfikację symboli').disabled, false);
    await act(async () =>
      completeOld({
        data: {
          projection: {
            ...status('game-1', 'rebuilding'),
            activeJobId: 'old-job',
          },
        },
      }),
    );
    await settle();
    assert.equal(button('Przygotuj weryfikację symboli').disabled, false);
    assert.doesNotMatch(document.body.textContent, /Trwa przygotowanie/);
  } finally {
    await act(async () => root.unmount());
  }
});

test('outside selection, keyboard reassignment and unreadable preserve visibility without image actions', async () => {
  const { root, calls } = await mount();
  try {
    await choose(1, 'outside');
    await eventually(() =>
      buttons().some((x) =>
        x.getAttribute('aria-label')?.startsWith('Zaznacz crop'),
      ),
    );
    assert.match(document.body.textContent, /Brak obrazu pola/);
    assert.match(document.body.textContent, /Poza zdjęciem/);
    assert.equal(calls.atlases.length, 0);
    await click(
      buttons().find((x) =>
        x.getAttribute('aria-label')?.startsWith('Zaznacz crop'),
      ),
    );
    assert.equal(button('Ustaw jako grafikę symbolu').disabled, true);
    assert.equal(button('Zapisz i zatwierdź').disabled, true);
    assert.equal(button('Nieczytelny').disabled, false);
    await act(async () =>
      window.dispatchEvent(
        new KeyboardEvent('keydown', { key: '1', bubbles: true }),
      ),
    );
    await act(async () =>
      window.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
      ),
    );
    await eventually(() => calls.decisions.length === 1);
    assert.equal(calls.decisions[0].command.action, 'reassign');
    assert.equal(calls.decisions[0].command.expectedCropSampleId, null);
    assert.equal(calls.decisions[0].command.expectedCropChecksumSha256, null);
    assert.equal(calls.decisions[0].command.expectedGeometryRevision, 4);
    await choose(1, 'cherry');
    await eventually(() =>
      document.body.textContent.includes('Brak obrazu pola'),
    );
    assert.match(document.body.textContent, /Poza zdjęciem/);
    const outside = buttons().find(
      (x) =>
        x.getAttribute('aria-label') ===
        'Zaznacz crop z planszy 62287, pozycja 1/1',
    );
    await click(outside);
    await click(button('Nieczytelny'));
    await eventually(() => calls.decisions.length === 2);
    await choose(1, 'outside');
    await eventually(
      () => !document.body.textContent.includes('Brak obrazu pola'),
    );
    assert.match(document.body.textContent, /Brak pól w wybranej grupie/);
    assert.doesNotMatch(document.body.textContent, /Uzupełnij projekcję/);
    await choose(1, 'cherry');
    await eventually(() =>
      document.body.textContent.includes('Poza zdjęciem · Nieczytelny'),
    );
    assert.equal(calls.reference, 0);
    assert.ok(
      calls.atlases.every((body) =>
        body.cells.every((cell) => cell.cellReviewId !== 'outside-cell'),
      ),
    );
    assert.ok(
      calls.pages.every(
        (query) =>
          query.minConfidence === undefined &&
          query.maxConfidence === undefined,
      ),
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('unassigned outside marked unreadable stays outside and never enters unknown', async () => {
  const { root, calls } = await mount();
  try {
    await choose(1, 'outside');
    await eventually(() =>
      buttons().some((x) =>
        x.getAttribute('aria-label')?.startsWith('Zaznacz crop'),
      ),
    );
    await click(
      buttons().find((x) =>
        x.getAttribute('aria-label')?.startsWith('Zaznacz crop'),
      ),
    );
    await click(button('Nieczytelny'));
    await eventually(() => calls.decisions.length === 1);
    await eventually(() =>
      document.body.textContent.includes('Poza zdjęciem · Nieczytelny'),
    );
    assert.equal(symbolField('Symbol').value, 'outside');
    assert.doesNotMatch(
      document.body.textContent,
      /Brak pól w wybranej grupie/,
    );
    await choose(1, 'unknown');
    await eventually(
      () => !document.body.textContent.includes('Brak obrazu pola'),
    );
    await choose(1, 'outside');
    await eventually(() =>
      document.body.textContent.includes('Poza zdjęciem · Nieczytelny'),
    );
    assert.equal(calls.decisions[0].command.action, 'mark_unreadable');
  } finally {
    await act(async () => root.unmount());
  }
});

test('source modal uses current geometry, blocks workspace shortcuts and closes without a decision', async () => {
  const { root, calls } = await mount();
  try {
    await choose(1, 'outside');
    await eventually(() => buttons().some((x) => x.textContent === 'Źródło'));
    await click(button('Źródło'));
    await eventually(() => document.querySelector('dialog img'));
    assert.equal(calls.source, 1);
    const img = document.querySelector('dialog img');
    Object.defineProperty(img, 'naturalWidth', { value: 500 });
    Object.defineProperty(img, 'naturalHeight', { value: 300 });
    await act(async () => img.dispatchEvent(new Event('load')));
    assert.equal(document.querySelectorAll('dialog polygon').length, 15);
    assert.match(
      document.querySelector('dialog svg').getAttribute('viewBox'),
      /^-150 0 650 300$/,
    );
    const zoomInput = document.querySelector('dialog input[type="range"]');
    assert.ok(zoomInput, 'zoom range input exists');
    assert.equal(zoomInput.min, '100');
    assert.equal(zoomInput.max, '700');
    assert.equal(zoomInput.value, '100');
    await act(async () =>
      window.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
      ),
    );
    assert.equal(calls.decisions.length, 0);
    await click(button('Zamknij podgląd źródła'));
    assert.equal(document.querySelector('dialog'), null);
    await click(button('Źródło'));
    await eventually(() => document.querySelector('dialog img'));
    await click(document.querySelector('dialog'));
    assert.equal(document.querySelector('dialog'), null);
  } finally {
    await act(async () => root.unmount());
  }
});

test('bulk unreadable freezes two outside positions until refresh without changing the group', async () => {
  const { root, calls, cells } = await mount();
  cells.push(
    partialReviewItem({ id: 'outside-second', cellIndex: 5, rowIndex: 1 }),
  );
  try {
    await choose(1, 'outside');
    await eventually(
      () =>
        buttons().filter((x) =>
          x.getAttribute('aria-label')?.startsWith('Zaznacz crop'),
        ).length === 2,
    );
    await click(button('Zaznacz stronę'));
    await click(button('Nieczytelny'));
    await eventually(() =>
      buttons().some((x) => x.textContent === 'Uruchom operację'),
    );
    await click(button('Uruchom operację'));
    await eventually(
      () => document.querySelectorAll('.cardSettled').length === 2,
    );
    assert.equal(calls.decisions.length, 2);
    await click(button('Odśwież cropy'));
    await eventually(
      () =>
        document.querySelectorAll('.cardBadge').length === 2 &&
        [...document.querySelectorAll('.cardBadge')].every(
          (node) => node.textContent === 'Poza zdjęciem · Nieczytelny',
        ),
    );
    assert.equal(calls.decisions.length, 2);
    assert.equal(symbolField('Symbol').value, 'outside');
    assert.equal(calls.atlases.length, 0);
  } finally {
    await act(async () => root.unmount());
  }
});

test('retained blurry option cannot turn an outside assignment into an image action; visible crop keeps its image workflow', async () => {
  const { root, calls } = await mount();
  try {
    await choose(1, 'all');
    await eventually(() =>
      buttons().some(
        (x) =>
          x.getAttribute('aria-label') ===
          'Zaznacz crop z planszy 62287, pozycja 1/3',
      ),
    );
    const selectPosition = (position) =>
      buttons().find(
        (x) =>
          x.getAttribute('aria-label') ===
          `Zaznacz crop z planszy 62287, pozycja 1/${position}`,
      );
    await click(selectPosition(3));
    assert.equal(button('Ustaw jako grafikę symbolu').disabled, false);
    await click(button('Ustaw jako grafikę symbolu'));
    await eventually(() => calls.reference === 1);
    assert.equal(calls.decisions[0].command.action, 'approve');
    await click(selectPosition(2));
    const checkbox = document.querySelector('input[type="checkbox"]');
    await click(checkbox);
    assert.equal(checkbox.checked, true);
    await click(button('Wyczyść zaznaczenie'));
    await click(selectPosition(1));
    assert.equal(checkbox.disabled, true);
    await act(async () =>
      window.dispatchEvent(
        new KeyboardEvent('keydown', { key: '1', bubbles: true }),
      ),
    );
    await act(async () =>
      window.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
      ),
    );
    await eventually(() => calls.decisions.length === 2);
    assert.equal(calls.decisions[1].command.action, 'reassign');
    assert.equal(calls.reference, 1);
    await eventually(() =>
      buttons().some(
        (x) =>
          x.getAttribute('aria-label') ===
          'Zaznacz crop z planszy 62287, pozycja 1/1',
      ),
    );
    assert.equal(symbolField('Symbol').value, 'all');
    assert.match(document.body.textContent, /Symbol zapisano i zatwierdzono\./);
    assert.doesNotMatch(
      document.body.textContent,
      /Symbol zapisano i zatwierdzono jako niewyraźny/,
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('one explicit symbol save approves the same pending label for a legacy game', async () => {
  const { root, calls, cells } = await mount();
  try {
    await choose(1, 'all');
    await eventually(() =>
      buttons().some(
        (x) =>
          x.getAttribute('aria-label') ===
          'Zaznacz crop z planszy 62287, pozycja 1/3',
      ),
    );
    const selectPosition = (position) =>
      buttons().find(
        (x) =>
          x.getAttribute('aria-label') ===
          `Zaznacz crop z planszy 62287, pozycja 1/${position}`,
      );
    await click(selectPosition(3));
    assert.equal(button('Zapisz i zatwierdź').disabled, true);
    assert.equal(
      buttons().some((node) =>
        ['Zatwierdź', 'Zastosuj zmianę'].includes(node.textContent.trim()),
      ),
      false,
    );
    await act(async () =>
      window.dispatchEvent(
        new KeyboardEvent('keydown', { key: '1', bubbles: true }),
      ),
    );
    assert.equal(button('Zapisz i zatwierdź').disabled, false);
    await click(button('Zapisz i zatwierdź'));
    await eventually(() => calls.decisions.length === 1);
    assert.equal(calls.decisions[0].command.action, 'reassign');
    assert.equal(calls.decisions[0].command.targetSymbolId, 'cherry');
    assert.equal(
      cells.find((cell) => cell.id === 'full-cell').reviewState,
      'approved',
    );
    assert.equal(
      cells.find((cell) => cell.id === 'full-cell').assignedSymbolId,
      'cherry',
    );
    assert.match(document.body.textContent, /Symbol zapisano i zatwierdzono\./);
    await eventually(() =>
      document.body.textContent.includes('zatwierdzone: 1'),
    );
    await choose(1, 'cherry');
    assert.equal(symbolField('Symbol do zatwierdzenia').value, '');
  } finally {
    await act(async () => root.unmount());
  }
});

test('explicit correction moves a pending crop into its approved target and survives a cold mount', async () => {
  const fixture = await createPartialReviewClient();
  fixture.api.listSymbols = async () => ({
    data: [
      {
        id: 'cherry',
        name: 'Wiśnia',
        code: 'cherry',
        status: 'active',
        displayOrder: 0,
      },
      {
        id: 'plum',
        name: 'Śliwka',
        code: 'plum',
        status: 'active',
        displayOrder: 1,
      },
    ],
  });
  const chooseState = async (name) => {
    const label = [...document.querySelectorAll('label')].find(
      (node) => node.textContent.trim() === name,
    );
    assert.ok(label, name);
    await click(label.querySelector('input[type="radio"]'));
  };
  const crop = () =>
    buttons().find(
      (node) =>
        node.getAttribute('aria-label') ===
        'Zaznacz crop z planszy 62287, pozycja 1/3',
    );
  const { root, calls, cells } = await mount(fixture);
  try {
    await choose(1, 'cherry');
    await chooseState('Oczekujące');
    await eventually(() => crop());
    await click(crop());
    assert.equal(button('Zapisz i zatwierdź').disabled, true);
    await chooseSymbolField('Symbol do zatwierdzenia', 'plum');
    await click(button('Zapisz i zatwierdź'));
    await eventually(() => calls.decisions.length === 1);
    assert.equal(calls.decisions[0].command.action, 'reassign');
    assert.equal(calls.decisions[0].command.targetSymbolId, 'plum');
    assert.equal(
      cells.find((cell) => cell.id === 'full-cell').assignedSymbolId,
      'plum',
    );
    assert.equal(
      cells.find((cell) => cell.id === 'full-cell').reviewState,
      'approved',
    );
    await eventually(() => !crop());
    await choose(1, 'plum');
    assert.equal(symbolField('Symbol do zatwierdzenia').value, '');
    await chooseState('Zatwierdzone');
    await eventually(() => crop());
    assert.equal(calls.decisions.length, 1);
  } finally {
    await act(async () => root.unmount());
  }
  const cold = await mount(fixture);
  try {
    await choose(1, 'plum');
    await chooseState('Zatwierdzone');
    await eventually(() => crop());
    assert.equal(symbolField('Symbol do zatwierdzenia').value, '');
    assert.equal(calls.decisions.length, 1);
  } finally {
    await act(async () => cold.root.unmount());
  }
});

test('unified save keeps the explicit target on a blurry approval', async () => {
  const { root, calls } = await mount();
  try {
    await choose(1, 'cherry');
    await eventually(() =>
      buttons().some((node) =>
        node.getAttribute('aria-label')?.startsWith('Zaznacz crop'),
      ),
    );
    await click(button('Zaznacz stronę'));
    await chooseSymbolField('Symbol do zatwierdzenia', 'cherry');
    const checkbox = [...document.querySelectorAll('label')]
      .find((node) => node.textContent.trim() === 'Niewyraźny')
      .querySelector('input');
    await click(checkbox);
    await click(button('Zapisz i zatwierdź'));
    await eventually(() => calls.decisions.length === 1);
    assert.equal(calls.decisions[0].command.action, 'mark_blurry');
    assert.equal(calls.decisions[0].command.targetSymbolId, 'cherry');
    assert.match(
      document.body.textContent,
      /Symbol zapisano i zatwierdzono jako niewyraźny, poza uczeniem/,
    );
  } finally {
    await act(async () => root.unmount());
  }
});

test('Mumie same-symbol bulk save approves pending crops and freezes the current page', async () => {
  const fixture = await createPartialReviewClient();
  fixture.api.listGames = async () => ({
    data: [
      {
        id: 'game-1',
        name: 'Mumie',
        code: 'mumie',
        status: 'draft',
        shapeGeometryConfiguration: 'grid_profile_mumie_v1',
      },
    ],
  });
  fixture.cells.push({
    ...fixture.cells.find((cell) => cell.id === 'full-cell'),
    id: 'full-cell-second',
    cellIndex: 3,
    columnIndex: 3,
  });
  const { root, calls, cells } = await mount(fixture);
  try {
    await choose(1, 'cherry');
    await eventually(() =>
      buttons().some(
        (node) =>
          node.getAttribute('aria-label') ===
          'Zaznacz crop z planszy 62287, pozycja 1/4',
      ),
    );
    assert.equal(button('Zapisz i zatwierdź').disabled, true);
    await click(button('Zaznacz stronę'));
    assert.equal(button('Zapisz i zatwierdź').disabled, true);
    await chooseSymbolField('Symbol do zatwierdzenia', 'cherry');
    assert.equal(button('Zapisz i zatwierdź').disabled, false);
    const pageReads = calls.pages.length;
    await click(button('Zapisz i zatwierdź'));
    await eventually(() =>
      buttons().some((node) => node.textContent === 'Uruchom operację'),
    );
    await click(button('Uruchom operację'));
    await eventually(() => calls.decisions.length === 2);
    await eventually(() =>
      document.body.textContent.includes('Operacja zakończona: 2 symboli.'),
    );
    assert.equal(calls.pages.length, pageReads);
    assert.ok(
      calls.decisions.every(
        (call) =>
          call.command.action === 'reassign' &&
          call.command.targetSymbolId === 'cherry',
      ),
    );
    assert.ok(
      cells
        .filter((cell) => cell.assignedSymbolId === 'cherry')
        .every((cell) => cell.reviewState === 'approved'),
    );
    assert.equal(
      buttons().find((node) =>
        node
          .getAttribute('aria-label')
          ?.endsWith('crop z planszy 62287, pozycja 1/4'),
      ).disabled,
      true,
    );
    await choose(1, 'outside');
    await eventually(() =>
      buttons().some(
        (node) =>
          node.getAttribute('aria-label') ===
          'Zaznacz crop z planszy 62287, pozycja 1/1',
      ),
    );
    await click(button('Zaznacz stronę'));
    assert.equal(button('Zapisz i zatwierdź').disabled, true);
  } finally {
    await act(async () => root.unmount());
  }
});

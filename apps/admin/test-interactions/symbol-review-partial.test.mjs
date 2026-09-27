import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import {
  createPartialReviewClient,
  partialReviewItem,
} from './fixtures/symbol-review-partial-client.mjs';

registerHooks({
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
  for (let i = 0; i < 30; i++) {
    if (predicate()) return;
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
  await act(async () => {
    const node = document.querySelectorAll('select')[index];
    node.value = value;
    node.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await settle();
}
async function mount() {
  const fixture = await createPartialReviewClient();
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
    assert.equal(button('Zatwierdź').disabled, true);
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
    assert.equal(document.querySelectorAll('select')[1].value, 'outside');
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
    await act(async () =>
      window.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
      ),
    );
    assert.equal(calls.decisions.length, 0);
    await click(button('Zamknij podgląd źródła'));
    assert.equal(document.querySelector('dialog'), null);
  } finally {
    await act(async () => root.unmount());
  }
});

test('bulk unreadable reconciles two outside positions in place without changing the group', async () => {
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
      () =>
        document.querySelectorAll('.cardBadge').length === 2 &&
        [...document.querySelectorAll('.cardBadge')].every(
          (node) => node.textContent === 'Poza zdjęciem · Nieczytelny',
        ),
    );
    assert.equal(calls.decisions.length, 2);
    assert.equal(document.querySelectorAll('select')[1].value, 'outside');
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
    assert.equal(document.querySelectorAll('select')[1].value, 'all');
    assert.match(document.body.textContent, /Symbol został zmieniony\./);
    assert.doesNotMatch(
      document.body.textContent,
      /Symbol został zmieniony i oznaczony jako niewyraźny/,
    );
  } finally {
    await act(async () => root.unmount());
  }
});

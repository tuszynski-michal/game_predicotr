import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';

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
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { SemiAutomaticSelectionWorkspace } =
  await import('../src/features/semi-automatic-image-selection/semi-automatic-selection-workspace.tsx');
after(() => dom.window.close());

for (const policy of ['exact_sources', 'operator_selected_local_folder']) {
  test(`workspace explains server source policy ${policy}`, async () => {
    const container = document.getElementById('root');
    const root = createRoot(container);
    const client = {
      listSemiAutomaticImageSelections: async () => ({
        data: { items: [], nextOffset: null },
      }),
      getSemiAutomaticImageSelectionCapabilities: async () => ({
        data: {
          enabled: true,
          v7: {
            startEnabled: true,
            sourcePolicy: policy,
            automaticStartEnabled: false,
            reason: 'Manual confirmation required',
            borderStyles: ['top_and_sides'],
          },
        },
      }),
    };
    await act(async () => {
      root.render(
        React.createElement(SemiAutomaticSelectionWorkspace, {
          apiBaseUrl: 'http://127.0.0.1:8020',
          client,
        }),
      );
    });
    if (policy === 'operator_selected_local_folder') {
      assert.match(container.textContent, /katalog dowolnej gry/);
      assert.match(container.textContent, /każdy wynik zatwierdzasz ręcznie/);
      assert.doesNotMatch(
        container.textContent,
        /wyłącznie wcześniej zatwierdzone katalogi testowe/,
      );
    } else {
      assert.match(
        container.textContent,
        /wyłącznie wcześniej zatwierdzone katalogi testowe/,
      );
    }
    await act(async () => root.unmount());
  });
}

test('opening a saved folder is guarded against double clicks and changes the review URL', async () => {
  const container = document.getElementById('root');
  const root = createRoot(container);
  const id = '11111111-1111-4111-8111-111111111111';
  let resolvePicker;
  let opens = 0;
  const client = {
    getSemiAutomaticImageSelectionCapabilities: async () => ({
      data: {
        enabled: true,
        v7: { startEnabled: true, borderStyles: ['top_and_sides'] },
      },
    }),
    listSemiAutomaticImageSelections: async () => ({
      data: { items: [], nextOffset: null },
    }),
    openSemiAutomaticImageSelectionReviewFolder: () => {
      opens++;
      return new Promise((resolve) => {
        resolvePicker = resolve;
      });
    },
    getSemiAutomaticImageSelection: async () => ({
      error: { message: 'Saved run unavailable' },
      response: { status: 404 },
    }),
  };
  await act(async () => {
    root.render(
      React.createElement(SemiAutomaticSelectionWorkspace, {
        apiBaseUrl: 'http://localhost',
        client,
      }),
    );
  });
  const button = [...container.querySelectorAll('button')].find(
    (item) => item.textContent === 'Otwórz zapisane wybory',
  );
  await act(async () => {
    button.click();
    button.click();
  });
  assert.equal(opens, 1);
  await act(async () => {
    resolvePicker({ data: { status: 'selected', runId: id } });
  });
  assert.equal(
    new URL(window.location.href).searchParams.get('semiAutomaticRunId'),
    id,
  );
  assert.match(container.textContent, /Nie udało się otworzyć/);
  await act(async () => root.unmount());
  window.localStorage.clear();
  window.history.replaceState(null, '', '/');
});

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
  'MouseEvent',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { CorrectedGridSymbolReinference } =
  await import('../src/features/operational-reviews/corrected-grid-symbol-reinference.tsx');
after(() => dom.window.close());
const button = (label) =>
  [...document.querySelectorAll('button')].find(
    (node) => node.textContent === label,
  );
const job = {
  id: 'job-1',
  status: 'created',
  progress: { current: 0, total: 2 },
};

test('preview does not start a job; explicit click freezes scope and prevents double submit', async () => {
  const requests = [];
  let finish;
  const api = {
    previewPendingSymbolReinference: async (game, options) => {
      requests.push(['preview', game, options]);
      return { data: { pendingCount: 2 } };
    },
    startPendingSymbolReinference: (game, options) => {
      requests.push(['start', game, options]);
      return new Promise((resolve) => {
        finish = resolve;
      });
    },
    getJob: async () => ({
      data: { ...job, status: 'completed', progress: { current: 2, total: 2 } },
    }),
  };
  const root = createRoot(document.getElementById('root'));
  try {
    const render = (refreshKey) =>
      root.render(
        React.createElement(CorrectedGridSymbolReinference, {
          api,
          gameId: 'g',
          importJobId: 'i',
          refreshKey,
        }),
      );
    await act(async () => render(0));
    assert.equal(requests.filter(([kind]) => kind === 'start').length, 0);
    assert.match(document.body.textContent, /Poprawione plansze.*2/);
    await act(async () => {
      const start = button('Rozpoznaj symbole poprawionych plansz');
      start.click();
      start.click();
    });
    assert.equal(requests.filter(([kind]) => kind === 'start').length, 1);
    assert.deepEqual(requests.at(-1), [
      'start',
      'g',
      { correctedGeometry: true, importJobId: 'i' },
    ]);
    await act(async () => finish({ data: job }));
    assert.match(document.body.textContent, /Zadanie job-1: Oczekuje/);
    assert.equal(
      button('Rozpoznaj symbole poprawionych plansz').disabled,
      true,
    );
    await act(async () => button('Odśwież postęp zadania').click());
    assert.match(document.body.textContent, /Zakończone.*2 \/ 2/);
    await act(async () => render(1));
    assert.equal(requests.filter(([kind]) => kind === 'start').length, 1);
    assert.equal(requests.filter(([kind]) => kind === 'preview').length, 3);
  } finally {
    await act(async () => root.unmount());
  }
});

test('empty and failed scopes show no successful start', async () => {
  let starts = 0;
  let pending = 0;
  const api = {
    previewPendingSymbolReinference: async () => ({
      data: { pendingCount: pending },
    }),
    startPendingSymbolReinference: async () => {
      starts++;
      return { error: { code: 'BUSY', message: 'Inny job już działa' } };
    },
  };
  const root = createRoot(document.getElementById('root'));
  try {
    const render = (refreshKey) =>
      root.render(
        React.createElement(CorrectedGridSymbolReinference, {
          api,
          gameId: 'g',
          refreshKey,
        }),
      );
    await act(async () => render(0));
    assert.equal(
      button('Rozpoznaj symbole poprawionych plansz').disabled,
      true,
    );
    assert.equal(starts, 0);
    pending = 1;
    await act(async () => render(1));
    await act(async () =>
      button('Rozpoznaj symbole poprawionych plansz').click(),
    );
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /Inny job już działa/,
    );
    assert.equal(starts, 1);
    assert.equal(document.querySelector('[role="status"]'), null);
  } finally {
    await act(async () => root.unmount());
  }
});

test('a lost start response recovers the existing job on retry', async () => {
  const api = {
    previewPendingSymbolReinference: async () => ({
      data: { pendingCount: 1 },
    }),
    startPendingSymbolReinference: async () => ({
      error: {
        code: 'JOB_INPUT_ALREADY_EXISTS',
        message: 'Already created',
        details: { existingJobId: job.id },
      },
    }),
    getJob: async (id) => {
      assert.equal(id, job.id);
      return { data: job };
    },
  };
  const root = createRoot(document.getElementById('root'));
  try {
    await act(async () =>
      root.render(
        React.createElement(CorrectedGridSymbolReinference, {
          api,
          gameId: 'g',
          refreshKey: 0,
        }),
      ),
    );
    await act(async () =>
      button('Rozpoznaj symbole poprawionych plansz').click(),
    );
    assert.match(
      document.querySelector('[role="status"]').textContent,
      /Zadanie job-1/,
    );
    assert.equal(document.querySelector('[role="alert"]'), null);
  } finally {
    await act(async () => root.unmount());
  }
});

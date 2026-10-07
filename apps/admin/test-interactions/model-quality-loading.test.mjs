import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';

const reactUrl = import.meta.resolve('react');
registerHooks({
  resolve(specifier, context, nextResolve) {
    return nextResolve(specifier === 'react' ? reactUrl : specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith('/grid-quality-panel.tsx'))
      return {
        format: 'module',
        shortCircuit: true,
        source: 'export function GridQualityPanel() { return null; }',
      };
    if (url.endsWith('/lab-candidate-registry-panel.tsx'))
      return {
        format: 'module',
        shortCircuit: true,
        source: 'export function LabCandidateRegistryPanel() { return null; }',
      };
    return nextLoad(url, context);
  },
});
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
const { ModelQualityWorkspace } =
  await import('../src/features/model-quality/model-quality-workspace.tsx');
after(() => dom.window.close());

function quality(gameId, count = 12) {
  return {
    gameId,
    activeHeavyJob: false,
    activeModel: null,
    advisoryThresholds: [],
    canFreeze: false,
    cellSampleCount: count,
    incompleteItemCount: 0,
    latestCohort: null,
    manifestSchemaVersion: 4,
    manifestChecksumSha256: 'a'.repeat(64),
    newVerifiedLayoutCount: count,
    pendingItemCount: 0,
    protectedItemCount: 0,
    rejectedItemCount: 0,
    resolvedLayoutCount: count,
    sourceImageCount: 1,
    symbolCoverage: [{ symbolCode: `class-${gameId}`, sampleCount: count }],
    trainingExclusions: {
      changedCrop: 0,
      gridIssue: 0,
      missingAsset: 0,
      unknown: 0,
      unreadable: 0,
    },
    warnings: [],
  };
}
function client(overrides = {}) {
  return {
    getModelQuality: async (gameId) => ({ data: quality(gameId) }),
    listSymbolModelIterations: async () => ({ data: [] }),
    listSymbolModelActivations: async () => ({ data: [] }),
    previewPendingSymbolReinference: async (gameId) => ({
      data: { gameId, pendingCount: 0 },
    }),
    ...overrides,
  };
}
async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}
async function mount(api, gameId = 'one') {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(ModelQualityWorkspace, {
        apiBaseUrl: '',
        client: api,
        gameId,
      }),
    ),
  );
  await flush();
  return root;
}
async function unmount(root) {
  await act(async () => root.unmount());
}

test('renders quality while pending preview is stalled, then cancels on unmount', async () => {
  let pendingSignal;
  const root = await mount(
    client({
      previewPendingSymbolReinference: (_game, { signal }) => {
        pendingSignal = signal;
        return new Promise(() => {});
      },
    }),
  );
  try {
    assert.match(document.body.textContent, /Pokrycie symboli/);
    assert.doesNotMatch(document.body.textContent, /Ładowanie jakości modelu/);
    const recalculate = [...document.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Przelicz oczekujące'),
    );
    assert.equal(recalculate.disabled, true);
  } finally {
    await unmount(root);
  }
  assert.equal(pendingSignal.aborted, true);
});

test('shows timeout and recovers on retry after a lost response', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let calls = 0;
  let firstSignal;
  const root = await mount(
    client({
      getModelQuality: (gameId, { signal }) => {
        calls++;
        if (calls === 1) {
          firstSignal = signal;
          return new Promise(() => {});
        }
        return Promise.resolve({ data: quality(gameId) });
      },
    }),
  );
  try {
    assert.match(document.body.textContent, /Ładowanie jakości modelu/);
    await act(async () => t.mock.timers.tick(45_000));
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /Odczyt trwa zbyt długo/,
    );
    assert.equal(firstSignal.aborted, true);
    const retry = [...document.querySelectorAll('button')].find(
      (b) => b.textContent === 'Spróbuj ponownie',
    );
    await act(async () => retry.click());
    await flush();
    assert.match(document.body.textContent, /Pokrycie symboli/);
    assert.equal(calls, 2);
  } finally {
    await unmount(root);
    t.mock.timers.reset();
  }
});

test('game change cancels old reads and ignores their late responses', async () => {
  let resolveOldQuality;
  let resolveOldPending;
  const signals = [];
  const api = client({
    getModelQuality: (gameId, { signal }) => {
      if (gameId === 'one') {
        signals.push(signal);
        return new Promise((resolve) => {
          resolveOldQuality = resolve;
        });
      }
      return Promise.resolve({ data: quality(gameId, 23) });
    },
    previewPendingSymbolReinference: (gameId, { signal }) => {
      if (gameId === 'one') {
        signals.push(signal);
        return new Promise((resolve) => {
          resolveOldPending = resolve;
        });
      }
      return Promise.resolve({ data: { gameId, pendingCount: 0 } });
    },
  });
  const root = await mount(api);
  try {
    await act(async () =>
      root.render(
        React.createElement(ModelQualityWorkspace, {
          apiBaseUrl: '',
          client: api,
          gameId: 'two',
        }),
      ),
    );
    await flush();
    assert.ok(signals.every((s) => s.aborted));
    await act(async () => {
      resolveOldQuality({ data: quality('one', 99) });
      resolveOldPending({ data: { gameId: 'one', pendingCount: 99 } });
    });
    assert.match(document.body.textContent, /class-two/);
    assert.doesNotMatch(document.body.textContent, /class-one|\(99\)/);
  } finally {
    await unmount(root);
  }
});

test('a pending-preview timeout keeps the loaded report visible and retryable', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const root = await mount(
    client({ previewPendingSymbolReinference: () => new Promise(() => {}) }),
  );
  try {
    await act(async () => t.mock.timers.tick(45_000));
    assert.match(document.body.textContent, /Pokrycie symboli/);
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /liczby oczekujących plansz/,
    );
    assert.ok(
      [...document.querySelectorAll('button')].some(
        (b) => b.textContent === 'Spróbuj ponownie',
      ),
    );
  } finally {
    await unmount(root);
    t.mock.timers.reset();
  }
});

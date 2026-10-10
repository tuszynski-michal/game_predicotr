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
        source:
          "import React from 'react'; export function GridQualityPanel() { const [n,setN]=React.useState(0); return React.createElement('button', { 'data-grid-control': true, onClick:()=>setN(n+1) }, 'Ustaw siatkę '+n); }",
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

test('grid stays mounted and usable during a stalled overview without a timeout', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let resolveOverview;
  const root = await mount(
    client({
      getModelQuality: (gameId, options) => {
        assert.equal(options.view, 'overview');
        return new Promise((resolve) => {
          resolveOverview = resolve;
        });
      },
    }),
  );
  try {
    await act(async () =>
      document.querySelector('[data-grid-control]').click(),
    );
    await act(async () => t.mock.timers.tick(60_000));
    assert.match(document.body.textContent, /Ustaw siatkę 1/);
    assert.equal(document.querySelector('[role="alert"]'), null);
    await act(async () => resolveOverview({ data: quality('one') }));
    assert.match(document.body.textContent, /Pokrycie symboli/);
    assert.match(document.body.textContent, /Ustaw siatkę 1/);
  } finally {
    await unmount(root);
    t.mock.timers.reset();
  }
});

test('exact cohort runs only on training intent and leaves grid usable while preparing', async () => {
  const views = [];
  let fullSignal;
  const root = await mount(
    client({
      getModelQuality: (gameId, options) => {
        views.push(options.view ?? 'full');
        if (options.view === 'overview')
          return Promise.resolve({ data: quality(gameId) });
        fullSignal = options.signal;
        return new Promise(() => {});
      },
    }),
  );
  try {
    assert.deepEqual(views, ['overview']);
    const improve = [...document.querySelectorAll('button')].find(
      (b) => b.textContent === 'Ulepsz rozpoznawanie',
    );
    await act(async () => improve.click());
    assert.deepEqual(views, ['overview', 'full']);
    assert.match(document.body.textContent, /Sprawdzanie wycinków do treningu/);
    assert.doesNotMatch(
      document.body.textContent,
      /Potwierdź niezmienny manifest/,
    );
    await act(async () =>
      document.querySelector('[data-grid-control]').click(),
    );
    assert.match(document.body.textContent, /Ustaw siatkę 1/);
  } finally {
    await unmount(root);
  }
  assert.equal(fullSignal.aborted, true);
});

test('training requires the attested full checksum and never freezes overview counts', async () => {
  let freezeCommand;
  const root = await mount(
    client({
      getModelQuality: async (gameId, options) => ({
        data:
          options.view === 'overview' ? quality(gameId) : fullQuality(gameId),
      }),
      freezeVerifiedTrainingCohort: async (_game, command) => {
        freezeCommand = command;
        return {
          data: { cohort: { id: 'cohort-1', gameId: 'one' }, created: true },
        };
      },
      createSymbolTraining: async () => ({
        data: { iteration: { iterationNumber: 1 }, job: {} },
      }),
    }),
  );
  try {
    const button = (text) =>
      [...document.querySelectorAll('button')].find(
        (b) => b.textContent === text,
      );
    assert.equal(button('Potwierdź manifest'), undefined);
    await act(async () => button('Ulepsz rozpoznawanie').click());
    assert.match(document.body.textContent, /Potwierdź niezmienny manifest/);
    assert.equal(freezeCommand, undefined);
    await act(async () => button('Potwierdź manifest').click());
    assert.equal(freezeCommand.expectedManifestChecksumSha256, 'a'.repeat(64));
    assert.match(document.body.textContent, /Uruchomiono trening iteracji #1/);
    assert.ok(document.querySelector('[data-grid-control]'));
  } finally {
    await unmount(root);
  }
});

test('an empty exact cohort does not offer confirmation despite metadata approvals', async () => {
  const root = await mount(
    client({
      getModelQuality: async (gameId, options) => ({
        data:
          options.view === 'overview'
            ? quality(gameId)
            : {
                ...fullQuality(gameId),
                canFreeze: false,
                cellSampleCount: 0,
                resolvedLayoutCount: 0,
              },
      }),
    }),
  );
  try {
    await act(async () =>
      [...document.querySelectorAll('button')]
        .find((b) => b.textContent === 'Ulepsz rozpoznawanie')
        .click(),
    );
    assert.match(
      document.body.textContent,
      /Brak wycinków spełniających warunki/,
    );
    assert.doesNotMatch(
      document.body.textContent,
      /Potwierdź niezmienny manifest/,
    );
  } finally {
    await unmount(root);
  }
});

function fullQuality(gameId, count = 12) {
  return {
    gameId,
    activeHeavyJob: false,
    activeModel: null,
    advisoryThresholds: [],
    canFreeze: true,
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
function quality(gameId, count = 12) {
  return {
    view: 'overview',
    gameId,
    activeHeavyJob: false,
    latestCohort: null,
    approvedCellCount: count,
    approvedLayoutCount: count,
    sourceImageCount: 1,
    symbolCoverage: [{ symbolCode: 'class-' + gameId, sampleCount: count }],
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

test('a real symbol read error leaves grid available and recovers on retry', async () => {
  let calls = 0;
  let firstSignal;
  const root = await mount(
    client({
      getModelQuality: (gameId, { signal }) => {
        calls++;
        if (calls === 1) {
          firstSignal = signal;
          return Promise.resolve({
            error: { detail: { message: 'API unavailable' } },
          });
        }
        return Promise.resolve({ data: quality(gameId) });
      },
    }),
  );
  try {
    assert.ok(document.querySelector('[role="alert"]'));
    assert.ok(document.querySelector('[data-grid-control]'));
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

test('pending preview failure keeps quality and grid available', async () => {
  const root = await mount(
    client({ previewPendingSymbolReinference: async () => ({ error: {} }) }),
  );
  try {
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
  }
});

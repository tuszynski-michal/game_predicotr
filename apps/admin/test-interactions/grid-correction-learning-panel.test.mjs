import assert from 'node:assert/strict';
import test from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';
const bootstrap = new JSDOM('<div></div>');
globalThis.window = bootstrap.window;
globalThis.document = bootstrap.window.document;
const { createRoot } = await import('react-dom/client');
delete globalThis.window;
delete globalThis.document;
bootstrap.window.close();
const { GridCorrectionLearningPanel } =
  await import('../src/features/model-quality/grid-correction-learning-panel.tsx');
const { learningCommandKey } =
  await import('../src/features/model-quality/grid-correction-learning-state.ts');
const GAME = '11111111-1111-4111-8111-111111111111',
  OTHER = '22222222-2222-4222-8222-222222222222',
  RUN = '33333333-3333-4333-8333-333333333333';
const apiBaseUrl = 'http://127.0.0.1:8000';
const readiness = {
  gameId: GAME,
  baseVersionId: 'base',
  defaultRevision: 2,
  importJobIds: ['import'],
  roleCounts: [
    { role: 'TRAIN', photos: 12, boards: 32 },
    { role: 'VALIDATION', photos: 5, boards: 16 },
    { role: 'REGRESSION', photos: 5, boards: 16 },
  ],
  bufferPhotos: 20,
  priorScopeDocumented: false,
  priorGameIds: [],
  historicalCohorts: [],
  exclusions: [],
  requiredGameIds: [GAME, OTHER],
  blockers: [],
  pendingWorkerChecks: [],
  canStart: true,
  evidenceLevel: 'photo-only',
  limitations: [],
  previewSha256: 'a'.repeat(64),
};
const run = {
  learningId: RUN,
  gameId: GAME,
  status: 'completed',
  stage: 'completed',
  baseVersionId: 'base',
  defaultRevision: 2,
  candidateVersionId: 'candidate',
  evaluationId: null,
  verdict: 'PASS',
  requiredGameIds: [GAME, OTHER],
  createdAt: '2026-11-02T12:00:00Z',
};
const applyPreview = {
  gameId: GAME,
  learningId: RUN,
  versionId: 'candidate',
  versionLabel: 'Model 2',
  defaultVersionId: 'base',
  baseVersionId: 'base',
  defaultRevision: 2,
  additionalGameIds: [],
  requiredGameIds: [GAME, OTHER],
  targets: [
    {
      gameId: GAME,
      gameLabel: 'Mumie',
      assignmentRevision: 3,
      assignedVersionId: 'actual',
      requiresComparison: true,
    },
  ],
  excludedGameIds: [],
  limitations: [],
  evidenceLevel: 'photo-only',
  blockers: [],
  canApply: true,
  previewSha256: 'b'.repeat(64),
};
function fixture(overrides = {}) {
  const calls = [];
  const implementations = {
    getGridCorrectionLearningReady: () => ({ data: readiness }),
    getGridModelDefault: () => ({ data: { version: null, revision: 2 } }),
    listGridCorrectionLearning: () => ({ data: { items: [] } }),
    listGames: () => ({
      data: [
        { id: GAME, name: 'Mumie', code: 'mumie' },
        { id: OTHER, name: '777', code: '777' },
      ],
    }),
    listGridModelVersions: () => ({ data: [] }),
    getGameGridModelHistory: () => ({ data: [] }),
    getGridCorrectionLearning: () => ({ data: run }),
    previewGridCorrectionApply: () => ({ data: applyPreview }),
    listGridCorrectionApply: () => ({ data: { items: [] } }),
    ...overrides,
  };
  const api = new Proxy(
    {},
    {
      get:
        (_, name) =>
        async (...args) => {
          calls.push([name, ...structuredClone(args)]);
          if (!(name in implementations))
            throw new Error(`Unexpected call ${name}`);
          return implementations[name](...args);
        },
    },
  );
  return { api, calls };
}
async function mount(api, saved = {}, gameId = GAME) {
  const dom = new JSDOM('<div id="root"></div>', {
    url: 'http://127.0.0.1:3000',
  });
  for (const [key, value] of Object.entries(saved))
    dom.window.localStorage.setItem(key, value);
  const previous = {};
  for (const [key, value] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    previous[key] = globalThis[key];
    globalThis[key] = value;
  }
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(GridCorrectionLearningPanel, {
        apiBaseUrl,
        gameId,
        client: api,
      }),
    ),
  );
  return {
    saved: () => Object.fromEntries(Object.entries(dom.window.localStorage)),
    close: async () => {
      await act(async () => root.unmount());
      dom.window.close();
      Object.assign(globalThis, previous);
    },
  };
}
async function click(text) {
  const button = [...document.querySelectorAll('button')].find(
    (item) => item.textContent === text,
  );
  assert.ok(button, text);
  await act(async () => button.click());
}
const settle = () =>
  act(async () => new Promise((resolve) => setTimeout(resolve, 10)));
async function check(text) {
  const label = [...document.querySelectorAll('label')].find((item) =>
    item.textContent.includes(text),
  );
  assert.ok(label, text);
  await act(async () => label.querySelector('input').click());
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

test('pending default model is shown as loading even when readiness is already known', async () => {
  const defaults = deferred();
  const setup = fixture({ getGridModelDefault: () => defaults.promise });
  const view = await mount(setup.api);
  try {
    await settle();
    const model = document.querySelector('.gridCorrectionLearning > p');
    assert.match(model.textContent, /Wczytywanie/);
    assert.doesNotMatch(model.textContent, /Nie udało się ustalić/);
    await act(async () =>
      defaults.resolve({ data: { version: null, revision: 2 } }),
    );
    await settle();
    assert.match(model.textContent, /Brak wersji domyślnej/);
  } finally {
    await view.close();
  }
});

test('a failed refresh list still completes the operator selection invalidated by refresh', async () => {
  const oldDetail = deferred();
  let lists = 0,
    details = 0;
  const first = { ...run, verdict: null };
  const next = {
    ...run,
    learningId: 'chosen-next',
    verdict: null,
    status: 'failed',
    errorCode: 'FRESH_SELECTED_B',
  };
  const setup = fixture({
    listGridCorrectionLearning: () => {
      if (++lists === 2) throw new Error('List read failed');
      return { data: { items: [first, next] } };
    },
    getGridCorrectionLearning: (_game, id) =>
      id === RUN
        ? { data: first }
        : ++details === 1
          ? oldDetail.promise
          : { data: next },
  });
  const view = await mount(setup.api);
  try {
    await settle();
    const button = [
      ...document.querySelectorAll('[aria-label="Przebiegi uczenia"] button'),
    ].find((b) => b.textContent.endsWith('Błąd'));
    await act(async () => button.click());
    await click('Odśwież stan uczenia');
    await settle();
    assert.match(
      document.querySelector('[aria-label="Postęp uczenia"]').textContent,
      /FRESH_SELECTED_B/,
    );
    assert.match(document.body.textContent, /List read failed/);
    await act(async () =>
      oldDetail.resolve({ data: { ...next, errorCode: 'OLD_SELECTED_B' } }),
    );
    await settle();
    assert.doesNotMatch(document.body.textContent, /OLD_SELECTED_B/);
    assert.equal(details, 2);
  } finally {
    await view.close();
  }
});

for (const changed of [false, true]) {
  test(`report fetch failure ${changed ? 'clears a changed evaluation' : 'retains the same evaluation'}`, async () => {
    let refreshing = false;
    const setup = fixture({
      listGridCorrectionLearning: () => ({
        data: { items: [{ ...run, verdict: null }] },
      }),
      getGridCorrectionLearning: () => ({
        data: {
          ...run,
          verdict: null,
          evaluationId: refreshing && changed ? 'new-report' : 'old-report',
        },
      }),
      getGridCorrectionLearningEvaluation: () => {
        if (refreshing) throw new Error('Report read failed');
        return {
          data: { evaluationId: 'old-report', report: null, verdict: 'PASS' },
        };
      },
    });
    const view = await mount(setup.api);
    try {
      await settle();
      assert.match(document.body.textContent, /Raport oceny: PASS/);
      refreshing = true;
      await click('Odśwież stan uczenia');
      await settle();
      assert.match(document.body.textContent, /Report read failed/);
      assert.equal(
        document.body.textContent.includes('Raport oceny: PASS'),
        !changed,
      );
    } finally {
      await view.close();
    }
  });
}

test('slow readiness does not hide existing workflow status on entry', async () => {
  const ready = deferred();
  const failed = {
    ...run,
    verdict: null,
    status: 'failed',
    errorCode: 'VISIBLE_HISTORY',
  };
  const setup = fixture({
    getGridCorrectionLearningReady: () => ready.promise,
    listGridCorrectionLearning: () => ({ data: { items: [failed] } }),
    getGridCorrectionLearning: () => ({ data: failed }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    assert.match(
      document.querySelector('[aria-label="Postęp uczenia"]').textContent,
      /VISIBLE_HISTORY/,
    );
    const button = [...document.querySelectorAll('button')].find(
      (b) => b.textContent === 'Odświeżanie stanu uczenia…',
    );
    assert.ok(button?.disabled);
    assert.equal(button.getAttribute('aria-busy'), 'true');
    await act(async () => ready.resolve({ data: readiness }));
    await settle();
    assert.ok(setup.calls.every(([name]) => /^(get|list)/.test(name)));
  } finally {
    await view.close();
  }
});

test('manual refresh immediately loads, deduplicates clicks and shows fresh status before readiness', async (t) => {
  let now = Date.parse('2026-11-03T12:00:00Z');
  t.mock.method(Date, 'now', () => now);
  const ready = deferred();
  let reads = 0,
    changed = false;
  const setup = fixture({
    getGridCorrectionLearningReady: () =>
      ++reads === 1 ? { data: readiness } : ready.promise,
    listGridCorrectionLearning: () => ({
      data: { items: [{ ...run, verdict: null }] },
    }),
    getGridCorrectionLearning: () => ({
      data: {
        ...run,
        verdict: null,
        errorCode: changed ? 'FRESH_STATUS' : 'PREVIOUS_STATUS',
      },
    }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    const previous = [...document.querySelectorAll('[role="status"]')].find(
      (p) => p.textContent.startsWith('Stan odświeżony:'),
    ).textContent;
    now += 1000;
    changed = true;
    const button = [...document.querySelectorAll('button')].find(
      (b) => b.textContent === 'Odśwież stan uczenia',
    );
    await act(async () => {
      button.click();
      assert.equal(button.disabled, false); // before React commits this event batch
      button.click();
    });
    assert.equal(button.textContent, 'Odświeżanie stanu uczenia…');
    assert.equal(button.disabled, true);
    assert.equal(button.getAttribute('aria-busy'), 'true');
    await settle();
    assert.equal(reads, 2);
    assert.match(
      document.querySelector('[aria-label="Postęp uczenia"]').textContent,
      /FRESH_STATUS/,
    );
    await act(async () => ready.resolve({ data: readiness }));
    await settle();
    assert.equal(button.disabled, false);
    assert.equal(button.getAttribute('aria-busy'), 'false');
    assert.equal(button.textContent, 'Odśwież stan uczenia');
    const confirmation = [...document.querySelectorAll('[role="status"]')].find(
      (p) => p.textContent.startsWith('Stan odświeżony:'),
    ).textContent;
    assert.notEqual(confirmation, previous);
    assert.ok(setup.calls.every(([name]) => /^(get|list)/.test(name)));
  } finally {
    await view.close();
  }
});

test('readiness failure preserves workflow data and releases refresh for explicit retry', async () => {
  let reads = 0;
  const setup = fixture({
    getGridCorrectionLearningReady: () => {
      if (++reads === 2) throw new Error('Readiness timed out');
      return { data: readiness };
    },
    listGridCorrectionLearning: () => ({
      data: { items: [{ ...run, verdict: null }] },
    }),
    getGridCorrectionLearning: () => ({
      data: {
        ...run,
        verdict: null,
        errorCode: reads > 1 ? 'FRESH_AFTER_FAILURE' : 'RETAINED_WORKFLOW',
      },
    }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await click('Odśwież stan uczenia');
    await settle();
    assert.match(document.body.textContent, /Readiness timed out/);
    assert.match(
      document.querySelector('[aria-label="Postęp uczenia"]').textContent,
      /FRESH_AFTER_FAILURE/,
    );
    await click('Odśwież stan uczenia');
    await settle();
    assert.equal(reads, 3);
    assert.doesNotMatch(document.body.textContent, /Readiness timed out/);
    assert.ok(setup.calls.every(([name]) => /^(get|list)/.test(name)));
  } finally {
    await view.close();
  }
});

test('late refresh responses after unmount cannot replace another game or trigger a stale status read', async () => {
  const oldReady = deferred(),
    oldList = deferred();
  const old = fixture({
    getGridCorrectionLearningReady: () => oldReady.promise,
    listGridCorrectionLearning: () => oldList.promise,
  });
  const first = await mount(old.api);
  await first.close();
  const next = {
    ...run,
    gameId: OTHER,
    verdict: null,
    errorCode: 'NEW_GAME_STATUS',
  };
  const fresh = fixture({
    getGridCorrectionLearningReady: () => ({
      data: { ...readiness, gameId: OTHER },
    }),
    listGridCorrectionLearning: () => ({ data: { items: [next] } }),
    getGridCorrectionLearning: () => ({ data: next }),
  });
  const second = await mount(fresh.api, {}, OTHER);
  try {
    await settle();
    await act(async () => {
      oldReady.resolve({ data: readiness });
      oldList.resolve({
        data: { items: [{ ...run, errorCode: 'OLD_GAME_STATUS' }] },
      });
    });
    await settle();
    assert.match(document.body.textContent, /NEW_GAME_STATUS/);
    assert.doesNotMatch(document.body.textContent, /OLD_GAME_STATUS/);
    assert.equal(
      old.calls.some(([name]) => name === 'getGridCorrectionLearning'),
      false,
    );
  } finally {
    await second.close();
  }
});

test('refresh after an explicit resume supersedes an older in-flight refresh', async () => {
  const oldReady = deferred(),
    oldList = deferred();
  let readyReads = 0,
    listReads = 0,
    resumed = false;
  const previous = { ...run, status: 'failed', verdict: null };
  const latest = {
    ...run,
    status: 'created',
    verdict: null,
    errorCode: 'LATEST_RESUMED',
  };
  const setup = fixture({
    getGridCorrectionLearningReady: () => {
      if (++readyReads === 2) return oldReady.promise;
      return { data: readiness };
    },
    listGridCorrectionLearning: () => {
      if (++listReads === 2) return oldList.promise;
      return { data: { items: [resumed ? latest : previous] } };
    },
    getGridCorrectionLearning: () => ({ data: resumed ? latest : previous }),
    resumeGridCorrectionLearning: () => {
      resumed = true;
      return { data: latest };
    },
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await click('Odśwież stan uczenia');
    await click('Wznów uczenie');
    await settle();
    assert.match(document.body.textContent, /LATEST_RESUMED/);
    await act(async () => {
      oldReady.resolve({
        data: { ...readiness, blockers: ['STALE_READINESS'], canStart: false },
      });
      oldList.resolve({
        data: { items: [{ ...previous, errorCode: 'STALE_WORKFLOW' }] },
      });
    });
    await settle();
    assert.match(document.body.textContent, /LATEST_RESUMED/);
    assert.doesNotMatch(
      document.body.textContent,
      /STALE_READINESS|STALE_WORKFLOW/,
    );
    assert.equal(
      setup.calls.filter(([name]) => name === 'resumeGridCorrectionLearning')
        .length,
      1,
    );
    assert.equal(
      setup.calls.filter(([name]) => name === 'getGridCorrectionLearning')
        .length,
      2,
    );
    assert.equal(
      [...document.querySelectorAll('button')].find(
        (b) => b.textContent === 'Odśwież stan uczenia',
      ).disabled,
      false,
    );
  } finally {
    await view.close();
  }
});

test('entry reads readiness and history without creating a workflow, even when ready', async () => {
  const { api, calls } = fixture();
  const view = await mount(api);
  try {
    await settle();
    assert.match(document.body.textContent, /32/);
    assert.match(document.body.textContent, /nie jest udokumentowany/);
    assert.equal(
      [...document.querySelectorAll('button')].find(
        (button) => button.textContent === 'Przywróć wersję gry',
      ).disabled,
      true,
    );
    assert.ok(calls.length >= 6);
    assert.ok(calls.every(([name]) => /^(get|list)/.test(name)));
  } finally {
    await view.close();
  }
});
test('lost start response survives reload and exact command is retried only by explicit action', async () => {
  let failures = 1;
  const setup = fixture({
    startGridCorrectionLearning: () => {
      if (failures--) throw new Error('lost response');
      return { data: { ...run, verdict: null, status: 'created' } };
    },
  });
  let view = await mount(setup.api);
  await settle();
  await click('Ulepsz siatki z korekt');
  const first = setup.calls.find(
    ([name]) => name === 'startGridCorrectionLearning',
  );
  const saved = view.saved();
  assert.ok(saved[learningCommandKey(apiBaseUrl, GAME)]);
  await view.close();
  const count = setup.calls.filter(
    ([name]) => name === 'startGridCorrectionLearning',
  ).length;
  view = await mount(setup.api, saved);
  try {
    await settle();
    assert.equal(
      setup.calls.filter(([name]) => name === 'startGridCorrectionLearning')
        .length,
      count,
    );
    await click('Ponów zapisane polecenie uczenia');
    assert.deepEqual(
      setup.calls
        .filter(([name]) => name === 'startGridCorrectionLearning')
        .at(-1),
      first,
    );
    assert.equal(view.saved()[learningCommandKey(apiBaseUrl, GAME)], undefined);
  } finally {
    await view.close();
  }
});
test('apply requires limited-evidence confirmation and other games remain opt-in', async () => {
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [run] } }),
    startGridCorrectionApply: () => ({
      data: {
        applyId: 'apply',
        gameId: GAME,
        learningId: RUN,
        versionId: 'candidate',
        status: 'created',
        steps: [],
        createdAt: '2026-11-02',
      },
    }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    const button = [...document.querySelectorAll('button')].find(
      (item) => item.textContent === 'Zastosuj wersję',
    );
    assert.ok(button.disabled);
    assert.ok(setup.calls.every(([name]) => /^(get|list|preview)/.test(name)));
    await check('Potwierdzam ograniczony dowód');
    assert.equal(button.disabled, false);
    await click('Zastosuj wersję');
    const call = setup.calls.find(
      ([name]) => name === 'startGridCorrectionApply',
    );
    assert.deepEqual(call[3].additionalGameIds, []);
    assert.equal(call[3].confirmLimitedEvidence, true);
    assert.equal(call[3].previewSha256, applyPreview.previewSha256);
  } finally {
    await view.close();
  }
});
test('partial success is read after reload; resume is explicit and keeps the same apply identity', async () => {
  const partial = {
    applyId: 'durable-apply',
    gameId: GAME,
    learningId: RUN,
    versionId: 'candidate',
    status: 'failed',
    createdAt: '2026-11-02',
    errorCode: 'GRID_MODEL_REVISION_CONFLICT',
    steps: [
      {
        kind: 'publish',
        gameId: null,
        status: 'completed',
        receipt: { revision: 1 },
      },
      { kind: 'activate', gameId: GAME, status: 'pending' },
    ],
  };
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [run] } }),
    listGridCorrectionApply: () => ({ data: { items: [partial] } }),
    resumeGridCorrectionApply: () => ({
      data: { ...partial, status: 'created' },
    }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    assert.match(document.body.textContent, /Wykonane kroki są zachowane/);
    assert.equal(
      setup.calls.some(([name]) => name === 'resumeGridCorrectionApply'),
      false,
    );
    await click('Wznów zastosowanie');
    assert.deepEqual(
      setup.calls
        .find(([name]) => name === 'resumeGridCorrectionApply')
        .slice(1),
      [GAME, RUN, 'durable-apply'],
    );
  } finally {
    await view.close();
  }
});

test('apply response loss survives remount without a second submission until explicit retry', async () => {
  let attempts = 0;
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [run] } }),
    startGridCorrectionApply: () => {
      attempts++;
      throw new Error('lost apply response');
    },
  });
  let view = await mount(setup.api);
  await settle();
  await check('Potwierdzam ograniczony dowód');
  await click('Zastosuj wersję');
  const first = setup.calls.find(
      ([name]) => name === 'startGridCorrectionApply',
    ),
    saved = view.saved();
  await view.close();
  view = await mount(setup.api, saved);
  try {
    await settle();
    assert.equal(attempts, 1);
    await click('Ponów zapisane polecenie zastosowania');
    assert.equal(attempts, 2);
    assert.deepEqual(
      setup.calls
        .filter(([name]) => name === 'startGridCorrectionApply')
        .at(-1),
      first,
    );
  } finally {
    await view.close();
  }
});

test('foreign default conflict refreshes preview and requires new confirmation without automatic retraining', async () => {
  let changed = false;
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [run] } }),
    previewGridCorrectionApply: () => ({
      data: changed
        ? {
            ...applyPreview,
            canApply: false,
            blockers: ['GRID_APPLY_DEFAULT_CHANGED'],
            previewSha256: 'c'.repeat(64),
          }
        : applyPreview,
    }),
    startGridCorrectionApply: () => {
      changed = true;
      return {
        error: { detail: 'GRID_APPLY_DEFAULT_CHANGED' },
        response: { status: 409 },
      };
    },
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await check('Potwierdzam ograniczony dowód');
    await click('Zastosuj wersję');
    assert.match(
      document.body.textContent,
      /Inna baza wymaga nowego przebiegu uczenia/,
    );
    assert.equal(
      [...document.querySelectorAll('button')].find(
        (item) => item.textContent === 'Zastosuj wersję',
      ).disabled,
      true,
    );
    assert.equal(
      setup.calls.filter(([name]) => name === 'startGridCorrectionApply')
        .length,
      1,
    );
    assert.equal(
      setup.calls.some(([name]) => name === 'startGridCorrectionLearning'),
      false,
    );
    assert.equal(
      document.body.textContent.includes(
        'Ponów zapisane polecenie zastosowania',
      ),
      false,
    );
  } finally {
    await view.close();
  }
});

test('another game is opt-in and changing scope clears the previous confirmation', async () => {
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [run] } }),
    previewGridCorrectionApply: (_game, _learning, ids) => ({
      data: {
        ...applyPreview,
        additionalGameIds: ids,
        targets: [
          ...applyPreview.targets,
          ...ids.map((id) => ({
            gameId: id,
            assignedVersionId: 'base',
            assignmentRevision: 1,
            requiresComparison: false,
          })),
        ],
      },
    }),
    startGridCorrectionApply: () => ({
      data: {
        applyId: 'apply',
        gameId: GAME,
        learningId: RUN,
        versionId: 'candidate',
        status: 'created',
        steps: [],
        createdAt: '2026-11-02',
      },
    }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await check('Potwierdzam ograniczony dowód');
    await check('777');
    await settle();
    const button = [...document.querySelectorAll('button')].find(
      (item) => item.textContent === 'Zastosuj wersję',
    );
    assert.equal(button.disabled, true);
    await check('Potwierdzam ograniczony dowód');
    await click('Zastosuj wersję');
    assert.deepEqual(
      setup.calls.find(([name]) => name === 'startGridCorrectionApply')[3]
        .additionalGameIds,
      [OTHER],
    );
  } finally {
    await view.close();
  }
});

test('a late workflow answer cannot replace a later explicit selection', async () => {
  let resolveOld;
  const oldAnswer = new Promise((resolve) => {
    resolveOld = resolve;
  });
  const next = {
    ...run,
    learningId: 'next-run',
    verdict: 'REVISE',
    errorCode: 'NEW_SELECTION',
  };
  const setup = fixture({
    listGridCorrectionLearning: () => ({
      data: { items: [{ ...run, verdict: null, status: 'created' }, next] },
    }),
    getGridCorrectionLearning: (_game, id) =>
      id === RUN ? oldAnswer : { data: next },
  });
  const view = await mount(setup.api);
  try {
    await settle();
    const button = [...document.querySelectorAll('button')].find((item) =>
      item.textContent.endsWith('REVISE'),
    );
    assert.ok(button);
    await act(async () => button.click());
    await act(async () =>
      resolveOld({ data: { ...run, errorCode: 'OLD_SELECTION' } }),
    );
    assert.match(document.body.textContent, /NEW_SELECTION/);
    assert.doesNotMatch(document.body.textContent, /OLD_SELECTION/);
  } finally {
    await view.close();
  }
});

for (const [availability, expected] of [
  [
    {
      photos: 12,
      boards: 34,
      minimumPhotos: 20,
      minimumBoards: 60,
      photoDeficit: 8,
      boardDeficit: 26,
      splitStatus: 'minima',
    },
    /Brakuje co najmniej: 8 zdjęć \/ 26 plansz/,
  ],
  [
    {
      photos: 40,
      boards: 80,
      minimumPhotos: 20,
      minimumBoards: 60,
      photoDeficit: 0,
      boardDeficit: 0,
      splitStatus: 'infeasible',
    },
    /bufory lub ochrona danych uniemożliwiają bezpieczny podział/,
  ],
  [null, /Liczba dostępnych korekt i braków nie została ustalona/],
])
  test(`blocked availability remains honest: ${availability?.splitStatus ?? 'unknown'}`, async () => {
    const setup = fixture({
      getGridCorrectionLearningReady: () => ({
        data: {
          ...readiness,
          dataAvailability: availability,
          roleCounts: [],
          canStart: false,
          blockers: ['GRID_COHORT_MINIMUM_NOT_MET'],
        },
      }),
    });

    const view = await mount(setup.api);
    try {
      await settle();
      assert.match(document.body.textContent, expected);
      assert.equal(
        [...document.querySelectorAll('button')].find(
          (item) => item.textContent === 'Ulepsz siatki z korekt',
        ).disabled,
        true,
      );
      assert.doesNotMatch(document.body.textContent, /Zdjęcia buforowe: 0/);
      if (availability === null)
        assert.doesNotMatch(
          document.body.textContent,
          /Dostępne przed buforami: 0/,
        );
    } finally {
      await view.close();
    }
  });

for (const status of ['completed', 'failed'])
  test(`own default explains ${status} history without offering impossible opt-in`, async () => {
    const operation = {
      applyId: 'apply',
      gameId: GAME,
      learningId: RUN,
      versionId: 'candidate',
      status,
      createdAt: '2026-11-02',
      steps: [
        {
          kind: 'publish',
          gameId: null,
          status: 'completed',
          receipt: { kind: 'already-published' },
        },
        { kind: 'set_default', gameId: null, status: 'completed' },
        {
          kind: 'activate',
          gameId: GAME,
          status: status === 'completed' ? 'completed' : 'pending',
        },
      ],
    };
    const setup = fixture({
      listGridCorrectionLearning: () => ({ data: { items: [run] } }),
      previewGridCorrectionApply: () => ({
        data: {
          ...applyPreview,
          defaultVersionId: 'candidate',
          canApply: false,
          blockers: ['GRID_APPLY_ALREADY_DEFAULT'],
          targets: [],
        },
      }),
      listGridCorrectionApply: () => ({ data: { items: [operation] } }),
    });
    const view = await mount(setup.api);
    try {
      await settle();
      assert.match(
        document.body.textContent,
        /Kandydat jest już wersją domyślną/,
      );
      assert.match(
        document.body.textContent,
        /Potwierdzono istniejącą publikację/,
      );
      assert.doesNotMatch(
        document.body.textContent,
        /Inna baza wymaga nowego przebiegu|Zastosuj także w innych ocenionych grach/,
      );
      assert.equal(
        [...document.querySelectorAll('button')].some(
          (button) => button.textContent === 'Zastosuj wersję',
        ),
        false,
      );
      assert.equal(
        [...document.querySelectorAll('button')].some(
          (button) => button.textContent === 'Wznów zastosowanie',
        ),
        status === 'failed',
      );
    } finally {
      await view.close();
    }
  });

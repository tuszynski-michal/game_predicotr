import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
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
registerHooks({
  load(url, context, next) {
    if (url.endsWith('/src/api/admin-api-client.ts'))
      return {
        format: 'module',
        shortCircuit: true,
        source:
          'export function createConfiguredAdminApiClient(){return globalThis.workspaceFixture;}',
      };
    return next(url, context);
  },
});
const { GridModelWorkspace } =
  await import('../src/features/model-quality/grid-model-workspace.tsx');
const { GridTrainingRunPanel } =
  await import('../src/features/model-quality/grid-training-run-panel.tsx');
const { GridModelVersionsPanel } =
  await import('../src/features/model-quality/grid-model-versions-panel.tsx');
const { cohortLabel, modelCommandKey } =
  await import('../src/features/model-quality/grid-model-state.ts');

const apiBaseUrl = 'http://127.0.0.1:8000';
const GAME = '11111111-1111-4111-8111-111111111111';
const OTHER = '22222222-2222-4222-8222-222222222222';
const COHORT = '33333333-3333-4333-8333-333333333333';
const OTHER_COHORT = '44444444-4444-4444-8444-444444444444';
const header = (gameId, id, createdAt) => ({
  id,
  gameId,
  status: 'frozen',
  mode: 'grid-only',
  createdAt,
  revision: 2,
});
const games = [
  {
    id: GAME,
    name: 'Mumie',
    code: 'mumie',
    shapeGeometryConfiguration: 'neural_grid_v3',
  },
  {
    id: OTHER,
    name: '777a2',
    code: '777a2',
    shapeGeometryConfiguration: 'neural_grid_v3',
  },
  {
    id: 'legacy',
    name: 'Stara 777',
    code: '7',
    shapeGeometryConfiguration: 'classical',
  },
];
const preset = {
  presetId: 'grid-only-v1',
  fingerprint: 'f'.repeat(64),
  mode: 'grid-only',
};

async function mount(element, saved = {}) {
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
  const render = async (next) => act(async () => root.render(next));
  await render(element);
  return {
    render,
    async close() {
      await act(async () => root.unmount());
      dom.window.close();
      Object.assign(globalThis, previous);
    },
  };
}
const buttons = () => [...document.querySelectorAll('button')];
async function click(text) {
  const button = buttons().find((item) => item.textContent === text);
  assert.ok(button, text);
  await act(async () => button.click());
}
async function choose(select, value) {
  await act(async () => {
    select.value = value;
    select.dispatchEvent(new window.Event('change', { bubbles: true }));
  });
}
const optionValue = (select, label) =>
  [...select.options].find((option) => option.textContent === label)?.value;
const settle = () =>
  act(async () => new Promise((resolve) => setTimeout(resolve, 10)));

test('entering the whole V3 section only reads, whatever the backend answers', async () => {
  const calls = [];
  globalThis.workspaceFixture = new Proxy(
    {},
    {
      get: (_target, name) =>
        typeof name === 'string' && name !== 'then'
          ? async () => {
              calls.push(name);
              return { error: {} };
            }
          : undefined,
    },
  );
  const view = await mount(
    React.createElement(GridModelWorkspace, { apiBaseUrl, gameId: GAME }),
  );
  try {
    await act(async () => new Promise((resolve) => setTimeout(resolve, 20)));
    assert.ok(calls.length > 5, calls.join(','));
    const writes = calls.filter((name) => !/^(list|get|preview)/.test(name));
    assert.deepEqual(writes, []);
    for (const step of [
      'Trening',
      'Porównanie z bazą',
      'Wersje',
      'Ponowne rozpoznanie',
    ])
      assert.match(document.body.textContent, new RegExp(step));
  } finally {
    await view.close();
  }
});

function runFixture() {
  const calls = [];
  const client = {
    async listGames() {
      calls.push(['GET', 'games']);
      return { data: games };
    },
    async listGridModelVersions() {
      calls.push(['GET', 'versions']);
      return { data: [] };
    },
    async listGridTrainingCohorts(game) {
      calls.push(['GET', 'cohorts', game]);
      return {
        data: {
          items:
            game === GAME
              ? [header(GAME, COHORT, '2026-10-01T08:00:00Z')]
              : [header(OTHER, OTHER_COHORT, '2026-10-02T09:00:00Z')],
          nextCursor: null,
        },
      };
    },
    async previewGridTrainingRun(game, cohort) {
      calls.push(['GET', 'preview', game, cohort]);
      return {
        data: {
          cohortId: cohort,
          gameId: game,
          presets: [preset],
          selectedPresetId: preset.presetId,
          apiBlockers: ['GRID_RUN_LEASE_BUSY'],
          cohortReasons: [],
          cohortQualification: 'eligible',
          cost: { plannedSteps: 1200 },
        },
      };
    },
    async listGridTrainingRuns(game) {
      calls.push(['GET', 'runs', game]);
      return { data: { items: [] } };
    },
    async createGridTrainingRun(game, body) {
      const saved = JSON.parse(
        window.localStorage.getItem(modelCommandKey(apiBaseUrl, game, 'run')),
      );
      calls.push(['POST', game, structuredClone(body), saved.body]);
      return { error: { code: 'LOST' } };
    },
    async cancelGridTrainingRun() {
      throw new Error('not expected');
    },
    async resumeGridTrainingRun() {
      throw new Error('not expected');
    },
  };
  return { client, calls };
}

test('a shared run is chosen by game and cohort names and saved before it is sent', async () => {
  const f = runFixture();
  const view = await mount(
    React.createElement(GridTrainingRunPanel, {
      apiBaseUrl,
      gameId: GAME,
      client: f.client,
    }),
  );
  try {
    assert.ok(f.calls.every((call) => call[0] === 'GET'));
    assert.equal(document.querySelectorAll('textarea').length, 0);
    const cohortSelect = document.querySelector('select');
    const ownLabel = cohortLabel(header(GAME, COHORT, '2026-10-01T08:00:00Z'));
    await choose(cohortSelect, optionValue(cohortSelect, ownLabel));
    assert.match(
      document.body.textContent,
      /GPU jest zajęte — run poczeka w kolejce/,
    );
    const shared = [...document.querySelectorAll('label')].find((label) =>
      label.textContent.includes('777a2 (777a2)'),
    );
    assert.ok(shared && !document.body.textContent.includes('Stara 777'));
    await act(async () => shared.querySelector('input').click());
    const otherSelect = document.querySelector(
      'select[aria-label="Kohorta gry 777a2"]',
    );
    const otherLabel = cohortLabel(
      header(OTHER, OTHER_COHORT, '2026-10-02T09:00:00Z'),
    );
    await choose(otherSelect, optionValue(otherSelect, otherLabel));
    await click('Uruchom trening');
    const post = f.calls.find((call) => call[0] === 'POST');
    assert.ok(post);
    assert.deepEqual(post[2], {
      idempotencyKey: post[2].idempotencyKey,
      cohortId: COHORT,
      presetId: preset.presetId,
      presetFingerprint: preset.fingerprint,
      sharedCohorts: [{ gameId: OTHER, cohortId: OTHER_COHORT }],
    });
    assert.deepEqual(
      post[3],
      post[2],
      'the exact body was saved before the request',
    );
    // A lost answer keeps the command for an explicit retry.
    assert.match(document.body.textContent, /Zapisane zlecenie runu czeka/);
  } finally {
    await view.close();
  }
});

test('changing the game discards the previous selection and reads the new game only', async () => {
  const f = runFixture();
  const view = await mount(
    React.createElement(GridTrainingRunPanel, {
      apiBaseUrl,
      gameId: GAME,
      client: f.client,
    }),
  );
  try {
    const cohortSelect = document.querySelector('select');
    await choose(cohortSelect, COHORT);
    f.calls.length = 0;
    await view.render(
      React.createElement(GridTrainingRunPanel, {
        apiBaseUrl,
        gameId: OTHER,
        client: f.client,
      }),
    );
    await act(async () => new Promise((resolve) => setTimeout(resolve, 10)));
    assert.equal(document.querySelector('select').value, '');
    assert.ok(f.calls.every((call) => call[0] === 'GET'));
    assert.ok(
      f.calls
        .filter((call) => call[1] === 'cohorts' || call[1] === 'runs')
        .every((call) => call[2] === OTHER),
    );
    assert.doesNotMatch(document.body.textContent, /Podgląd runu/);
  } finally {
    await view.close();
  }
});

const version = (id, family, label, base, extra = {}) => ({
  manifest: {
    versionId: id,
    familyLabel: family,
    version: label,
    baseVersionId: base,
    admission: base ? 'not_evaluated' : 'historical_baseline',
  },
  available: true,
  reasonCode: 'GRID_MODEL_ARTIFACT_AVAILABLE',
  published: false,
  eligible: false,
  eligibilityReasonCode: 'GRID_MODEL_NOT_PUBLISHED',
  ...extra,
});

function versionsFixture(verdict) {
  const calls = [];
  const versions = [
    version('base-m', 'Mumie', 'v1', null, { published: true, eligible: true }),
    version('base-7', '777 v2', 'v1', null, {
      published: true,
      eligible: false,
      eligibilityReasonCode: 'GRID_MODEL_EVALUATION_STALE',
    }),
    version('shared', 'Mumie', 'r-shared', 'base-m'),
  ];
  const client = {
    async listGridModelVersions() {
      calls.push('GET versions');
      return { data: versions };
    },
    async getGridModelDefault() {
      calls.push('GET default');
      return {
        data: {
          revision: 1,
          version: versions[0],
          eligible: true,
          reasonCode: 'GRID_MODEL_ELIGIBLE',
        },
      };
    },
    async getGameGridModelAssignment(game) {
      calls.push('GET assignment');
      return {
        data: {
          gameId: game,
          revision: 2,
          eventCount: 2,
          version: versions[0],
        },
      };
    },
    async getGameGridModelHistory() {
      calls.push('GET history');
      return {
        data: [
          {
            kind: 'historical_assignment',
            createdAt: '2026-10-01T08:00:00Z',
            versionId: 'base-7',
            revision: 1,
            actor: 'x',
            gameId: GAME,
          },
          {
            kind: 'activate',
            createdAt: '2026-10-02T08:00:00Z',
            versionId: 'base-m',
            revision: 2,
            actor: 'x',
            gameId: GAME,
          },
        ],
      };
    },
    async listGridModelEvaluations() {
      calls.push('GET evaluations');
      return {
        data: {
          items: [
            {
              evaluationId: 'e1',
              reportId: 'r1',
              createdAt: '2026-10-03T08:00:00Z',
              status: 'completed',
              verdict,
            },
          ],
        },
      };
    },
    async getGridModelEvaluation() {
      calls.push('GET evaluation');
      return {
        data: {
          evaluationId: 'e1',
          reportId: 'r1',
          status: 'completed',
          report: { verdict },
          currentness: [{ state: 'current' }, { state: 'current' }],
        },
      };
    },
    async publishGridModelVersion(id, body) {
      calls.push(['POST publish', id, body]);
      return { data: {} };
    },
    async activateGameGridModel() {
      calls.push('POST activate');
      return { data: {} };
    },
    async setGridModelDefault() {
      calls.push('POST default');
      return { data: {} };
    },
    async rollbackGameGridModel(game, body) {
      calls.push(['POST rollback', game, body]);
      return { data: {} };
    },
  };
  return { client, calls };
}

test('two bases and a rejected shared candidate stay usable and never publish', async () => {
  const f = versionsFixture('REVISE');
  const view = await mount(
    React.createElement(GridModelVersionsPanel, {
      apiBaseUrl,
      gameId: GAME,
      client: f.client,
    }),
  );
  try {
    assert.ok(
      f.calls.every(
        (call) => typeof call === 'string' && call.startsWith('GET'),
      ),
    );
    const text = document.body.textContent;
    assert.match(text, /Mumie · v1/);
    assert.match(text, /777 v2 · v1 · Dowód oceny jest nieaktualny/);
    const candidate = document.querySelector('select');
    assert.ok(optionValue(candidate, 'Mumie · r-shared · baza Mumie · v1'));
    await choose(candidate, 'shared');
    const evaluation = [...document.querySelectorAll('select')][1];
    await choose(evaluation, 'e1');
    const publish = buttons().find(
      (item) => item.textContent === 'Opublikuj kandydata',
    );
    assert.equal(publish.disabled, true);
    assert.match(document.body.textContent, /Kandydat wymaga poprawy/);
    // Earlier versions of the game can be restored explicitly; nothing switched by itself.
    assert.ok(
      buttons().some((item) => item.textContent === 'Przywróć w tej grze'),
    );
    assert.ok(f.calls.every((call) => typeof call === 'string'));
  } finally {
    await view.close();
  }
});

test('a measured PASS with current proofs publishes with its report as evidence', async () => {
  const f = versionsFixture('PASS');
  const view = await mount(
    React.createElement(GridModelVersionsPanel, {
      apiBaseUrl,
      gameId: GAME,
      client: f.client,
    }),
  );
  try {
    await choose(document.querySelector('select'), 'shared');
    await choose([...document.querySelectorAll('select')][1], 'e1');
    await click('Opublikuj kandydata');
    const post = f.calls.find(
      (call) => Array.isArray(call) && call[0] === 'POST publish',
    );
    assert.equal(post[1], 'shared');
    assert.deepEqual(post[2], {
      idempotencyKey: post[2].idempotencyKey,
      expectedRevision: 0,
      evaluationId: 'r1',
    });
  } finally {
    await view.close();
  }
});

test('a frozen cohort on the second catalogue page can be trained', async () => {
  const f = runFixture();
  const pages = [];
  f.client.listGridTrainingCohorts = async (game, options = {}) => {
    pages.push([game, options.cursor ?? null]);
    return options.cursor
      ? {
          data: {
            items: [header(game, COHORT, '2026-10-01T08:00:00Z')],
            nextCursor: null,
          },
        }
      : { data: { items: [], nextCursor: 'page-2' } };
  };
  const view = await mount(
    React.createElement(GridTrainingRunPanel, {
      apiBaseUrl,
      gameId: GAME,
      client: f.client,
    }),
  );
  try {
    await settle();
    assert.deepEqual(pages, [
      [GAME, null],
      [GAME, 'page-2'],
    ]);
    const select = document.querySelector('select');
    const label = cohortLabel(header(GAME, COHORT, '2026-10-01T08:00:00Z'));
    assert.equal(optionValue(select, label), COHORT);
  } finally {
    await view.close();
  }
});

test('a lost run answer survives a remount and is retried only explicitly with the same body', async () => {
  const f = runFixture();
  const panel = () =>
    React.createElement(GridTrainingRunPanel, {
      apiBaseUrl,
      gameId: GAME,
      client: f.client,
    });
  const key = modelCommandKey(apiBaseUrl, GAME, 'run');
  let view = await mount(panel());
  let saved;
  try {
    await choose(document.querySelector('select'), COHORT);
    await click('Uruchom trening');
    saved = window.localStorage.getItem(key);
    assert.ok(saved);
  } finally {
    await view.close();
  }
  f.calls.length = 0;
  view = await mount(panel(), { [key]: saved });
  try {
    await settle();
    assert.match(document.body.textContent, /Zapisane zlecenie runu czeka/);
    assert.ok(
      f.calls.every((call) => call[0] === 'GET'),
      'a remount never sends the command by itself',
    );
    const first = JSON.parse(saved).body;
    await click('Ponów zapisane zlecenie');
    const retry = f.calls.filter((call) => call[0] === 'POST');
    assert.equal(retry.length, 1);
    assert.deepEqual(retry[0][2], first, 'same key and body');
    // A refusal (409) is an answer: the command is cleared, not retried forever.
    f.client.createGridTrainingRun = async (game, body) => {
      f.calls.push(['POST', game, structuredClone(body)]);
      return {
        error: { code: 'GRID_RUN_IDEMPOTENCY_CONFLICT' },
        response: { status: 409 },
      };
    };
    await click('Ponów zapisane zlecenie');
    assert.equal(window.localStorage.getItem(key), null);
    assert.doesNotMatch(document.body.textContent, /Zapisane zlecenie runu/);
    assert.match(document.body.textContent, /Backend odrzucił zlecenie/);
  } finally {
    await view.close();
  }
});

test('a lost version command survives a remount; a revision conflict clears it after a fresh read', async () => {
  const f = versionsFixture('PASS');
  let answer = { error: { code: 'LOST' } };
  f.client.publishGridModelVersion = async (id, body) => {
    f.calls.push(['POST publish', id, structuredClone(body)]);
    return answer;
  };
  const panel = () =>
    React.createElement(GridModelVersionsPanel, {
      apiBaseUrl,
      gameId: GAME,
      client: f.client,
    });
  const key = modelCommandKey(apiBaseUrl, GAME, 'versions');
  let view = await mount(panel());
  let saved;
  try {
    await choose(document.querySelector('select'), 'shared');
    await choose([...document.querySelectorAll('select')][1], 'e1');
    await click('Opublikuj kandydata');
    saved = window.localStorage.getItem(key);
    assert.ok(saved);
  } finally {
    await view.close();
  }
  f.calls.length = 0;
  view = await mount(panel(), { [key]: saved });
  try {
    await settle();
    assert.match(document.body.textContent, /Zapisane polecenie wersji czeka/);
    assert.ok(f.calls.every((call) => typeof call === 'string'));
    answer = {
      error: { code: 'GRID_MODEL_REVISION_CONFLICT' },
      response: { status: 409 },
    };
    await click('Ponów zapisane polecenie');
    const posts = f.calls.filter((call) => Array.isArray(call));
    assert.equal(posts.length, 1);
    assert.deepEqual(
      { target: posts[0][1], ...posts[0][2] },
      {
        target: JSON.parse(saved).target,
        ...JSON.parse(saved).body,
        evaluationId: 'r1',
      },
    );
    assert.equal(window.localStorage.getItem(key), null);
    assert.match(document.body.textContent, /Backend odrzucił polecenie/);
    // The refusal re-read the catalogue, so the panel shows the current state.
    assert.ok(f.calls.filter((call) => call === 'GET versions').length >= 2);
  } finally {
    await view.close();
  }
});

test('clearing the evaluation before a late answer keeps publication blocked', async () => {
  const f = versionsFixture('PASS');
  let release;
  const late = new Promise((resolve) => {
    release = resolve;
  });
  const original = f.client.getGridModelEvaluation;
  f.client.getGridModelEvaluation = async (id) => {
    await late;
    return original(id);
  };
  const view = await mount(
    React.createElement(GridModelVersionsPanel, {
      apiBaseUrl,
      gameId: GAME,
      client: f.client,
    }),
  );
  try {
    await choose(document.querySelector('select'), 'shared');
    const evaluation = [...document.querySelectorAll('select')][1];
    await choose(evaluation, 'e1');
    await choose(evaluation, '');
    await act(async () => {
      release();
      await late;
    });
    await settle();
    const publish = buttons().find(
      (item) => item.textContent === 'Opublikuj kandydata',
    );
    assert.equal(publish.disabled, true);
    assert.match(document.body.textContent, /Wybierz ocenę kandydata/);
  } finally {
    await view.close();
  }
});

test('another step changing data re-reads the training lists without a reload', async () => {
  const f = runFixture();
  let frozen = false;
  f.client.listGridTrainingCohorts = async (game) => {
    f.calls.push(['GET', 'cohorts', game]);
    return {
      data: {
        items: frozen ? [header(game, COHORT, '2026-10-01T08:00:00Z')] : [],
        nextCursor: null,
      },
    };
  };
  const panel = (refreshKey) =>
    React.createElement(GridTrainingRunPanel, {
      apiBaseUrl,
      gameId: GAME,
      client: f.client,
      refreshKey,
    });
  const view = await mount(panel(0));
  try {
    await settle();
    assert.equal(document.querySelector('select').options.length, 1);
    frozen = true; // the cohort step froze a cohort
    await view.render(panel(1));
    await settle();
    const label = cohortLabel(header(GAME, COHORT, '2026-10-01T08:00:00Z'));
    assert.equal(optionValue(document.querySelector('select'), label), COHORT);
    assert.ok(f.calls.every((call) => call[0] === 'GET'));
  } finally {
    await view.close();
  }
});

test('a confirmed run in the workspace makes the other steps re-read their lists', async () => {
  const counts = {};
  const implementations = {
    async listGames() {
      return { data: games };
    },
    async listGridTrainingCohorts(game) {
      return {
        data: {
          items: [header(game, COHORT, '2026-10-01T08:00:00Z')],
          nextCursor: null,
        },
      };
    },
    async previewGridTrainingRun(game, cohort) {
      return {
        data: {
          cohortId: cohort,
          gameId: game,
          presets: [preset],
          selectedPresetId: preset.presetId,
          apiBlockers: [],
          cohortReasons: [],
          cohortQualification: 'eligible',
          cost: { plannedSteps: 40 },
        },
      };
    },
    async createGridTrainingRun(game, body) {
      return { data: { runId: 'run-1', gameId: game, body } };
    },
  };
  globalThis.workspaceFixture = new Proxy(
    {},
    {
      get: (_target, name) =>
        typeof name === 'string' && name !== 'then'
          ? async (...args) => {
              counts[name] = (counts[name] ?? 0) + 1;
              return implementations[name]
                ? implementations[name](...args)
                : { error: {} };
            }
          : undefined,
    },
  );
  const view = await mount(
    React.createElement(GridModelWorkspace, { apiBaseUrl, gameId: GAME }),
  );
  try {
    await settle();
    const before = { ...counts };
    const label = cohortLabel(header(GAME, COHORT, '2026-10-01T08:00:00Z'));
    const select = [...document.querySelectorAll('select')].find(
      (item) => optionValue(item, label) === COHORT,
    );
    await choose(select, COHORT);
    await click('Uruchom trening');
    await settle();
    assert.equal(counts.createGridTrainingRun, 1);
    for (const read of [
      'listGridModelVersions',
      'getGridModelDefault',
      'listSourceRecordingGroups',
      'getGameGridModelAssignment',
    ])
      assert.ok(
        (counts[read] ?? 0) > (before[read] ?? 0),
        `${read} re-read after the confirmed run`,
      );
    assert.ok(counts.listGridTrainingRuns > before.listGridTrainingRuns);
  } finally {
    await view.close();
  }
});

test('a run finished by the worker is noticed by reading only and unlocks the next steps', async () => {
  const f = runFixture();
  let status = 'processing';
  f.client.listGridTrainingRuns = async (game) => {
    f.calls.push(['GET', 'runs', game]);
    return {
      data: {
        items: [
          {
            runId: 'run-1',
            gameId: game,
            cohortId: COHORT,
            status,
            mode: 'grid-only',
            progressCurrent: status === 'completed' ? 40 : 3,
            progressTotal: 40,
            candidateVersionId: status === 'completed' ? 'cand' : null,
            cancelRequested: false,
            createdAt: '2026-10-16T08:00:00Z',
          },
        ],
      },
    };
  };
  let changed = 0;
  const view = await mount(
    React.createElement(GridTrainingRunPanel, {
      apiBaseUrl,
      gameId: GAME,
      client: f.client,
      pollMs: 5,
      onChanged: () => {
        changed += 1;
      },
    }),
  );
  try {
    await settle();
    assert.equal(changed, 0);
    status = 'completed';
    await act(async () => new Promise((resolve) => setTimeout(resolve, 30)));
    assert.equal(changed, 1, 'the finished run notifies the later steps once');
    const reads = f.calls.filter((call) => call[1] === 'runs').length;
    await act(async () => new Promise((resolve) => setTimeout(resolve, 30)));
    assert.equal(
      f.calls.filter((call) => call[1] === 'runs').length,
      reads,
      'no polling once nothing is running',
    );
    assert.ok(f.calls.every((call) => call[0] === 'GET'));
  } finally {
    await view.close();
  }
});

test('a new evaluation of the chosen candidate appears after a change elsewhere', async () => {
  const f = versionsFixture('PASS');
  let items = [];
  f.client.listGridModelEvaluations = async () => {
    f.calls.push('GET evaluations');
    return { data: { items } };
  };
  const panel = (refreshKey) =>
    React.createElement(GridModelVersionsPanel, {
      apiBaseUrl,
      gameId: GAME,
      client: f.client,
      refreshKey,
    });
  const view = await mount(panel(0));
  try {
    await choose(document.querySelector('select'), 'shared');
    assert.equal([...document.querySelectorAll('select')][1].options.length, 1);
    items = [
      {
        evaluationId: 'e1',
        reportId: 'r1',
        createdAt: '2026-10-03T08:00:00Z',
        status: 'completed',
        verdict: 'PASS',
      },
    ];
    await view.render(panel(1)); // the comparison step created an evaluation
    await settle();
    const evaluation = [...document.querySelectorAll('select')][1];
    assert.equal(document.querySelector('select').value, 'shared');
    assert.equal(evaluation.options.length, 2);
    assert.ok(f.calls.every((call) => typeof call === 'string'));
  } finally {
    await view.close();
  }
});

test('a currentness check elsewhere unblocks the chosen evaluation without choosing again', async () => {
  const f = versionsFixture('PASS');
  let state = 'stale';
  f.client.getGridModelEvaluation = async () => {
    f.calls.push('GET evaluation');
    return {
      data: {
        evaluationId: 'e1',
        reportId: 'r1',
        status: 'completed',
        report: { verdict: 'PASS' },
        currentness: [{ state }],
      },
    };
  };
  const panel = (refreshKey) =>
    React.createElement(GridModelVersionsPanel, {
      apiBaseUrl,
      gameId: GAME,
      client: f.client,
      refreshKey,
    });
  const view = await mount(panel(0));
  try {
    await choose(document.querySelector('select'), 'shared');
    await choose([...document.querySelectorAll('select')][1], 'e1');
    const publish = () =>
      buttons().find((item) => item.textContent === 'Opublikuj kandydata');
    assert.equal(publish().disabled, true);
    state = 'current'; // the comparison step proved the cohorts current
    await view.render(panel(1));
    await settle();
    assert.equal(publish().disabled, false);
    assert.ok(f.calls.every((call) => typeof call === 'string'));
  } finally {
    await view.close();
  }
});

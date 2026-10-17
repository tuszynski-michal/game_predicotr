import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import test from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';
import {
  gridCohortCommandKey,
  gridCohortSelectionKey,
} from '../src/features/model-quality/grid-cohort-command-storage.ts';
import { cohortLabel } from '../src/features/model-quality/grid-model-state.ts';

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
          'export function createConfiguredAdminApiClient(){throw new Error("Injected client required");}',
      };
    return next(url, context);
  },
});
const { GridCohortPreview } =
  await import('../src/features/model-quality/grid-cohort-preview.tsx');
const apiBaseUrl = 'http://127.0.0.1:8000',
  game = '11111111-1111-4111-8111-111111111111',
  cohort = '22222222-2222-4222-8222-222222222222';
const key = '33333333-3333-4333-8333-333333333333';
const pending = {
  kind: 'materialize-page',
  cohortId: cohort,
  body: { idempotencyKey: key, expectedRevision: 3, cursor: 5 },
};
const header = (gameId = game) => ({
  id: cohort,
  gameId,
  revision: 3,
  status: 'materializing',
  mode: 'grid-only',
  familyId: key,
  baseVersionId: key,
  previewSha256: 'a'.repeat(64),
  manifestSha256: null,
  nextCaptureCursor: null,
  nextMaterializationCursor: 5,
  createdAt: 'now',
  summary: {
    roles: [
      {
        role: 'VALIDATION',
        requiredBoards: 15,
        requiredPhotos: 5,
        requiredFullPhotos: 5,
        eligibleBoards: 9,
        eligiblePhotos: 1,
        eligibleFullPhotos: 1,
        materializedBoards: 0,
        materializedPhotos: 0,
        materializedFullPhotos: 0,
        missingBoards: 6,
        missingPhotos: 4,
        missingFullPhotos: 4,
        recordingRequired: true,
      },
    ],
    reasonCounts: { RECORDING_MEMBERSHIP_REQUIRED: 1 },
  },
});
function fixture(extra = {}) {
  const calls = [];
  const api = {
    async listGridTrainingCohorts(g) {
      calls.push(['GET-list', g]);
      return { data: { items: [header(g)], nextCursor: null } };
    },
    async getGridTrainingCohort(g) {
      calls.push(['GET-header', g]);
      return { data: header(g) };
    },
    async getGridTrainingCohortMembers(g) {
      calls.push(['GET-members', g]);
      return {
        data: {
          items: [
            {
              sourceId: key,
              role: null,
              qualification: 'unresolved',
              boardEligibleCount: 0,
              screenEligible: false,
              metadataMissing: true,
              reasons: ['RECORDING_MEMBERSHIP_REQUIRED'],
            },
          ],
          nextCursor: null,
        },
      };
    },
    async getGridTrainingCohortEligibility(g) {
      calls.push(['GET-eligibility', g]);
      return {
        data: {
          qualification: 'unresolved',
          reasons: ['SOURCE_RETENTION_POLICY_PENDING'],
          manifestSha256: null,
          humanLabelWithdrawn: null,
          liveSourceLinked: null,
          snapshotBytesAvailable: null,
        },
      };
    },
    async materializeGridTrainingCohortPage(g, id, body) {
      calls.push(['POST', g, id, structuredClone(body)]);
      assert.deepEqual(
        JSON.parse(
          window.localStorage.getItem(gridCohortCommandKey(apiBaseUrl, g)),
        ).command.body,
        body,
      );
      return { error: { code: 'CONFLICT' } };
    },
    // TASK-1000: family/base come from the assignment, recordings and imports by name.
    async getGameGridModelAssignment(g) {
      calls.push(['GET-assignment', g]);
      return {
        data: { gameId: g, eventCount: 0, revision: null, version: null },
      };
    },
    async listSourceRecordingGroups(g) {
      calls.push(['GET-recordings', g]);
      return { data: { items: [], nextCursor: null } };
    },
    async listJobs() {
      calls.push(['GET-jobs']);
      return { data: [] };
    },
    async listGridModelVersions() {
      calls.push(['GET-versions']);
      return { data: [] };
    },
    ...extra,
  };
  return { api, calls };
}
async function mount(api, saved = {}) {
  const dom = new JSDOM('<div id="root"></div>', {
      url: 'http://127.0.0.1:3000',
    }),
    previous = {};
  for (const [k, v] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    previous[k] = globalThis[k];
    globalThis[k] = v;
  }
  for (const [k, v] of Object.entries(saved)) window.localStorage.setItem(k, v);
  const root = createRoot(document.getElementById('root'));
  const render = async (gameId = game) =>
    act(async () =>
      root.render(
        React.createElement(GridCohortPreview, {
          apiBaseUrl,
          gameId,
          client: api,
        }),
      ),
    );
  await render();
  return {
    render,
    async close() {
      await act(async () => root.unmount());
      dom.window.close();
      Object.assign(globalThis, previous);
    },
  };
}
async function click(text) {
  const button = [...document.querySelectorAll('button')].find(
    (b) => b.textContent === text,
  );
  assert.ok(button, text);
  await act(async () => button.click());
}
for (const withdrawn of [false, true]) {
  test(`metadata facts preserve proven withdrawal=${withdrawn} separately from byte availability`, async () => {
    const f = fixture({
      getGridTrainingCohortEligibility: async () => ({
        data: {
          qualification: 'blocked',
          reasons: ['LABEL_STALE'],
          manifestSha256: null,
          humanLabelWithdrawn: withdrawn,
          liveSourceLinked: !withdrawn,
          snapshotBytesAvailable: null,
        },
      }),
    });
    const view = await mount(f.api, {
      [gridCohortSelectionKey(apiBaseUrl, game)]: cohort,
    });
    try {
      assert.ok(
        document.body.textContent.includes(
          `Cofnięcie ludzkiego zatwierdzenia: ${withdrawn ? 'potwierdzone' : 'nie stwierdzono'}`,
        ),
      );
      assert.ok(
        document.body.textContent.includes(
          `Aktualne powiązanie źródeł: ${withdrawn ? 'odłączone' : 'potwierdzone'}`,
        ),
      );
      assert.match(
        document.body.textContent,
        /Aktualna dostępność kopii: nie sprawdzono/,
      );
      assert.ok(f.calls.every((call) => call[0].startsWith('GET')));
    } finally {
      await view.close();
    }
  });
}

test('reload performs GET only; saved exact body survives conflict and explicit retry', async () => {
  const f = fixture(),
    saved = {
      [gridCohortCommandKey(apiBaseUrl, game)]: JSON.stringify({
        api: apiBaseUrl,
        game,
        command: pending,
      }),
      [gridCohortSelectionKey(apiBaseUrl, game)]: cohort,
    };
  const view = await mount(f.api, saved);
  try {
    assert.ok(f.calls.every((c) => c[0].startsWith('GET')));
    assert.match(document.body.textContent, /45 etykiet/);
    assert.match(
      document.body.textContent,
      /Polityka przechowywania kopii czeka na decyzję/,
    );
    assert.match(
      document.body.textContent,
      /Cofnięcie ludzkiego zatwierdzenia: nie ustalono/,
    );
    assert.match(
      document.body.textContent,
      /Aktualne powiązanie źródeł: nie ustalono/,
    );
    assert.match(
      document.body.textContent,
      /Aktualna dostępność kopii: nie sprawdzono/,
    );
    assert.match(
      document.body.textContent,
      /nie jest pozwoleniem na uruchomienie treningu/,
    );
    await click('Ponów zapisane polecenie');
    await click('Ponów zapisane polecenie');
    assert.deepEqual(
      f.calls.filter((c) => c[0] === 'POST').map((c) => c[3]),
      [pending.body, pending.body],
    );
    assert.equal(
      JSON.parse(
        window.localStorage.getItem(gridCohortCommandKey(apiBaseUrl, game)),
      ).command.body.idempotencyKey,
      key,
    );
    assert.ok(
      [...document.querySelectorAll('fieldset')].every(
        (fieldset) => fieldset.disabled,
      ),
    );
  } finally {
    await view.close();
  }
});
test('explicit page reserves UUID and body before request; response loss retains operation across remount', async () => {
  const f = fixture();
  const view = await mount(f.api, {
    [gridCohortSelectionKey(apiBaseUrl, game)]: cohort,
  });
  let saved;
  try {
    await click('Skopiuj następną stronę źródeł (do 5)');
    assert.equal(f.calls.filter((c) => c[0] === 'POST').length, 1);
    saved = window.localStorage.getItem(gridCohortCommandKey(apiBaseUrl, game));
    assert.ok(saved);
  } finally {
    await view.close();
  }
  const second = fixture(),
    remount = await mount(second.api, {
      [gridCohortCommandKey(apiBaseUrl, game)]: saved,
    });
  try {
    assert.ok(second.calls.every((c) => c[0].startsWith('GET')));
    await click('Ponów zapisane polecenie');
    assert.deepEqual(
      second.calls.find((c) => c[0] === 'POST')[3],
      JSON.parse(saved).command.body,
    );
  } finally {
    await remount.close();
  }
});
test('late old-game detail cannot replace current game view', async () => {
  let resolve;
  const nextGame = '44444444-4444-4444-8444-444444444444';
  const f = fixture({
    getGridTrainingCohort: (g) =>
      g === game
        ? new Promise((r) => {
            resolve = r;
          })
        : Promise.resolve({ data: header(g) }),
  });
  const view = await mount(f.api, {
    [gridCohortSelectionKey(apiBaseUrl, game)]: cohort,
  });
  try {
    await view.render(nextGame);
    await act(async () => resolve({ data: { ...header(), status: 'frozen' } }));
    assert.doesNotMatch(document.body.textContent, /Zamrożona/);
    assert.equal(
      window.localStorage.getItem(gridCohortSelectionKey(apiBaseUrl, nextGame)),
      null,
    );
  } finally {
    await view.close();
  }
});

test('late detail from another selected cohort cannot replace the current cohort', async () => {
  const other = '44444444-4444-4444-8444-444444444444';
  const later = '2026-10-01T10:00:00Z';
  let resolve;
  const f = fixture({
    listGridTrainingCohorts: async () => ({
      data: {
        items: [header(), { ...header(), id: other, createdAt: later }],
        nextCursor: null,
      },
    }),
    getGridTrainingCohort: (g, id) =>
      id === cohort
        ? new Promise((r) => {
            resolve = r;
          })
        : Promise.resolve({ data: { ...header(g), id: other } }),
  });
  const view = await mount(f.api, {
    [gridCohortSelectionKey(apiBaseUrl, game)]: cohort,
  });
  try {
    await click(cohortLabel({ ...header(), id: other, createdAt: later }));
    await act(async () => resolve({ data: { ...header(), status: 'frozen' } }));
    assert.doesNotMatch(document.body.textContent, /Zamrożona/);
    assert.equal(
      window.localStorage.getItem(gridCohortSelectionKey(apiBaseUrl, game)),
      other,
    );
  } finally {
    await view.close();
  }
});

test('successful command receipt clears the exact durable body and reads current state', async () => {
  const f = fixture({
    materializeGridTrainingCohortPage: async (g, id, body) => ({
      data: {
        cohort: header(g),
        receipt: {
          idempotencyKey: body.idempotencyKey,
          kind: 'materialize-page',
          outcome: 'materialized',
          revision: 4,
        },
      },
    }),
  });
  const view = await mount(f.api, {
    [gridCohortSelectionKey(apiBaseUrl, game)]: cohort,
  });
  try {
    await click('Skopiuj następną stronę źródeł (do 5)');
    assert.equal(
      window.localStorage.getItem(gridCohortCommandKey(apiBaseUrl, game)),
      null,
    );
    assert.match(document.body.textContent, /Polecenie potwierdzone/);
    assert.match(document.body.textContent, /Sprawdzone kopie/);
  } finally {
    await view.close();
  }
});

const FAMILY_M = '44444444-4444-4444-8444-444444444444',
  BASE_M = '55555555-5555-4555-8555-555555555555',
  FAMILY_7 = '66666666-6666-4666-8666-666666666666',
  BASE_7 = '77777777-7777-4777-8777-777777777777';
const imports = [
  '81111111-1111-4111-8111-111111111111',
  '82222222-2222-4222-8222-222222222222',
  '83333333-3333-4333-8333-333333333333',
];
const manifest = (versionId, familyId, familyLabel) => ({
  versionId,
  familyId,
  familyLabel,
  version: 'v1',
  admission: 'historical_baseline',
});
const importJob = (id, name) => ({
  id,
  gameId: game,
  jobType: 'import',
  inputPayload: { importKind: 'image_directory', sourceDisplayName: name },
  createdAt: '2026-10-01T08:00:00Z',
  progress: {},
});
const recording = (id, role, importJobId) => ({
  id,
  revision: 3,
  membershipComplete: true,
  expectedSources: 10,
  registeredSources: 10,
  manifestId: id,
  manifestSha256: 'c'.repeat(64),
  pageCount: 1,
  createdAt: '2026-10-01T08:00:00Z',
  importJobId,
  declared: true,
  independent: true,
  role,
  qualification: 'eligible',
  reasonCodes: [],
});

test('a cohort of three named imports on a chosen catalogue base needs no typed identifier', async () => {
  const sent = [];
  const pages = [];
  const f = fixture({
    async getGameGridModelAssignment(g) {
      return {
        data: {
          gameId: g,
          eventCount: 1,
          revision: 1,
          version: { manifest: manifest(BASE_M, FAMILY_M, 'Mumie') },
        },
      };
    },
    async listGridModelVersions() {
      return {
        data: [
          {
            manifest: manifest(BASE_M, FAMILY_M, 'Mumie'),
            available: true,
            published: true,
          },
          {
            manifest: manifest(BASE_7, FAMILY_7, '777 v2'),
            available: true,
            published: true,
          },
        ],
      };
    },
    // The third recording is on the second page of the catalogue.
    async listSourceRecordingGroups(g, options) {
      pages.push(options.after ?? null);
      return options.after
        ? {
            data: {
              items: [
                recording(
                  '93333333-3333-4333-8333-333333333333',
                  'REGRESSION',
                  imports[2],
                ),
              ],
              nextCursor: null,
            },
          }
        : {
            data: {
              items: [
                recording(
                  '91111111-1111-4111-8111-111111111111',
                  'TRAIN',
                  imports[0],
                ),
                recording(
                  '92222222-2222-4222-8222-222222222222',
                  'VALIDATION',
                  imports[1],
                ),
              ],
              nextCursor: '92222222-2222-4222-8222-222222222222',
            },
          };
    },
    async listJobs() {
      return {
        data: [
          importJob(imports[0], 'Mumie poranek'),
          importJob(imports[1], 'Mumie wieczór'),
          importJob(imports[2], 'Mumie kontrola'),
        ],
      };
    },
    async prepareGridTrainingCohort(g, body) {
      sent.push([g, structuredClone(body)]);
      return { error: { code: 'LOST' } };
    },
  });
  const view = await mount(f.api);
  try {
    await act(async () => new Promise((resolve) => setTimeout(resolve, 10)));
    assert.deepEqual(pages, [null, '92222222-2222-4222-8222-222222222222']);
    for (const name of ['Mumie poranek', 'Mumie wieczór', 'Mumie kontrola']) {
      const label = [...document.querySelectorAll('label')].find(
        (item) =>
          item.textContent.includes(name) && item.querySelector('input'),
      );
      assert.ok(label, name);
      await act(async () => label.querySelector('input').click());
    }
    const base = [...document.querySelectorAll('select')].find((item) =>
      [...item.options].some((option) => option.value === BASE_7),
    );
    await act(async () => {
      base.value = BASE_7;
      base.dispatchEvent(new window.Event('change', { bubbles: true }));
    });
    assert.match(
      document.body.textContent,
      /Importy w kohorcie: Mumie poranek.*; Mumie wieczór.*; Mumie kontrola/,
    );
    await click('Przygotuj metadane kohorty');
    assert.equal(sent.length, 1, document.body.textContent);
    const [target, body] = sent[0];
    assert.equal(target, game);
    assert.deepEqual(body, {
      idempotencyKey: body.idempotencyKey,
      familyId: FAMILY_7,
      baseVersionId: BASE_7,
      mode: 'grid-only',
      selector: { importJobIds: imports },
      recordings: [
        { groupId: '91111111-1111-4111-8111-111111111111', role: 'TRAIN' },
        { groupId: '92222222-2222-4222-8222-222222222222', role: 'VALIDATION' },
        { groupId: '93333333-3333-4333-8333-333333333333', role: 'REGRESSION' },
      ],
    });
    assert.equal(
      [...document.querySelectorAll('textarea')].every((item) => !item.value),
      true,
    );
  } finally {
    await view.close();
  }
});

test('one recording keeps the single-import body; the assigned base stays the default', async () => {
  const sent = [];
  const f = fixture({
    async getGameGridModelAssignment(g) {
      return {
        data: {
          gameId: g,
          eventCount: 1,
          revision: 1,
          trainingFamilyId: FAMILY_7,
          version: { manifest: manifest(BASE_M, FAMILY_M, 'Mumie') },
        },
      };
    },
    async listSourceRecordingGroups() {
      return {
        data: {
          items: [
            recording(
              '91111111-1111-4111-8111-111111111111',
              'TRAIN',
              imports[0],
            ),
          ],
          nextCursor: null,
        },
      };
    },
    async prepareGridTrainingCohort(g, body) {
      sent.push(structuredClone(body));
      return { error: { code: 'LOST' } };
    },
  });
  const view = await mount(f.api);
  try {
    await act(async () => new Promise((resolve) => setTimeout(resolve, 10)));
    const box = [...document.querySelectorAll('input[type="checkbox"]')][0];
    await act(async () => box.click());
    await click('Przygotuj metadane kohorty');
    assert.equal(sent[0].familyId, FAMILY_7);
    assert.equal(sent[0].baseVersionId, BASE_M);
    assert.deepEqual(sent[0].selector, { importJobId: imports[0] });
  } finally {
    await view.close();
  }
});

test('games with different training forks of one base share a named family without reassignment', async () => {
  const FORK_A = '88888888-8888-4888-8888-888888888888',
    FORK_B = '99999999-9999-4999-8999-999999999999';
  const other = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  const sent = [];
  const assignments = {
    // This game: base Mumie with its own fork; the other game: base 777 with a fork.
    [game]: {
      gameId: game,
      eventCount: 1,
      revision: 1,
      trainingFamilyId: FORK_A,
      trainingFamilyLabel: 'Mumie odbiór',
      version: { manifest: manifest(BASE_M, FAMILY_M, 'Mumie') },
    },
    [other]: {
      gameId: other,
      eventCount: 1,
      revision: 1,
      trainingFamilyId: FORK_B,
      trainingFamilyLabel: '777a2 odbiór',
      version: { manifest: manifest(BASE_7, FAMILY_7, '777 v2') },
    },
  };
  const f = fixture({
    async getGameGridModelAssignment(g) {
      return { data: assignments[g] };
    },
    async listGames() {
      return {
        data: [
          {
            id: game,
            name: 'Mumie',
            code: 'mumie',
            shapeGeometryConfiguration: 'neural_grid_v3',
          },
          {
            id: other,
            name: '777a2',
            code: '777a2',
            shapeGeometryConfiguration: 'neural_grid_v3',
          },
          {
            id: 'legacy',
            name: 'Stara 777',
            code: '7',
            shapeGeometryConfiguration: 'grid_profile_777_v2',
          },
        ],
      };
    },
    async listGridModelVersions() {
      return {
        data: [
          {
            manifest: manifest(BASE_M, FAMILY_M, 'Mumie'),
            available: true,
            published: true,
          },
          {
            manifest: manifest(BASE_7, FAMILY_7, '777 v2'),
            available: true,
            published: true,
          },
        ],
      };
    },
    async listSourceRecordingGroups() {
      return {
        data: {
          items: [
            recording(
              '91111111-1111-4111-8111-111111111111',
              'TRAIN',
              imports[0],
            ),
          ],
          nextCursor: null,
        },
      };
    },
    async prepareGridTrainingCohort(g, body) {
      sent.push(structuredClone(body));
      return { error: { code: 'LOST' } };
    },
  });
  const view = await mount(f.api);
  try {
    await act(async () => new Promise((resolve) => setTimeout(resolve, 10)));
    const selects = () => [...document.querySelectorAll('select')];
    const base = selects().find((item) =>
      [...item.options].some((option) => option.value === BASE_7),
    );
    await act(async () => {
      base.value = BASE_7;
      base.dispatchEvent(new window.Event('change', { bubbles: true }));
    });
    const family = selects().find((item) =>
      [...item.options].some((option) => option.value === FORK_B),
    );
    assert.ok(family, 'the fork of the other game is offered by name');
    assert.deepEqual(
      [...family.options].map((option) => option.textContent),
      ['777 v2 (rodzina bazy)', '777a2 odbiór (rodzina treningowa gry 777a2)'],
    );
    await act(async () => {
      family.value = FORK_B;
      family.dispatchEvent(new window.Event('change', { bubbles: true }));
    });
    const box = [...document.querySelectorAll('input[type="checkbox"]')][0];
    await act(async () => box.click());
    await click('Przygotuj metadane kohorty');
    assert.equal(sent[0].familyId, FORK_B);
    assert.equal(sent[0].baseVersionId, BASE_7);
    // Back on its own base the game keeps its own fork as the default.
    await act(async () => {
      base.value = '';
      base.dispatchEvent(new window.Event('change', { bubbles: true }));
    });
    const own = selects().find((item) =>
      [...item.options].some((option) => option.value === FORK_A),
    );
    assert.equal(own.value, FORK_A);
  } finally {
    await view.close();
  }
});

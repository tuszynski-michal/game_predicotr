import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import test from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';
import {
  gridCohortCommandKey,
  gridCohortSelectionKey,
} from '../src/features/model-quality/grid-cohort-command-storage.ts';

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
    assert.match(document.body.textContent, /SOURCE_RETENTION_POLICY_PENDING/);
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
  let resolve;
  const f = fixture({
    listGridTrainingCohorts: async () => ({
      data: { items: [header(), { ...header(), id: other }], nextCursor: null },
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
    await click(`${other} — Kopiowanie źródeł`);
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

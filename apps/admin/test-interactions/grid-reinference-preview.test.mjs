import assert from 'node:assert/strict';
import test from 'node:test';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';
import { GridReinferencePreview } from '../src/features/model-quality/grid-reinference-preview.tsx';
import { GridQualityPanel } from '../src/features/model-quality/grid-quality-panel.tsx';
import {
  gridCommandKey,
  gridViewKey,
} from '../src/features/model-quality/grid-reinference-command.ts';

const gameId = '11111111-1111-4111-8111-111111111111';
const operationId = '22222222-2222-4222-8222-222222222222';
const pilotId = '33333333-3333-4333-8333-333333333333';
const apiBaseUrl = 'http://127.0.0.1:8000';
const sha = 'a'.repeat(64);
const operation = (state = 'prepared', extra = {}) => ({
  gameId,
  operationId,
  jobId: pilotId,
  state,
  phase: 'infer',
  revision: 2,
  executionScope: 'pilot',
  selector: { categories: ['grid_issue', 'deferred'] },
  pilotAcknowledgement: null,
  executionQuarantine: null,
  manifestSha256: sha,
  reportSha256: null,
  sourceCount: 2,
  targetCount: 3,
  processedSources: 0,
  outcomes: {},
  sourceStatusCounts: {},
  modelSnapshot: { version: 'fixed' },
  runtimePolicy: 'runtime',
  acceptancePolicy: 'acceptance',
  membershipCapturedAt: 'capture',
  preparationStartedAt: 'start',
  preparationFinishedAt: 'finish',
  scopeStats: null,
  effectStats: null,
  ...extra,
});
function fixture(extra = {}) {
  const requests = [];
  let current = operation();
  return {
    requests,
    set(value) {
      current = value;
    },
    api: {
      async listGridReinferenceOperations(game, query) {
        requests.push(['list', game, query]);
        return { data: { items: [current], nextCursor: null } };
      },
      async getGridReinference(game, id) {
        requests.push(['get', game, id]);
        return { data: current };
      },
      async getGridReinferenceTargets(game, id) {
        requests.push(['targets', game, id]);
        return { data: { items: [], nextCursor: null } };
      },
      async prepareGridReinference(game, body) {
        requests.push(['prepare', game, body]);
        current = operation('preparing', {
          executionScope: body.executionScope,
        });
        return { data: current };
      },
      async freezeGridReinference(game, id, body) {
        requests.push(['freeze', game, id, body]);
        current = { ...current, state: 'frozen', revision: 3 };
        return { data: current };
      },
      async startGridReinference(game, id, body) {
        requests.push(['start', game, id, body]);
        current = { ...current, state: 'queued', revision: 4 };
        return { data: current };
      },
      async acknowledgeGridReinferencePilot(game, id, body) {
        requests.push(['ack', game, id, body]);
        current = {
          ...current,
          pilotAcknowledgement: {
            pilotOperationId: body.pilotOperationId,
            actor: 'owner',
          },
          revision: 4,
        };
        return { data: current };
      },
      async cancelGridReinference(game, id, body) {
        requests.push(['cancel', game, id, body]);
        current = { ...current, state: 'cancelled', revision: 5 };
        return { data: current };
      },
      async resumeGridReinference(game, id, body) {
        requests.push(['resume', game, id, body]);
        current = { ...current, state: 'queued', revision: 6 };
        return { data: current };
      },
      ...extra,
    },
  };
}
async function mount(api, saved = {}, Component = GridReinferencePreview) {
  const dom = new JSDOM('<div id="root"></div>', {
    url: 'http://127.0.0.1:3000',
  });
  const previous = {};
  for (const [key, value] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    localStorage: dom.window.localStorage,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    previous[key] = globalThis[key];
    globalThis[key] = value;
  }
  for (const [key, value] of Object.entries(saved))
    localStorage.setItem(key, value);
  const root = createRoot(document.getElementById('root'));
  const render = async (id = gameId) =>
    act(async () =>
      root.render(
        React.createElement(Component, {
          api,
          client: api,
          apiBaseUrl,
          gameId: id,
        }),
      ),
    );
  await render();
  return {
    render,
    async cleanup() {
      await act(async () => root.unmount());
      dom.window.close();
      Object.assign(globalThis, previous);
    },
  };
}
const button = (text) =>
  [...document.querySelectorAll('button')].find((item) =>
    item.textContent.includes(text),
  );
async function click(text) {
  const item = button(text);
  assert.ok(item, text);
  await act(async () => item.click());
}
async function change(select, value) {
  await act(async () => {
    select.value = value;
    select.dispatchEvent(new window.Event('change', { bubbles: true }));
  });
}
async function select() {
  await change(
    document.querySelector('[aria-label="Zapisana operacja"]'),
    operationId,
  );
}

test('mounted workflow reads only, defaults to issues/deferred and gates prepare, freeze, start', async () => {
  const f = fixture();
  const m = await mount(f.api);
  try {
    assert.deepEqual(
      f.requests.map((item) => item[0]),
      ['list'],
    );
    assert.deepEqual(
      [...document.querySelectorAll('fieldset input')].map(
        (item) => item.checked,
      ),
      [true, true, false, false],
    );
    await click('Przygotuj nowy pilot');
    assert.deepEqual(
      f.requests.find((item) => item[0] === 'prepare')[2].selector.categories,
      ['grid_issue', 'deferred'],
    );
    assert.match(document.body.textContent, /Przygotowanie zakresu/);
    assert.equal(button('Uruchom rozpoznanie'), undefined);
    f.set(operation());
    await click('Odśwież operację');
    assert.match(document.body.textContent, /Statystyki zakresu: nie zapisano/);
    await click('Zamroź podgląd');
    assert.ok(button('Uruchom rozpoznanie'));
    assert.equal(f.requests.filter((item) => item[0] === 'start').length, 0);
    await click('Uruchom rozpoznanie');
    assert.equal(
      f.requests.find((item) => item[0] === 'start')[3].expectedRevision,
      3,
    );
    assert.equal(
      f.requests.find((item) => item[0] === 'start')[3].manifestSha256,
      sha,
    );
    await click('Anuluj operację');
    await click('Wznów zapisaną fazę');
    assert.equal(
      f.requests.find((item) => item[0] === 'resume')[3].expectedPhase,
      'infer',
    );
    assert.equal(
      localStorage.getItem(gridCommandKey(apiBaseUrl, gameId)),
      null,
    );
  } finally {
    await m.cleanup();
  }
});

test('lost response persists exact body before POST and reload never retries automatically', async () => {
  let first;
  let calls = 0;
  const f = fixture({
    async prepareGridReinference(_game, body) {
      calls++;
      const saved = JSON.parse(
        localStorage.getItem(gridCommandKey(apiBaseUrl, gameId)),
      );
      assert.deepEqual(saved.command.body, body);
      if (!first) {
        first = body;
        throw new Error('Lost response');
      }
      assert.deepEqual(body, first);
      return { data: operation() };
    },
  });
  let m = await mount(f.api);
  let saved;
  try {
    await click('Przygotuj nowy pilot');
    assert.match(document.body.textContent, /Lost response/);
    saved = localStorage.getItem(gridCommandKey(apiBaseUrl, gameId));
  } finally {
    await m.cleanup();
  }
  m = await mount(f.api, { [gridCommandKey(apiBaseUrl, gameId)]: saved });
  try {
    assert.equal(calls, 1);
    await click('Ponów dokładne');
    assert.equal(calls, 2);
    assert.match(document.body.textContent, /Operacja 2222/);
  } finally {
    await m.cleanup();
  }
});

test('409 stays pending and explains command conflict separately from target outcomes', async () => {
  const f = fixture({
    async freezeGridReinference() {
      return {
        error: { code: 'REVISION_CONFLICT', message: 'Stale revision' },
        response: { status: 409 },
      };
    },
  });
  const m = await mount(f.api);
  try {
    await select();
    await click('Zamroź podgląd');
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /HTTP 409: nieaktualna komenda/,
    );
    assert.ok(localStorage.getItem(gridCommandKey(apiBaseUrl, gameId)));
    assert.equal(button('Przygotuj nowy pilot').disabled, true);
  } finally {
    await m.cleanup();
  }
});

test('broader discovers compatible pilots and requires explicit ACK and separate broad confirmation', async () => {
  const pilot = operation('completed', {
    operationId: pilotId,
    reportSha256: sha,
  });
  const f = fixture();
  f.set(operation('frozen', { executionScope: 'broader' }));
  const originalList = f.api.listGridReinferenceOperations;
  f.api.listGridReinferenceOperations = async (game, query) =>
    query.compatibleWithOperationId
      ? { data: { items: [pilot], nextCursor: null } }
      : originalList(game, query);
  const m = await mount(f.api);
  try {
    await select();
    assert.equal(button('Uruchom rozpoznanie').disabled, true);
    const pilotSelect = [...document.querySelectorAll('select')].find((item) =>
      item.parentElement.textContent.includes('Zgodny zakończony pilot'),
    );
    await change(pilotSelect, pilotId);
    await click('Potwierdź raport pilota');
    assert.equal(
      f.requests.find((item) => item[0] === 'ack')[3].pilotReportSha256,
      sha,
    );
    assert.equal(button('Uruchom rozpoznanie').disabled, true);
    const broad = [...document.querySelectorAll('input')].find((item) =>
      item.parentElement.textContent.includes(
        'Potwierdzam uruchomienie szerokiego',
      ),
    );
    await act(async () => broad.click());
    await click('Uruchom rozpoznanie');
    assert.equal(
      f.requests.find((item) => item[0] === 'start')[3].broadScopeConfirmed,
      true,
    );
  } finally {
    await m.cleanup();
  }
});

test('quarantine has no resume and late response cannot enter another game', async () => {
  let resolve;
  const f = fixture({
    async getGridReinference(game) {
      if (game === gameId) return new Promise((done) => (resolve = done));
      return {
        data: operation('failed', {
          gameId: game,
          executionQuarantine: { code: 'START_REQUIRED' },
        }),
      };
    },
  });
  const m = await mount(f.api);
  try {
    await select();
    const other = '44444444-4444-4444-8444-444444444444';
    await m.render(other);
    await act(async () => resolve({ data: operation() }));
    assert.doesNotMatch(document.body.textContent, /Operacja 2222/);
  } finally {
    await m.cleanup();
  }
  const q = fixture();
  q.set(
    operation('failed', { executionQuarantine: { code: 'START_REQUIRED' } }),
  );
  const n = await mount(q.api);
  try {
    await select();
    assert.equal(button('Wznów zapisaną fazę'), undefined);
    assert.match(document.body.textContent, /Przygotuj nową operację/);
  } finally {
    await n.cleanup();
  }
});

test('malformed pending is preserved until confirmed raw archive succeeds', async () => {
  const key = gridCommandKey(apiBaseUrl, gameId);
  const m = await mount(fixture().api, { [key]: '{broken' });
  try {
    assert.equal(button('Archiwizuj i porzuć').disabled, true);
    await act(async () =>
      [...document.querySelectorAll('input')]
        .find((item) =>
          item.parentElement.textContent.includes('Potwierdzam porzucenie'),
        )
        .click(),
    );
    await click('Archiwizuj i porzuć');
    assert.equal(localStorage.getItem(key), null);
    const archive = Object.keys(localStorage).find((item) =>
      item.includes(':archive:'),
    );
    assert.equal(JSON.parse(localStorage.getItem(archive)).raw, '{broken');
  } finally {
    await m.cleanup();
  }
});

test('real GridQualityPanel mounts the new GET-only workflow and removes legacy pending start', async () => {
  let legacyCalls = 0;
  const f = fixture({
    async listGridCalibrationProfiles() {
      return { data: [] };
    },
    async listGridProfileActivations() {
      return { data: [] };
    },
    async getGridCalibrationCohortDiagnostics() {
      return { data: {} };
    },
    async previewPendingGridReinference() {
      legacyCalls++;
      throw new Error('legacy');
    },
    async startPendingGridReinference() {
      legacyCalls++;
      throw new Error('legacy');
    },
  });
  const m = await mount(f.api, {}, GridQualityPanel);
  try {
    assert.ok(button('Przygotuj nowy pilot'));
    assert.equal(button('Przelicz oczekujące'), undefined);
    assert.equal(legacyCalls, 0);
    assert.deepEqual(
      f.requests.map((item) => item[0]),
      ['list'],
    );
  } finally {
    await m.cleanup();
  }
});

test('reload reads saved operation and authoritative count units without creating work', async () => {
  const f = fixture();
  f.set(
    operation('completed', {
      scopeStats: {
        sourceOccurrenceCount: 2,
        selectedSlotCount: 3,
        existingBoardCount: 1,
        deferredSlotCount: 2,
        existingCellCount: 8,
        availableCellCount: 6,
        potentialCellCount: 45,
        proposalOnlySlotCount: 1,
        protectedSlotCount: 1,
        automaticCandidateSlotCount: 1,
      },
      effectStats: {
        recordedTargetCount: 3,
        automaticWrittenBoardCount: 1,
        createdBoardCount: 1,
        createdCellCount: 15,
        changedExistingPixelCellCount: 2,
        unchangedExistingPixelCellCount: 4,
        newlyRequiresReviewCellCount: 1,
        pixelComparisonUnavailableCellCount: 2,
        notRecordedTargetCount: 0,
      },
      outcomes: { proposal_ready: 1, automatic_written: 1, conflict: 1 },
    }),
  );
  const m = await mount(f.api, {
    [gridViewKey(apiBaseUrl, gameId)]: JSON.stringify({ operationId }),
  });
  try {
    assert.deepEqual(
      f.requests.map((item) => item[0]),
      ['list', 'get', 'targets'],
    );
    const counts = Object.fromEntries(
      [...document.querySelectorAll('dl > div')].map((item) => [
        item.querySelector('dt').textContent,
        item.querySelector('dd').textContent,
      ]),
    );
    assert.equal(counts['Wybrane pozycje plansz'], '3');
    assert.equal(counts['Istniejące komórki'], '8');
    assert.equal(counts['Potencjalne komórki'], '45');
    assert.equal(counts['Istniejące komórki ze zmienionymi pikselami'], '2');
    assert.match(
      document.body.textContent,
      /Propozycja do oceny człowieka: 1 celów/,
    );
    assert.match(document.body.textContent, /Konflikt celu: 1 celów/);
  } finally {
    await m.cleanup();
  }
});

test('late detail from a previous operation does not replace the selected operation', async () => {
  const secondId = '55555555-5555-4555-8555-555555555555';
  let finishFirst;
  const f = fixture({
    async listGridReinferenceOperations() {
      return {
        data: {
          items: [
            operation(),
            operation('completed', { operationId: secondId }),
          ],
          nextCursor: null,
        },
      };
    },
    async getGridReinference(_game, id) {
      if (id === operationId)
        return new Promise((resolve) => {
          finishFirst = resolve;
        });
      return { data: operation('completed', { operationId: secondId }) };
    },
  });
  const m = await mount(f.api);
  try {
    await select();
    await change(
      document.querySelector('[aria-label="Zapisana operacja"]'),
      secondId,
    );
    await act(async () => finishFirst({ data: operation('failed') }));
    assert.match(document.body.textContent, new RegExp(`Operacja ${secondId}`));
    assert.doesNotMatch(
      document.body.textContent,
      new RegExp(`Operacja ${operationId}`),
    );
    assert.equal(
      JSON.parse(localStorage.getItem(gridViewKey(apiBaseUrl, gameId)))
        .operationId,
      secondId,
    );
  } finally {
    await m.cleanup();
  }
});

test('preparing reload reads only the operation until a final manifest exists', async () => {
  let targetReads = 0;
  const f = fixture({
    async getGridReinferenceTargets() {
      targetReads++;
      return {
        error: { code: 'MANIFEST_NOT_READY', message: 'Manifest unavailable' },
        response: { status: 409 },
      };
    },
  });
  f.set(
    operation('preparing', {
      phase: 'prepare',
      manifestSha256: null,
      preparationFinishedAt: null,
    }),
  );
  const m = await mount(f.api, {
    [gridViewKey(apiBaseUrl, gameId)]: JSON.stringify({ operationId }),
  });
  try {
    assert.deepEqual(
      f.requests.map((item) => item[0]),
      ['list', 'get'],
    );
    assert.equal(targetReads, 0);
    assert.match(document.body.textContent, /Przygotowanie zakresu/);
    assert.equal(document.querySelector('[role="alert"]'), null);
    await click('Odśwież operację');
    assert.equal(targetReads, 0);
    assert.equal(document.querySelector('[role="alert"]'), null);
  } finally {
    await m.cleanup();
  }
});

test('new failed and cancelled preparation reports unfinished scope and effects; legacy stays unknown', async () => {
  for (const state of ['failed', 'cancelled']) {
    const f = fixture();
    f.set(
      operation(state, {
        statsPolicy: 'grid-reinference-stats-v1',
        phase: 'prepare',
        manifestSha256: null,
        preparationFinishedAt: null,
        effectStats: {
          recordedTargetCount: 0,
          automaticWrittenBoardCount: 0,
          createdBoardCount: 0,
          createdCellCount: 0,
          changedExistingPixelCellCount: 0,
          unchangedExistingPixelCellCount: 0,
          newlyRequiresReviewCellCount: 0,
          pixelComparisonUnavailableCellCount: 0,
          notRecordedTargetCount: 0,
        },
      }),
    );
    const m = await mount(f.api, {
      [gridViewKey(apiBaseUrl, gameId)]: JSON.stringify({ operationId }),
    });
    try {
      assert.match(
        document.body.textContent,
        /Statystyki zakresu są niedostępne: zakres nie został ukończony/,
      );
      assert.match(
        document.body.textContent,
        /Statystyki efektów są niedostępne: zakres nie został ukończony/,
      );
      assert.doesNotMatch(
        document.body.textContent,
        /Statystyki (zakresu|efektów): nie zapisano/,
      );
      assert.equal(document.querySelectorAll('dl').length, 0);
      assert.equal(
        f.requests.some((item) => item[0] === 'targets'),
        false,
      );
    } finally {
      await m.cleanup();
    }
  }
  const legacy = fixture();
  legacy.set(
    operation('failed', {
      statsPolicy: null,
      phase: 'prepare',
      manifestSha256: null,
    }),
  );
  const m = await mount(legacy.api, {
    [gridViewKey(apiBaseUrl, gameId)]: JSON.stringify({ operationId }),
  });
  try {
    assert.match(document.body.textContent, /Statystyki zakresu: nie zapisano/);
    assert.match(document.body.textContent, /Statystyki efektów: nie zapisano/);
    assert.doesNotMatch(
      document.body.textContent,
      /zakres nie został ukończony/,
    );
  } finally {
    await m.cleanup();
  }
});

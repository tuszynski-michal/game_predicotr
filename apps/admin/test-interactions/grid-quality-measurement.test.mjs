import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import test from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';
import { measurementCommandKey } from '../src/features/model-quality/grid-quality-measurement-command.ts';

// React detects input event support when react-dom loads. Give it a DOM then,
// so text field tests exercise the same change events as a browser.
const bootstrap = new JSDOM('<div></div>');
globalThis.window = bootstrap.window;
globalThis.document = bootstrap.window.document;
const { createRoot } = await import('react-dom/client');
delete globalThis.window;
delete globalThis.document;
bootstrap.window.close();

registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith('/src/api/admin-api-client.ts'))
      return {
        format: 'module',
        shortCircuit: true,
        source:
          'export function createConfiguredAdminApiClient(){throw new Error("Injected client required");}',
      };
    return nextLoad(url, context);
  },
});
const { GridQualityMeasurementPanel } =
  await import('../src/features/model-quality/grid-quality-measurement-panel.tsx');
const gameId = '11111111-1111-4111-8111-111111111111',
  measurementId = '22222222-2222-4222-8222-222222222222',
  sourceId = '33333333-3333-4333-8333-333333333333',
  importJobId = '44444444-4444-4444-8444-444444444444',
  reviewId = '55555555-5555-4555-8555-555555555555';
const apiBaseUrl = 'http://127.0.0.1:8000',
  sha = 'a'.repeat(64);
const nodes = Array.from({ length: 4 }, (_, row) =>
  Array.from({ length: 6 }, (_, col) => ({ x: 10 + col * 7, y: 10 + row * 7 })),
);
function detail(extra = {}) {
  return {
    measurementId,
    gameId,
    policy: 'test-v1',
    populationPolicy: 'own-live-v1',
    seed: 'fixed',
    capturedAt: '2026-10-16T10:00:00Z',
    frozenPopulationCount: 30,
    excludedSupersededCount: 1,
    populationSha256: sha,
    manifestSha256: sha,
    manifestAvailable: true,
    manifestBlocker: null,
    report: {
      random: { sampleCount: 1, expectedPositionCount: 9 },
      hard: { sampleCount: 0, expectedPositionCount: 0 },
    },
    members: [
      {
        sourceId,
        importJobId,
        sampleKind: 'random',
        revision: 0,
        source: {
          width: 200,
          height: 300,
          oriented_width: 300,
          oriented_height: 200,
        },
        available: true,
        unavailableReason: null,
        recordingStatus: 'unresolved',
        judgments: [],
        unexpectedDetections: [{ kind: 'unexpected', index: 0 }],
        unexpectedJudgments: [],
        positions: Array.from({ length: 9 }, (_, positionIndex) => ({
          positionIndex,
          sequenceNumber: positionIndex + 20,
          original: {
            available: true,
            reason: null,
            nodes,
            geometry: {},
            producer: { version: 'frozen' },
          },
          current: {
            available: true,
            reason: null,
            nodes: nodes.map((row) =>
              row.map((point) => ({ ...point, x: point.x + 3 })),
            ),
            geometry: {},
            producer: null,
          },
          reviewItemId: reviewId,
          targetSha256: sha,
          ownership: 'own',
          currentManualSymbolCount: 2,
          currentSymbolCellCount: 15,
          approvalEligible: true,
          approvalBlocker: null,
        })),
      },
    ],
    ...extra,
  };
}
const summary = (id = measurementId) => ({
  measurementId: id,
  capturedAt: '2026-10-16',
  seed: 'fixed',
  frozenPopulationCount: 30,
  randomSampleCount: 1,
  hardSampleCount: 0,
  manifestSha256: sha,
});
function fixture(extra = {}) {
  const calls = [];
  const current = detail();
  return {
    calls,
    current,
    api: {
      async listGridQualityMeasurements(game, query) {
        calls.push(['list', game, query]);
        return { data: { items: [summary()], nextCursor: null } };
      },
      async getGridQualityMeasurement(game, id) {
        calls.push(['get', game, id]);
        return { data: { ...current, gameId: game, measurementId: id } };
      },
      async captureGridQualityMeasurement(game, body) {
        calls.push(['capture', game, structuredClone(body)]);
        assert.equal(
          JSON.parse(
            localStorage.getItem(measurementCommandKey(apiBaseUrl, game)),
          ).command.body.idempotencyKey,
          body.idempotencyKey,
        );
        return { data: { receipt: {}, current } };
      },
      async assessGridQualityMeasurement(game, id, body) {
        calls.push(['assess', game, id, structuredClone(body)]);
        assert.deepEqual(
          JSON.parse(
            localStorage.getItem(measurementCommandKey(apiBaseUrl, game)),
          ).command.body,
          body,
        );
        return { data: { receipt: {}, current } };
      },
      async approveOperationalGeometry(id, context, body) {
        calls.push(['approve', id, context, structuredClone(body)]);
        assert.deepEqual(
          JSON.parse(
            localStorage.getItem(
              measurementCommandKey(apiBaseUrl, context.gameId),
            ),
          ).command.body,
          body,
        );
        return { data: { receipt: {} } };
      },
      ...extra,
    },
  };
}
async function mount(api, saved = {}) {
  const dom = new JSDOM('<div id="root"></div>', {
      url: 'http://127.0.0.1:3000',
    }),
    previous = {};
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
        React.createElement(GridQualityMeasurementPanel, {
          apiBaseUrl,
          gameId: id,
          client: api,
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
  [...document.querySelectorAll('button')].find(
    (el) => el.textContent === text,
  );
async function click(text) {
  const el = button(text);
  assert.ok(el, text);
  await act(async () => el.click());
}
async function change(label, value) {
  const el = document.querySelector(`[aria-label="${label}"]`);
  assert.ok(el, label);
  await act(async () => {
    const proto =
      el.tagName === 'INPUT'
        ? window.HTMLInputElement.prototype
        : el.tagName === 'TEXTAREA'
          ? window.HTMLTextAreaElement.prototype
          : window.HTMLSelectElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
    el.dispatchEvent(
      new window.Event(el.tagName === 'SELECT' ? 'change' : 'input', {
        bubbles: true,
      }),
    );
  });
}
async function open() {
  await change('Wybierz pomiar', measurementId);
}
const approvalLabel = (position) =>
  `Zatwierdzam pokazaną bieżącą geometrię bez zmiany — pozycja ${position}`;
async function loaded(current = true) {
  await act(async () =>
    document
      .querySelector('img[alt^="Oryginał"]')
      .dispatchEvent(new window.Event('load')),
  );
  if (current)
    await act(async () =>
      document
        .querySelector('img[alt^="Bieżąca geometria"]')
        .dispatchEvent(new window.Event('load')),
    );
}

test('mount/reload only GET; lost response retries exact persisted command explicitly', async () => {
  const f = fixture();
  let fail = true;
  f.api.captureGridQualityMeasurement = async (game, body) => {
    f.calls.push(['capture', game, structuredClone(body)]);
    assert.deepEqual(
      JSON.parse(localStorage.getItem(measurementCommandKey(apiBaseUrl, game)))
        .command.body,
      body,
    );
    if (fail) throw new Error('lost response');
    return { data: { receipt: {}, current: f.current } };
  };
  let mounted = await mount(f.api);
  try {
    assert.deepEqual(
      f.calls.map((c) => c[0]),
      ['list'],
    );
    await change('Seed próby', 'fixed seed');
    await change('Rozmiar próby', '2');
    await click('Zamroź nową próbę');
    const first = f.calls.find((c) => c[0] === 'capture')[2];
    const saved = Object.fromEntries(Object.entries(localStorage));
    await mounted.cleanup();
    mounted = await mount(f.api, saved);
    assert.equal(f.calls.filter((c) => c[0] === 'capture').length, 1);
    fail = false;
    await click('Ponów zapisane polecenie');
    assert.deepEqual(f.calls.filter((c) => c[0] === 'capture')[1][2], first);
    assert.equal(
      localStorage.getItem(measurementCommandKey(apiBaseUrl, gameId)),
      null,
    );
  } finally {
    await mounted.cleanup();
  }
});

test('Reviewer link explains manual scope and pagination makes no age claim', async () => {
  const f = fixture();
  f.api.listGridQualityMeasurements = async () => ({
    data: { items: [summary()], nextCursor: 'next-uuid-page' },
  });
  const mounted = await mount(f.api);
  try {
    assert.ok(button('Kolejne pomiary'));
    assert.equal(button('Starsze pomiary'), undefined);
    await open();
    const link = [...document.querySelectorAll('a')].find(
      (element) => element.textContent === 'Otwórz Reviewer',
    );
    assert.equal(link.href, 'http://127.0.0.1:3001/');
    assert.match(link.parentElement.textContent, /Ręcznie wybierz grę/);
    assert.ok(link.parentElement.textContent.includes(gameId));
    assert.ok(
      link.parentElement.textContent.includes(f.current.members[0].importJobId),
    );
    assert.ok(
      link.parentElement.textContent.includes(f.current.members[0].sourceId),
    );
  } finally {
    await mounted.cleanup();
  }
});

test('all nine original/current overlays, independent verdicts, assess never approves', async () => {
  const f = fixture(),
    mounted = await mount(f.api);
  try {
    await open();
    assert.equal(document.querySelectorAll('fieldset legend').length, 10);
    assert.equal(
      document.querySelector('svg').getAttribute('viewBox'),
      '0 0 300 200',
    );
    assert.equal(
      document.querySelectorAll('svg')[0].querySelectorAll('g').length,
      9,
    );
    assert.equal(
      document.querySelectorAll('svg')[1].querySelectorAll('g').length,
      9,
    );
    assert.equal(
      document.querySelectorAll('select[aria-label^="geometry"]').length,
      9,
    );
    assert.equal(
      f.calls.filter((c) => ['assess', 'approve'].includes(c[0])).length,
      0,
    );
    assert.equal(button(approvalLabel(1)).disabled, true);
    await loaded();
    await change('geometry 1', 'incorrect');
    await change('detection 1', 'correct');
    await click('Zapisz jawne oceny dziewięciu pozycji');
    const body = f.calls.find((c) => c[0] === 'assess')[3];
    assert.equal(body.positions.length, 9);
    assert.deepEqual(body.positions[0], {
      positionIndex: 0,
      geometry: 'incorrect',
      detection: 'correct',
      sequence: 'unreviewed',
    });
    assert.equal(body.positions[4].geometry, 'unreviewed');
    assert.equal(body.unexpected[0].verdict, 'unreviewed');
    assert.equal(f.calls.filter((c) => c[0] === 'approve').length, 0);
  } finally {
    await mounted.cleanup();
  }
});

test('approval is separate explicit exact target command and requires loaded current image', async () => {
  const f = fixture(),
    mounted = await mount(f.api);
  try {
    await open();
    await loaded(false);
    assert.equal(button(approvalLabel(1)).disabled, true);
    await loaded();
    assert.equal(
      document.querySelector('[aria-label="geometry 1"]').value,
      'unreviewed',
    );
    await click(approvalLabel(1));
    const call = f.calls.find((c) => c[0] === 'approve');
    assert.equal(call[1], reviewId);
    assert.deepEqual(call[2], { gameId, importJobId });
    assert.deepEqual(
      { ...call[3], idempotencyKey: 'key' },
      {
        idempotencyKey: 'key',
        measurementId,
        sourceId,
        sampleKind: 'random',
        positionIndex: 0,
        manifestSha256: sha,
        targetSha256: sha,
      },
    );
    assert.equal(f.calls.filter((c) => c[0] === 'assess').length, 0);
  } finally {
    await mounted.cleanup();
  }
});

test('missing original stays visible; explicit not assessable does not infer detector failure', async () => {
  const f = fixture();
  f.current.members[0].positions[4].original = {
    available: false,
    reason: 'missing producer',
    nodes: null,
    geometry: null,
    producer: null,
  };
  const mounted = await mount(f.api);
  try {
    await open();
    await loaded();
    assert.match(document.body.textContent, /missing producer/);
    assert.equal(
      document.querySelector(
        '[aria-label="geometry 5"] option[value="correct"]',
      ).disabled,
      true,
    );
    await change('geometry 5', 'not_assessable');
    await click('Zapisz jawne oceny dziewięciu pozycji');
    const body = f.calls.find((c) => c[0] === 'assess')[3];
    assert.equal(body.positions[4].geometry, 'not_assessable');
    assert.equal(body.positions[4].detection, 'unreviewed');
  } finally {
    await mounted.cleanup();
  }
});

test('producer gap permits explicit frozen current approval without changing original assessment', async () => {
  const f = fixture();
  const member = f.current.members[0];
  member.positions[0].original = {
    available: false,
    reason: 'original_producer_unavailable',
    nodes: null,
    geometry: null,
    producer: null,
  };
  member.judgments = [
    {
      positionIndex: 0,
      geometry: 'not_assessable',
      detection: 'unknown',
      sequence: 'unknown',
    },
  ];
  member.positions[1].approvalEligible = false; // Live target changed since capture.
  member.positions[2].current = {
    available: false,
    reason: 'current_incomplete',
    nodes: null,
    geometry: null,
    producer: null,
  };
  member.positions[3].reviewItemId = null;
  const mounted = await mount(f.api);
  try {
    await open();
    assert.equal(
      f.calls.filter((c) => ['assess', 'approve'].includes(c[0])).length,
      0,
    );
    assert.equal(button(approvalLabel(1)).disabled, true);
    await loaded();
    assert.match(document.body.textContent, /current-only/);
    assert.match(document.body.textContent, /original_producer_unavailable/);
    assert.equal(
      document.querySelector(
        '[aria-label="geometry 1"] option[value="correct"]',
      ).disabled,
      true,
    );
    assert.equal(
      document.querySelector('[aria-label="geometry 1"]').value,
      'not_assessable',
    );
    assert.equal(button(approvalLabel(1)).disabled, false);
    assert.equal(button(approvalLabel(2)).disabled, true);
    assert.equal(button(approvalLabel(3)).disabled, true);
    assert.equal(button(approvalLabel(4)).disabled, true);
    await click(approvalLabel(1));
    const approval = f.calls.find((c) => c[0] === 'approve');
    assert.equal(approval[3].positionIndex, 0);
    assert.equal(approval[3].targetSha256, sha);
    assert.equal(f.calls.filter((c) => c[0] === 'assess').length, 0);
    assert.equal(
      document.querySelector('[aria-label="geometry 1"]').value,
      'not_assessable',
    );
    assert.equal(
      document.querySelector('[aria-label="detection 1"]').value,
      'unknown',
    );
    assert.equal(
      document.querySelector('[aria-label="sequence 1"]').value,
      'unknown',
    );
  } finally {
    await mounted.cleanup();
  }
});

test('server approval blocker explains an unavailable import item without changing eligibility or assessment', async () => {
  const f = fixture();
  Object.assign(f.current.members[0].positions[0], {
    reviewItemId: null,
    approvalEligible: false,
    approvalBlocker: 'IMAGE_GRID_REVIEW_ITEM_NOT_FOUND',
  });
  const mounted = await mount(f.api);
  try {
    await open();
    await loaded();
    assert.match(
      document.querySelector(
        '[aria-label="Powód niedostępności zatwierdzenia 1"]',
      ).textContent,
      /Jeżeli import trwa, poczekaj na jego zakończenie i odśwież pomiar/,
    );
    assert.equal(button(approvalLabel(1)).disabled, true);
    assert.equal(button(approvalLabel(2)).disabled, false);
    assert.equal(
      button('Zapisz jawne oceny dziewięciu pozycji').disabled,
      false,
    );
    await click(approvalLabel(1));
    assert.equal(
      f.calls.filter((c) => ['assess', 'approve'].includes(c[0])).length,
      0,
    );
    assert.equal(
      document.querySelector('[aria-label="geometry 1"]').value,
      'unreviewed',
    );
  } finally {
    await mounted.cleanup();
  }
});

test('corrupt saved JSON is archived verbatim before discard; mount never posts', async () => {
  const f = fixture(),
    key = measurementCommandKey(apiBaseUrl, gameId),
    mounted = await mount(f.api, { [key]: '{broken' });
  try {
    assert.equal(button('Ponów zapisane polecenie').disabled, true);
    window.confirm = () => true;
    await click('Zarchiwizuj i porzuć polecenie');
    assert.equal(localStorage.getItem(key), null);
    const archive = Object.keys(localStorage).find((k) =>
      k.startsWith(`${key}:archive:`),
    );
    assert.equal(JSON.parse(localStorage.getItem(archive)).raw, '{broken');
    assert.deepEqual(
      f.calls.map((c) => c[0]),
      ['list'],
    );
  } finally {
    await mounted.cleanup();
  }
});

test('late detail cannot overwrite newer measurement or game', async () => {
  const second = '66666666-6666-4666-8666-666666666666',
    otherGame = '77777777-7777-4777-8777-777777777777';
  let resolve;
  const f = fixture({
    async listGridQualityMeasurements() {
      return {
        data: { items: [summary(), summary(second)], nextCursor: null },
      };
    },
    async getGridQualityMeasurement(game, id) {
      if (id === measurementId)
        return new Promise((r) => {
          resolve = r;
        });
      return {
        data: detail({
          measurementId: id,
          gameId: game,
          seed: 'new selection',
        }),
      };
    },
  });
  const mounted = await mount(f.api);
  try {
    await open();
    await change('Wybierz pomiar', second);
    await act(async () => resolve({ data: detail({ seed: 'old selection' }) }));
    assert.match(document.body.textContent, /new selection/);
    assert.doesNotMatch(document.body.textContent, /old selection/);
    await open();
    await mounted.render(otherGame);
    await act(async () => resolve({ data: detail({ seed: 'old game' }) }));
    assert.doesNotMatch(document.body.textContent, /old game/);
  } finally {
    await mounted.cleanup();
  }
});

test('failed command persistence prevents POST and a duplicate click cannot create two commands', async () => {
  const f = fixture();
  const mounted = await mount(f.api);
  try {
    await change('Seed próby', 'bounded');
    const storagePrototype = Object.getPrototypeOf(localStorage);
    const originalSet = storagePrototype.setItem;
    storagePrototype.setItem = () => {
      throw new Error('quota');
    };
    try {
      await click('Zamroź nową próbę');
    } finally {
      storagePrototype.setItem = originalSet;
    }
    assert.equal(f.calls.filter((c) => c[0] === 'capture').length, 0);
    await act(async () => {
      button('Zamroź nową próbę').click();
      button('Zamroź nową próbę').click();
    });
    assert.equal(f.calls.filter((c) => c[0] === 'capture').length, 1);
  } finally {
    await mounted.cleanup();
  }
});

test('unavailable image permits explicit unavailable verdicts and blocks positive approval', async () => {
  const f = fixture();
  f.current.members[0].available = false;
  f.current.members[0].unavailableReason = 'source_missing';
  const mounted = await mount(f.api);
  try {
    await open();
    assert.equal(document.querySelectorAll('img').length, 0);
    assert.match(document.body.textContent, /source_missing/);
    assert.equal(button(approvalLabel(1)).disabled, true);
    await change('geometry 1', 'not_assessable');
    await change('detection 1', 'unknown');
    await click('Zapisz jawne oceny dziewięciu pozycji');
    const body = f.calls.find((c) => c[0] === 'assess')[3];
    assert.equal(body.positions[0].geometry, 'not_assessable');
    assert.equal(body.positions[0].detection, 'unknown');
    assert.equal(body.positions[0].sequence, 'unreviewed');
  } finally {
    await mounted.cleanup();
  }
});

test('late mutation completion cannot replace a different measurement selected while waiting', async () => {
  const second = '66666666-6666-4666-8666-666666666666';
  let resolve;
  const f = fixture({
    async listGridQualityMeasurements() {
      return {
        data: { items: [summary(), summary(second)], nextCursor: null },
      };
    },
    async getGridQualityMeasurement(game, id) {
      return {
        data: detail({
          gameId: game,
          measurementId: id,
          seed: id === second ? 'second measurement' : 'first measurement',
        }),
      };
    },
    async assessGridQualityMeasurement() {
      return new Promise((done) => {
        resolve = done;
      });
    },
  });
  const mounted = await mount(f.api);
  try {
    await open();
    await click('Zapisz jawne oceny dziewięciu pozycji');
    await change('Wybierz pomiar', second);
    await act(async () =>
      resolve({ data: { receipt: {}, current: detail() } }),
    );
    assert.match(document.body.textContent, /second measurement/);
    assert.doesNotMatch(document.body.textContent, /first measurement/);
    assert.equal(
      document.querySelector('[aria-label="Wybierz pomiar"]').value,
      second,
    );
  } finally {
    await mounted.cleanup();
  }
});

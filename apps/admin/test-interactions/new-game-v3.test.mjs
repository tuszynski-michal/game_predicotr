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
});
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'Element',
  'Event',
  'MouseEvent',
  'localStorage',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { GameCatalog } = await import('../src/features/games/game-catalog.tsx');
after(() => dom.window.close());

const game = (configuration, code = 'new-game') => ({
  id: '10040000-0000-4000-8000-000000000001',
  code,
  name: 'New game',
  status: 'active',
  expectedLayoutCount: 100,
  superGameKind: 'none',
  createdAt: '2026-10-15',
  updatedAt: '2026-10-15',
  shapeGeometryConfiguration: configuration,
  storageWriteAvailable: true,
  storageStatus: 'active',
  storageVersion: 'game-data-v2-manifest-v11',
  storageGeneration: 2,
  storageSchema: 'game_data_v2',
  shapeGeometryReadiness: {
    configuration,
    status: 'manual_review_required',
    reasonCode: 'GRID_MODEL_ASSIGNMENT_REQUIRED',
    message: 'Przypisz geometrię.',
    sharedProfile: null,
  },
});
function client(
  games = [],
  createGame = async () => ({ data: game('neural_grid_v3') }),
) {
  return {
    listGames: async () => ({ data: games }),
    listGridEngineProfiles: async () => ({ data: [] }),
    listSuperGameKinds: async () => ({ data: [] }),
    listGridModelVersions: async () => ({ data: [] }),
    getGridModelDefault: async () => ({
      data: {
        revision: 0,
        version: null,
        eligible: false,
        reasonCode: 'GRID_MODEL_DEFAULT_REQUIRED',
      },
    }),
    getGameGridModelAssignment: async (gameId) => ({
      data: {
        gameId,
        revision: null,
        version: null,
        eventCount: 0,
        trainingFamilyId: null,
        initialTransferAllowed: true,
      },
    }),
    createGame,
  };
}
async function mount(api) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(GameCatalog, {
        apiBaseUrl: 'http://api-task1004',
        client: api,
      }),
    ),
  );
  return root;
}
async function change(name, value) {
  const input = document.querySelector(`[name="${name}"]`);
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      dom.window.HTMLInputElement.prototype,
      'value',
    ).set.call(input, value);
    input.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  });
}

test('ordinary create has no format picker; lost reply reload resends the stored command', async () => {
  localStorage.clear();
  const requests = [];
  let root = await mount(
    client([], async (body) => {
      requests.push(body);
      throw new Error('lost reply');
    }),
  );
  await act(async () =>
    document.querySelector('[data-testid="game-create-open"]').click(),
  );
  assert.equal(
    document.querySelector('[name="shapeGeometryConfiguration"]'),
    null,
  );
  await change('code', 'new-game');
  await change('name', 'New game');
  await act(async () =>
    document
      .querySelector('form.gameForm')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })),
  );
  assert.equal(requests.length, 1);
  assert.equal('shapeGeometryConfiguration' in requests[0], false);
  assert.ok(
    [...document.querySelectorAll('button')].some(
      (button) => button.textContent === 'Porzuć zapisane polecenie…',
    ),
  );

  await act(async () => root.unmount());
  root = await mount(
    client([], async (body) => {
      requests.push(body);
      return { data: game('neural_grid_v3') };
    }),
  );
  await act(async () =>
    document.querySelector('[data-testid="game-create-open"]').click(),
  );
  assert.equal(document.querySelector('[name="code"]').value, 'new-game');
  await act(async () =>
    document
      .querySelector('form.gameForm')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })),
  );
  assert.deepEqual(requests[1], requests[0]);
  assert.equal(
    localStorage.getItem('game-create-command-v1:http://api-task1004'),
    null,
  );
  await act(async () => root.unmount());
});

test('V3 edit hides the format picker; legacy7 edit retains it', async () => {
  for (const [configuration, code, visible] of [
    ['neural_grid_v3', 'new-game', false],
    ['grid_profile_mumie_v1', 'mumie', false],
    ['grid_profile_777_v2', '777a2', false],
    ['framed_full_page_v2', '7', true],
  ]) {
    const root = await mount(client([game(configuration, code)]));
    const edit = [...document.querySelectorAll('button')].find(
      (button) => button.textContent === 'Edytuj',
    );
    await act(async () => edit.click());
    assert.equal(
      document.querySelector('[name="shapeGeometryConfiguration"]') !== null,
      visible,
    );
    await act(async () => root.unmount());
  }
});

const versionId = '10040000-0000-4000-8000-000000000004';
const eligibleVersion = {
  eligible: true,
  available: true,
  published: true,
  manifest: {
    versionId,
    familyId: versionId,
    familyLabel: 'Shared family',
    version: 'v1',
  },
};
function withVersion(api) {
  return {
    ...api,
    listGridModelVersions: async () => ({ data: [eligibleVersion] }),
  };
}
async function select(name, value) {
  const input = document.querySelector(`[name="${name}"]`);
  await act(async () => {
    input.value = value;
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
}
async function submit() {
  await act(async () =>
    document
      .querySelector('form.gameForm')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })),
  );
}
async function clickText(text) {
  const button =
    text === 'Nowa gra'
      ? document.querySelector('[data-testid="game-create-open"]')
      : [...document.querySelectorAll('button')].find(
          (b) => b.textContent === text,
        );
  assert.ok(button, text);
  await act(async () => button.click());
}

test('advanced published and fork controls submit exact selection; rejected fork can be corrected', async () => {
  localStorage.clear();
  const requests = [];
  const api = withVersion(
    client([], async (body) => {
      requests.push(body);
      return requests.length === 1
        ? {
            error: {
              code: 'GRID_MODEL_FAMILY_CONFLICT',
              message: 'Zajęty kod rodziny',
              details: {
                createRecovery: {
                  schemaVersion: 'game-create-recovery-v1',
                  idempotencyKey: body.idempotencyKey,
                  reservation: 'not_created',
                },
              },
            },
            response: { status: 409 },
          }
        : { data: game('neural_grid_v3') };
    }),
  );
  const root = await mount(api);
  await clickText('Nowa gra');
  await change('code', 'advanced');
  await change('name', 'Advanced');
  await select('gridModelMode', 'published');
  await select('gridModelBase', versionId);
  assert.match(
    document.body.textContent,
    /Rodzina treningowa będzie rodziną wybranej wersji/,
  );
  await select('gridModelMode', 'fork');
  await select('gridModelBase', versionId);
  await change('gridModelFamilyCode', 'taken_family');
  await change('gridModelFamilyLabel', 'Fork family');
  await submit();
  assert.equal(requests.length, 1);
  assert.equal(
    localStorage.getItem('game-create-command-v1:http://api-task1004'),
    null,
  );
  assert.deepEqual(requests[0].gridModel, {
    mode: 'fork',
    baseVersionId: versionId,
    familyCode: 'taken_family',
    familyLabel: 'Fork family',
  });
  await change('gridModelFamilyCode', 'free_family');
  await submit();
  assert.equal(requests.length, 2);
  assert.notEqual(requests[0].idempotencyKey, requests[1].idempotencyKey);
  assert.equal(requests[1].gridModel.familyCode, 'free_family');
  await clickText('Nowa gra');
  await change('code', 'published-game');
  await change('name', 'Published game');
  await select('gridModelMode', 'published');
  await select('gridModelBase', versionId);
  await submit();
  assert.deepEqual(requests[2].gridModel, { mode: 'published', versionId });

  await act(async () => root.unmount());
});

test('initial transfer is explicit and lost assignment response reload reuses the exact command', async () => {
  localStorage.clear();
  const requests = [];
  const row = game('neural_grid_v3');
  const api = withVersion({
    ...client([row]),
    activateGameGridModel: async (id, body) => {
      requests.push(body);
      if (requests.length === 1) throw new Error('lost');
      return { data: {} };
    },
  });
  let root = await mount(api);
  await clickText('Edytuj');
  assert.match(
    document.body.textContent,
    /Nie oznacza pomiaru jakości tej gry/,
  );
  await select('gridModelAssignmentVersion', versionId);
  await clickText('Przypisz wybraną wersję');
  assert.equal(requests[0].mode, 'initial_transfer');
  await act(async () => root.unmount());
  root = await mount(api);
  await clickText('Edytuj');
  await clickText('Ponów zapisane przypisanie');
  assert.deepEqual(requests[0], requests[1]);
  await act(async () => root.unmount());
});

test('corrupt create command opens recovery and requires explicit confirmation before archiving', async () => {
  localStorage.clear();
  const ns = 'game-create-command-v1:http://api-task1004';
  localStorage.setItem(ns, '{broken');
  const root = await mount(client());
  await clickText('Nowa gra');
  await clickText('Porzuć zapisane polecenie…');
  assert.equal(localStorage.getItem(ns), '{broken');
  assert.match(
    document.body.textContent,
    /mogły już zostać zapisane na serwerze/,
  );
  await clickText('Potwierdzam: zachowaj archiwum i porzuć polecenie');
  assert.equal(localStorage.getItem(ns), null);
  const archive = Object.keys(localStorage).find((key) =>
    key.startsWith('game-command-recovery-v1:'),
  );
  assert.equal(JSON.parse(localStorage.getItem(archive)).raw, '{broken');
  await act(async () => root.unmount());
});

test('corrupt assignment recovery preserves pending on archive failure and never sends activation', async () => {
  localStorage.clear();
  const row = game('neural_grid_v3');
  const ns = `game-initial-assignment-v1:http://api-task1004:${row.id}`;
  localStorage.setItem(ns, '{"invalid":true}');
  let calls = 0;
  const api = withVersion({
    ...client([row]),
    activateGameGridModel: async () => {
      calls++;
      throw new Error('must not run');
    },
  });
  const root = await mount(api);
  await clickText('Edytuj');
  await clickText('Porzuć zapisane polecenie…');
  const original = dom.window.Storage.prototype.setItem;
  dom.window.Storage.prototype.setItem = function (key, value) {
    if (key.startsWith('game-command-recovery-v1:')) throw new Error('full');
    return original.call(this, key, value);
  };
  try {
    await clickText('Potwierdzam: zachowaj archiwum i porzuć polecenie');
    assert.equal(localStorage.getItem(ns), '{"invalid":true}');
    assert.match(document.body.textContent, /Polecenie pozostaje/);
    assert.equal(calls, 0);
  } finally {
    dom.window.Storage.prototype.setItem = original;
  }
  await clickText('Potwierdzam: zachowaj archiwum i porzuć polecenie');
  assert.equal(localStorage.getItem(ns), null);
  assert.equal(calls, 0);
  await act(async () => root.unmount());
});

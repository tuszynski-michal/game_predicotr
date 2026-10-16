import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';

const reactUrl = import.meta.resolve('react');
registerHooks({
  resolve(specifier, context, next) {
    return next(specifier === 'react' ? reactUrl : specifier, context);
  },
  load(url, context, next) {
    if (url.endsWith('/lab-candidate-registry-panel.tsx'))
      return {
        format: 'module',
        shortCircuit: true,
        source: 'export function LabCandidateRegistryPanel() { return null; }',
      };
    if (url.endsWith('/api/admin-api-client.ts'))
      return {
        format: 'module',
        shortCircuit: true,
        source:
          'export function createConfiguredAdminApiClient() { return globalThis.assignmentFixture; }',
      };
    if (url.endsWith('/grid-quality-panel.tsx'))
      return {
        format: 'module',
        shortCircuit: true,
        source:
          "import React from 'react'; export function GridQualityPanel() { globalThis.legacyGridMounts++; return React.createElement('span', {}, 'Historyczne raporty siatki'); }",
      };
    return next(url, context);
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
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { GridModelAssignmentSummary } =
  await import('../src/features/games/grid-model-assignment-summary.tsx');
const { ModelQualityWorkspace } =
  await import('../src/features/model-quality/model-quality-workspace.tsx');
const { GameCatalog } = await import('../src/features/games/game-catalog.tsx');
after(() => dom.window.close());

const version = (overrides = {}) => ({
  available: true,
  published: false,
  eligible: false,
  eligibilityReasonCode: 'GRID_MODEL_NOT_PUBLISHED',
  reasonCode: 'GRID_MODEL_AVAILABLE',
  manifest: {
    familyLabel: 'Wspólna rodzina',
    version: 'v12',
    versionId: 'version-12',
  },
  ...overrides,
});
const response = (gameId, selected = version()) => ({
  data: { gameId, revision: 1, eventCount: 1, version: selected },
});
const text = () => document.body.textContent;
async function render(
  root,
  api,
  gameId = 'one',
  Component = GridModelAssignmentSummary,
  extra = {},
) {
  await act(async () =>
    root.render(
      React.createElement(Component, {
        apiBaseUrl: 'http://fixture',
        client: api,
        gameId,
        ...extra,
      }),
    ),
  );
}

test('assignment states preserve independent availability and stale evidence without mutation', async () => {
  for (const selected of [
    null,
    version(),
    version({ available: false, reasonCode: 'MISSING' }),
    version({ eligibilityReasonCode: 'GRID_MODEL_EVALUATION_STALE' }),
    version({
      available: false,
      reasonCode: 'MISSING',
      eligibilityReasonCode: 'GRID_MODEL_PUBLICATION_STALE',
    }),
  ]) {
    const calls = [];
    const api = {
      getGameGridModelAssignment: async (id) => {
        calls.push(id);
        return response(id, selected);
      },
    };
    const root = createRoot(document.getElementById('root'));
    try {
      await render(root, api);
      assert.deepEqual(calls, ['one']);
      if (selected === null)
        assert.match(text(), /Brak przypisanej wersji.*Import wymaga/);
      else {
        assert.match(text(), /Wspólna rodzina.*v12.*version-12/);
        assert.match(text(), /Gotowość importu sprawdza preflight/);
        assert.equal(text().includes('niedostępne'), !selected.available);
        assert.equal(
          text().includes('nieaktualny'),
          selected.eligibilityReasonCode.endsWith('STALE'),
        );
        assert.doesNotMatch(text(), /Import wymaga przypisania/);
      }
    } finally {
      await act(async () => root.unmount());
    }
  }
});

test('loading, rejected reads and foreign responses never masquerade as unassigned', async () => {
  for (const getGameGridModelAssignment of [
    () => new Promise(() => {}),
    async () => {
      throw new Error('offline');
    },
    async () => ({ error: {} }),
    async () => ({}),
    async () => ({ data: { gameId: 'one' } }),
    async () => response('foreign'),
  ]) {
    const root = createRoot(document.getElementById('root'));
    try {
      await render(root, { getGameGridModelAssignment });
      assert.doesNotMatch(text(), /Brak przypisanej wersji/);
      assert.match(text(), /Sprawdzanie przypisanej|Nie udało się odczytać/);
    } finally {
      await act(async () => root.unmount());
    }
  }
});

test('game switch ignores delayed old response and reload reads current pin', async () => {
  let finishOld;
  let selected = version();
  const calls = [];
  const api = {
    getGameGridModelAssignment: (id) => {
      calls.push(id);
      return id === 'old'
        ? new Promise((resolve) => {
            finishOld = resolve;
          })
        : Promise.resolve(response(id, selected));
    },
  };
  let root = createRoot(document.getElementById('root'));
  await render(root, api, 'old');
  assert.match(text(), /Sprawdzanie/);
  await render(root, api, 'new');
  await act(async () => finishOld(response('old', null)));
  assert.match(text(), /version-12/);
  assert.doesNotMatch(text(), /Brak przypisanej/);
  await render(root, api, 'old');
  assert.match(text(), /Sprawdzanie/);
  assert.doesNotMatch(text(), /version-12/);
  await act(async () => root.unmount());
  selected = null;
  root = createRoot(document.getElementById('root'));
  await render(root, api, 'new');
  assert.match(text(), /Brak przypisanej/);
  assert.deepEqual(calls, ['old', 'new', 'old', 'new']);
  await act(async () => root.unmount());
});

test('quality uses assignment for three V3 formats and preserves code7 legacy reports', async () => {
  for (const configuration of [
    'neural_grid_v3',
    'grid_profile_777_v2',
    'grid_profile_mumie_v1',
  ]) {
    for (const code of ['new-game', '7']) {
      const calls = [];
      globalThis.legacyGridMounts = 0;
      globalThis.assignmentFixture = {
        getGameGridModelAssignment: async (id) => {
          calls.push(id);
          return response(id);
        },
        getModelQuality: async () => ({ error: {} }),
        listSymbolModelIterations: async () => ({ data: [] }),
        listSymbolModelActivations: async () => ({ data: [] }),
        previewPendingSymbolReinference: async () => ({ error: {} }),
      };
      const root = createRoot(document.getElementById('root'));
      try {
        await render(
          root,
          globalThis.assignmentFixture,
          'one',
          ModelQualityWorkspace,
          { gameCode: code, shapeGeometryConfiguration: configuration },
        );
        if (code === '7') {
          assert.match(text(), /Historyczne raporty siatki/);
          assert.deepEqual(calls, []);
        } else {
          assert.match(text(), /Geometria V3.*version-12/s);
          assert.doesNotMatch(
            text(),
            /Ulepszanie geometrii|Cięcie siatki|Historyczne raporty/,
          );
          assert.equal(globalThis.legacyGridMounts, 0);
          // TASK-1000: several V3 steps read the same game's pin, never another game.
          assert.ok(calls.length >= 1 && calls.every((id) => id === 'one'));
        }
      } finally {
        await act(async () => root.unmount());
      }
    }
  }
});

test('catalog reads only rendered V3 cards and retains legacy readiness', async () => {
  const configurations = [
    'neural_grid_v3',
    'grid_profile_777_v2',
    'grid_profile_mumie_v1',
  ];
  const games = [
    ...configurations.map((shapeGeometryConfiguration, index) => ({
      id: `v3-${index}`,
      code: `new-${index}`,
      shapeGeometryConfiguration,
    })),
    {
      id: 'legacy',
      code: '7',
      shapeGeometryConfiguration: 'grid_profile_777_v2',
    },
    {
      id: 'hidden',
      code: 'hidden',
      shapeGeometryConfiguration: 'neural_grid_v3',
      status: 'archived',
    },
  ].map((game) => ({
    name: game.id,
    expectedLayoutCount: 100,
    status: 'active',
    superGameKind: 'none',
    storageWriteAvailable: true,
    storageVersion: 'v2',
    storageGeneration: 1,
    shapeGeometryReadiness: {
      status: 'ready_for_shared_preflight',
      sharedProfile: { profileNumber: 42 },
      message: 'Klasyczny raport zachowany',
    },
    ...game,
  }));
  const calls = [];
  const api = {
    listGames: async () => ({ data: games }),
    listGridEngineProfiles: async () => ({ data: [] }),
    listSuperGameKinds: async () => ({ data: [] }),
    getGameGridModelAssignment: async (id) => {
      calls.push(id);
      return response(id);
    },
  };
  const root = createRoot(document.getElementById('root'));
  try {
    await render(root, api, 'unused', GameCatalog);
    assert.deepEqual(calls.sort(), ['v3-0', 'v3-1', 'v3-2']);
    for (const id of calls) {
      const card = document.querySelector(`[data-testid="game-row-${id}"]`);
      assert.match(card.textContent, /version-12/);
      assert.doesNotMatch(
        card.textContent,
        /Klasyczny raport|profil wspólny|ręcznej korekty/,
      );
    }
    assert.match(
      document.querySelector('[data-testid="game-row-legacy"]').textContent,
      /profil wspólny #42.*Klasyczny raport/s,
    );
  } finally {
    await act(async () => root.unmount());
  }
});

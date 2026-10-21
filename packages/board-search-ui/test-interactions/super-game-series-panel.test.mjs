import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';

const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'http://127.0.0.1:3001',
});
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'HTMLInputElement',
  'HTMLSelectElement',
  'Element',
  'Event',
  'KeyboardEvent',
  'MouseEvent',
  'Image',
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '');
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open');
};
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.React = React;
const { createRoot } = await import('react-dom/client');
const { SuperGameSeriesPanel } =
  await import('../src/super-game-series/super-game-series-panel.tsx');
after(() => dom.window.close());

const FRESH = { fresh: true, generationInputVersion: 1, inputVersion: 1 };

const settle = () =>
  act(async () => new Promise((resolve) => setTimeout(resolve, 5)));
const button = (text) =>
  [...document.querySelectorAll('button')].find((node) =>
    node.textContent.includes(text),
  );
const click = async (node) => {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
  await settle();
};
const press = async (key, target = document.body, init = {}) => {
  await act(async () =>
    target.dispatchEvent(
      new dom.window.KeyboardEvent('keydown', {
        bubbles: true,
        cancelable: true,
        key,
        ...init,
      }),
    ),
  );
  await settle();
};
const heading = () => document.querySelector('h4')?.textContent;
const notice = () =>
  [...document.querySelectorAll('[role="status"], [role="alert"]')]
    .map((node) => node.textContent)
    .join(' | ');

function series(overrides = {}) {
  return {
    completeness: 'complete',
    definedAt: null,
    definedBy: null,
    endSequenceNumber: 110,
    gameId: 'shared',
    id: 'series-100',
    length: 10,
    retriggerSequenceNumbers: [105],
    revision: 3,
    runVerification: 'verified',
    startSequenceNumber: 101,
    superSymbolId: null,
    triggerSequenceNumber: 100,
    updatedAt: '2026-10-18T10:00:00Z',
    ...overrides,
  };
}

function boardsResponse(seriesOverrides = {}) {
  const base = series(seriesOverrides);
  const boards = [];
  for (
    let n = base.triggerSequenceNumber;
    n <= base.endSequenceNumber;
    n += 1
  ) {
    const missing = n === base.triggerSequenceNumber + 3;
    boards.push({
      assetMode: missing ? null : 'operational_review',
      boardChecksumSha256: missing ? null : `checksum-${n}`,
      importJobId: null,
      missing,
      recognizedBoardId: null,
      reviewItemId: null,
      role:
        n === base.triggerSequenceNumber
          ? 'trigger'
          : base.retriggerSequenceNumbers.includes(n)
            ? 'retrigger'
            : 'spin',
      sequenceNumber: n,
      spinIndex:
        n === base.triggerSequenceNumber
          ? null
          : n - base.triggerSequenceNumber,
      status: missing ? null : 'accepted',
    });
  }
  return { boards, series: base, superGameState: FRESH };
}

function symbol(id, order, overrides = {}) {
  return {
    code: id.toUpperCase(),
    displayOrder: order,
    gameId: 'shared',
    id,
    imagePath: null,
    isWildcard: false,
    mobileCode: order,
    name: `Symbol ${order + 1}`,
    nameEn: null,
    namePl: null,
    status: 'active',
    superGameTriggerCount: null,
    ...overrides,
  };
}

const SYMBOLS = [
  ...Array.from({ length: 3 }, (_, index) => symbol(`s${index + 1}`, index)),
  symbol('mumia', 3, { superGameTriggerCount: 3 }),
  symbol('wild', 4, { isWildcard: true }),
];

/**
 * A fake series client: `store` maps a series id to its boards response and
 * `undefinedAfter` maps a trigger (or `null`) to the answer of the "next
 * undefined" search.
 */
function fakeClient({ store, undefinedAfter = {}, saveError = null } = {}) {
  const calls = { boards: [], details: [], next: [], saves: [] };
  const data = store ?? { 'series-100': boardsResponse() };
  return {
    calls,
    client: {
      boardSearchBoardViewUrl: (gameId, sequence, checksum, revision) =>
        `/view/${gameId}/${sequence}/${checksum}/${revision ?? ''}`,
      getBoardSearchBoardDetail: async (gameId, sequence) => {
        calls.details.push(sequence);
        return {
          data: {
            boardChecksumSha256: `checksum-${sequence}`,
            sequenceNumber: sequence,
            symbolCodes: [
              'S1',
              'MUMIA',
              'S2',
              'S3',
              'S1',
              'S2',
              'MUMIA',
              'S3',
              'S1',
              'S2',
              'S3',
              'S1',
              'S2',
              'MUMIA',
              'S3',
            ],
            view: { cellPolygons: null, revision: 'rev-1' },
          },
        };
      },
      listNextUndefinedSuperGameSeries: async (gameId, query) => {
        calls.next.push(query);
        const key = query.afterTrigger === null ? 'start' : query.afterTrigger;
        return { data: { items: undefinedAfter[key] ?? [] } };
      },
      listSuperGameSeriesBoards: async (gameId, seriesId) => {
        calls.boards.push(seriesId);
        const response = data[seriesId];
        return response === undefined
          ? { error: { code: 'SUPER_GAME_SERIES_NOT_FOUND', message: 'no' } }
          : { data: response };
      },
      setSuperGameSeriesSuperSymbol: async (gameId, seriesId, body) => {
        calls.saves.push({ body, gameId, seriesId });
        if (saveError !== null) return { error: saveError };
        const saved = series({
          ...data[seriesId].series,
          revision: body.expectedRevision + 1,
          superSymbolId: body.symbolId,
        });
        data[seriesId] = { ...data[seriesId], series: saved };
        return { data: saved };
      },
      symbolImageAssetUrl: () => '/symbol.png',
    },
  };
}

async function mount(client, props = {}) {
  const container = document.getElementById('root');
  container.replaceChildren();
  const root = createRoot(container);
  const events = { changes: [], loaded: [], saved: [], states: [], edited: 0 };
  const render = (next = {}) =>
    act(async () =>
      root.render(
        React.createElement(SuperGameSeriesPanel, {
          client,
          gameId: 'shared',
          onBoardEdited: () => {
            events.edited += 1;
          },
          onSeriesChange: (id) => events.changes.push(id),
          onSeriesLoaded: (loaded) => events.loaded.push(loaded.id),
          onSeriesSaved: (saved) => events.saved.push(saved.id),
          onSuperGameStateChange: (state) => events.states.push(state.fresh),
          seriesId: 'series-100',
          symbols: SYMBOLS,
          ...props,
          ...next,
        }),
      ),
    );
  await render();
  await settle();
  await settle();
  return { events, render, root };
}

test('reads the series, marks the trigger cells and walks the carousel', async () => {
  const { calls, client } = fakeClient();
  const { events, root } = await mount(client);
  assert.deepEqual(calls.boards, ['series-100']);
  assert.deepEqual(events.loaded, ['series-100']);
  assert.deepEqual(events.states, [true]);
  assert.equal(heading(), 'Wyzwalacz · #100');
  assert.equal(button('Lista serii'), undefined);
  assert.ok(document.querySelector('[aria-label="Karuzela pozycji serii"]'));
  assert.equal(
    document.querySelectorAll('.superGameSeriesTriggerCell').length,
    3,
  );
  assert.ok(
    document.querySelector('img').getAttribute('src').endsWith('/rev-1'),
  );
  await press('ArrowRight');
  assert.equal(heading(), 'Spin 1 · #101');
  await click(button('Następna →'));
  await click(button('Następna →'));
  assert.ok(document.querySelector('[data-testid="missing-card"]'));
  const badges = [...document.querySelectorAll('[data-badge]')].map(
    (node) => node.textContent,
  );
  assert.deepEqual(badges, [
    'Kompletna',
    'Do zdefiniowania',
    'Przebieg zweryfikowany',
  ]);
  await act(async () => root.unmount());
});

test('highlights the candidate by code with exact photo polygons across selection, navigation, cancel and clear', async () => {
  const { calls, client } = fakeClient({
    store: { 'series-100': boardsResponse({ superSymbolId: 's2' }) },
  });
  const originalDetail = client.getBoardSearchBoardDetail;
  // Deliberately skewed cells: an equal rectangular grid would be incorrect.
  const polygons = Array.from({ length: 15 }, (_, index) => {
    const x = (index % 5) / 5;
    const y = Math.floor(index / 5) / 3;
    return [
      { x, y },
      { x: x + 0.18, y: y + 0.02 },
      { x: x + 0.19, y: y + 0.3 },
      { x: x + 0.01, y: y + 0.28 },
    ];
  });
  client.getBoardSearchBoardDetail = async (...args) => {
    const result = await originalDetail(...args);
    if (args[1] === 101) result.data.symbolCodes = Array(15).fill('S3');
    result.data.view.cellPolygons = polygons;
    return result;
  };
  const { root } = await mount(client);
  const selectedIndexes = () =>
    [...document.querySelectorAll('.superGameSeriesSelectedOutline')].map(
      (node) => Number(node.getAttribute('data-cell')),
    );
  const checkSelection = (indexes) => {
    assert.deepEqual(selectedIndexes(), indexes);
    assert.equal(
      document.querySelectorAll('.superGameSeriesSelectedCell').length,
      indexes.length,
    );
    assert.equal(
      document.querySelectorAll(
        '.superGameSeriesSelectedCell [aria-label="Symbol serii"]',
      ).length,
      indexes.length,
    );
    for (const node of document.querySelectorAll(
      '.superGameSeriesSelectedOutline',
    )) {
      const index = Number(node.getAttribute('data-cell'));
      assert.equal(
        node.getAttribute('points'),
        polygons[index].map(({ x, y }) => `${x},${y}`).join(' '),
      );
    }
  };
  checkSelection([2, 5, 9, 12]); // Saved symbol, loaded on opening.
  await press('1');
  checkSelection([0, 4, 8, 11]); // ID s1 maps to code S1.
  assert.equal(
    document.querySelectorAll('.superGameSeriesTriggerCell').length,
    3,
  );
  assert.equal(
    document.querySelectorAll('polygon:not(.superGameSeriesSelectedOutline)')
      .length,
    3,
  );
  const select = document.querySelector('select');
  await act(async () => {
    select.value = 's3';
    select.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });
  checkSelection([3, 7, 10, 14]);
  await press('ArrowRight');
  checkSelection(Array.from({ length: 15 }, (_, index) => index));
  await press('Escape');
  checkSelection([]); // Saved S2 is absent on the second board.
  await press('ArrowLeft');
  checkSelection([2, 5, 9, 12]);
  await click(button('Wyczyść symbol'));
  checkSelection([]);
  assert.equal(
    document.querySelectorAll('.superGameSeriesTriggerCell').length,
    3,
  );
  assert.deepEqual(calls.saves, []); // Preview does not persist the choice.
  await act(async () => root.unmount());
});

test('without geometry the candidate remains marked in the hint and unknown cells never match', async () => {
  const { client } = fakeClient();
  const originalDetail = client.getBoardSearchBoardDetail;
  client.getBoardSearchBoardDetail = async (...args) => {
    const result = await originalDetail(...args);
    result.data.symbolCodes[0] = null;
    return result;
  };
  const { root } = await mount(client);
  await press('1');
  assert.equal(
    document.querySelectorAll('.superGameSeriesSelectedCell').length,
    3,
  );
  assert.equal(
    document.querySelector('.superGameSeriesSymbolGrid li').textContent,
    '?',
  );
  assert.equal(document.querySelector('.superGameSeriesBoardOverlay'), null);
  assert.match(document.body.textContent, /Brak geometrii pól/);
  await press('Escape');
  assert.equal(
    document.querySelectorAll('.superGameSeriesSelectedCell').length,
    0,
  );
  await press('ArrowRight');
  await press('ArrowRight');
  await press('ArrowRight');
  assert.ok(document.querySelector('[data-testid="missing-card"]'));
  assert.equal(document.querySelector('.superGameSeriesBoardOverlay'), null);
  await act(async () => root.unmount());
});

test('opens at the requested position and shows the back button only with a host', async () => {
  const { client } = fakeClient();
  const back = [];
  const { root } = await mount(client, {
    initialSequenceNumber: 105,
    onBack: () => back.push(1),
  });
  assert.equal(heading(), 'Retrigger · pozycja 5 · #105');
  await click(button('Lista serii'));
  assert.deepEqual(back, [1]);
  await act(async () => root.unmount());
});

test('a digit picks a symbol, Enter confirms the retrigger and saves with the revision, then the next series opens', async () => {
  const next = series({ id: 'series-200', triggerSequenceNumber: 200 });
  const { calls, client } = fakeClient({
    store: {
      'series-100': boardsResponse(),
      'series-200': boardsResponse({
        endSequenceNumber: 210,
        id: 'series-200',
        retriggerSequenceNumbers: [],
        startSequenceNumber: 201,
        triggerSequenceNumber: 200,
      }),
    },
    undefinedAfter: { 100: [next] },
  });
  const { events, render, root } = await mount(client);
  await press('2');
  assert.equal(document.querySelector('select').value, 's2');
  assert.ok(button('Do retriggera 1 z 1 (Enter)'));
  await press('Enter');
  assert.equal(heading(), 'Retrigger · pozycja 5 · #105');
  assert.ok(button('Potwierdź retrigger 1 z 1 i zapisz (Enter)'));
  await press('Enter');
  assert.deepEqual(calls.saves, [
    {
      body: { expectedRevision: 3, symbolId: 's2' },
      gameId: 'shared',
      seriesId: 'series-100',
    },
  ]);
  assert.deepEqual(events.saved, ['series-100']);
  assert.deepEqual(
    calls.next,
    [{ afterTrigger: 100, filters: undefined }].map((query) => ({
      ...query,
      filters: calls.next[0].filters,
    })),
  );
  assert.deepEqual(events.changes, ['series-200']);
  // The host opens the next series; the panel reads it and keeps the toast.
  await render({ seriesId: 'series-200' });
  await settle();
  assert.equal(heading(), 'Wyzwalacz · #200');
  assert.ok(notice().includes('Zapisano super symbol Symbol 2'));
  await act(async () => root.unmount());
});

test('Escape cancels the candidate and shortcuts are ignored in the select and with modifiers', async () => {
  const { calls, client } = fakeClient();
  const { root } = await mount(client);
  await press('1');
  assert.equal(document.querySelector('select').value, 's1');
  await press('Escape');
  assert.equal(document.querySelector('select').value, '');
  await press('2', document.querySelector('select'));
  assert.equal(document.querySelector('select').value, '');
  await press('2', document.body, { ctrlKey: true });
  assert.equal(document.querySelector('select').value, '');
  await press('Enter');
  assert.deepEqual(calls.saves, []);
  await act(async () => root.unmount());
});

test('a revision conflict writes nothing, says so and reads the series again', async () => {
  const { calls, client } = fakeClient({
    saveError: { code: 'SUPER_GAME_SERIES_REVISION_CONFLICT', message: 'x' },
  });
  const { root } = await mount(client);
  await press('1');
  await press('Enter');
  await press('Enter');
  assert.equal(calls.saves.length, 1);
  assert.ok(notice().includes('zmieniona w międzyczasie'));
  assert.deepEqual(calls.boards, ['series-100', 'series-100']);
  assert.equal(document.querySelector('select').value, '');
  await act(async () => root.unmount());
});

test('N wraps to the first series without a symbol and says so; nothing left keeps the series', async () => {
  const first = series({ id: 'series-50', triggerSequenceNumber: 50 });
  const { calls, client } = fakeClient({
    undefinedAfter: { start: [first, series()] },
  });
  const { events, root } = await mount(client);
  await press('n');
  assert.deepEqual(
    calls.next.map((query) => query.afterTrigger),
    [100, null],
  );
  assert.deepEqual(events.changes, ['series-50']);
  assert.ok(notice().includes('od początku listy'));
  await act(async () => root.unmount());

  const nothing = fakeClient({ undefinedAfter: { start: [series()] } });
  const mounted = await mount(nothing.client);
  await click(button('Następna bez symbolu'));
  assert.deepEqual(mounted.events.changes, []);
  assert.ok(notice().includes('Nie ma innej serii bez super symbolu'));
  await press('1');
  await press('n');
  assert.ok(notice().includes('nie jest zapisany'));
  await act(async () => mounted.root.unmount());
});

test('a host refresh token re-reads the series at the same position; the lines window blocks shortcuts', async () => {
  const { calls, client } = fakeClient();
  const { render, root } = await mount(client);
  await press('ArrowRight');
  assert.equal(heading(), 'Spin 1 · #101');
  await render({ refreshToken: 1 });
  await settle();
  assert.deepEqual(calls.boards, ['series-100', 'series-100']);
  assert.equal(heading(), 'Spin 1 · #101');

  await click(button('Pokaż planszę z liniami'));
  assert.ok(document.querySelector('dialog[open]'));
  await press('ArrowRight');
  assert.equal(heading(), 'Spin 1 · #101');
  await act(async () => root.unmount());
});

test('a missing series shows the API message', async () => {
  const { client } = fakeClient({ store: {} });
  const { root } = await mount(client);
  assert.ok(notice().includes('Seria nie istnieje'));
  assert.equal(heading(), undefined);
  await act(async () => root.unmount());
});

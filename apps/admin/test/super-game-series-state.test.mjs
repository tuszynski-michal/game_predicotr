import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_SERIES_FILTERS,
  UNDEFINED_COUNT_LIMIT,
  activeSeriesCard,
  applySeriesListPage,
  applySeriesListUndefinedCount,
  applySeriesRefresh,
  applySuperSymbolConflict,
  applySuperSymbolFailure,
  applySuperSymbolSaved,
  beginSuperSymbolSave,
  blockSuperSymbolSave,
  buildSeriesPositionCards,
  cancelSuperSymbolCandidate,
  changeSeriesFilters,
  createSeriesListState,
  createSeriesViewState,
  deriveResultMessage,
  failSeriesList,
  goToSeriesPosition,
  isSeriesNotFound,
  isSeriesRevisionConflict,
  isSuperSymbolCandidateDirty,
  missingCardLabel,
  moveSeriesPosition,
  ordinarySuperSymbols,
  pickSeriesRulesVersion,
  reloadSeriesList,
  replaceSeriesInList,
  seriesMatchesFilters,
  selectSuperSymbolCandidate,
  seriesBadges,
  seriesListQuery,
  seriesNeighbourIndexes,
  seriesPositionCardLabel,
  seriesRangeLabel,
  seriesRulesVersionOptions,
  shouldPollSeriesState,
  startLoadingMoreSeries,
  superGameSeriesErrorMessage,
  superGameStateBanner,
  superSymbolSaveBlock,
  triggerCellIndexes,
  triggerSymbols,
  undefinedSeriesCount,
  undefinedSeriesCountLabel,
  undefinedSeriesCountQuery,
} from '../src/features/super-games/super-game-series-state.ts';

const FRESH = { fresh: true, generationInputVersion: 7, inputVersion: 7 };
const STALE = { fresh: false, generationInputVersion: 6, inputVersion: 7 };

function series(overrides = {}) {
  return {
    completeness: 'complete',
    definedAt: null,
    definedBy: null,
    endSequenceNumber: 120,
    gameId: 'game-1',
    id: 'series-100',
    length: 20,
    retriggerSequenceNumbers: [105],
    revision: 3,
    runVerification: 'verified',
    startSequenceNumber: 101,
    superSymbolId: null,
    triggerSequenceNumber: 100,
    updatedAt: '2026-10-09T10:00:00Z',
    ...overrides,
  };
}

function board(sequenceNumber, role = 'spin', missing = false) {
  return {
    assetMode: missing ? null : 'operational_review',
    boardChecksumSha256: missing ? null : `checksum-${sequenceNumber}`,
    importJobId: missing ? null : 'job-1',
    missing,
    recognizedBoardId: null,
    reviewItemId: missing ? null : `item-${sequenceNumber}`,
    role,
    sequenceNumber,
    spinIndex: role === 'trigger' ? null : sequenceNumber - 100,
    status: missing ? null : 'accepted',
  };
}

/** Series 101–120 triggered at 100 with a retrigger at 105; 103 has no board. */
function boardsResponse(seriesOverrides = {}, missing = [103]) {
  const boards = [];
  for (let n = 100; n <= 120; n += 1) {
    boards.push(
      board(
        n,
        n === 100 ? 'trigger' : n === 105 ? 'retrigger' : 'spin',
        missing.includes(n),
      ),
    );
  }
  return {
    boards,
    series: series(seriesOverrides),
    superGameState: FRESH,
  };
}

function symbol(id, order, overrides = {}) {
  return {
    code: id.toUpperCase(),
    displayOrder: order,
    gameId: 'game-1',
    id,
    imagePath: null,
    isWildcard: false,
    mobileCode: order,
    name: `Symbol ${id}`,
    nameEn: null,
    namePl: null,
    status: 'active',
    superGameTriggerCount: null,
    ...overrides,
  };
}

/** Nine ordinary symbols, a trigger symbol (the tenth, Mumia), a Wild and an archived one. */
function catalog() {
  const ordinary = Array.from({ length: 9 }, (_, index) =>
    symbol(`s${index + 1}`, index),
  );
  return [
    ...ordinary,
    symbol('mumia', 9, { superGameTriggerCount: 3 }),
    symbol('wild', 10, { isWildcard: true }),
    symbol('old', 11, { status: 'archived' }),
  ];
}

// --- carousel -----------------------------------------------------------

test('a series 101-120 with a retrigger at 105 has 20 series cards and the trigger', () => {
  const cards = buildSeriesPositionCards(series(), boardsResponse().boards);
  assert.equal(cards.length, 21);
  assert.equal(cards[0].role, 'trigger');
  assert.equal(cards[0].sequenceNumber, 100);
  const inSeries = cards.filter((card) => card.role !== 'trigger');
  assert.equal(inSeries.length, 20);
  assert.deepEqual(
    [inSeries[0].sequenceNumber, inSeries[19].sequenceNumber],
    [101, 120],
  );
  const retriggers = cards.filter((card) => card.role === 'retrigger');
  assert.deepEqual(
    retriggers.map((card) => card.sequenceNumber),
    [105],
  );
  assert.equal(
    seriesPositionCardLabel(retriggers[0]),
    'Retrigger · pozycja 5 · #105',
  );
  assert.equal(seriesPositionCardLabel(cards[1]), 'Spin 1 · #101');
  assert.equal(seriesPositionCardLabel(cards[0]), 'Wyzwalacz · #100');
});

test('a position without a board is an empty "brak planszy" card', () => {
  const cards = buildSeriesPositionCards(series(), boardsResponse().boards);
  const gap = cards.find((card) => card.sequenceNumber === 103);
  assert.equal(gap.missing, true);
  assert.equal(gap.outOfRange, false);
  assert.equal(gap.board, null);
  assert.equal(missingCardLabel(gap), 'brak planszy');
  assert.equal(
    cards.find((card) => card.sequenceNumber === 104).missing,
    false,
  );
});

test('positions the API left out stay in the carousel as empty cards', () => {
  const boards = boardsResponse().boards.filter(
    (item) => item.sequenceNumber <= 115,
  );
  const cards = buildSeriesPositionCards(series(), boards);
  assert.equal(cards.length, 21);
  const last = cards.at(-1);
  assert.equal(last.sequenceNumber, 120);
  assert.equal(last.missing, true);
  assert.equal(last.outOfRange, true);
  assert.match(missingCardLabel(last), /poza zakresem/);
});

test('the view opens on the trigger and moves within the carousel', () => {
  let state = createSeriesViewState(boardsResponse());
  assert.equal(activeSeriesCard(state).sequenceNumber, 100);
  assert.equal(moveSeriesPosition(state, -1), state);
  state = moveSeriesPosition(state, 1);
  assert.equal(activeSeriesCard(state).sequenceNumber, 101);
  state = goToSeriesPosition(state, 999);
  assert.equal(activeSeriesCard(state).sequenceNumber, 120);
  assert.equal(moveSeriesPosition(state, 1), state);
  assert.deepEqual(seriesNeighbourIndexes(state), [19]);
  assert.deepEqual(seriesNeighbourIndexes(goToSeriesPosition(state, 0)), [1]);
});

// --- list: filters and pagination ----------------------------------------

test('filters map to the API query and "all" is omitted', () => {
  assert.deepEqual(seriesListQuery(DEFAULT_SERIES_FILTERS, null), {
    limit: 50,
  });
  assert.deepEqual(
    seriesListQuery(
      {
        completeness: 'incomplete',
        defined: 'undefined',
        runVerification: 'unverified',
      },
      '120',
      25,
    ),
    {
      completeness: 'incomplete',
      cursor: '120',
      defined: false,
      limit: 25,
      runVerification: 'unverified',
    },
  );
  assert.equal(
    seriesListQuery({ ...DEFAULT_SERIES_FILTERS, defined: 'defined' }, null)
      .defined,
    true,
  );
  assert.deepEqual(undefinedSeriesCountQuery(), {
    defined: false,
    limit: UNDEFINED_COUNT_LIMIT,
  });
});

function page(ids, nextCursor = null) {
  return {
    items: ids.map((id) =>
      series({ id: `series-${id}`, triggerSequenceNumber: id }),
    ),
    nextCursor,
    superGameKind: 'wild_super_spins',
    superGameState: FRESH,
  };
}

test('pages are appended by cursor and late or repeated pages are ignored', () => {
  let state = createSeriesListState();
  const key = state.generation;
  assert.equal(state.status, 'loading');
  state = applySeriesListPage(state, {
    cursor: null,
    generation: key,
    response: page([100, 200], '200'),
  });
  assert.equal(state.status, 'ready');
  assert.equal(state.nextCursor, '200');
  assert.deepEqual(
    state.items.map((item) => item.triggerSequenceNumber),
    [100, 200],
  );

  assert.equal(startLoadingMoreSeries(state).status, 'loading');
  const second = {
    cursor: '200',
    generation: key,
    response: page([200, 300], null),
  };
  const loaded = applySeriesListPage(startLoadingMoreSeries(state), second);
  assert.deepEqual(
    loaded.items.map((item) => item.triggerSequenceNumber),
    [100, 200, 300],
  );
  assert.equal(loaded.nextCursor, null);
  // A repeated page and a page for another cursor change nothing.
  assert.equal(applySeriesListPage(loaded, second), loaded);
  assert.equal(
    applySeriesListPage(loaded, { ...second, cursor: '999' }),
    loaded,
  );
  assert.equal(startLoadingMoreSeries(loaded), loaded);
});

test('changing the filters starts a new list and ignores pages of the old one', () => {
  let state = applySeriesListPage(createSeriesListState(), {
    cursor: null,
    generation: createSeriesListState().generation,
    response: page([100], '100'),
  });
  state = applySeriesListUndefinedCount(state, { count: 4, hasMore: false });
  const oldKey = state.generation;
  assert.equal(changeSeriesFilters(state, state.filters), state);

  const next = changeSeriesFilters(state, {
    ...DEFAULT_SERIES_FILTERS,
    completeness: 'incomplete',
  });
  assert.notEqual(next.generation, oldKey);
  assert.equal(next.items.length, 0);
  assert.equal(next.status, 'loading');
  assert.deepEqual(next.undefinedCount, { count: 4, hasMore: false });
  assert.equal(
    applySeriesListPage(next, {
      cursor: null,
      generation: oldKey,
      response: page([100, 200]),
    }),
    next,
  );
  assert.equal(failSeriesList(next, oldKey, 'x'), next);
  const failed = failSeriesList(next, next.generation, 'Błąd');
  assert.equal(failed.status, 'error');
  assert.equal(failed.error, 'Błąd');

  const reloaded = reloadSeriesList(state);
  assert.equal(reloaded.items.length, 0);
  assert.equal(reloaded.filtersKey, state.filtersKey);
  assert.equal(reloaded.generation, state.generation + 1);
});

test('the counter of series without a symbol shows a lower bound at the page limit', () => {
  assert.equal(undefinedSeriesCountLabel(null), '—');
  assert.equal(
    undefinedSeriesCountLabel(
      undefinedSeriesCount({ items: [{}, {}], nextCursor: null }),
    ),
    '2',
  );
  assert.equal(
    undefinedSeriesCountLabel(
      undefinedSeriesCount({ items: new Array(200).fill({}), nextCursor: '9' }),
    ),
    '200+',
  );
});

test('a saved series replaces its row in place', () => {
  const state = applySeriesListPage(createSeriesListState(), {
    cursor: null,
    generation: createSeriesListState().generation,
    response: page([100, 200]),
  });
  const updated = series({
    id: 'series-100',
    revision: 4,
    superSymbolId: 's1',
    triggerSequenceNumber: 100,
  });
  const next = replaceSeriesInList(state, updated);
  assert.equal(next.items[0].revision, 4);
  assert.equal(next.items[1], state.items[1]);
  assert.equal(replaceSeriesInList(state, series({ id: 'other' })), state);
});

// --- generation state ----------------------------------------------------

test('a stale generation shows the banner and asks for polling', () => {
  assert.equal(superGameStateBanner(FRESH), null);
  assert.equal(superGameStateBanner(null), null);
  assert.match(superGameStateBanner(STALE), /Serie w trakcie przeliczania/);
  assert.equal(shouldPollSeriesState(STALE), true);
  assert.equal(shouldPollSeriesState(FRESH), false);
  assert.equal(shouldPollSeriesState(null), false);
});

test('the derive toast tells a new job from an already queued one', () => {
  assert.match(
    deriveResultMessage({ deduplicated: false, jobId: 'j1' }),
    /Zakolejkowano .*j1/,
  );
  assert.match(
    deriveResultMessage({ deduplicated: true, jobId: 'j2' }),
    /już zakolejkowane .*j2/,
  );
});

// --- super symbol choice -------------------------------------------------

test('only active ordinary symbols can be a super symbol, in catalog order', () => {
  const symbols = catalog();
  const ordinary = ordinarySuperSymbols([...symbols].reverse());
  assert.deepEqual(
    ordinary.map((item) => item.id),
    ['s1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9'],
  );
  assert.deepEqual(
    triggerSymbols(symbols).map((item) => item.id),
    ['mumia'],
  );
});

test('a trigger symbol can be a candidate but never saved', () => {
  const symbols = catalog();
  let state = createSeriesViewState(boardsResponse());
  // `0` over the whole catalog would pick the tenth symbol, the trigger one.
  state = selectSuperSymbolCandidate(state, 'mumia');
  assert.equal(state.candidateSymbolId, 'mumia');
  assert.equal(isSuperSymbolCandidateDirty(state), true);
  const block = superSymbolSaveBlock(state, symbols);
  assert.equal(block.reason, 'not_ordinary');
  assert.equal(beginSuperSymbolSave(state, symbols), null);
  const blocked = blockSuperSymbolSave(state, block);
  assert.equal(blocked.notice.kind, 'error');
  assert.equal(blocked.series, state.series);
  assert.equal(blocked.saving, false);

  for (const forbidden of ['wild', 'old']) {
    const other = selectSuperSymbolCandidate(state, forbidden);
    assert.equal(superSymbolSaveBlock(other, symbols).reason, 'not_ordinary');
  }
  assert.equal(
    superSymbolSaveBlock(selectSuperSymbolCandidate(state, 'zzz'), symbols)
      .reason,
    'unknown_symbol',
  );
});

test('an unchanged candidate is not saved and Escape returns to the saved symbol', () => {
  const symbols = catalog();
  let state = createSeriesViewState(boardsResponse({ superSymbolId: 's2' }));
  assert.equal(state.candidateSymbolId, 's2');
  assert.equal(superSymbolSaveBlock(state, symbols).reason, 'unchanged');
  assert.equal(beginSuperSymbolSave(state, symbols), null);
  assert.equal(
    blockSuperSymbolSave(state, superSymbolSaveBlock(state, symbols)),
    state,
  );

  state = selectSuperSymbolCandidate(state, 's5');
  assert.equal(state.candidateSymbolId, 's5');
  state = cancelSuperSymbolCandidate(state);
  assert.equal(state.candidateSymbolId, 's2');
  assert.equal(cancelSuperSymbolCandidate(state), state);
});

test('saving binds the request to the shown revision and keeps completeness and verification', () => {
  const symbols = catalog();
  const initial = createSeriesViewState(
    boardsResponse({
      completeness: 'incomplete',
      runVerification: 'unverified',
    }),
  );
  const chosen = selectSuperSymbolCandidate(initial, 's4');
  const begun = beginSuperSymbolSave(chosen, symbols);
  assert.deepEqual(begun.request, { expectedRevision: 3, symbolId: 's4' });
  assert.equal(begun.state.saving, true);
  // While saving the choice is frozen.
  assert.equal(selectSuperSymbolCandidate(begun.state, 's6'), begun.state);
  assert.equal(beginSuperSymbolSave(begun.state, symbols), null);
  assert.equal(cancelSuperSymbolCandidate(begun.state), begun.state);

  const updated = series({
    completeness: 'incomplete',
    definedBy: 'local-owner',
    revision: 4,
    runVerification: 'unverified',
    superSymbolId: 's4',
  });
  const saved = applySuperSymbolSaved(begun.state, updated, symbols);
  assert.equal(saved.saving, false);
  assert.equal(saved.series.superSymbolId, 's4');
  assert.equal(saved.series.revision, 4);
  assert.equal(saved.candidateSymbolId, 's4');
  assert.equal(saved.series.completeness, 'incomplete');
  assert.equal(saved.series.runVerification, 'unverified');
  assert.equal(saved.notice.kind, 'success');
  assert.match(saved.notice.text, /Symbol s4/);
  // Nothing else changed: the carousel and its position.
  assert.equal(saved.cards, begun.state.cards);
  assert.equal(saved.activeIndex, begun.state.activeIndex);
  assert.equal(isSuperSymbolCandidateDirty(saved), false);
});

test('clearing the symbol saves null against the current revision', () => {
  const symbols = catalog();
  const state = selectSuperSymbolCandidate(
    createSeriesViewState(boardsResponse({ revision: 8, superSymbolId: 's2' })),
    null,
  );
  assert.equal(isSuperSymbolCandidateDirty(state), true);
  assert.equal(superSymbolSaveBlock(state, symbols), null);
  const begun = beginSuperSymbolSave(state, symbols);
  assert.deepEqual(begun.request, { expectedRevision: 8, symbolId: null });
  const cleared = applySuperSymbolSaved(
    begun.state,
    series({ revision: 9, superSymbolId: null }),
    symbols,
  );
  assert.equal(cleared.candidateSymbolId, null);
  assert.match(cleared.notice.text, /Wyczyszczono/);
});

test('a 409 changes nothing in the series and the refresh drops the stale choice', () => {
  const symbols = catalog();
  const begun = beginSuperSymbolSave(
    selectSuperSymbolCandidate(
      goToSeriesPosition(createSeriesViewState(boardsResponse()), 5),
      's4',
    ),
    symbols,
  );
  const conflict = applySuperSymbolConflict(begun.state);
  assert.equal(conflict.saving, false);
  assert.equal(conflict.series, begun.state.series);
  assert.equal(conflict.series.superSymbolId, null);
  assert.equal(conflict.candidateSymbolId, null);
  assert.equal(conflict.notice.kind, 'error');
  assert.match(conflict.notice.text, /Nic nie zapisano/);

  // The fresh series (someone else saved s7 meanwhile) replaces the shown one
  // without overwriting it; the position and the message stay.
  const refreshed = applySeriesRefresh(
    conflict,
    boardsResponse({ revision: 4, superSymbolId: 's7' }),
  );
  assert.equal(refreshed.series.superSymbolId, 's7');
  assert.equal(refreshed.series.revision, 4);
  assert.equal(refreshed.candidateSymbolId, 's7');
  assert.equal(activeSeriesCard(refreshed).sequenceNumber, 105);
  assert.equal(refreshed.notice, conflict.notice);
});

test('a refused save keeps the series and shows the API message', () => {
  const symbols = catalog();
  const begun = beginSuperSymbolSave(
    selectSuperSymbolCandidate(createSeriesViewState(boardsResponse()), 's1'),
    symbols,
  );
  const failed = applySuperSymbolFailure(begun.state, 'Odmowa API');
  assert.equal(failed.saving, false);
  assert.equal(failed.series, begun.state.series);
  assert.equal(failed.candidateSymbolId, 's1');
  assert.equal(failed.notice.text, 'Odmowa API');
});

// --- badges --------------------------------------------------------------

test('the three badges are independent of each other', () => {
  const symbols = catalog();
  const [completeness, symbolBadge, verification] = seriesBadges(
    series({ completeness: 'incomplete', runVerification: 'unverified' }),
    symbols,
  );
  assert.deepEqual(
    [completeness.id, symbolBadge.id, verification.id],
    ['completeness', 'symbol', 'verification'],
  );
  assert.equal(completeness.label, 'Niekompletna');
  assert.equal(symbolBadge.label, 'Do zdefiniowania');
  assert.equal(verification.label, 'Przebieg niezweryfikowany');

  const [c2, s2, v2] = seriesBadges(
    series({
      completeness: 'incomplete',
      runVerification: 'unverified',
      superSymbolId: 's3',
    }),
    symbols,
  );
  assert.equal(s2.label, 'Symbol: Symbol s3');
  assert.equal(s2.tone, 'ok');
  // Defining the symbol did not touch the other two.
  assert.equal(c2.label, completeness.label);
  assert.equal(v2.label, verification.label);

  const [c3, , v3] = seriesBadges(series(), symbols);
  assert.equal(c3.label, 'Kompletna');
  assert.equal(v3.label, 'Przebieg zweryfikowany');
});

test('series ranges are labelled with the trigger and the series positions', () => {
  assert.equal(seriesRangeLabel(series()), '#100 → #101–120');
});

// --- trigger cells, errors, rules ----------------------------------------

test('trigger symbol cells are found row-major and unknown cells are skipped', () => {
  const codes = Array.from({ length: 15 }, () => 'S1');
  codes[2] = 'MUMIA';
  codes[7] = 'MUMIA';
  codes[11] = null;
  codes[14] = 'MUMIA';
  assert.deepEqual(triggerCellIndexes(codes, ['MUMIA']), [2, 7, 14]);
  assert.deepEqual(triggerCellIndexes(codes, []), []);
});

test('API errors of the series routes get Polish messages', () => {
  assert.match(
    superGameSeriesErrorMessage(
      { code: 'SUPER_SYMBOL_NOT_ORDINARY', message: 'x', details: {} },
      'fallback',
    ),
    /zwykły symbol.*SUPER_SYMBOL_NOT_ORDINARY/,
  );
  assert.equal(
    superGameSeriesErrorMessage(
      { code: 'SOMETHING_ELSE', message: 'Kłopot', details: {} },
      'fallback',
    ),
    'Kłopot (SOMETHING_ELSE)',
  );
  assert.equal(superGameSeriesErrorMessage(undefined, 'fallback'), 'fallback');
  assert.equal(
    isSeriesRevisionConflict({ code: 'SUPER_GAME_SERIES_REVISION_CONFLICT' }),
    true,
  );
  assert.equal(isSeriesRevisionConflict({ code: 'OTHER' }), false);
  assert.equal(isSeriesRevisionConflict(null), false);
  assert.equal(isSeriesNotFound({ code: 'SUPER_GAME_SERIES_NOT_FOUND' }), true);
});

test('the board symbols are read with the newest draft, else the newest published rules', () => {
  const versions = [
    { id: 'v1', status: 'published', version: 1 },
    { id: 'v2', status: 'archived', version: 2 },
    { id: 'v3', status: 'published', version: 3 },
  ];
  assert.equal(pickSeriesRulesVersion(versions), 'v3');
  assert.equal(
    pickSeriesRulesVersion([
      ...versions,
      { id: 'v4', status: 'draft', version: 4 },
    ]),
    'v4',
  );
  assert.equal(pickSeriesRulesVersion([]), null);
  assert.deepEqual(
    seriesRulesVersionOptions(versions).map((option) => option.id),
    ['v3', 'v1'],
  );
});

// --- load generations and filter-aware rows (audit round 1) ---------------

function readyList(ids, nextCursor, filters) {
  const initial = createSeriesListState(filters);
  return applySeriesListPage(initial, {
    cursor: null,
    generation: initial.generation,
    response: page(ids, nextCursor),
  });
}

test('a page of an earlier load generation is rejected after a reload, even with the same cursor', () => {
  const first = readyList([100, 200], '200');
  // "Wczytaj kolejne" starts in generation 0 ...
  const loading = startLoadingMoreSeries(first);
  const oldGeneration = loading.generation;
  // ... then the list is refreshed and its new first page has the same cursor.
  const reloaded = reloadSeriesList(loading);
  assert.equal(reloaded.generation, oldGeneration + 1);
  const fresh = applySeriesListPage(reloaded, {
    cursor: null,
    generation: reloaded.generation,
    response: page([100, 200], '200'),
  });
  assert.equal(fresh.items.length, 2);

  const late = applySeriesListPage(fresh, {
    cursor: '200',
    generation: oldGeneration,
    response: {
      ...page([250, 300], null),
      superGameState: STALE,
    },
  });
  assert.equal(late, fresh);
  assert.deepEqual(
    late.items.map((item) => item.triggerSequenceNumber),
    [100, 200],
  );
  assert.equal(late.superGameState, FRESH);
  assert.equal(late.nextCursor, '200');
});

test('the first page of an earlier generation is rejected after a filter change', () => {
  const initial = createSeriesListState();
  const changed = changeSeriesFilters(initial, {
    ...DEFAULT_SERIES_FILTERS,
    defined: 'undefined',
  });
  assert.equal(changed.generation, initial.generation + 1);
  assert.equal(
    applySeriesListPage(changed, {
      cursor: null,
      generation: initial.generation,
      response: page([100]),
    }),
    changed,
  );
});

test('an error of an earlier generation is discarded', () => {
  const initial = createSeriesListState();
  const reloaded = reloadSeriesList(initial);
  const afterLateError = failSeriesList(reloaded, initial.generation, 'Stary');
  assert.equal(afterLateError, reloaded);
  assert.equal(afterLateError.status, 'loading');
  assert.equal(afterLateError.error, null);
  const current = failSeriesList(reloaded, reloaded.generation, 'Nowy');
  assert.equal(current.status, 'error');
  assert.equal(current.error, 'Nowy');
});

test('a series matches the list filters by completeness, verification and symbol', () => {
  const defined = series({ superSymbolId: 's1' });
  const open = series({ superSymbolId: null });
  assert.equal(seriesMatchesFilters(defined, DEFAULT_SERIES_FILTERS), true);
  assert.equal(
    seriesMatchesFilters(defined, {
      ...DEFAULT_SERIES_FILTERS,
      defined: 'defined',
    }),
    true,
  );
  assert.equal(
    seriesMatchesFilters(defined, {
      ...DEFAULT_SERIES_FILTERS,
      defined: 'undefined',
    }),
    false,
  );
  assert.equal(
    seriesMatchesFilters(open, {
      ...DEFAULT_SERIES_FILTERS,
      defined: 'defined',
    }),
    false,
  );
  assert.equal(
    seriesMatchesFilters(open, {
      ...DEFAULT_SERIES_FILTERS,
      completeness: 'incomplete',
    }),
    false,
  );
  assert.equal(
    seriesMatchesFilters(open, {
      ...DEFAULT_SERIES_FILTERS,
      runVerification: 'unverified',
    }),
    false,
  );
});

test('setting a symbol removes the row under "undefined" and keeps it under "defined"', () => {
  const undefinedList = readyList([100, 200], '200', {
    ...DEFAULT_SERIES_FILTERS,
    defined: 'undefined',
  });
  const set = series({
    id: 'series-100',
    revision: 4,
    superSymbolId: 's1',
    triggerSequenceNumber: 100,
  });
  const afterSet = replaceSeriesInList(undefinedList, set);
  assert.deepEqual(
    afterSet.items.map((item) => item.id),
    ['series-200'],
  );
  // The cursor is the trigger number of the last loaded row, so it stays valid.
  assert.equal(afterSet.nextCursor, '200');

  const definedList = readyList([100, 200], null, {
    ...DEFAULT_SERIES_FILTERS,
    defined: 'defined',
  });
  const keptAfterSet = replaceSeriesInList(definedList, set);
  assert.equal(keptAfterSet.items[0], set);
  assert.equal(keptAfterSet.items.length, 2);
});

test('clearing a symbol removes the row under "defined" and keeps it under "undefined"', () => {
  const cleared = series({
    id: 'series-100',
    revision: 5,
    superSymbolId: null,
    triggerSequenceNumber: 100,
  });
  const definedList = readyList([100, 200], null, {
    ...DEFAULT_SERIES_FILTERS,
    defined: 'defined',
  });
  assert.deepEqual(
    replaceSeriesInList(definedList, cleared).items.map((item) => item.id),
    ['series-200'],
  );
  const undefinedList = readyList([100, 200], null, {
    ...DEFAULT_SERIES_FILTERS,
    defined: 'undefined',
  });
  assert.equal(replaceSeriesInList(undefinedList, cleared).items[0], cleared);
});

test('a failed next page can be retried for the same cursor, a failed first page cannot', () => {
  const ready = readyList([100, 200], '200');
  const loading = startLoadingMoreSeries(ready);
  const failed = failSeriesList(loading, loading.generation, 'Blad');
  assert.equal(failed.status, 'error');
  assert.equal(failed.nextCursor, '200');
  assert.equal(failed.items.length, 2);

  const retry = startLoadingMoreSeries(failed);
  assert.equal(retry.status, 'loading');
  assert.equal(retry.error, null);
  const loaded = applySeriesListPage(retry, {
    cursor: '200',
    generation: retry.generation,
    response: page([300], null),
  });
  assert.deepEqual(
    loaded.items.map((item) => item.triggerSequenceNumber),
    [100, 200, 300],
  );

  const firstFailed = failSeriesList(
    createSeriesListState(),
    0,
    'Blad pierwszej strony',
  );
  assert.equal(startLoadingMoreSeries(firstFailed), firstFailed);
});

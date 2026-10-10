import assert from 'node:assert/strict';
import test from 'node:test';

import {
  SUPER_GAME_DEFINE_LINK,
  SUPER_GAME_OPEN_LINK,
  superGameMarkerLabel,
  superGameMarkerLink,
  superGameMarkerNotes,
  superGameSeriesAdminHref,
  superGameSpinLabel,
  superGameStateIsStale,
} from '../src/board-search-super-game.ts';

const series = '33333333-3333-4333-8333-333333333333';

function marker(overrides = {}) {
  return {
    completeness: 'complete',
    kind: 'in_series',
    runVerification: 'verified',
    seriesId: series,
    seriesLength: 10,
    spinIndex: 3,
    superSymbolCode: 'K',
    ...overrides,
  };
}

test('labels name the trigger, the spin with its symbol, or the missing symbol', () => {
  assert.equal(
    superGameMarkerLabel(marker({ kind: 'trigger', spinIndex: null })),
    'Supergra: trigger',
  );
  assert.equal(superGameMarkerLabel(marker()), 'Supergra: spin 3/10, symbol K');
  assert.equal(
    superGameMarkerLabel(marker({ superSymbolCode: null })),
    'Supergra: super symbol do zdefiniowania',
  );
  // A public marker may omit the null fields altogether.
  assert.equal(
    superGameMarkerLabel({
      kind: 'in_series',
      seriesLength: 20,
      spinIndex: 11,
    }),
    'Supergra: super symbol do zdefiniowania',
  );
  assert.equal(
    superGameSpinLabel(marker({ seriesLength: 20, spinIndex: 11 })),
    'spin 11/20',
  );
  assert.equal(
    superGameSpinLabel(marker({ kind: 'trigger', spinIndex: null })),
    '',
  );
});

test('notes flag an incomplete series and a trigger resting on predictions', () => {
  assert.deepEqual(superGameMarkerNotes(marker()), []);
  assert.deepEqual(
    superGameMarkerNotes(
      marker({ completeness: 'incomplete', runVerification: 'unverified' }),
    ),
    [
      'Seria niepełna: brakuje plansz do końca serii.',
      'Trigger lub retrigger oparty na predykcji modelu.',
    ],
  );
});

test('only an explicit fresh = false marks the generation as stale', () => {
  assert.equal(superGameStateIsStale({ fresh: false }), true);
  assert.equal(superGameStateIsStale({ fresh: true }), false);
  assert.equal(superGameStateIsStale(null), false);
  assert.equal(superGameStateIsStale(undefined), false);
});

test('the Admin URL addresses the series view of the game', () => {
  assert.equal(
    superGameSeriesAdminHref('game-1', series),
    `?workspace=games&game=game-1&section=super-games&series=${series}`,
  );
  assert.equal(
    superGameSeriesAdminHref('a b', 'c&d'),
    '?workspace=games&game=a+b&section=super-games&series=c%26d',
  );
});

test('the link needs the Admin capability and the series identity', () => {
  assert.equal(superGameMarkerLink(marker(), 'game-1', undefined), null);
  assert.equal(
    superGameMarkerLink(
      marker({ seriesId: undefined }),
      'game-1',
      superGameSeriesAdminHref,
    ),
    null,
  );
  assert.deepEqual(
    superGameMarkerLink(
      marker({ superSymbolCode: null }),
      'game-1',
      superGameSeriesAdminHref,
    ),
    {
      href: `?workspace=games&game=game-1&section=super-games&series=${series}`,
      label: SUPER_GAME_DEFINE_LINK,
    },
  );
  assert.equal(
    superGameMarkerLink(marker(), 'game-1', superGameSeriesAdminHref)?.label,
    SUPER_GAME_OPEN_LINK,
  );
});

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_ADMIN_NAVIGATION,
  isGameSectionAvailable,
  normalizeAdminNavigation,
  parseAdminNavigation,
  serializeAdminNavigation,
} from '../src/features/catalog/admin-navigation-state.ts';

test('uses the games workspace for an empty or invalid URL', () => {
  assert.deepEqual(parseAdminNavigation(''), DEFAULT_ADMIN_NAVIGATION);
  assert.deepEqual(parseAdminNavigation('?workspace=unknown&section=rules'), {
    workspace: 'games',
    gameId: null,
    section: null,
    seriesId: null,
  });
});

test('restores a valid workspace, game and accordion section', () => {
  assert.deepEqual(
    parseAdminNavigation(
      '?workspace=jobs&game=game-123&section=reviews&unrelated=kept',
    ),
    {
      workspace: 'jobs',
      gameId: 'game-123',
      section: 'reviews',
      seriesId: null,
    },
  );
});

test('restores the v0.4 image selection workspace with its game context', () => {
  assert.deepEqual(
    parseAdminNavigation('?workspace=image-selection&game=game-777'),
    {
      workspace: 'image-selection',
      gameId: 'game-777',
      section: null,
      seriesId: null,
    },
  );
  assert.equal(
    serializeAdminNavigation('', {
      workspace: 'image-selection',
      gameId: 'game-777',
      section: null,
      seriesId: null,
    }),
    '?workspace=image-selection&game=game-777',
  );
});

test('restores the independent symbol verification workspace', () => {
  assert.deepEqual(parseAdminNavigation('?workspace=symbol-verification'), {
    workspace: 'symbol-verification',
    gameId: null,
    section: null,
    seriesId: null,
  });
  assert.equal(
    serializeAdminNavigation('', {
      workspace: 'symbol-verification',
      gameId: null,
      section: null,
      seriesId: null,
    }),
    '?workspace=symbol-verification',
  );
});

test('does not restore a dependent section without a game', () => {
  assert.deepEqual(parseAdminNavigation('?section=symbols'), {
    workspace: 'games',
    gameId: null,
    section: null,
    seriesId: null,
  });
});

test('restores the model quality section only inside a selected game', () => {
  assert.deepEqual(
    parseAdminNavigation('?game=game-123&section=model-quality'),
    {
      workspace: 'games',
      gameId: 'game-123',
      section: 'model-quality',
      seriesId: null,
    },
  );
});

test('restores board search only inside the selected game context', () => {
  assert.deepEqual(
    parseAdminNavigation('?game=game-123&section=board-search'),
    {
      workspace: 'games',
      gameId: 'game-123',
      section: 'board-search',
      seriesId: null,
    },
  );
});

test('rejects removed Dataset and Manual Review section URLs', () => {
  for (const section of ['datasets', 'manual-review']) {
    assert.deepEqual(
      parseAdminNavigation(`?game=game-123&section=${section}`),
      {
        workspace: 'games',
        gameId: 'game-123',
        section: null,
        seriesId: null,
      },
    );
  }
});

test('serializes deterministic navigation without dropping unrelated params', () => {
  assert.equal(
    serializeAdminNavigation('?unrelated=kept', {
      workspace: 'releases',
      gameId: 'game-123',
      section: 'rules',
      seriesId: null,
    }),
    '?unrelated=kept&workspace=releases&game=game-123&section=rules',
  );
});

test('removes game-dependent state when the active game is cleared', () => {
  assert.equal(
    serializeAdminNavigation('?workspace=jobs&game=old&section=imports', {
      workspace: 'games',
      gameId: null,
      section: null,
      seriesId: null,
    }),
    '',
  );
});

test('restores the super games section and its opened series (TASK-0934)', () => {
  assert.deepEqual(
    parseAdminNavigation(
      '?workspace=games&game=game-1&section=super-games&series=series-9',
    ),
    {
      workspace: 'games',
      gameId: 'game-1',
      section: 'super-games',
      seriesId: 'series-9',
    },
  );
  assert.equal(
    parseAdminNavigation('?game=game-1&section=super-games&series=%20')
      .seriesId,
    null,
  );
});

test('ignores the series parameter outside the super games section', () => {
  assert.equal(
    parseAdminNavigation('?game=game-1&section=rules&series=series-9').seriesId,
    null,
  );
  assert.equal(parseAdminNavigation('?series=series-9').seriesId, null);
  assert.equal(
    parseAdminNavigation('?section=super-games&series=series-9').seriesId,
    null,
  );
});

test('serialises the series only inside the super games section', () => {
  assert.equal(
    serializeAdminNavigation('', {
      workspace: 'games',
      gameId: 'game-1',
      section: 'super-games',
      seriesId: 'series-9',
    }),
    '?game=game-1&section=super-games&series=series-9',
  );
  assert.equal(
    serializeAdminNavigation('?game=game-1&section=super-games&series=old', {
      workspace: 'games',
      gameId: 'game-1',
      section: 'super-games',
      seriesId: null,
    }),
    '?game=game-1&section=super-games',
  );
  assert.equal(
    serializeAdminNavigation('?game=game-1&section=super-games&series=old', {
      workspace: 'games',
      gameId: 'game-1',
      section: 'rules',
      seriesId: 'old',
    }),
    '?game=game-1&section=rules',
  );
  assert.equal(
    serializeAdminNavigation('?game=game-1&section=super-games&series=old', {
      workspace: 'games',
      gameId: null,
      section: null,
      seriesId: 'old',
    }),
    '',
  );
});

test('a round trip keeps the opened series', () => {
  const state = {
    workspace: 'games',
    gameId: 'game-1',
    section: 'super-games',
    seriesId: 'series-9',
  };
  assert.deepEqual(
    parseAdminNavigation(serializeAdminNavigation('', state)),
    state,
  );
});

test('normalising drops a series that does not belong to the section', () => {
  const kept = {
    workspace: 'games',
    gameId: 'game-1',
    section: 'super-games',
    seriesId: 'series-9',
  };
  assert.equal(normalizeAdminNavigation(kept), kept);
  assert.equal(
    normalizeAdminNavigation({ ...kept, section: 'imports' }).seriesId,
    null,
  );
  assert.equal(
    normalizeAdminNavigation({ ...kept, gameId: null, section: null }).seriesId,
    null,
  );
});

test('the super games section is hidden for games without a super game', () => {
  assert.equal(
    isGameSectionAvailable('super-games', { superGameKind: 'none' }),
    false,
  );
  assert.equal(isGameSectionAvailable('super-games', null), false);
  assert.equal(
    isGameSectionAvailable('super-games', {
      superGameKind: 'wild_super_spins',
    }),
    true,
  );
  assert.equal(
    isGameSectionAvailable('rules', { superGameKind: 'none' }),
    true,
  );
});

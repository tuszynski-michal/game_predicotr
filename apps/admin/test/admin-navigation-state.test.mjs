import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_ADMIN_NAVIGATION,
  parseAdminNavigation,
  serializeAdminNavigation,
} from '../src/features/catalog/admin-navigation-state.ts';

test('uses the games workspace for an empty or invalid URL', () => {
  assert.deepEqual(parseAdminNavigation(''), DEFAULT_ADMIN_NAVIGATION);
  assert.deepEqual(parseAdminNavigation('?workspace=unknown&section=rules'), {
    workspace: 'games',
    gameId: null,
    section: null,
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
    },
  );
  assert.equal(
    serializeAdminNavigation('', {
      workspace: 'image-selection',
      gameId: 'game-777',
      section: null,
    }),
    '?workspace=image-selection&game=game-777',
  );
});

test('restores the independent symbol verification workspace', () => {
  assert.deepEqual(parseAdminNavigation('?workspace=symbol-verification'), {
    workspace: 'symbol-verification',
    gameId: null,
    section: null,
  });
  assert.equal(
    serializeAdminNavigation('', {
      workspace: 'symbol-verification',
      gameId: null,
      section: null,
    }),
    '?workspace=symbol-verification',
  );
});

test('does not restore a dependent section without a game', () => {
  assert.deepEqual(parseAdminNavigation('?section=symbols'), {
    workspace: 'games',
    gameId: null,
    section: null,
  });
});

test('restores the model quality section only inside a selected game', () => {
  assert.deepEqual(
    parseAdminNavigation('?game=game-123&section=model-quality'),
    {
      workspace: 'games',
      gameId: 'game-123',
      section: 'model-quality',
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
    }),
    '',
  );
});

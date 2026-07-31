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

test('does not restore a dependent section without a game', () => {
  assert.deepEqual(parseAdminNavigation('?section=symbols'), {
    workspace: 'games',
    gameId: null,
    section: null,
  });
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

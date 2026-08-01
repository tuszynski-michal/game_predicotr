import assert from 'node:assert/strict';
import test from 'node:test';

import {
  rulesVersionToDraft,
  selectCurrentRulesVersion,
  selectRulesGameId,
  upsertRulesVersion,
  validateRulesVersionDraft,
} from '../src/features/rules/rules-version-state.ts';

const game = {
  code: 'game-1',
  createdAt: '2026-07-27T10:00:00Z',
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Game 1',
  status: 'active',
  updatedAt: '2026-07-27T10:00:00Z',
};

const versionOne = {
  columns: 5,
  createdAt: '2026-07-27T10:00:00Z',
  gameId: game.id,
  id: '22222222-2222-4222-8222-222222222222',
  publishedAt: null,
  rows: 3,
  spinCost: 10,
  status: 'draft',
  version: 1,
};

test('validates integer dimensions and spin cost', () => {
  assert.deepEqual(
    validateRulesVersionDraft({
      columns: ' 5 ',
      rows: ' 3 ',
      spinCost: ' 10 ',
    }),
    {
      valid: true,
      value: { columns: 5, rows: 3, spinCost: 10 },
    },
  );
  assert.equal(
    validateRulesVersionDraft({
      columns: '5',
      rows: '0',
      spinCost: '10',
    }).valid,
    false,
  );
  assert.equal(
    validateRulesVersionDraft({
      columns: '1.5',
      rows: '3',
      spinCost: '10',
    }).valid,
    false,
  );
  assert.equal(
    validateRulesVersionDraft({
      columns: '5',
      rows: '3',
      spinCost: '-1',
    }).valid,
    false,
  );
  assert.deepEqual(rulesVersionToDraft(versionOne), {
    columns: '5',
    rows: '3',
    spinCost: '10',
  });
});

test('chooses an available game and keeps rules versions newest first', () => {
  const archived = { ...game, id: 'archived', status: 'archived' };
  const active = { ...game, id: 'active' };
  assert.equal(selectRulesGameId([archived, active], null), 'active');
  assert.equal(selectRulesGameId([archived, active], 'archived'), 'archived');

  const versionTwo = {
    ...versionOne,
    id: '33333333-3333-4333-8333-333333333333',
    version: 2,
  };
  const inserted = upsertRulesVersion([versionOne], versionTwo);
  const updated = upsertRulesVersion(inserted, {
    ...versionOne,
    spinCost: 25,
  });

  assert.deepEqual(
    inserted.map((item) => item.version),
    [2, 1],
  );
  assert.equal(updated[1].spinCost, 25);
});

test('current rules workspace prefers the newest draft then the newest published version', () => {
  const published = { ...versionOne, status: 'published' };
  const newerPublished = {
    ...published,
    id: 'published-2',
    version: 2,
  };
  const draft = { ...versionOne, id: 'draft-3', version: 3 };
  const archived = {
    ...versionOne,
    id: 'archived-4',
    status: 'archived',
    version: 4,
  };

  assert.equal(
    selectCurrentRulesVersion([published, newerPublished, draft, archived])?.id,
    draft.id,
  );
  assert.equal(
    selectCurrentRulesVersion([published, newerPublished, archived])?.id,
    newerPublished.id,
  );
  assert.equal(selectCurrentRulesVersion([archived]), null);
});

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  archivePayline,
  savePayline,
} from '../src/features/rules/payline-actions.ts';

const rulesVersionId = '11111111-1111-4111-8111-111111111111';
const savedPayline = {
  code: 'line-v',
  displayOrder: 10,
  id: '22222222-2222-4222-8222-222222222222',
  isActive: true,
  name: 'V',
  rowPath: [0, 1, 2, 1, 0],
  rulesVersionId,
};
const draft = {
  code: 'line-v',
  isActive: true,
  rowPath: [0, 1, 2, 1, 0],
};

function createClient(overrides = {}) {
  return {
    archivePayline: async () => ({ data: undefined }),
    createPayline: async () => ({ data: savedPayline }),
    listPaylines: async () => ({ data: [] }),
    updatePayline: async () => ({ data: savedPayline }),
    ...overrides,
  };
}

test('creates a payline with the complete zero-based contract', async () => {
  let receivedRulesVersionId;
  let request;
  const result = await savePayline(
    createClient({
      createPayline: async (currentRulesVersionId, body) => {
        receivedRulesVersionId = currentRulesVersionId;
        request = body;
        return { data: savedPayline };
      },
    }),
    rulesVersionId,
    { mode: 'create' },
    draft,
    [
      {
        ...savedPayline,
        displayOrder: 9,
      },
    ],
  );

  assert.equal(receivedRulesVersionId, rulesVersionId);
  assert.deepEqual(request, {
    code: 'line-v',
    displayOrder: 10,
    isActive: true,
    name: 'line-v',
    rowPath: [0, 1, 2, 1, 0],
  });
  assert.deepEqual(result, { ok: true, payline: savedPayline });
});

test('updates mutable fields without sending the stable code', async () => {
  let request;
  const result = await savePayline(
    createClient({
      updatePayline: async (_rulesVersionId, _paylineId, body) => {
        request = body;
        return { data: { ...savedPayline, ...body } };
      },
    }),
    rulesVersionId,
    { mode: 'edit', paylineId: savedPayline.id },
    { ...draft, isActive: false },
    [savedPayline],
  );

  assert.equal('code' in request, false);
  assert.equal('name' in request, false);
  assert.equal('displayOrder' in request, false);
  assert.equal(request.isActive, false);
  assert.equal(result.ok, true);
});

test('archives through the typed boundary and preserves duplicate errors', async () => {
  let archivedId;
  const success = await archivePayline(
    createClient({
      archivePayline: async (_rulesVersionId, paylineId) => {
        archivedId = paylineId;
        return { data: undefined };
      },
    }),
    rulesVersionId,
    savedPayline.id,
  );
  const duplicate = await savePayline(
    createClient({
      createPayline: async () => ({
        error: {
          code: 'DUPLICATE_PAYLINE',
          details: { existingPaylineId: savedPayline.id },
          message: 'A payline with this rowPath already exists.',
        },
      }),
    }),
    rulesVersionId,
    { mode: 'create' },
    draft,
    [],
  );

  assert.equal(archivedId, savedPayline.id);
  assert.deepEqual(success, { ok: true });
  assert.deepEqual(duplicate, {
    error: 'A payline with this rowPath already exists. (DUPLICATE_PAYLINE)',
    ok: false,
  });
});

test('blocks a create before the API call when automatic display order would overflow', async () => {
  let called = false;
  const result = await savePayline(
    createClient({
      createPayline: async () => {
        called = true;
        return { data: savedPayline };
      },
    }),
    rulesVersionId,
    { mode: 'create' },
    draft,
    [{ ...savedPayline, displayOrder: 2_147_483_647 }],
  );

  assert.equal(called, false);
  assert.deepEqual(result, {
    error:
      'Nie można nadać automatycznej kolejności: osiągnięto maksymalną liczbę wzorców.',
    ok: false,
  });
});

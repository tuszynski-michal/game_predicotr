import assert from 'node:assert/strict';
import test from 'node:test';

import {
  emptyPaylineDraft,
  formatRowPath1Based,
  isPaylineComplete,
  markPaylineArchived,
  paylineToDraft,
  selectPaylineCell,
  upsertPayline,
  validatePaylineDraft,
} from '../src/features/rules/payline-editor-state.ts';

const payline = {
  code: 'line-v',
  displayOrder: 10,
  id: '22222222-2222-4222-8222-222222222222',
  isActive: true,
  name: 'V',
  rowPath: [0, 1, 2, 1, 0],
  rulesVersionId: '11111111-1111-4111-8111-111111111111',
};

test('grid selection keeps exactly one selected row per column', () => {
  const empty = emptyPaylineDraft(5);
  const first = selectPaylineCell(empty.rowPath, 1, 2);
  const replaced = selectPaylineCell(first, 1, 0);
  const completed = [0, 0, 1, 2, 1];

  assert.deepEqual(empty.rowPath, [null, null, null, null, null]);
  assert.deepEqual(first, [null, 2, null, null, null]);
  assert.deepEqual(replaced, [null, 0, null, null, null]);
  assert.equal(isPaylineComplete(replaced, 5), false);
  assert.equal(isPaylineComplete(completed, 5), true);
});

test('validates a complete zero-based row path and normalizes fields', () => {
  assert.deepEqual(
    validatePaylineDraft(
      {
        code: ' line-v ',
        displayOrder: ' 10 ',
        isActive: true,
        name: ' V ',
        rowPath: [0, 1, 2, 1, 0],
      },
      { columns: 5, rows: 3 },
    ),
    {
      valid: true,
      value: {
        code: 'line-v',
        displayOrder: 10,
        isActive: true,
        name: 'V',
        rowPath: [0, 1, 2, 1, 0],
      },
    },
  );
  assert.equal(
    validatePaylineDraft(emptyPaylineDraft(5), {
      columns: 5,
      rows: 3,
    }).valid,
    false,
  );
  assert.equal(
    validatePaylineDraft(
      {
        ...emptyPaylineDraft(5),
        code: 'line',
        name: 'Line',
        rowPath: [0, 1, 3, 1, 0],
      },
      { columns: 5, rows: 3 },
    ).valid,
    false,
  );
});

test('presents one-based rows and keeps archived records in canonical order', () => {
  const earlier = {
    ...payline,
    code: 'line-top',
    displayOrder: 5,
    id: 'earlier',
    rowPath: [0, 0, 0, 0, 0],
  };
  const inserted = upsertPayline([payline], earlier);
  const archived = markPaylineArchived(inserted, payline.id);

  assert.equal(formatRowPath1Based(payline.rowPath), '[1, 2, 3, 2, 1]');
  assert.deepEqual(
    inserted.map((item) => item.id),
    ['earlier', payline.id],
  );
  assert.equal(archived[1].isActive, false);
  assert.equal(inserted[1].isActive, true);
  assert.equal(paylineToDraft(payline).code, 'line-v');
});

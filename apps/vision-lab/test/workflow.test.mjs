import test from 'node:test';
import assert from 'node:assert/strict';
import {
  boardStatus,
  photoCounts,
  matchesPhotoFilter,
  positionIndices,
  nextApprovedPosition,
  approvalSummary,
} from '../src/lib/annotation-status.ts';
import {
  enqueueToast,
  tickToasts,
  toastDuration,
} from '../../../packages/ui/src/toast-store.ts';

const row = (board_index, fields = {}) => ({
  board_index,
  presence: 'present',
  full_approved: false,
  location_approved: false,
  ...fields,
});
test('counts separate present full grids, locations and drafts; absence never counts as a full grid', () => {
  const rows = [
    row(0, { full_approved: true, location_approved: true }),
    row(1, { location_approved: true }),
    row(2),
    row(3, {
      presence: 'absent',
      full_approved: true,
      location_approved: true,
    }),
  ];
  assert.deepEqual(photoCounts(rows), {
    full: 1,
    location: 2,
    draft: 1,
    saved: 4,
  });
  assert.equal(boardStatus(), 'missing');
  assert.equal(matchesPhotoFilter(rows, 'full'), true);
  assert.equal(matchesPhotoFilter(rows, 'missing'), false);
  assert.equal(matchesPhotoFilter([], 'missing'), true);
  assert.equal(matchesPhotoFilter([row(0)], 'started'), true);
  assert.equal(matchesPhotoFilter([row(0)], 'full'), false);
});
test('position nine is only the automatic stop; stored positions beyond nine remain selectable', () => {
  assert.deepEqual(
    positionIndices([row(12), row(9)]),
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12],
  );
  for (const action of ['approve_full', 'approve_location']) {
    assert.equal(
      nextApprovedPosition({ action, annotation: { board_index: 0 } }),
      1,
    );
    assert.equal(
      nextApprovedPosition({ action, annotation: { board_index: 8 } }),
      8,
    );
    assert.equal(
      nextApprovedPosition({ action, annotation: { board_index: 12 } }),
      12,
    );
  }
  assert.equal(
    nextApprovedPosition({ action: 'draft', annotation: { board_index: 0 } }),
    0,
  );
});
test('nine-grid success requires all nine exact positions, not arbitrary approved count', () => {
  const rows = Array.from({ length: 9 }, (_, i) =>
    row(i, { full_approved: true }),
  );
  assert.match(approvalSummary(rows), /Zatwierdzono 9/);
  rows[0].board_index = 10;
  assert.match(approvalSummary(rows), /Bez pełnego zatwierdzenia.*: 1\./);
});
test('toast clock starts only when visible and pauses for hidden tabs and interaction', () => {
  let items = [];
  for (let i = 0; i < 4; i++)
    items = enqueueToast(items, { kind: 'success', message: `ok${i}` }, i);
  assert.equal(toastDuration('error'), 180000);
  assert.equal(toastDuration('warning'), 180000);
  assert.equal(toastDuration('info'), 120000);
  assert.deepEqual(tickToasts(items, 5000, true), items);
  items[0].paused = true;
  const next = tickToasts(items, 120000, false);
  assert.deepEqual(
    next.map((item) => item.id),
    [0, 3],
  );
  assert.equal(next[1].remaining, 120000);
});
test('toast results preserve errors and repeated result removes same-operation progress', () => {
  let items = enqueueToast([], { kind: 'error', message: 'failed' }, 1);
  items = enqueueToast(
    items,
    { kind: 'info', message: 'working', operation: 'save' },
    2,
  );
  items = enqueueToast(
    items,
    { kind: 'success', message: 'saved', operation: 'save' },
    3,
  );
  items = enqueueToast(
    items,
    { kind: 'info', message: 'working', operation: 'save' },
    4,
  );
  items = enqueueToast(
    items,
    { kind: 'success', message: 'saved', operation: 'save' },
    5,
  );
  assert.deepEqual(
    items.map((item) => [item.kind, item.count]),
    [
      ['error', 1],
      ['success', 2],
    ],
  );
});

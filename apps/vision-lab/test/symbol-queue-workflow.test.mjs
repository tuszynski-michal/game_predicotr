import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import {
  confirmedQueuePage,
  queueDecision,
  queueSourceCaption,
  selectableQueueItems,
} from '../src/lib/symbol-queue-workflow.ts';

const page = {
  kind: 'lab_queue',
  revision: 9,
  read_token: 'view',
  total: 2,
  items: [0, 1].map((cell_index) => ({
    binding: { crop_id: `crop-${cell_index}`, cell_index },
    status: 'unassigned',
    png_base64: 'bytes',
    reason: null,
  })),
};
const active = {
  version: 2,
  digest: 'digest',
  entries: [{ id: 'lemon', display_name: 'Cytryna' }],
};

test('assignment requires displayed image and keeps only selected visible bindings', () => {
  const selected = new Set(['crop-0', 'crop-1']);
  assert.equal(
    queueDecision(page, selected, new Set(), new Set(), active, 'lemon', 'id'),
    null,
  );
  const loaded = new Set(['crop-0', 'crop-1']);
  const failed = new Set(['crop-1']);
  assert.deepEqual(
    selectableQueueItems(page, loaded, failed).map((x) => x.binding.crop_id),
    ['crop-0'],
  );
  assert.equal(
    queueDecision(page, selected, loaded, failed, active, 'lemon', 'id'),
    null,
  );
  const decision = queueDecision(
    page,
    new Set(['crop-0']),
    loaded,
    failed,
    active,
    'lemon',
    'id',
  );
  assert.equal(decision.op, 'label_cells_decide');
  assert.deepEqual(decision.bindings, [page.items[0].binding]);
  assert.equal(decision.expected_revision, 9);
  assert.equal(
    queueDecision(
      page,
      new Set(['crop-0']),
      loaded,
      failed,
      active,
      'other',
      'id',
    ),
    null,
  );
});

test('2000 visible crops do not permit more than 30 in one assignment', () => {
  const many = {
    ...page,
    items: Array.from({ length: 31 }, (_, i) => ({
      binding: { crop_id: `crop-${i}`, cell_index: i % 15 },
      status: 'unassigned',
      png_base64: 'bytes',
      reason: null,
    })),
  };
  const selected = new Set(many.items.map((item) => item.binding.crop_id));
  assert.equal(
    queueDecision(many, selected, selected, new Set(), active, 'lemon', 'id'),
    null,
  );
});

test('confirmed writes freeze pixels, advance CAS and exclude assigned crops without renewing token', () => {
  const request = queueDecision(
    page,
    new Set(['crop-0']),
    new Set(['crop-0']),
    new Set(),
    active,
    'lemon',
    'first',
  );
  const result = {
    revision: 10,
    request_id: 'first',
    label_valid: true,
    decision_ids: ['decision-0'],
  };
  const next = confirmedQueuePage(page, { request, result });
  assert.equal(next.items.length, 2);
  assert.equal(next.items[0].png_base64, page.items[0].png_base64);
  assert.equal(next.items[0].binding, page.items[0].binding);
  assert.equal(next.items[0].status, 'assigned');
  assert.equal(next.items[1], page.items[1]);
  assert.equal(next.read_token, page.read_token);
  assert.equal(next.revision, 10);
  assert.equal(
    queueDecision(
      next,
      new Set(['crop-0']),
      new Set(['crop-0']),
      new Set(),
      active,
      'lemon',
      'again',
    ),
    null,
  );
  const second = queueDecision(
    next,
    new Set(['crop-1']),
    new Set(['crop-1']),
    new Set(),
    active,
    'lemon',
    'second',
  );
  assert.equal(second.expected_revision, 10);
  assert.equal(
    confirmedQueuePage(page, {
      request,
      result: { ...result, label_valid: false },
    }),
    null,
  );
  assert.equal(
    confirmedQueuePage(page, { request, result: { ...result, revision: 12 } }),
    null,
  );
  assert.equal(
    confirmedQueuePage(page, {
      request,
      result: { ...result, request_id: 'other' },
    }),
    null,
  );
  assert.equal(
    confirmedQueuePage(page, {
      request: {
        ...request,
        bindings: [{ ...request.bindings[0], cell_index: 8 }],
      },
      result,
    }),
    null,
  );
});

test('queue exposes image error and stale-page recovery controls', async () => {
  const source = await readFile(
    new URL('../src/components/symbol-candidate-queue.tsx', import.meta.url),
    'utf8',
  );
  assert.match(source, /onLoad=/);
  assert.match(source, /onError=/);
  assert.match(source, /Odśwież poczekalnię/);
  assert.match(source, /read_token/);
});

test('queue caption keeps the distinguishing frame suffix of long names', () => {
  assert.equal(
    queueSourceCaption('blazing zd/BLAZING476100__BLAZING476100_002545.jpg'),
    '…476100_002545.jpg',
  );
  assert.equal(queueSourceCaption('short.jpg'), 'short.jpg');
});

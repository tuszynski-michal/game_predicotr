import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { queueDecision, queueSourceCaption, selectableQueueItems } from '../src/lib/symbol-queue-workflow.ts';

const page = {
  kind: 'lab_queue', revision: 9, read_token: 'view', total: 2,
  items: [0, 1].map((cell_index) => ({
    binding: { crop_id: `crop-${cell_index}`, cell_index },
    status: 'unassigned', png_base64: 'bytes', reason: null,
  })),
};
const active = { version: 2, digest: 'digest', entries: [{ id: 'lemon', display_name: 'Cytryna' }] };

test('assignment requires displayed image and keeps only selected visible bindings', () => {
  const selected = new Set(['crop-0', 'crop-1']);
  assert.equal(queueDecision(page, selected, new Set(), new Set(), active,
    'lemon', 'id'), null);
  const loaded = new Set(['crop-0', 'crop-1']);
  const failed = new Set(['crop-1']);
  assert.deepEqual(selectableQueueItems(page, loaded, failed).map((x) => x.binding.crop_id), ['crop-0']);
  assert.equal(queueDecision(page, selected, loaded, failed, active, 'lemon', 'id'), null);
  const decision = queueDecision(page, new Set(['crop-0']), loaded, failed, active, 'lemon', 'id');
  assert.equal(decision.op, 'label_cells_decide');
  assert.deepEqual(decision.bindings, [page.items[0].binding]);
  assert.equal(decision.expected_revision, 9);
  assert.equal(queueDecision(page, new Set(['crop-0']), loaded, failed, active, 'other', 'id'), null);
});

test('queue exposes image error and stale-page recovery controls', async () => {
  const source = await readFile(new URL('../src/components/symbol-candidate-queue.tsx', import.meta.url), 'utf8');
  assert.match(source, /onLoad=/);
  assert.match(source, /onError=/);
  assert.match(source, /Odśwież poczekalnię/);
  assert.match(source, /read_token/);
});

test('queue caption keeps the distinguishing frame suffix of long names', () => {
  assert.equal(queueSourceCaption('blazing zd/BLAZING476100__BLAZING476100_002545.jpg'),
    '…476100_002545.jpg');
  assert.equal(queueSourceCaption('short.jpg'), 'short.jpg');
});

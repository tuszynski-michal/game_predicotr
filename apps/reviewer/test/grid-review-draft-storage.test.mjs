import assert from 'node:assert/strict';
import test from 'node:test';
import {
  gridDraftKey,
  serializeGridDraft,
  restoreGridDraft,
} from '../src/features/grid-reviews/grid-review-draft-storage.ts';

const items = Array.from({ length: 9 }, (_, i) => ({
  slotId: `slot-${i}`,
  gameId: 'game',
  importJobId: 'job',
  sourceImageId: 'source',
  sourceChecksumSha256: 'a'.repeat(64),
  sourceWidth: 1000,
  sourceHeight: 800,
  geometryRevision: 1,
  resolutionRevision: 1,
}));
const drafts = new Map(items.map((item) => [item.slotId, [{ x: 10, y: 20 }]]));

test('reload restores all nine drafts including unfinished corners', () => {
  const text = serializeGridDraft(items, drafts);
  assert.deepEqual(restoreGridDraft(items, text), drafts);
  assert.equal(gridDraftKey(items), 'grid-source-draft-v1:game:job:source');
});
test('changed source revision, removed slot and invalid coordinates reject draft', () => {
  const text = serializeGridDraft(items, drafts);
  assert.equal(
    restoreGridDraft(
      [{ ...items[0], geometryRevision: 2 }, ...items.slice(1)],
      text,
    ),
    null,
  );
  assert.equal(restoreGridDraft(items.slice(1), text), null);
  const changed = new Map(drafts);
  changed.set(items[0].slotId, [{ x: 1001, y: 0 }]);
  assert.equal(
    restoreGridDraft(items, serializeGridDraft(items, changed)),
    null,
  );
  assert.equal(restoreGridDraft(items, '{'), null);
});

import assert from 'node:assert/strict';
import test from 'node:test';
import {
  readPageGeometryDraft,
  writePageGeometryDraft,
  clearPageGeometryDraft,
  PageGeometryDraftConflict,
  clearCommittedPageGeometryDraft,
  serializePageGeometryDraft,
} from '../src/features/imports/page-geometry-draft-storage.ts';
const scope = {
  gameId: 'g',
  uploadId: 'u',
  preflightJobId: 'p',
  checksum: 'a'.repeat(64),
  revision: 1,
  width: 300,
  height: 200,
  count: 9,
};
const quad = [
  { x: 0, y: -10 },
  { x: 299, y: -10 },
  { x: 299, y: 199 },
  { x: 0, y: 199 },
];
const draft = {
  quads: Array(9).fill(quad),
  flags: Array(9).fill({ partial: true, exclude: true, manualUnavailable: [] }),
  pageCorners: quad,
  cornerPlacement: null,
  boardCornerPlacement: [{ x: -10, y: 20 }],
};
function storage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
    values,
  };
}
test('navigation and a new reader restore flags, all slots and unfinished corners without API writes', () => {
  const store = storage();
  writePageGeometryDraft(store, scope, draft);
  assert.equal(
    readPageGeometryDraft(store, { ...scope, checksum: 'b'.repeat(64) }),
    null,
  );
  assert.deepEqual(
    readPageGeometryDraft(store, JSON.parse(JSON.stringify(scope))),
    draft,
  );
  assert.throws(
    () => readPageGeometryDraft(store, { ...scope, revision: 2 }),
    PageGeometryDraftConflict,
  );
  assert.deepEqual(readPageGeometryDraft(store, scope), draft);
  clearPageGeometryDraft(store, { ...scope, revision: 2 });
  assert.equal(store.values.size, 0);
});
test('corrupted local data never becomes source geometry', () => {
  const store = storage();
  writePageGeometryDraft(store, scope, { ...draft, flags: [] });
  assert.throws(() => readPageGeometryDraft(store, scope), /Uszkodzony/);
  writePageGeometryDraft(store, scope, {
    ...draft,
    pageCorners: [{ x: 99999, y: 1 }],
  });
  assert.throws(() => readPageGeometryDraft(store, scope), /Uszkodzony/);
});

test('successful save cleans only its own submitted draft, not another tab or revision', () => {
  const store = storage();
  const submitted = serializePageGeometryDraft(scope, draft);
  const otherDraft = { ...draft, boardCornerPlacement: null };
  writePageGeometryDraft(store, scope, otherDraft);
  clearCommittedPageGeometryDraft(store, scope, submitted);
  assert.deepEqual(readPageGeometryDraft(store, scope), otherDraft);
  writePageGeometryDraft(store, scope, draft);
  const nextScope = { ...scope, revision: 2 };
  writePageGeometryDraft(store, nextScope, otherDraft);
  clearCommittedPageGeometryDraft(store, scope, submitted);
  assert.deepEqual(readPageGeometryDraft(store, nextScope), otherDraft);
  clearCommittedPageGeometryDraft(
    store,
    nextScope,
    serializePageGeometryDraft(nextScope, otherDraft),
  );
  assert.equal(store.values.size, 0);
});

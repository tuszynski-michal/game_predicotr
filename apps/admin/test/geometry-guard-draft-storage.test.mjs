import assert from 'node:assert/strict';
import test from 'node:test';
import {
  readGuardDraft,
  writeGuardDraft,
  clearGuardDraft,
  clearCommittedGuardDraft,
  guardDraftKey,
} from '../src/features/imports/geometry-guard-draft-storage.ts';
test('guard drafts retain masks and independent exclusions; server revisions cannot be overwritten', () => {
  const values = new Map(),
    store = {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    };
  const key = guardDraftKey('g', 'u', 'j', 'a'.repeat(64));
  const draft = {
    disposition: 'partial',
    dirty: true,
    quad: [
      { x: -5, y: 0 },
      { x: 20, y: 0 },
      { x: 20, y: 199 },
      { x: -5, y: 199 },
    ],
    unavailable: [0],
    excludeGeometry: true,
    baseRevision: 1,
  };
  writeGuardDraft(store, key, 0, draft);
  assert.deepEqual(readGuardDraft(store, key, 0, 1, 300, 200), draft);
  assert.equal(readGuardDraft(store, key, 1, 0, 300, 200), null);
  assert.throws(
    () => readGuardDraft(store, key, 0, 2, 300, 200),
    /starszej rewizji/,
  );
  const newer = { ...draft, unavailable: [0, 1] };
  writeGuardDraft(store, key, 0, newer);
  clearCommittedGuardDraft(store, key, 0, draft);
  assert.deepEqual(readGuardDraft(store, key, 0, 1, 300, 200), newer);
  clearGuardDraft(store, key, 0);
  assert.equal(values.size, 0);
});

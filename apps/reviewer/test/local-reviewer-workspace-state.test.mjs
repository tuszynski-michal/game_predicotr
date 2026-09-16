import assert from 'node:assert/strict';
import test from 'node:test';

import { initialLocalReviewerWorkspaceMode } from '../src/features/access/local-reviewer-workspace-state.ts';

test('opens deferred correction when the import has no materialized grids', () => {
  assert.equal(initialLocalReviewerWorkspaceMode(0, 36), 'deferred');
});

test('keeps ordinary grid validation when materialized boards exist', () => {
  assert.equal(initialLocalReviewerWorkspaceMode(9, 36), 'grid');
  assert.equal(initialLocalReviewerWorkspaceMode(9, 0), 'grid');
  assert.equal(initialLocalReviewerWorkspaceMode(0, 0), 'grid');
});

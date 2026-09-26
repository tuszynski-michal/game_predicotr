import assert from 'node:assert/strict';
import test from 'node:test';

import { initialLocalReviewerWorkspaceMode } from '../src/features/access/local-reviewer-workspace-state.ts';

test('opens deferred correction whenever the import has incomplete grids', () => {
  assert.equal(initialLocalReviewerWorkspaceMode(0, 36), 'deferred');
  assert.equal(initialLocalReviewerWorkspaceMode(9, 36), 'deferred');
});

test('keeps ordinary grid validation only when no incomplete grids remain', () => {
  assert.equal(initialLocalReviewerWorkspaceMode(9, 0), 'grid');
  assert.equal(initialLocalReviewerWorkspaceMode(0, 0), 'grid');
});

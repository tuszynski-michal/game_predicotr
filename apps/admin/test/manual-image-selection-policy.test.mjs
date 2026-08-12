import assert from 'node:assert/strict';
import test from 'node:test';

import {
  defaultManualCandidateIndex,
  nextUnresolvedManualIndex,
} from '../src/features/image-selection/manual-image-selection-policy.ts';

test('defaults to the middle candidate for at most twenty images', () => {
  assert.equal(defaultManualCandidateIndex(0), null);
  assert.equal(defaultManualCandidateIndex(1), 0);
  assert.equal(defaultManualCandidateIndex(2), 0);
  assert.equal(defaultManualCandidateIndex(13), 6);
  assert.equal(defaultManualCandidateIndex(20), 9);
});

test('defaults to the tenth candidate for larger galleries', () => {
  assert.equal(defaultManualCandidateIndex(21), 9);
  assert.equal(defaultManualCandidateIndex(500), 9);
});

test('advances to the next unresolved group and skips resolved decisions', () => {
  assert.equal(nextUnresolvedManualIndex([true, true, false, true], 0), 1);
  assert.equal(nextUnresolvedManualIndex([true, false, false, true], 0), 3);
  assert.equal(nextUnresolvedManualIndex([false, false, false], 1), 1);
});

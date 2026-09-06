import assert from 'node:assert/strict';
import test from 'node:test';

import { SymbolReviewRequestCoordinator } from '../src/features/symbol-reviews/symbol-review-request-coordinator.ts';

test('starting a request aborts the previous request in the same channel', () => {
  const coordinator = new SymbolReviewRequestCoordinator();
  const first = coordinator.begin('counts');
  const second = coordinator.begin('counts');

  assert.equal(first.signal.aborted, true);
  assert.equal(second.signal.aborted, false);
  assert.equal(coordinator.activeCount('counts'), 1);

  coordinator.finish('counts', first);
  assert.equal(coordinator.activeCount('counts'), 1);
  coordinator.finish('counts', second);
  assert.equal(coordinator.activeCount('counts'), 0);
});

test('page, prefetch, and counts requests are cancelled together on scope changes', () => {
  const coordinator = new SymbolReviewRequestCoordinator();
  const page = coordinator.begin('page');
  const prefetch = coordinator.begin('prefetch');
  const counts = coordinator.begin('counts');

  assert.equal(coordinator.activeCount(), 3);
  coordinator.cancelAll();

  assert.equal(page.signal.aborted, true);
  assert.equal(prefetch.signal.aborted, true);
  assert.equal(counts.signal.aborted, true);
  assert.equal(coordinator.activeCount(), 0);
});

test('cleanup cannot cancel a newer request in the same channel', () => {
  const coordinator = new SymbolReviewRequestCoordinator();
  const first = coordinator.begin('page');
  const second = coordinator.begin('page');

  coordinator.cancelIfCurrent('page', first);
  assert.equal(second.signal.aborted, false);
  assert.equal(coordinator.isCurrent('page', second), true);
});

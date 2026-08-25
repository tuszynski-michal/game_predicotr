import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildPreparedLocalReviewUrl,
  navigatePreparedLocalReviewerWindow,
  prepareLocalReviewerWindow,
} from '../src/features/reviewer-access/reviewer-local-window.ts';

const input = { gameId: 'game-1', importJobId: 'job-1' };

test('prepares the scoped Reviewer URL directly instead of opening about:blank', () => {
  const calls = [];
  const reviewerWindow = {
    close() {},
    location: { href: '' },
    opener: {},
  };

  const prepared = prepareLocalReviewerWindow(
    'http://127.0.0.1:3000/?section=reviews',
    input,
    (...args) => {
      calls.push(args);
      return reviewerWindow;
    },
  );

  assert.equal(prepared, reviewerWindow);
  assert.deepEqual(calls, [
    [
      'http://127.0.0.1:3001/?mode=local&gameId=game-1&importJobId=job-1',
      '_blank',
    ],
  ]);
  assert.equal(reviewerWindow.opener, null);
});

test('an opener isolation error does not abort the prepared local launch', () => {
  const reviewerWindow = {
    close() {},
    location: { href: '' },
    set opener(_value) {
      throw new DOMException('Blocked', 'SecurityError');
    },
  };

  assert.doesNotThrow(() =>
    prepareLocalReviewerWindow(
      'http://localhost:3000/?section=reviews',
      input,
      () => reviewerWindow,
    ),
  );
  assert.equal(
    prepareLocalReviewerWindow(
      'http://localhost:3000/?section=reviews',
      input,
      () => reviewerWindow,
    ),
    reviewerWindow,
  );
});

test('retries navigation through the cross-origin location setter after API readiness', () => {
  const reviewerWindow = {
    close() {},
    location: { href: 'http://localhost:3001/?mode=local' },
    opener: null,
  };
  const returnedUrl =
    'http://127.0.0.1:3001/?mode=local&gameId=game-1&importJobId=job-1';

  assert.equal(
    navigatePreparedLocalReviewerWindow(reviewerWindow, returnedUrl),
    true,
  );
  assert.equal(reviewerWindow.location.href, returnedUrl);
});

test('does not prepare a local Reviewer tab from a non-loopback Admin origin', () => {
  assert.equal(
    buildPreparedLocalReviewUrl('https://admin.example/reviews', input),
    null,
  );
});

import assert from 'node:assert/strict';
import test from 'node:test';

import { startLocalReviewerProcess } from '../src/features/reviewer-access/reviewer-local-start.ts';

const readyResponse = {
  publicOrigin: null,
  reviewerReady: true,
  startedAt: '2026-09-04T12:00:00+02:00',
  state: 'running',
  target: 'http://127.0.0.1:3001',
};

test('starts the exact local Reviewer target and accepts only a ready process', async () => {
  const calls = [];
  const result = await startLocalReviewerProcess({
    startLocalReviewer: async (body) => {
      calls.push(body);
      return { data: readyResponse };
    },
  });

  assert.deepEqual(calls, [{ confirmed: true, target: 'local-reviewer' }]);
  assert.deepEqual(result, { ok: true });
});

test('rejects a response before the local Reviewer is ready', async () => {
  const result = await startLocalReviewerProcess({
    startLocalReviewer: async () => ({
      data: { ...readyResponse, reviewerReady: false, state: 'degraded' },
    }),
  });

  assert.deepEqual(result, {
    error: 'Lokalna aplikacja Reviewer nie osiągnęła gotowego stanu.',
    ok: false,
  });
});

test('rejects a ready response pointing outside the exact loopback target', async () => {
  const result = await startLocalReviewerProcess({
    startLocalReviewer: async () => ({
      data: { ...readyResponse, target: 'http://127.0.0.1:3002' },
    }),
  });

  assert.equal(result.ok, false);
});

test('preserves a stable API error and handles a lost connection', async () => {
  const apiFailure = await startLocalReviewerProcess({
    startLocalReviewer: async () => ({
      error: { code: 'REVIEWER_START_FAILED', message: 'Build missing' },
    }),
  });
  const connectionFailure = await startLocalReviewerProcess({
    startLocalReviewer: async () => {
      throw new TypeError('fetch failed');
    },
  });

  assert.deepEqual(apiFailure, {
    error: 'Build missing (REVIEWER_START_FAILED)',
    ok: false,
  });
  assert.deepEqual(connectionFailure, {
    error: 'Połączenie z lokalnym Admin API zostało przerwane.',
    ok: false,
  });
});

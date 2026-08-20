import assert from 'node:assert/strict';
import test from 'node:test';

import {
  closeReviewerWork,
  heartbeatReviewerWork,
  loadReviewerWork,
  openLocalReviewer,
  openOnlineReviewer,
} from '../src/features/reviewer-access/reviewer-access-actions.ts';

const localAssignment = {
  assignmentId: 'assignment-local',
  assignmentType: 'local',
  createdAt: '2026-08-20T12:00:00Z',
  gameId: 'game-1',
  heartbeatAt: '2026-08-20T12:00:00Z',
  importJobId: 'job-1',
  leaseExpiresAt: '2026-08-20T20:00:00Z',
  ready: true,
  reviewUrl:
    'http://127.0.0.1:3001/?mode=local&gameId=game-1&importJobId=job-1',
};

const onlineAssignment = {
  ...localAssignment,
  assignmentId: 'assignment-online',
  assignmentType: 'online',
  reviewUrl:
    'https://safe-name.trycloudflare.com/?session=11111111-2222-3333-4444-555555555555',
};

test('opens one scoped local work assignment without a session or code', async () => {
  const calls = [];
  const result = await openLocalReviewer(
    {
      openLocalReviewerWork: async (...args) => {
        calls.push(args);
        return {
          data: {
            accessCode: null,
            accessExpiresAt: null,
            assignment: localAssignment,
            created: true,
          },
        };
      },
    },
    { gameId: 'game-1', importJobId: 'job-1' },
  );

  assert.deepEqual(calls, [['game-1', 'job-1', { lifetimeMinutes: 480 }]]);
  assert.equal(result.ok, true);
  assert.equal(result.opened.assignment.reviewUrl, localAssignment.reviewUrl);
});

test('rejects a non-loopback URL returned for local work', async () => {
  const result = await openLocalReviewer(
    {
      openLocalReviewerWork: async () => ({
        data: {
          accessCode: null,
          accessExpiresAt: null,
          assignment: {
            ...localAssignment,
            reviewUrl: 'https://unexpected.example',
          },
          created: true,
        },
      }),
    },
    { gameId: 'game-1', importJobId: 'job-1' },
  );

  assert.equal(result.ok, false);
  assert.match(result.error, /nieprawidłowy adres/);
});

test('opens online work and keeps the one-time code only in creation response', async () => {
  const result = await openOnlineReviewer(
    {
      openOnlineReviewerWork: async () => ({
        data: {
          accessCode: 'ABCD-EFGH',
          accessExpiresAt: '2026-08-20T20:00:00Z',
          assignment: onlineAssignment,
          created: true,
        },
      }),
    },
    { gameId: 'game-1', importJobId: 'job-1' },
  );

  assert.equal(result.ok, true);
  assert.equal(result.opened.accessCode, 'ABCD-EFGH');
  assert.equal(result.opened.assignment.assignmentType, 'online');
});

test('loads assignment overview without starting a process', async () => {
  const overview = {
    activeOnlineCount: 1,
    assignments: [onlineAssignment],
    ingress: {
      publicOrigin: 'https://safe-name.trycloudflare.com',
      reviewerReady: true,
      startedAt: '2026-08-20T12:00:00Z',
      state: 'running',
      target: 'http://127.0.0.1:3001',
    },
    maximumOnlineCount: 3,
  };
  const result = await loadReviewerWork(
    { listReviewerWorkAssignments: async () => ({ data: overview }) },
    'game-1',
  );

  assert.deepEqual(result, { ok: true, overview });
});

test('heartbeats and closes only the selected assignment', async () => {
  const calls = [];
  const client = {
    closeReviewerWorkAssignment: async (...args) => {
      calls.push(['close', ...args]);
      return {
        data: {
          assignmentId: 'assignment-online',
          closedAt: '2026-08-20T12:05:00Z',
          closeReason: 'owner_stopped',
        },
      };
    },
    heartbeatReviewerWorkAssignment: async (...args) => {
      calls.push(['heartbeat', ...args]);
      return {
        data: {
          assignmentId: 'assignment-online',
          heartbeatAt: '2026-08-20T12:01:00Z',
          leaseExpiresAt: '2026-08-20T20:00:00Z',
        },
      };
    },
  };

  assert.equal(await heartbeatReviewerWork(client, 'assignment-online'), true);
  assert.deepEqual(await closeReviewerWork(client, 'assignment-online'), {
    assignmentId: 'assignment-online',
    ok: true,
  });
  assert.deepEqual(calls, [
    ['heartbeat', 'assignment-online', { confirmed: true }],
    ['close', 'assignment-online', { confirmed: true }],
  ]);
});

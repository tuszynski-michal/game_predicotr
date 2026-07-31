import assert from 'node:assert/strict';
import test from 'node:test';

import {
  loadReviewerIngress,
  publishReviewerSession,
  stopReviewerPublishing,
} from '../src/features/reviewer-access/reviewer-access-actions.ts';

const ingress = {
  publicOrigin: 'https://safe-name.trycloudflare.com',
  reviewerReady: true,
  startedAt: '2026-07-31T10:00:00Z',
  state: 'running',
  target: 'http://127.0.0.1:3001',
};

const session = {
  accessCode: 'ABCD-EFGH',
  expiresAt: '2026-07-31T18:00:00Z',
  gameId: 'game-1',
  importJobId: 'job-1',
  reviewUrl: `${ingress.publicOrigin}/?session=session-1`,
  sessionId: 'session-1',
};

test('starts ingress before creating the scoped public session', async () => {
  const calls = [];
  const result = await publishReviewerSession(
    {
      startReviewerIngress: async (body) => {
        calls.push(['start', body]);
        return { data: ingress };
      },
      createReviewerSession: async (body) => {
        calls.push(['create', body]);
        return { data: session };
      },
    },
    {
      gameId: 'game-1',
      importJobId: 'job-1',
      lifetimeMinutes: 480,
    },
  );

  assert.equal(result.ok, true);
  assert.equal(result.session.reviewUrl, session.reviewUrl);
  assert.deepEqual(calls, [
    [
      'start',
      {
        confirmed: true,
        target: 'remote-reviewer',
      },
    ],
    [
      'create',
      {
        gameId: 'game-1',
        importJobId: 'job-1',
        lifetimeMinutes: 480,
      },
    ],
  ]);
});

test('does not create a session when public ingress failed', async () => {
  let created = false;
  const result = await publishReviewerSession(
    {
      startReviewerIngress: async () => ({
        error: {
          code: 'REVIEWER_INGRESS_COMMAND_FAILED',
          details: {},
          message: 'Reviewer production build is missing.',
        },
      }),
      createReviewerSession: async () => {
        created = true;
        return { data: session };
      },
    },
    {
      gameId: 'game-1',
      importJobId: 'job-1',
      lifetimeMinutes: 480,
    },
  );

  assert.equal(result.ok, false);
  assert.equal(created, false);
  assert.match(result.error, /REVIEWER_INGRESS_COMMAND_FAILED/);
});

test('stops public exposure even when revoking the current session fails', async () => {
  let stopCommand;
  const result = await stopReviewerPublishing(
    {
      revokeReviewerSession: async () => ({
        error: {
          code: 'REVIEWER_SESSION_NOT_FOUND',
          details: {},
          message: 'Session missing.',
        },
      }),
      stopReviewerIngress: async (body) => {
        stopCommand = body;
        return {
          data: {
            ...ingress,
            publicOrigin: null,
            startedAt: null,
            state: 'stopped',
          },
        };
      },
    },
    session.sessionId,
  );

  assert.deepEqual(stopCommand, {
    confirmed: true,
    target: 'remote-reviewer',
  });
  assert.equal(result.ok, false);
  assert.equal(result.ingress.state, 'stopped');
  assert.match(result.error, /tunel został jednak zatrzymany/);
});

test('loads the current ingress state without starting it', async () => {
  const result = await loadReviewerIngress({
    getReviewerIngressStatus: async () => ({ data: ingress }),
  });

  assert.deepEqual(result, { ingress, ok: true });
});

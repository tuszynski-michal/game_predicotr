/**
 * TASK-0770: the Reviewer's own review proxy never accepts the online
 * board-search share cookie (surfaces stay separated in both directions).
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import { NextRequest } from 'next/server';

const { GET } = await import('../src/app/review-api/[...path]/route.ts');

test('the share cookie does not authorize the review proxy', async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (...args) => {
    calls.push(args);
    return new Response('{}', {
      headers: { 'Content-Type': 'application/json' },
    });
  };
  try {
    const request = new NextRequest(
      'https://share.trycloudflare.com/review-api/api/v1/admin/games',
      {
        headers: {
          Cookie:
            'gp_board_search_token=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNO_123456789',
        },
      },
    );
    const response = await GET(request, {
      params: Promise.resolve({ path: ['v1', 'admin', 'games'] }),
    });
    assert.equal(response.status, 401);
    assert.equal((await response.json()).code, 'REVIEWER_TOKEN_REQUIRED');
    assert.equal(calls.length, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

import assert from 'node:assert/strict';
import test from 'node:test';
import { v7PilotApiRewrites } from '../next.config.ts';

test('ordinary Admin retains direct API routing without a pilot proxy', () => {
  assert.deepEqual(v7PilotApiRewrites(undefined), []);
});

test('isolated pilot forwards the existing contract to its fixed loopback API', () => {
  assert.deepEqual(v7PilotApiRewrites('C:\\isolated-worktree'), [
    {
      source: '/api/v1/:path*',
      destination: 'http://127.0.0.1:8020/api/v1/:path*',
    },
  ]);
});

import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

test('default Admin keeps inferred root; scoped launch pins the worktree root', async () => {
  const previous = process.env.GAME_PREDICTOR_ADMIN_WORKSPACE_ROOT;
  try {
    delete process.env.GAME_PREDICTOR_ADMIN_WORKSPACE_ROOT;
    const ordinary = await import('../next.config.ts?pilot-default');
    assert.equal(ordinary.default.turbopack, undefined);
    assert.equal(ordinary.default.distDir, undefined);
    const worktree = fileURLToPath(new URL('../../../', import.meta.url));
    process.env.GAME_PREDICTOR_ADMIN_WORKSPACE_ROOT = worktree;
    const scoped = await import('../next.config.ts?pilot-explicit');
    assert.equal(scoped.default.turbopack.root, worktree);
    assert.equal(scoped.default.distDir, '.next-v7-reviewed-pilot');
    assert.equal(
      scoped.default.reactStrictMode,
      ordinary.default.reactStrictMode,
    );
    assert.deepEqual(
      await scoped.default.headers(),
      await ordinary.default.headers(),
    );
  } finally {
    if (previous === undefined)
      delete process.env.GAME_PREDICTOR_ADMIN_WORKSPACE_ROOT;
    else process.env.GAME_PREDICTOR_ADMIN_WORKSPACE_ROOT = previous;
  }
});

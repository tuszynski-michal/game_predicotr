import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, writeFile, stat } from 'node:fs/promises';
import path from 'node:path';
import {
  hashFile,
  requireFreshArchive,
  removeOwnedTemp,
  gitBuildInfo,
} from '../scripts/release-support.mjs';

test('release streams SHA-256 and rejects stale or empty Forge artifacts', async () => {
  const root = path.resolve('.tmp');
  await mkdir(root, { recursive: true });
  const fixture = await mkdtemp(path.join(root, 'release-test-'));
  try {
    const archive = path.join(fixture, 'test.zip');
    await writeFile(archive, 'abc');
    assert.equal(
      await hashFile(archive),
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    );
    const modified = (await stat(archive)).mtimeMs;
    assert.equal(await requireFreshArchive(archive, modified), 3);
    await assert.rejects(requireFreshArchive(archive, modified + 1), /fresh/);
    await writeFile(archive, '');
    await assert.rejects(requireFreshArchive(archive, 0), /nonempty/);
    await assert.rejects(removeOwnedTemp(root, root), /direct child/);
    const sibling = path.join(root, '..', 'not-owned');
    await assert.rejects(removeOwnedTemp(sibling, root), /direct child/);
  } finally {
    await removeOwnedTemp(fixture, root);
  }
});

test('build provenance records an actual Git commit and explicit dirty booleans', () => {
  const result = gitBuildInfo(path.resolve('../..'));
  assert.match(result.sourceCommit, /^[a-f0-9]{40}$/);
  assert.equal(typeof result.dirty, 'boolean');
  assert.equal(typeof result.applicationSourceDirty, 'boolean');
  assert.ok(Number.isFinite(Date.parse(result.builtAt)));
});

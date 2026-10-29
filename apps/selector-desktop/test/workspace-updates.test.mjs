import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { mkdir, mkdtemp, writeFile, rename } from 'node:fs/promises';
import { sourceLookup } from '../src/source-index.ts';
import { applyWorkspaceUpdate } from '../src/renderer/workspace-updates.ts';
import { ProjectController } from '../src/native/project-controller.ts';
import { SourceRegistry } from '../src/native/source-registry.ts';
import { disposeNativeChecks } from '../src/native/windows-check-worker.ts';
import { removeOwnedTemp } from '../scripts/release-support.mjs';

after(disposeNativeChecks);
const source = () => ({
  id: 'source',
  images: [{ id: 'a', relativePath: 'a.jpg' }],
});
const workspace = () => ({
  projectId: 'project',
  revision: 2,
  source: source(),
  currentImageId: 'a',
  acceptedImageIds: [],
  view: { zoom: 100 },
});
const delta = (workspace) => {
  const { source, ...scalars } = workspace;
  return { ...scalars, sourceId: source?.id ?? null };
};

test('lookup is reused without traversing source; same ids in another bootstrap remain independent', () => {
  const s = source();
  const index = sourceLookup(s);
  Object.defineProperty(s, 'images', {
    get() {
      throw new Error('inventory traversed again');
    },
  });
  assert.equal(sourceLookup(s), index);
  assert.equal(index.byPath.get('a.jpg'), 'a');
  assert.equal(index.ordinal.get('a'), 0);
  assert.equal(index.byId.get('a').relativePath, 'a.jpg');
  const other = source();
  other.images[0].relativePath = 'new.jpg';
  assert.notEqual(sourceLookup(other), index);
  assert.equal(sourceLookup(other).byPath.has('a.jpg'), false);
});

test('complete updates keep bootstrap and local view, allow revision gaps and reject foreign/stale/incomplete state', () => {
  const current = workspace();
  const update = { ...delta(current), revision: 8, view: { zoom: 200 } };
  const next = applyWorkspaceUpdate(current, update);
  assert.equal(next.source, current.source);
  assert.equal(next.view, current.view);
  assert.equal(next.revision, 8);
  assert.equal('sourceId' in next, false);
  for (const invalid of [
    { projectId: 'other' },
    { sourceId: 'other' },
    { revision: 1 },
    { revision: NaN },
    { currentImageId: 'unknown' },
    { acceptedImageIds: ['unknown'] },
  ])
    assert.throws(() =>
      applyWorkspaceUpdate(current, { ...update, ...invalid }),
    );
  assert.throws(() => applyWorkspaceUpdate(null, update));
  const empty = { ...current, source: null, currentImageId: null };
  assert.equal(applyWorkspaceUpdate(empty, delta(empty)).source, null);
  assert.throws(() => applyWorkspaceUpdate(empty, update));
  const renderer2 = structuredClone(current);
  assert.equal(
    applyWorkspaceUpdate(renderer2, update).source,
    renderer2.source,
  );
  assert.notEqual(renderer2.source, current.source);
});

async function fixture(t, count) {
  const base = path.resolve('.tmp');
  await mkdir(base, { recursive: true });
  const root = await mkdtemp(path.join(base, 'workspace-update-'));
  let chosen = path.join(root, 'photos');
  await mkdir(chosen);
  for (let n = 0; n < count; n++)
    await writeFile(
      path.join(chosen, `photo${n}.jpg`),
      Buffer.from([255, 216, n, 255, 217]),
    );
  const controller = new ProjectController(
    path.join(root, 'user'),
    new SourceRegistry(),
    {
      directory: async () => chosen,
      confirm: async () => true,
      openFolder: async () => {},
    },
  );
  t.after(async () => {
    await controller.close();
    await removeOwnedTemp(root, base);
  });
  const initial = await controller.create({
    gameUpdate: 'a1',
    firstLayout: 1,
    direction: 'ascending',
    sequenceUpperBound: 500000,
    customLocations: false,
    localStorageConfirmed: true,
  });
  const execute = (command, operationId = randomUUID()) =>
    controller.execute({ projectId: initial.projectId, operationId, command });
  return {
    controller,
    initial,
    execute,
    root,
    choose: (value) => {
      chosen = value;
    },
  };
}

test('native updates are independent of N; navigate/accept/undo/range/retry preserve a cached index', async (t) => {
  const samples = [];
  for (const count of [1, 3]) {
    const f = await fixture(t, count);
    const bootstrap = f.initial;
    const index = sourceLookup(bootstrap.source);
    // Native ordinary operations must no longer inspect this array.
    Object.defineProperty(bootstrap.source, 'images', {
      get() {
        throw new Error('native inventory traversed');
      },
    });
    let current = bootstrap;
    for (const command of [
      { kind: 'navigate', imageId: bootstrap.currentImageId },
      { kind: 'accept', imageId: bootstrap.currentImageId },
      { kind: 'undo' },
      { kind: 'range', start: 21, direction: 'descending' },
    ]) {
      const operationId = randomUUID();
      const update = await f.execute(command, operationId);
      assert.equal('source' in update, false);
      assert.equal(update.sourceId, bootstrap.source.id);
      assert.equal(sourceLookup(bootstrap.source), index);
      const wire = JSON.stringify(update);
      assert.doesNotMatch(
        wire,
        /inventory|receipts|sourceRoot|relativePath|images/,
      );
      assert.equal(wire.includes(f.root.replaceAll('\\', '\\\\')), false);
      current = applyWorkspaceUpdate(current, update);
      const retry = await f.execute(command, operationId);
      assert.equal(retry.revision, update.revision);
      assert.deepEqual(retry, update);
      if (command.kind === 'range') samples.push(update);
    }
    assert.equal(current.nextRangeStart, 21);
    await assert.rejects(
      f.execute({ kind: 'navigate', imageId: randomUUID() }),
      { code: 'UNKNOWN_IMAGE' },
    );
    assert.equal(f.controller.snapshot().revision, current.revision);
    await f.controller.close();
  }
  assert.deepEqual(
    Object.keys(samples[0]).sort(),
    Object.keys(samples[1]).sort(),
  );
  assert.equal(
    JSON.stringify(samples[0]).length,
    JSON.stringify(samples[1]).length,
  );
});

test('relink and close/reopen replace SourceIndex; old update cannot bind to the new source', async (t) => {
  const f = await fixture(t, 2);
  const update = await f.execute({
    kind: 'navigate',
    imageId: f.initial.currentImageId,
  });
  const old = sourceLookup(f.initial.source);
  const moved = path.join(f.root, 'moved');
  await rename(path.join(f.root, 'photos'), moved);
  f.choose(moved);
  const relinked = await f.controller.relink('source');
  assert.notEqual(sourceLookup(relinked.source), old);
  assert.notEqual(relinked.source.id, f.initial.source.id);
  assert.throws(() => applyWorkspaceUpdate(relinked, update));
  await f.controller.close();
  assert.equal(f.controller.snapshot(), null);
  f.choose(path.join(f.root, 'photos selekcja'));
  const reopened = await f.controller.open();
  assert.notEqual(reopened.source, relinked.source);
  assert.notEqual(sourceLookup(reopened.source), sourceLookup(relinked.source));
  assert.equal(
    sourceLookup(reopened.source).byId.get(reopened.currentImageId)
      .relativePath,
    sourceLookup(relinked.source).byId.get(relinked.currentImageId)
      .relativePath,
  );
});

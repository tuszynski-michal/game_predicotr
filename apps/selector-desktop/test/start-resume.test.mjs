import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import {
  mkdir,
  mkdtemp,
  readFile,
  writeFile,
  readdir,
  unlink,
  symlink,
  rename,
} from 'node:fs/promises';
import path from 'node:path';
import {
  ProjectController,
  validateCreate,
} from '../src/native/project-controller.ts';
import { SourceRegistry } from '../src/native/source-registry.ts';
import { ProjectStore } from '../src/project/project-store.ts';
import { PROJECT_JOURNAL_NAME } from '../src/project/state-codec.ts';
import { RecentProjects } from '../src/project/recent-projects.ts';
import { disposeNativeChecks } from '../src/native/windows-check-worker.ts';
import { removeOwnedTemp } from '../scripts/release-support.mjs';

after(() => disposeNativeChecks());
test('pending creation restores the game label; a foreign pending source is rejected without rewriting its journal', async (t) => {
  const f = await fixture(t);
  const createPending = async (sourceRoot, projectRoot, outputRoot) => {
    let interrupted = false;
    await assert.rejects(
      ProjectStore.create(
        {
          sourceRoot,
          projectRoot,
          outputRoot,
          gameName: 'Mumie',
          firstLayout: 20,
          direction: 'descending',
          localStorageConfirmed: true,
        },
        {
          checkpoint(phase) {
            if (phase === 'prepare:after') {
              interrupted = true;
              throw new Error('Injected interruption');
            }
          },
        },
      ),
      { code: 'WRITE_FAILED' },
    );
    assert.equal(interrupted, true);
  };
  await createPending(f.source, `${f.source} selekcja`, `${f.source} wybrane`);
  const c = f.controller();
  const recovered = await c.begin();
  assert.equal(recovered.workspace.issue, null);
  assert.equal(recovered.workspace.gameName, 'Mumie');
  assert.equal(recovered.workspace.direction, 'descending');
  await c.close();
  const other = path.join(f.root, 'other-source');
  await mkdir(other);
  await writeFile(
    path.join(other, 'photo.jpg'),
    Buffer.from([255, 216, 1, 255, 217]),
  );
  const foreignProject = path.join(f.root, 'foreign-pending');
  await createPending(
    other,
    foreignProject,
    path.join(f.root, 'foreign-output'),
  );
  const journalPath = path.join(foreignProject, PROJECT_JOURNAL_NAME);
  const before = await readFile(journalPath);
  await assert.rejects(
    ProjectStore.open(foreignProject, { expectedSourceRoot: f.source }),
    { code: 'SOURCE_PROJECT_CONFLICT' },
  );
  assert.deepEqual(await readFile(journalPath), before);
});
async function fixture(t) {
  const base = path.resolve('.tmp');
  await mkdir(base, { recursive: true });
  const root = await mkdtemp(path.join(base, 'selector-start-'));
  const source = path.join(root, 'Mumie', '123');
  await mkdir(source, { recursive: true });
  for (const name of ['photo1.jpg', 'photo2.jpg', 'photo10.jpg'])
    await writeFile(
      path.join(source, name),
      Buffer.from([255, 216, 1, 2, 255, 217]),
    );
  const userData = path.join(root, 'user-data');
  const controllers = [];
  let chosen = source;
  let pickers = 0;
  let confirmations = 0;
  const controller = () => {
    const c = new ProjectController(userData, new SourceRegistry(), {
      directory: async () => {
        pickers++;
        return chosen;
      },
      confirm: async () => {
        confirmations++;
        return true;
      },
      openFolder: async () => {},
    });
    controllers.push(c);
    return c;
  };
  t.after(async () => {
    for (const c of controllers) await c.close();
    await removeOwnedTemp(root, base);
  });
  return {
    source,
    root,
    userData,
    controller,
    choose(value) {
      chosen = value;
    },
    get pickers() {
      return pickers;
    },
    get confirmations() {
      return confirmations;
    },
  };
}
function request(draft, direction = 'ascending') {
  return {
    sourceToken: draft.sourceToken,
    gameName: ' Mumie ',
    firstLayout: 20,
    direction,
    sequenceUpperBound: null,
    customLocations: false,
    localStorageConfirmed: true,
  };
}
async function command(controller, cmd) {
  return controller.execute({
    projectId: controller.snapshot().projectId,
    operationId: randomUUID(),
    command: cmd,
  });
}
function position(state) {
  return state.source.images.find((i) => i.id === state.currentImageId)
    .relativePath;
}
for (const direction of ['ascending', 'descending']) {
  test(`${direction}: one source picker creates siblings; reselect after restart retains game, cursor, numbering, view and exact JPEG`, async (t) => {
    const f = await fixture(t);
    const c = f.controller();
    const start = await c.begin();
    assert.equal(start.kind, 'new');
    assert.equal(start.draft.projectPath, `${f.source} selekcja`);
    assert.equal(start.draft.outputPath, `${f.source} wybrane`);
    const options = request(start.draft, direction);
    const created = await c.create(options);
    assert.equal(f.pickers, 1);
    assert.equal(f.confirmations, 0);
    assert.equal(created.gameName, 'Mumie');
    assert.equal((await c.create(options)).projectId, created.projectId);
    assert.equal(f.pickers, 1);
    await assert.rejects(c.create({ ...options, gameName: 'Siódemki' }), {
      code: 'STALE_SOURCE_TOKEN',
    });
    let s = await command(c, {
      kind: 'accept',
      imageId: created.currentImageId,
    });
    const next = direction === 'ascending' ? 29 : 11;
    assert.equal(s.nextRangeStart, next);
    assert.equal(position(s), 'photo2.jpg');
    s = await command(c, { kind: 'skip' });
    assert.equal(s.nextRangeStart, direction === 'ascending' ? 38 : 2);
    assert.equal(position(s), 'photo2.jpg');
    s = await command(c, { kind: 'range', start: next });
    s = await command(c, { kind: 'accept', imageId: s.currentImageId });
    s = await command(c, { kind: 'undo' });
    assert.equal(s.nextRangeStart, next);
    assert.equal(s.acceptedCount, 1);
    s = await command(c, { kind: 'navigate', imageId: s.source.images[2].id });
    const view = { navigationStep: 15, zoom: 300, scrollX: 30, scrollY: 40 };
    await c.saveView(s.projectId, view);
    await c.close();
    // The source sibling is authoritative even if the history cache disappears.
    await unlink(path.join(f.userData, 'selector-recent-projects-v1.json'));
    const reopened = f.controller();
    const resumed = await reopened.begin();
    assert.equal(resumed.kind, 'existing');
    s = resumed.workspace;
    assert.equal(s.projectId, created.projectId);
    assert.equal(s.gameName, 'Mumie');
    assert.equal(s.direction, direction);
    assert.equal(s.firstLayout, 20);
    assert.equal(s.nextRangeStart, next);
    assert.equal(s.acceptedCount, 1);
    assert.equal(s.skippedCount, 1);
    assert.equal(position(s), 'photo10.jpg');
    assert.deepEqual(s.view, view);
    assert.equal((await reopened.recent())[0].name, 'Mumie — 123');
    const original = await readFile(path.join(f.source, 'photo1.jpg'));
    assert.deepEqual(
      await readFile(path.join(`${f.source} wybrane`, 'seq_20-28.jpg')),
      original,
    );
    s = await command(reopened, { kind: 'accept', imageId: s.currentImageId });
    assert.equal(s.acceptedCount, 2);
    const manifest = JSON.parse(
      await readFile(
        path.join(
          `${f.source} wybrane`,
          'manual-image-selection-output-v1.json',
        ),
        'utf8',
      ),
    );
    assert.equal(manifest.schemaVersion, 2);
    assert.equal(manifest.direction, direction);
    assert.equal(manifest.items, undefined);
    await reopened.close();
    const again = (await f.controller().begin()).workspace;
    assert.equal(again.acceptedCount, 2);
    assert.equal(again.nextRangeStart, s.nextRangeStart);
  });
}
test('old schema-1 projects and old recent cache have a source-only label and resume without reset', async (t) => {
  const f = await fixture(t);
  const store = await ProjectStore.create({
    sourceRoot: f.source,
    projectRoot: `${f.source} selekcja`,
    outputRoot: `${f.source} wybrane`,
    firstLayout: 1,
    direction: 'ascending',
    localStorageConfirmed: true,
  });
  const id = store.snapshot().projectId;
  await store.close();
  const cache = new RecentProjects(f.userData);
  await cache.remember({
    projectId: id,
    projectRoot: `${f.source} selekcja`,
    sourceDirectoryName: '123',
    openedAt: new Date().toISOString(),
  });
  const c = f.controller();
  const result = await c.begin();
  assert.equal(result.workspace.projectId, id);
  assert.equal(result.workspace.gameName, undefined);
  assert.equal((await c.recent())[0].name, '123');
});
test('cancelled picker preserves the active project; renderer paths, stale token and invalid names are rejected', async (t) => {
  const f = await fixture(t);
  const c = f.controller();
  const draft = (await c.begin()).draft;
  const options = request(draft);
  f.choose(null);
  assert.equal(await c.begin(), null);
  f.choose(f.source);
  for (const gameName of ['', ' '.repeat(3), 'a'.repeat(81), 'Mumie\n'])
    assert.throws(() => validateCreate({ ...options, gameName }), {
      code: 'INVALID_ARGUMENT',
    });
  assert.throws(() => validateCreate({ ...options, sourceRoot: 'D:/other' }), {
    code: 'INVALID_ARGUMENT',
  });
  await assert.rejects(c.create({ ...options, sourceToken: randomUUID() }), {
    code: 'STALE_SOURCE_TOKEN',
  });
  const state = await c.create(options);
  f.choose(null);
  assert.equal(await c.begin(), null);
  assert.equal(c.snapshot().projectId, state.projectId);
});
test('foreign sibling contents block creation and remain byte-identical', async (t) => {
  const f = await fixture(t);
  const folder = `${f.source} selekcja`;
  await mkdir(folder);
  await writeFile(path.join(folder, 'foreign.txt'), 'preserve');
  await assert.rejects(f.controller().begin(), { code: 'PROJECT_NOT_FOUND' });
  assert.deepEqual(await readdir(folder), ['foreign.txt']);
  assert.equal(
    await readFile(path.join(folder, 'foreign.txt'), 'utf8'),
    'preserve',
  );
});
test('source mismatch is rejected under lock before recovery; no project/output contents change', async (t) => {
  const f = await fixture(t);
  const other = path.join(f.root, 'other');
  await mkdir(other);
  await writeFile(
    path.join(other, 'photo.jpg'),
    Buffer.from([255, 216, 1, 255, 217]),
  );
  const projectRoot = `${f.source} selekcja`;
  const outputRoot = `${f.source} wybrane`;
  const store = await ProjectStore.create({
    sourceRoot: other,
    projectRoot,
    outputRoot,
    firstLayout: 1,
    direction: 'ascending',
    localStorageConfirmed: true,
  });
  await store.close();
  const before = await readFile(
    path.join(projectRoot, 'selector-project-v1.json'),
  );
  const output = await readFile(
    path.join(outputRoot, 'manual-image-selection-output-v1.json'),
  );
  await assert.rejects(f.controller().begin(), {
    code: 'SOURCE_PROJECT_CONFLICT',
  });
  assert.deepEqual(
    await readFile(path.join(projectRoot, 'selector-project-v1.json')),
    before,
  );
  assert.deepEqual(
    await readFile(
      path.join(outputRoot, 'manual-image-selection-output-v1.json'),
    ),
    output,
  );
});
test('multiple cached projects for one source require explicit history choice; stale projectId is not trusted', async (t) => {
  const f = await fixture(t);
  const c = f.controller();
  const created = await c.create(request((await c.begin()).draft));
  await c.close();
  const cache = new RecentProjects(f.userData);
  await cache.remember({
    projectId: randomUUID(),
    projectRoot: path.join(f.root, 'other-project'),
    sourceRoot: f.source,
    sourceDirectoryName: '123',
    openedAt: new Date().toISOString(),
  });
  await assert.rejects(f.controller().begin(), {
    code: 'SOURCE_PROJECT_AMBIGUOUS',
  });
  await cache.remember({
    projectId: randomUUID(),
    projectRoot: `${f.source} selekcja`,
    sourceRoot: f.source,
    sourceDirectoryName: '123',
    openedAt: new Date().toISOString(),
  });
  // Remove the other candidate by replacing the disposable cache with one stale ID.
  const stale = (await cache.list())[0];
  await writeFile(
    path.join(f.userData, 'selector-recent-projects-v1.json'),
    JSON.stringify({ schemaVersion: 1, projects: [stale] }),
  );
  await assert.rejects(f.controller().begin(), {
    code: 'SOURCE_PROJECT_CONFLICT',
  });
  assert.notEqual(stale.projectId, created.projectId);
});

test('source picker rejects a junction before looking up or creating a project', async (t) => {
  const f = await fixture(t);
  const linked = path.join(f.root, 'linked-source');
  await symlink(f.source, linked, 'junction');
  f.choose(linked);
  await assert.rejects(f.controller().begin(), { code: 'REPARSE_POINT' });
});

test('relinked source is remembered and its next selection resumes the same project in a new controller', async (t) => {
  const f = await fixture(t);
  const c = f.controller();
  const initial = await c.create(
    request((await c.begin()).draft, 'descending'),
  );
  await command(c, { kind: 'accept', imageId: initial.currentImageId });
  const moved = path.join(f.root, 'Mumie', 'moved-123');
  await rename(f.source, moved);
  f.choose(moved);
  const linked = await c.relink('source');
  assert.equal(linked.projectId, initial.projectId);
  const entry = (await new RecentProjects(f.userData).list())[0];
  assert.equal(entry.sourceRoot.toLowerCase(), moved.toLowerCase());
  await c.close();
  const result = await f.controller().begin();
  assert.equal(result.kind, 'existing');
  assert.equal(result.workspace.projectId, initial.projectId);
  assert.equal(result.workspace.gameName, 'Mumie');
  assert.equal(result.workspace.direction, 'descending');
  assert.equal(result.workspace.nextRangeStart, 11);
  assert.equal(result.workspace.acceptedCount, 1);
  assert.equal(position(result.workspace), 'photo2.jpg');
});

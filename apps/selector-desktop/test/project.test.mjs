import test, { describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  mkdir,
  mkdtemp,
  rm,
  writeFile,
  readFile,
  rename,
  readdir,
  symlink,
  utimes,
} from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { ProjectStore } from '../src/project/project-store.ts';
import {
  ProjectLock,
  PROJECT_LOCK_NAME,
  nativeProcesses,
} from '../src/project/project-lock.ts';
import {
  SecureFiles,
  assertSeparateRoots,
} from '../src/filesystem/secure-files.ts';
import { assertLocalStorage } from '../src/filesystem/local-storage.ts';
import {
  decodeEnvelope,
  encodeEnvelope,
  PROJECT_STATE_NAME,
  PROJECT_BACKUP_NAME,
  PROJECT_JOURNAL_NAME,
} from '../src/project/state-codec.ts';
import { OUTPUT_MANIFEST_NAME } from '../src/manifest/operator-local.ts';
import { RecentProjects } from '../src/project/recent-projects.ts';
import { buildRemoteSourceManifestV1 } from '@game-predictor/manual-image-selection-core';

async function fixture(t, overrides = {}) {
  const base = path.resolve('.tmp');
  await mkdir(base, { recursive: true });
  const root = await mkdtemp(path.join(base, 'selector-project-'));
  const stores = [];
  t.after(async () => {
    for (const store of stores) await store.close();
    await rm(root, { recursive: true, force: true });
  });
  const sourceRoot = path.join(root, 'source');
  await mkdir(sourceRoot);
  for (const name of ['photo10.jpg', 'photo2.jpg', 'photo1.jpg']) {
    await writeFile(
      path.join(sourceRoot, name),
      Buffer.concat([
        Buffer.from([255, 216]),
        Buffer.from(`original bytes ${name}`),
        Buffer.from([255, 217]),
      ]),
    );
    // Exact historical browser-compatible timestamps, also used by moved source.
    await utimes(path.join(sourceRoot, name), 1700000000, 1700000000.123);
  }
  const input = {
    sourceRoot,
    projectRoot: path.join(root, 'project'),
    outputRoot: path.join(root, 'output'),
    firstLayout: 1,
    direction: 'ascending',
    localStorageConfirmed: true,
    ...overrides,
  };
  return {
    root,
    input,
    track(store) {
      stores.push(store);
      return store;
    },
    async create(options) {
      const store = await ProjectStore.create(input, options);
      stores.push(store);
      return store;
    },
  };
}
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const child = (args, expectedCode = 0) =>
  new Promise((resolve, reject) => {
    const worker = spawn(
      process.execPath,
      [
        '--experimental-strip-types',
        fileURLToPath(new URL('./project-worker.mjs', import.meta.url)),
        ...args,
      ],
      {
        cwd: fileURLToPath(new URL('../', import.meta.url)),
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    );
    let stdout = '',
      stderr = '';
    const timer = setTimeout(() => {
      worker.kill();
      reject(new Error('child process timeout'));
    }, 60000);
    worker.stdout.on('data', (chunk) => {
      stdout += chunk;
    });
    worker.stderr.on('data', (chunk) => {
      stderr += chunk;
    });
    worker.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    worker.on('exit', (code) => {
      clearTimeout(timer);
      if (code !== expectedCode)
        reject(new Error(`worker exit ${code}: ${stderr}`));
      else resolve(stdout);
    });
  });

describe('durable Windows projects', { concurrency: 8 }, () => {
  test('project commits exact original JPEG and Reviewer v2; accept advances one, skip stays, natural order persists', async (t) => {
    const f = await fixture(t, { direction: 'descending', firstLayout: 20 });
    const store = await f.create();
    assert.deepEqual(
      store.snapshot().inventory.map((item) => item.relativePath),
      ['photo1.jpg', 'photo2.jpg', 'photo10.jpg'],
    );
    const expected = await buildRemoteSourceManifestV1(
      store.snapshot().inventory,
      'directory_handle',
    );
    assert.equal(
      store.snapshot().sourceManifestChecksumSha256,
      expected.manifestChecksumSha256,
    );
    const receipt = await store.execute('accept-0001', {
      kind: 'accept',
      imagePath: 'photo1.jpg',
    });
    assert.equal(receipt.currentRelativePath, 'photo2.jpg');
    assert.equal(receipt.nextRangeStart, 11);
    await store.execute('skip-000001', { kind: 'skip' });
    assert.equal(store.snapshot().currentRelativePath, 'photo2.jpg');
    assert.equal(store.snapshot().nextRangeStart, 2);
    const source = await readFile(path.join(f.input.sourceRoot, 'photo1.jpg'));
    assert.deepEqual(
      await readFile(path.join(f.input.outputRoot, 'seq_20-28.jpg')),
      source,
    );
    const manifest = JSON.parse(
      await readFile(
        path.join(f.input.outputRoot, OUTPUT_MANIFEST_NAME),
        'utf8',
      ),
    );
    assert.equal(manifest.schemaVersion, 2);
    assert.equal(manifest.storageMode, 'operator_local');
    assert.equal(manifest.sourceTraversalSemantics, 'natural_v2');
    assert.equal(manifest.currentIndex, 1);
    assert.equal(manifest.decisions[0].imageChecksumSha256, hash(source));
    assert.equal(manifest.items, undefined);
    assert.deepEqual(manifest.decisions[1], {
      action: 'skipped',
      operationId: 'skip-000001',
      fileId: null,
      sourceIndex: 1,
      imagePath: null,
      imageChecksumSha256: null,
      outputName: null,
      rangeStart: 11,
      rangeEnd: 19,
      activeBoardCount: 9,
      selectionGeneration: 0,
    });
    assert.deepEqual(
      (await readdir(f.input.outputRoot)).sort(),
      [OUTPUT_MANIFEST_NAME, 'seq_20-28.jpg'].sort(),
    );
    await store.close();
    const reopened = f.track(await ProjectStore.open(f.input.projectRoot));
    assert.equal(reopened.getIssue(), null);
    assert.equal(reopened.snapshot().currentRelativePath, 'photo2.jpg');
    assert.equal(reopened.snapshot().decisions.length, 2);
  });
  test('same operation replays its exact durable result after undo; different arguments conflict', async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    const command = { kind: 'accept', imagePath: 'photo1.jpg' };
    const result = await store.execute('accept-0001', command);
    assert.deepEqual(await store.execute('accept-0001', command), result);
    await assert.rejects(store.execute('accept-0001', { kind: 'skip' }), {
      code: 'OPERATION_ID_CONFLICT',
    });
    await store.execute('undo-000001', { kind: 'undo' });
    assert.deepEqual(await store.execute('accept-0001', command), result);
    assert.equal(store.snapshot().decisions.length, 0);
    assert.deepEqual(await readdir(f.input.outputRoot), [OUTPUT_MANIFEST_NAME]);
    const second = await store.execute('accept-0002', command);
    assert.equal(second.decisionCount, 1);
  });
  test('terminal short range, duplicate source, overlapping ranges and restart preview enforce domain rules', async (t) => {
    const f = await fixture(t, { sequenceUpperBound: 11 });
    const store = await f.create();
    await store.execute('accept-0001', {
      kind: 'accept',
      imagePath: 'photo1.jpg',
    });
    await store.execute('navigate-01', {
      kind: 'navigate',
      imagePath: 'photo1.jpg',
    });
    await assert.rejects(
      store.execute('accept-0002', { kind: 'accept', imagePath: 'photo1.jpg' }),
      { code: 'IMAGE_ALREADY_ACCEPTED' },
    );
    await store.execute('navigate-02', {
      kind: 'navigate',
      imagePath: 'photo2.jpg',
    });
    await store.execute('accept-0003', {
      kind: 'accept',
      imagePath: 'photo2.jpg',
    });
    assert.equal(store.snapshot().decisions[1].activeBoardCount, 2);
    assert.equal(store.snapshot().selectionComplete, true);
    await assert.rejects(store.execute('skip-000001', { kind: 'skip' }), {
      code: 'SELECTION_COMPLETE',
    });
    await store.execute('undo-000001', { kind: 'undo' });
    await store.execute('range-00001', { kind: 'range', start: 5 });
    await assert.rejects(store.execute('skip-000002', { kind: 'skip' }), {
      code: 'RANGE_CONFLICT',
    });
    const preview = await store.previewRestart();
    await store.execute('navigate-03', {
      kind: 'navigate',
      imagePath: 'photo10.jpg',
    });
    await assert.rejects(
      store.execute('restart-001', {
        kind: 'restart',
        expectedRevision: preview.revision,
        previewChecksum: preview.checksum,
      }),
      { code: 'STALE_RESTART_PREVIEW' },
    );
    const finalPreview = await store.previewRestart();
    await store.execute('restart-002', {
      kind: 'restart',
      expectedRevision: finalPreview.revision,
      previewChecksum: finalPreview.checksum,
    });
    assert.equal(store.snapshot().decisions.length, 0);
    assert.equal(store.snapshot().currentRelativePath, 'photo1.jpg');
    assert.equal(store.snapshot().selectionGeneration, 1);
  });

  for (const phase of [
    'prepare:before',
    'prepare:after',
    'jpeg:before',
    'jpeg:chunk',
    'jpeg:after',
    'state:before',
    'state:after',
    'manifest:before',
    'manifest:after',
    'backup:before',
    'backup:after',
    'finalize:before',
    'finalize:after',
    `${PROJECT_JOURNAL_NAME}:sync`,
    `${PROJECT_STATE_NAME}:sync`,
    `${OUTPUT_MANIFEST_NAME}:replace`,
    'jpeg:replace',
  ]) {
    test(`fault ${phase} preserves confirmed work; explicit recovery and identical retry apply once`, async (t) => {
      const f = await fixture(t);
      let armed = false;
      const store = await f.create({
        checkpoint(point) {
          if (armed && point === phase) {
            armed = false;
            throw Object.assign(new Error('disk full injected'), {
              code: 'ENOSPC',
            });
          }
        },
      });
      await store.execute('accept-0001', {
        kind: 'accept',
        imagePath: 'photo1.jpg',
      });
      armed = true;
      await assert.rejects(
        store.execute('accept-0002', {
          kind: 'accept',
          imagePath: 'photo2.jpg',
        }),
        { code: 'DISK_FULL' },
      );
      assert.equal(store.getIssue().code, 'DISK_FULL');
      await assert.rejects(store.execute('skip-000001', { kind: 'skip' }), {
        code: 'PROJECT_FROZEN',
      });
      assert.equal(
        hash(await readFile(path.join(f.input.outputRoot, 'seq_1-9.jpg'))),
        store.snapshot().decisions[0].imageChecksumSha256,
      );
      await store.close();
      const recovered = f.track(await ProjectStore.open(f.input.projectRoot));
      assert.equal(recovered.getIssue(), null);
      const retry = await recovered.execute('accept-0002', {
        kind: 'accept',
        imagePath: 'photo2.jpg',
      });
      assert.equal(retry.decisionCount, 2);
      assert.equal(recovered.snapshot().decisions.length, 2);
      assert.equal(
        await new SecureFiles(f.input.projectRoot).read(PROJECT_JOURNAL_NAME),
        null,
      );
    });
  }
  test('state replacement failure keeps old state, backup, JPEG and journal; recovery finishes once', async (t) => {
    const f = await fixture(t);
    let armed = false;
    const store = await f.create({
      checkpoint(phase) {
        if (armed && phase === `${PROJECT_STATE_NAME}:replace`) {
          armed = false;
          throw Object.assign(new Error('rename denied'), { code: 'EACCES' });
        }
      },
    });
    armed = true;
    await assert.rejects(
      store.execute('accept-0001', { kind: 'accept', imagePath: 'photo1.jpg' }),
      { code: 'WRITE_DENIED' },
    );
    const files = new SecureFiles(f.input.projectRoot);
    assert.equal(
      decodeEnvelope(await files.read(PROJECT_STATE_NAME)).decisions.length,
      0,
    );
    assert.equal(
      decodeEnvelope(await files.read(PROJECT_BACKUP_NAME)).decisions.length,
      0,
    );
    assert.ok(await files.read(PROJECT_JOURNAL_NAME));
    await store.resume();
    assert.equal(store.snapshot().decisions.length, 1);
  });
  test('corrupt primary recovers matching last-good backup; both corrupt block without output mutation', async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    await store.execute('accept-0001', {
      kind: 'accept',
      imagePath: 'photo1.jpg',
    });
    await store.close();
    const before = await readFile(
      path.join(f.input.outputRoot, OUTPUT_MANIFEST_NAME),
    );
    await writeFile(
      path.join(f.input.projectRoot, PROJECT_STATE_NAME),
      'corrupt',
    );
    const recovered = await ProjectStore.open(f.input.projectRoot);
    assert.equal(recovered.getIssue(), null);
    assert.equal(recovered.snapshot().decisions.length, 1);
    await recovered.close();
    await writeFile(
      path.join(f.input.projectRoot, PROJECT_STATE_NAME),
      'corrupt',
    );
    await writeFile(
      path.join(f.input.projectRoot, PROJECT_BACKUP_NAME),
      'corrupt',
    );
    await assert.rejects(ProjectStore.open(f.input.projectRoot), {
      code: 'PROJECT_CORRUPT',
    });
    assert.deepEqual(
      await readFile(path.join(f.input.outputRoot, OUTPUT_MANIFEST_NAME)),
      before,
    );
  });
  test('foreign JPEG, manifest identity, checksum drift block overwrite, undo and restart', async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    await writeFile(path.join(f.input.outputRoot, 'seq_1-9.jpg'), 'foreign');
    await assert.rejects(
      store.execute('accept-0001', { kind: 'accept', imagePath: 'photo1.jpg' }),
      { code: 'FOREIGN_CONTENT' },
    );
    assert.equal(
      await readFile(path.join(f.input.outputRoot, 'seq_1-9.jpg'), 'utf8'),
      'foreign',
    );
    await rm(path.join(f.input.outputRoot, 'seq_1-9.jpg'));
    await store.resume();
    await store.execute('accept-0002', {
      kind: 'accept',
      imagePath: 'photo1.jpg',
    });
    await writeFile(path.join(f.input.outputRoot, 'seq_1-9.jpg'), 'changed');
    await assert.rejects(store.execute('undo-000001', { kind: 'undo' }), {
      code: 'OUTPUT_CHECKSUM_CONFLICT',
    });
    await assert.rejects(store.resume(), { code: 'OUTPUT_CHECKSUM_CONFLICT' });
    assert.equal(
      await readFile(path.join(f.input.outputRoot, 'seq_1-9.jpg'), 'utf8'),
      'changed',
    );
  });
  test('missing/moved source and output relink without resetting; different source and foreign manifest fail closed', async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    await store.execute('accept-0001', {
      kind: 'accept',
      imagePath: 'photo1.jpg',
    });
    await store.close();
    const movedSource = path.join(f.root, 'moved-source'),
      movedOutput = path.join(f.root, 'moved-output');
    await rename(f.input.sourceRoot, movedSource);
    await rename(f.input.outputRoot, movedOutput);
    const reopened = f.track(await ProjectStore.open(f.input.projectRoot));
    assert.equal(reopened.getIssue().code, 'SOURCE_MISSING');
    await reopened.execute('relink-0001', {
      kind: 'relink',
      sourceRoot: movedSource,
      outputRoot: movedOutput,
    });
    assert.equal(reopened.snapshot().decisions.length, 1);
    assert.equal(reopened.snapshot().currentRelativePath, 'photo2.jpg');
    await writeFile(path.join(movedSource, 'photo2.jpg'), 'different');
    await assert.rejects(
      reopened.execute('relink-0002', {
        kind: 'relink',
        sourceRoot: movedSource,
      }),
      { code: 'SOURCE_IDENTITY_CONFLICT' },
    );
  });
  test('foreign manifest identity and corrupt journal block writes without overwriting data', async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    const manifestPath = path.join(f.input.outputRoot, OUTPUT_MANIFEST_NAME);
    const original = await readFile(manifestPath);
    const foreign = {
      ...JSON.parse(original.toString()),
      sessionId: 'foreign-project',
    };
    await writeFile(manifestPath, JSON.stringify(foreign));
    await assert.rejects(
      store.execute('accept-0001', { kind: 'accept', imagePath: 'photo1.jpg' }),
      { code: 'OUTPUT_MANIFEST_CONFLICT' },
    );
    assert.equal(
      JSON.parse(await readFile(manifestPath, 'utf8')).sessionId,
      'foreign-project',
    );
    assert.deepEqual(await readdir(f.input.outputRoot), [OUTPUT_MANIFEST_NAME]);
    await writeFile(manifestPath, original);
    await store.resume();
    await store.close();
    await writeFile(
      path.join(f.input.projectRoot, PROJECT_JOURNAL_NAME),
      'corrupt',
    );
    await assert.rejects(ProjectStore.open(f.input.projectRoot), {
      code: 'PROJECT_CORRUPT',
    });
    assert.deepEqual(await readFile(manifestPath), original);
  });
  test('pending transaction survives missing roots and verified relink before recovery', async (t) => {
    const f = await fixture(t);
    let armed = false;
    const store = await f.create({
      checkpoint(phase) {
        if (armed && phase === 'state:before') {
          armed = false;
          throw Object.assign(new Error('disk full'), { code: 'ENOSPC' });
        }
      },
    });
    armed = true;
    await assert.rejects(
      store.execute('accept-0001', { kind: 'accept', imagePath: 'photo1.jpg' }),
      { code: 'DISK_FULL' },
    );
    await store.close();
    const sourceRoot = path.join(f.root, 'moved-source'),
      outputRoot = path.join(f.root, 'moved-output');
    await rename(f.input.sourceRoot, sourceRoot);
    await rename(f.input.outputRoot, outputRoot);
    const reopened = f.track(await ProjectStore.open(f.input.projectRoot));
    assert.equal(reopened.getIssue().code, 'SOURCE_MISSING');
    await reopened.execute('relink-0001', {
      kind: 'relink',
      sourceRoot,
      outputRoot,
    });
    assert.equal(reopened.snapshot().decisions.length, 1);
    const retry = await reopened.execute('accept-0001', {
      kind: 'accept',
      imagePath: 'photo1.jpg',
    });
    assert.equal(retry.revision, 1);
    assert.equal(reopened.snapshot().revision, 2);
    assert.deepEqual(
      await readFile(path.join(outputRoot, 'seq_1-9.jpg')),
      await readFile(path.join(sourceRoot, 'photo1.jpg')),
    );
  });
  for (const kind of ['undo', 'restart']) {
    test(`${kind} records durable intent before removal; crash recovers once`, async (t) => {
      const f = await fixture(t);
      let armed = false;
      const store = await f.create({
        checkpoint(phase) {
          if (armed && phase === 'jpeg:after') {
            armed = false;
            throw Object.assign(new Error('disk full'), { code: 'ENOSPC' });
          }
        },
      });
      await store.execute('accept-0001', {
        kind: 'accept',
        imagePath: 'photo1.jpg',
      });
      const preview = await store.previewRestart();
      const command =
        kind === 'undo'
          ? { kind }
          : {
              kind,
              expectedRevision: preview.revision,
              previewChecksum: preview.checksum,
            };
      armed = true;
      await assert.rejects(store.execute('remove-0001', command), {
        code: 'DISK_FULL',
      });
      const journal = decodeEnvelope(
        await readFile(path.join(f.input.projectRoot, PROJECT_JOURNAL_NAME)),
      );
      assert.equal(journal.removals.length, 1);
      assert.equal(journal.before.decisions.length, 1);
      await store.close();
      const reopened = f.track(await ProjectStore.open(f.input.projectRoot));
      assert.equal(reopened.getIssue(), null);
      assert.equal(reopened.snapshot().decisions.length, 0);
      assert.equal(
        (await reopened.execute('remove-0001', command)).decisionCount,
        0,
      );
      assert.deepEqual(await readdir(f.input.outputRoot), [
        OUTPUT_MANIFEST_NAME,
      ]);
    });
  }
  test('restart verifies checksum again after preview and leaves changed JPEG intact', async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    await store.execute('accept-0001', {
      kind: 'accept',
      imagePath: 'photo1.jpg',
    });
    const preview = await store.previewRestart();
    await writeFile(
      path.join(f.input.outputRoot, 'seq_1-9.jpg'),
      'changed-after-preview',
    );
    await assert.rejects(
      store.execute('restart-001', {
        kind: 'restart',
        expectedRevision: preview.revision,
        previewChecksum: preview.checksum,
      }),
      { code: 'OUTPUT_CHECKSUM_CONFLICT' },
    );
    assert.equal(
      await readFile(path.join(f.input.outputRoot, 'seq_1-9.jpg'), 'utf8'),
      'changed-after-preview',
    );
    assert.equal(store.snapshot().decisions.length, 1);
  });
  test('two projects racing for one output cannot overwrite the winning manifest', async (t) => {
    const f = await fixture(t);
    let arrivals = 0,
      release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    const options = {
      async checkpoint(phase) {
        if (phase === 'prepare:after') {
          if (++arrivals === 2) release();
          await gate;
        }
      },
    };
    const secondInput = {
      ...f.input,
      projectRoot: path.join(f.root, 'project-second'),
    };
    const results = await Promise.allSettled([
      ProjectStore.create(f.input, options),
      ProjectStore.create(secondInput, options),
    ]);
    const winners = results.filter((result) => result.status === 'fulfilled');
    assert.equal(winners.length, 1);
    const winner = f.track(winners[0].value);
    const loser = results.find((result) => result.status === 'rejected');
    assert.ok(
      ['PROJECT_LOCKED', 'OUTPUT_MANIFEST_CONFLICT'].includes(
        loser.reason.code,
      ),
    );
    const manifest = JSON.parse(
      await readFile(
        path.join(f.input.outputRoot, OUTPUT_MANIFEST_NAME),
        'utf8',
      ),
    );
    assert.equal(manifest.sessionId, winner.snapshot().projectId);
    assert.deepEqual(await readdir(f.input.outputRoot), [OUTPUT_MANIFEST_NAME]);
  });
  test('pending recovery never steals an active or unknown-host output lease', async (t) => {
    const f = await fixture(t);
    let armed = false;
    const store = await f.create({
      checkpoint(phase) {
        if (armed && phase === 'state:before') {
          armed = false;
          throw Object.assign(new Error('disk full'), { code: 'ENOSPC' });
        }
      },
    });
    armed = true;
    await assert.rejects(
      store.execute('accept-0001', { kind: 'accept', imagePath: 'photo1.jpg' }),
      { code: 'DISK_FULL' },
    );
    await store.close();
    const output = new SecureFiles(f.input.outputRoot);
    const liveLease = await ProjectLock.acquire(output);
    const active = f.track(await ProjectStore.open(f.input.projectRoot));
    assert.equal(active.getIssue().code, 'PROJECT_LOCKED');
    await active.close();
    await liveLease.release();
    const foreignOwner = {
      schemaVersion: 1,
      ownerId: 'foreign-output-owner',
      host: nativeProcesses.host + '-foreign',
      pid: process.pid,
      processIdentity: 'unknown',
      createdAt: new Date().toISOString(),
    };
    const bytes = JSON.stringify(foreignOwner);
    await writeFile(path.join(f.input.outputRoot, PROJECT_LOCK_NAME), bytes);
    const unknown = f.track(await ProjectStore.open(f.input.projectRoot));
    assert.equal(unknown.getIssue().code, 'LOCK_OWNER_UNKNOWN');
    assert.equal(
      await readFile(path.join(f.input.outputRoot, PROJECT_LOCK_NAME), 'utf8'),
      bytes,
    );
    assert.equal(unknown.snapshot().decisions.length, 0);
  });
  test('real dead-process output lease survives moved folders and verified relink', async (t) => {
    const f = await fixture(t);
    const original = await f.create();
    await original.close();
    await child(
      ['crash', f.input.projectRoot, 'accept-0001', 'photo1.jpg', 'jpeg:after'],
      73,
    );
    const sourceRoot = path.join(f.root, 'moved-source'),
      outputRoot = path.join(f.root, 'moved-output');
    await rename(f.input.sourceRoot, sourceRoot);
    await rename(f.input.outputRoot, outputRoot);
    const reopened = f.track(await ProjectStore.open(f.input.projectRoot));
    assert.equal(reopened.getIssue().code, 'SOURCE_MISSING');
    await reopened.execute('relink-0001', {
      kind: 'relink',
      sourceRoot,
      outputRoot,
    });
    assert.equal(reopened.getIssue(), null);
    assert.equal(reopened.snapshot().decisions.length, 1);
    assert.ok(!(await readdir(outputRoot)).includes(PROJECT_LOCK_NAME));
    assert.equal(
      (
        await reopened.execute('accept-0001', {
          kind: 'accept',
          imagePath: 'photo1.jpg',
        })
      ).revision,
      1,
    );
  });
  test('source moved during selection reports a relink issue and keeps committed choices', async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    await store.execute('accept-0001', {
      kind: 'accept',
      imagePath: 'photo1.jpg',
    });
    const sourceRoot = path.join(f.root, 'moved-source');
    await rename(f.input.sourceRoot, sourceRoot);
    await assert.rejects(
      store.execute('accept-0002', { kind: 'accept', imagePath: 'photo2.jpg' }),
      { code: 'SOURCE_MISSING' },
    );
    assert.equal(store.getIssue().code, 'SOURCE_MISSING');
    assert.equal(store.snapshot().decisions.length, 1);
    assert.equal(
      (
        await store.execute('accept-0001', {
          kind: 'accept',
          imagePath: 'photo1.jpg',
        })
      ).revision,
      1,
    );
    await store.execute('relink-0001', { kind: 'relink', sourceRoot });
    assert.equal(store.getIssue(), null);
    assert.equal(store.snapshot().decisions.length, 1);
    await store.execute('accept-0002', {
      kind: 'accept',
      imagePath: 'photo2.jpg',
    });
    assert.equal(store.snapshot().decisions.length, 2);
  });
  test('unsupported project version never falls back to an old backup or overwrites newer state', async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    await store.close();
    const state = decodeEnvelope(
      await readFile(path.join(f.input.projectRoot, PROJECT_STATE_NAME)),
    );
    const newer = encodeEnvelope({ ...state, schemaVersion: 2 });
    await writeFile(path.join(f.input.projectRoot, PROJECT_STATE_NAME), newer);
    const manifest = await readFile(
      path.join(f.input.outputRoot, OUTPUT_MANIFEST_NAME),
    );
    await assert.rejects(ProjectStore.open(f.input.projectRoot), {
      code: 'UNSUPPORTED_PROJECT_SCHEMA',
    });
    assert.equal(
      await readFile(
        path.join(f.input.projectRoot, PROJECT_STATE_NAME),
        'utf8',
      ),
      newer,
    );
    assert.deepEqual(
      await readFile(path.join(f.input.outputRoot, OUTPUT_MANIFEST_NAME)),
      manifest,
    );
  });
  test('local roots reject overlap, nested targets, network storage, sync and missing explicit confirmation', async () => {
    assert.throws(
      () =>
        assertSeparateRoots(['D:/source', 'D:/source/project', 'D:/output']),
      { code: 'OVERLAPPING_ROOTS' },
    );
    await assert.rejects(assertLocalStorage('D:/project', false), {
      code: 'LOCAL_STORAGE_CONFIRMATION_REQUIRED',
    });
    await assert.rejects(assertLocalStorage('\\\\server\\share', true), {
      code: 'NETWORK_STORAGE',
    });
    await assert.rejects(assertLocalStorage('D:/OneDrive/project', true), {
      code: 'SYNC_STORAGE',
    });
  });
  test('writer rejects junction leaf and linked ancestor without changing outside data', async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    const outside = path.join(f.root, 'outside');
    await mkdir(outside);
    await writeFile(path.join(outside, 'secret'), 'safe');
    await rename(f.input.outputRoot, path.join(f.root, 'original-output'));
    await symlink(
      outside,
      f.input.outputRoot,
      process.platform === 'win32' ? 'junction' : 'dir',
    );
    await assert.rejects(
      store.execute('accept-0001', { kind: 'accept', imagePath: 'photo1.jpg' }),
      { code: 'REPARSE_POINT' },
    );
    assert.deepEqual(await readdir(outside), ['secret']);
    assert.equal(await readFile(path.join(outside, 'secret'), 'utf8'), 'safe');
  });
  test('exclusive lock rejects live second instance, foreign host and unknown process; confirmed dead local identity recovers', async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    await assert.rejects(ProjectStore.open(f.input.projectRoot), {
      code: 'PROJECT_LOCKED',
    });
    await store.close();
    const files = new SecureFiles(f.input.projectRoot);
    const owner = {
      schemaVersion: 1,
      ownerId: 'old-owner',
      host: 'test-host',
      pid: 123,
      processIdentity: 'old-start',
      createdAt: '2000-01-01',
    };
    await writeFile(
      path.join(f.input.projectRoot, PROJECT_LOCK_NAME),
      JSON.stringify(owner),
    );
    const inspector = {
      host: 'different-host',
      pid: 456,
      identity: async () => 'new-start',
    };
    await assert.rejects(ProjectLock.acquire(files, inspector), {
      code: 'LOCK_OWNER_UNKNOWN',
    });
    inspector.host = 'test-host';
    inspector.identity = async (pid) => {
      if (pid === 123) throw new Error('unknown');
      return 'new-start';
    };
    await assert.rejects(ProjectLock.acquire(files, inspector), {
      code: 'LOCK_OWNER_UNKNOWN',
    });
    inspector.identity = async (pid) => (pid === 123 ? null : 'new-start');
    const lock = await ProjectLock.acquire(files, inspector);
    await lock.release();
    await writeFile(
      path.join(f.input.projectRoot, PROJECT_LOCK_NAME),
      'partial',
    );
    await assert.rejects(ProjectLock.acquire(files, inspector), {
      code: 'LOCK_OWNER_UNKNOWN',
    });
    await rm(path.join(f.input.projectRoot, PROJECT_LOCK_NAME));
  });
  test('recent cache is bounded and disposable; corrupt cache never affects authoritative project', async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    const cache = new RecentProjects(path.join(f.root, 'recent'));
    const state = store.snapshot();
    await cache.remember({
      projectId: state.projectId,
      projectRoot: f.input.projectRoot,
      sourceDirectoryName: 'source',
      openedAt: state.updatedAt,
    });
    assert.equal((await cache.list())[0].projectId, state.projectId);
    await writeFile(
      path.join(f.root, 'recent/selector-recent-projects-v1.json'),
      'corrupt',
    );
    assert.deepEqual(await cache.list(), []);
    assert.equal(store.snapshot().projectId, state.projectId);
  });
  for (const phase of [
    'prepare:after',
    'jpeg:after',
    'state:after',
    'manifest:after',
    'finalize:after',
  ]) {
    test(`real process dies at ${phase}; new process recovers local files and exact retry`, async (t) => {
      const f = await fixture(t);
      const store = await f.create();
      await store.close();
      await child(
        ['crash', f.input.projectRoot, 'accept-0001', 'photo1.jpg', phase],
        73,
      );
      const result = JSON.parse(
        await child([
          'recover',
          f.input.projectRoot,
          'accept-0001',
          'photo1.jpg',
        ]),
      );
      assert.equal(result.state.decisions.length, 1);
      assert.equal(result.receipt.revision, 1);
      assert.equal(result.state.currentRelativePath, 'photo2.jpg');
      assert.deepEqual(
        await readFile(path.join(f.input.outputRoot, 'seq_1-9.jpg')),
        await readFile(path.join(f.input.sourceRoot, 'photo1.jpg')),
      );
      assert.ok(
        !(await readdir(f.input.outputRoot)).includes(PROJECT_LOCK_NAME),
      );
    });
  }
});

import test, { describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  utimes,
  writeFile,
} from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { checksum, stableStringify } from '../src/filesystem/secure-files.ts';
import { ProjectStore } from '../src/project/project-store.ts';
import {
  ProjectStorage,
  compactNames,
  PROJECT_LEDGER_NAME,
  PROJECT_LEDGER_BACKUP_NAME,
} from '../src/project/project-storage.ts';
import {
  decodeEnvelope,
  encodeEnvelope,
  validateState,
  validateJournal,
  PROJECT_STATE_NAME,
  PROJECT_BACKUP_NAME,
  PROJECT_JOURNAL_NAME,
} from '../src/project/state-codec.ts';
import { OUTPUT_MANIFEST_NAME } from '../src/manifest/operator-local.ts';

const worker = fileURLToPath(new URL('./compact-worker.mjs', import.meta.url));
const command = { kind: 'accept', imagePath: 'photo1.jpg' };

async function fixture(t) {
  const base = path.resolve('.tmp');
  await mkdir(base, { recursive: true });
  const root = await mkdtemp(path.join(base, 'selector-compact-'));
  const stores = [];
  t.after(async () => {
    for (const store of stores) await store.close();
    // The generated fixture is the only recursive deletion target.
    assert.equal(path.dirname(root), base);
    await rm(root, { recursive: true, force: true });
  });
  const input = {
    sourceRoot: path.join(root, 'source'),
    projectRoot: path.join(root, 'project'),
    outputRoot: path.join(root, 'output'),
    firstLayout: 1,
    direction: 'ascending',
    localStorageConfirmed: true,
  };
  await mkdir(input.sourceRoot);
  for (const name of ['photo1.jpg', 'photo2.jpg', 'photo10.jpg']) {
    await writeFile(
      path.join(input.sourceRoot, name),
      Buffer.from(`\xff\xd8fixture ${name}\xff\xd9`, 'latin1'),
    );
    await utimes(path.join(input.sourceRoot, name), 1700000000, 1700000000.123);
  }
  const track = (store) => {
    stores.push(store);
    return store;
  };
  return {
    root,
    input,
    track,
    async create(options) {
      return track(await ProjectStore.create(input, options));
    },
    async open(options) {
      return track(await ProjectStore.open(input.projectRoot, options));
    },
    async head() {
      return decodeEnvelope(
        await readFile(path.join(input.projectRoot, PROJECT_STATE_NAME)),
      );
    },
    async legacy() {
      const store = await this.create();
      await store.execute('legacy-confirmed-accept', command);
      const state = store.snapshot();
      const head = await this.head();
      await store.close();
      for (const name of compactNames(head))
        await rm(path.join(input.projectRoot, name));
      for (const name of [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME])
        await writeFile(
          path.join(input.projectRoot, name),
          encodeEnvelope(state),
        );
      return state;
    },
  };
}

async function directoryBytes(root) {
  return Object.fromEntries(
    await Promise.all(
      (await readdir(root))
        .sort()
        .map(async (name) => [
          name,
          (await readFile(path.join(root, name))).toString('hex'),
        ]),
    ),
  );
}

async function assertFailedOpen(f, codes) {
  let failure;
  try {
    const store = await f.open();
    failure = store.getIssue();
    if (failure)
      await assert.rejects(
        store.execute('blocked-compact-write', { kind: 'skip' }),
        { code: 'PROJECT_FROZEN' },
      );
    await store.close();
  } catch (error) {
    failure = error;
  }
  assert.ok(failure, 'Opening corrupted data must fail or freeze the store');
  assert.ok(codes.includes(failure.code), `Unexpected failure ${failure.code}`);
}

async function child(mode, projectRoot, point, extra = []) {
  const args = ['--experimental-strip-types', worker, mode, projectRoot];
  if (point) args.push(point);
  args.push(...extra);
  return new Promise((resolve, reject) => {
    const processHandle = spawn(process.execPath, args, {
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '',
      stderr = '',
      timedOut = false;
    processHandle.stdout.on('data', (bytes) => {
      stdout += bytes;
    });
    processHandle.stderr.on('data', (bytes) => {
      stderr += bytes;
    });
    const timer = setTimeout(() => {
      timedOut = true;
      processHandle.kill();
    }, 25000);
    processHandle.once('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    processHandle.once('close', (code) => {
      clearTimeout(timer);
      if (timedOut)
        reject(new Error(`Compact worker timed out: ${mode} ${point ?? ''}`));
      else resolve({ code, stdout, stderr });
    });
  });
}

test('serialized projects retain 30000 inventory entries and the last cursor in both directions', async (t) => {
  const f = await fixture(t);
  const store = await f.create();
  const state = store.snapshot();
  state.inventory = Array.from({ length: 30000 }, (_, i) => ({
    ...state.inventory[0],
    relativePath: `photo${i + 1}.jpg`,
    name: `photo${i + 1}.jpg`,
  }));
  state.currentRelativePath = 'photo30000.jpg';
  for (const direction of ['ascending', 'descending']) {
    state.direction = direction;
    const serialized = encodeEnvelope(state);
    const restored = decodeEnvelope(Buffer.from(serialized));
    assert.doesNotThrow(() => validateState(restored));
    assert.equal(restored.inventory.length, 30000);
    assert.equal(restored.currentRelativePath, 'photo30000.jpg');
    assert.equal(restored.direction, direction);
  }
  const invalid = structuredClone(state);
  invalid.inventory[1].relativePath = '../outside.jpg';
  assert.throws(() => validateState(invalid), { code: 'PROJECT_CORRUPT' });
});

test('compact heads omit collections, immutable bytes stay fixed, and snapshots isolate all public projections', async (t) => {
  const f = await fixture(t);
  const store = await f.create();
  const head = await f.head();
  const immutable = compactNames(head).filter(
    (name) => !name.endsWith('.jsonl'),
  );
  const bytes = await Promise.all(
    immutable.map((name) => readFile(path.join(f.input.projectRoot, name))),
  );
  const snapshot = store.snapshot();
  snapshot.inventory[0].relativePath = 'poison.jpg';
  snapshot.receipts.poison = {};
  snapshot.nextRangeStart = 900;
  const receipt = await store.execute('compact-stable-accept', command);
  receipt.decisionCount = 999;
  const view = store.workspaceSnapshot();
  assert.equal(Object.hasOwn(view, 'receipts'), false);
  assert.equal(Object.hasOwn(view, 'inventory'), false);
  view.decisions[0].outputName = 'poison.jpg';
  const source = store.sourceSnapshot();
  source.inventory[0].name = 'poison.jpg';
  await store.execute('compact-stable-nav', {
    kind: 'navigate',
    imagePath: 'photo10.jpg',
  });
  assert.equal(store.snapshot().decisions[0].outputName, 'seq_1-9.jpg');
  assert.equal(store.snapshot().inventory[0].name, 'photo1.jpg');
  assert.equal(
    store.snapshot().receipts['compact-stable-accept'].decisionCount,
    1,
  );
  for (let index = 0; index < immutable.length; index++)
    assert.deepEqual(
      await readFile(path.join(f.input.projectRoot, immutable[index])),
      bytes[index],
    );
  for (const name of [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME]) {
    const disk = decodeEnvelope(
      await readFile(path.join(f.input.projectRoot, name)),
    );
    assert.equal(disk.schemaVersion, 2);
    for (const key of ['inventory', 'decisions', 'receipts']) {
      assert.equal(Object.hasOwn(disk, key), false);
      assert.equal(Object.hasOwn(disk.scalar, key), false);
    }
  }
});

test('very old receipts and __proto__ survive undo, restart, upgrade baseline and reopen without retention', async (t) => {
  const f = await fixture(t);
  const legacy = await f.legacy();
  const oldReceipt = legacy.receipts['legacy-confirmed-accept'];
  const store = await f.open();
  assert.equal(store.getIssue(), null);
  const protoReceipt = await store.execute('__proto__', {
    kind: 'navigate',
    imagePath: 'photo10.jpg',
  });
  await store.execute('compact-old-undo', { kind: 'undo' });
  await store.execute('compact-old-accept', command);
  const preview = await store.previewRestart();
  await store.execute('compact-old-restart', {
    kind: 'restart',
    expectedRevision: preview.revision,
    previewChecksum: preview.checksum,
  });
  for (let index = 0; index < 12; index++)
    await store.execute(`compact-old-nav-${index}`, {
      kind: 'navigate',
      imagePath: index % 2 ? 'photo1.jpg' : 'photo2.jpg',
    });
  await store.close();
  const reopened = await f.open();
  assert.equal(reopened.getIssue(), null);
  assert.deepEqual(
    await reopened.execute('legacy-confirmed-accept', command),
    oldReceipt,
  );
  assert.deepEqual(
    await reopened.execute('__proto__', {
      kind: 'navigate',
      imagePath: 'photo10.jpg',
    }),
    protoReceipt,
  );
  await assert.rejects(
    reopened.execute('legacy-confirmed-accept', { kind: 'skip' }),
    { code: 'OPERATION_ID_CONFLICT' },
  );
  await assert.rejects(reopened.execute('__proto__', { kind: 'skip' }), {
    code: 'OPERATION_ID_CONFLICT',
  });
  const state = reopened.snapshot();
  assert.ok(Object.hasOwn(state.receipts, '__proto__'));
  assert.equal(state.decisions.length, 0);
  assert.equal(state.selectionGeneration, 1);
  assert.equal(state.revision, legacy.revision + 16);
  assert.deepEqual(await readdir(f.input.outputRoot), [OUTPUT_MANIFEST_NAME]);
});

test('frozen legacy relink upgrades before acknowledgement and keeps its exact receipt across a fresh-process retry', async (t) => {
  const f = await fixture(t);
  const legacy = await f.legacy();
  const movedSource = path.join(f.root, 'legacy-source-moved');
  const movedOutput = path.join(f.root, 'legacy-output-moved');
  const output = await directoryBytes(f.input.outputRoot);
  await rename(f.input.sourceRoot, movedSource);
  await rename(f.input.outputRoot, movedOutput);
  const frozen = await f.open();
  assert.equal(frozen.getIssue()?.code, 'SOURCE_MISSING');
  const relink = {
    kind: 'relink',
    sourceRoot: movedSource,
    outputRoot: movedOutput,
  };
  const receipt = await frozen.execute('legacy-relink-0001', relink);
  const relinkState = frozen.snapshot();
  assert.equal(frozen.getIssue(), null);
  assert.equal(relinkState.revision, legacy.revision + 1);
  assert.deepEqual(relinkState.receipts['legacy-relink-0001'], receipt);
  assert.deepEqual(
    relinkState.receipts['legacy-confirmed-accept'],
    legacy.receipts['legacy-confirmed-accept'],
  );
  assert.deepEqual(relinkState.decisions, legacy.decisions);
  for (const name of [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME])
    assert.equal(
      decodeEnvelope(await readFile(path.join(f.input.projectRoot, name)))
        .schemaVersion,
      2,
    );
  const skipped = await frozen.execute('legacy-after-relink-skip', {
    kind: 'skip',
  });
  const expected = frozen.snapshot();
  assert.equal(expected.revision, legacy.revision + 2);
  assert.equal(expected.revision, receipt.revision + 1);
  assert.equal(skipped.decisionCount, legacy.decisions.length + 1);
  assert.equal(expected.decisions.at(-1).action, 'skipped');
  assert.deepEqual(await frozen.execute('legacy-relink-0001', relink), receipt);
  assert.deepEqual(frozen.snapshot(), expected);
  await assert.rejects(frozen.execute('legacy-relink-0001', { kind: 'skip' }), {
    code: 'OPERATION_ID_CONFLICT',
  });
  assert.deepEqual(frozen.snapshot(), expected);
  await frozen.close();
  const retried = await child(
    'legacy-relink-retry',
    f.input.projectRoot,
    movedSource,
    [movedOutput],
  );
  assert.equal(retried.code, 0, retried.stderr);
  const result = JSON.parse(retried.stdout);
  assert.deepEqual(result.receipt, receipt);
  assert.deepEqual(result.state, expected);
  assert.deepEqual(
    await readFile(path.join(movedOutput, 'seq_1-9.jpg')),
    Buffer.from(output['seq_1-9.jpg'], 'hex'),
  );
  const reopened = await f.open({
    expectedSourceRoot: movedSource,
    expectedProjectId: legacy.projectId,
  });
  assert.equal(reopened.getIssue(), null);
  assert.deepEqual(
    await reopened.execute('legacy-relink-0001', relink),
    receipt,
  );
  assert.equal(reopened.snapshot().revision, expected.revision);
});

test('frozen legacy relink retry completes upgrade after failure before its descriptor without another revision', async (t) => {
  const f = await fixture(t);
  const legacy = await f.legacy();
  const movedSource = path.join(f.root, 'legacy-retry-source-moved');
  await rename(f.input.sourceRoot, movedSource);
  let armed = false;
  let hit = false;
  const frozen = await f.open({
    checkpoint(point) {
      if (armed && point === 'upgrade:prepare:before') {
        armed = false;
        hit = true;
        throw Object.assign(new Error('upgrade before descriptor disk full'), {
          code: 'ENOSPC',
        });
      }
    },
  });
  assert.equal(frozen.getIssue()?.code, 'SOURCE_MISSING');
  const relink = { kind: 'relink', sourceRoot: movedSource };
  armed = true;
  await assert.rejects(frozen.execute('legacy-relink-retry-0001', relink), {
    code: 'DISK_FULL',
  });
  assert.ok(hit);
  const expected = frozen.snapshot();
  const retained = expected.receipts['legacy-relink-retry-0001'];
  assert.ok(retained);
  assert.equal(retained.revision, legacy.revision + 1);
  assert.equal(expected.revision, retained.revision);
  assert.equal(
    (await readdir(f.input.projectRoot)).includes(PROJECT_JOURNAL_NAME),
    false,
  );
  for (const name of [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME]) {
    const disk = decodeEnvelope(
      await readFile(path.join(f.input.projectRoot, name)),
    );
    assert.equal(disk.schemaVersion, 1);
    assert.deepEqual(disk.receipts['legacy-relink-retry-0001'], retained);
  }
  assert.deepEqual(
    await frozen.execute('legacy-relink-retry-0001', relink),
    retained,
  );
  assert.deepEqual(frozen.snapshot(), expected);
  assert.equal(frozen.getIssue(), null);
  for (const name of [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME])
    assert.equal(
      decodeEnvelope(await readFile(path.join(f.input.projectRoot, name)))
        .schemaVersion,
      2,
    );
  await frozen.execute('legacy-retry-after-upgrade-skip', { kind: 'skip' });
  assert.equal(frozen.getIssue(), null);
  const advanced = frozen.snapshot();
  assert.equal(advanced.revision, expected.revision + 1);
  assert.deepEqual(
    await frozen.execute('legacy-relink-retry-0001', relink),
    retained,
  );
  assert.deepEqual(frozen.snapshot(), advanced);
  await frozen.close();
  const reopened = await f.open({
    expectedSourceRoot: movedSource,
    expectedProjectId: legacy.projectId,
  });
  assert.equal(reopened.getIssue(), null);
  assert.deepEqual(
    await reopened.execute('legacy-relink-retry-0001', relink),
    retained,
  );
  assert.deepEqual(reopened.snapshot(), advanced);
});

test('pending upgrade relink preserves immutable hashes and legacy receipts after both roots move', async (t) => {
  const f = await fixture(t);
  const legacy = await f.legacy();
  let hit = false;
  try {
    const interrupted = await f.open({
      checkpoint(point) {
        if (!hit && point === 'upgrade:prepare:after') {
          hit = true;
          throw Object.assign(new Error('pending upgrade disk full'), {
            code: 'ENOSPC',
          });
        }
      },
    });
    assert.ok(interrupted.getIssue());
    await interrupted.close();
  } catch (error) {
    assert.ok(['ENOSPC', 'DISK_FULL'].includes(error.code), error.message);
  }
  assert.ok(hit);
  const descriptor = decodeEnvelope(
    await readFile(path.join(f.input.projectRoot, PROJECT_JOURNAL_NAME)),
  );
  assert.equal(descriptor.mode, 'upgrade');
  assert.deepEqual(descriptor.state, legacy);
  for (const name of compactNames(descriptor.head))
    assert.equal((await readdir(f.input.projectRoot)).includes(name), false);
  const movedSource = path.join(f.root, 'upgrade-source-moved');
  const movedOutput = path.join(f.root, 'upgrade-output-moved');
  await rename(f.input.sourceRoot, movedSource);
  await rename(f.input.outputRoot, movedOutput);
  const frozen = await f.open();
  assert.equal(frozen.getIssue()?.code, 'SOURCE_MISSING');
  const relink = {
    kind: 'relink',
    sourceRoot: movedSource,
    outputRoot: movedOutput,
  };
  const receipt = await frozen.execute('upgrade-relink-0001', relink);
  assert.equal(frozen.getIssue(), null);
  const expected = frozen.snapshot();
  assert.equal(expected.revision, legacy.revision + 1);
  assert.equal(expected.sourceRoot, movedSource);
  assert.equal(expected.outputRoot, movedOutput);
  assert.deepEqual(expected.decisions, legacy.decisions);
  assert.deepEqual(expected.receipts['upgrade-relink-0001'], receipt);
  assert.deepEqual(
    expected.receipts['legacy-confirmed-accept'],
    legacy.receipts['legacy-confirmed-accept'],
  );
  assert.deepEqual(
    await frozen.execute('legacy-confirmed-accept', command),
    legacy.receipts['legacy-confirmed-accept'],
  );
  for (const name of [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME]) {
    const head = decodeEnvelope(
      await readFile(path.join(f.input.projectRoot, name)),
    );
    assert.equal(head.schemaVersion, 2);
    assert.equal(head.inventoryHash, descriptor.head.inventoryHash);
    assert.equal(head.baselineHash, descriptor.head.baselineHash);
  }
  const baseline = decodeEnvelope(
    await readFile(
      path.join(f.input.projectRoot, compactNames(descriptor.head)[2]),
    ),
  );
  assert.deepEqual(baseline.receipts, legacy.receipts);
  await frozen.close();
  const retried = await child(
    'upgrade-relink-retry',
    f.input.projectRoot,
    movedSource,
    [movedOutput],
  );
  assert.equal(retried.code, 0, retried.stderr);
  const result = JSON.parse(retried.stdout);
  assert.deepEqual(result.receipt, receipt);
  assert.deepEqual(result.state, expected);
});

test('legacy retry after descriptor ENOSPC persists journal3 before publishing sidecars and survives process exit', async (t) => {
  const f = await fixture(t);
  const legacy = await f.legacy();
  const movedSource = path.join(f.root, 'legacy-source-offline');
  const output = await directoryBytes(f.input.outputRoot);
  await rename(f.input.sourceRoot, movedSource);
  const crashed = await child(
    'legacy-descriptor-resume-crash',
    f.input.projectRoot,
    movedSource,
    [f.input.sourceRoot],
  );
  assert.equal(crashed.code, 73, crashed.stderr);
  const descriptor = decodeEnvelope(
    await readFile(path.join(f.input.projectRoot, PROJECT_JOURNAL_NAME)),
  );
  assert.equal(descriptor.schemaVersion, 3);
  assert.equal(descriptor.mode, 'upgrade');
  assert.deepEqual(descriptor.state, legacy);
  const names = compactNames(descriptor.head);
  assert.ok((await readdir(f.input.projectRoot)).includes(names[0]));
  const recovered = await f.open();
  assert.equal(recovered.getIssue(), null);
  assert.deepEqual(recovered.snapshot(), legacy);
  assert.deepEqual(await directoryBytes(f.input.outputRoot), output);
  for (const name of [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME])
    assert.equal(
      decodeEnvelope(await readFile(path.join(f.input.projectRoot, name)))
        .schemaVersion,
      2,
    );
});

// Every explicit upgrade boundary is exercised, using actual content-addressed names.
for (const boundary of ['before', 'after']) {
  for (const target of [
    'prepare',
    'inventory-primary',
    'inventory-backup',
    'baseline-primary',
    'baseline-backup',
    'ledger-primary',
    'ledger-backup',
    'head-primary',
    'head-backup',
    'finalize',
  ]) {
    test(`upgrade ENOSPC ${target}:${boundary} resumes exact legacy state and never changes output`, async (t) => {
      const f = await fixture(t);
      const legacy = await f.legacy();
      const descriptor = ProjectStorage.upgradeDescriptor(legacy);
      const names = compactNames(descriptor.head);
      const byTarget = {
        'inventory-primary': names[0],
        'inventory-backup': names[1],
        'baseline-primary': names[2],
        'baseline-backup': names[3],
        'ledger-primary': names[4],
        'ledger-backup': names[5],
        'head-primary': PROJECT_STATE_NAME,
        'head-backup': PROJECT_BACKUP_NAME,
      };
      const point = `upgrade:${byTarget[target] ?? target}:${boundary}`;
      const output = await directoryBytes(f.input.outputRoot);
      let hit = false;
      try {
        const interrupted = await f.open({
          checkpoint(current) {
            if (!hit && current === point) {
              hit = true;
              throw Object.assign(new Error('upgrade disk full'), {
                code: 'ENOSPC',
              });
            }
          },
        });
        assert.ok(interrupted.getIssue());
        await interrupted.close();
      } catch (error) {
        assert.ok(['ENOSPC', 'DISK_FULL'].includes(error.code), error.message);
      }
      assert.ok(hit, `Checkpoint was not reached: ${point}`);
      assert.deepEqual(await directoryBytes(f.input.outputRoot), output);
      const recovered = await f.open();
      assert.equal(recovered.getIssue(), null);
      assert.deepEqual(recovered.snapshot(), legacy);
      assert.deepEqual(
        await recovered.execute('legacy-confirmed-accept', command),
        legacy.receipts['legacy-confirmed-accept'],
      );
      for (const name of [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME])
        assert.equal(
          decodeEnvelope(await readFile(path.join(f.input.projectRoot, name)))
            .schemaVersion,
          2,
        );
      assert.equal(
        (await readdir(f.input.projectRoot)).includes(PROJECT_JOURNAL_NAME),
        false,
      );
      assert.deepEqual(await directoryBytes(f.input.outputRoot), output);
    });
  }
}

for (const family of ['head', 'inventory', 'baseline', 'ledger']) {
  test(`healthy ${family} mirror repairs corruption; both damaged copies block without changing output`, async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    await store.execute('compact-mirror-accept', command);
    const expected = store.snapshot();
    const head = await f.head();
    const names = compactNames(head);
    const pair = {
      head: [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME],
      inventory: names.slice(0, 2),
      baseline: names.slice(2, 4),
      ledger: names.slice(4, 6),
    }[family];
    await store.close();
    const output = await directoryBytes(f.input.outputRoot);
    const healthy = await readFile(path.join(f.input.projectRoot, pair[1]));
    await writeFile(path.join(f.input.projectRoot, pair[0]), 'corrupt');
    const repaired = await f.open();
    assert.equal(repaired.getIssue(), null);
    assert.deepEqual(repaired.snapshot(), expected);
    assert.deepEqual(
      await readFile(path.join(f.input.projectRoot, pair[0])),
      healthy,
    );
    await repaired.close();
    for (const name of pair)
      await writeFile(path.join(f.input.projectRoot, name), 'both corrupt');
    await assertFailedOpen(f, ['PROJECT_CORRUPT']);
    assert.deepEqual(await directoryBytes(f.input.outputRoot), output);
  });
}

async function pending(f, point = `${PROJECT_LEDGER_NAME}:append`) {
  let armed = false;
  const store = await f.create({
    checkpoint(current) {
      if (armed && current === point) {
        armed = false;
        throw Object.assign(new Error('pending disk full'), { code: 'ENOSPC' });
      }
    },
  });
  armed = true;
  await assert.rejects(store.execute('compact-pending-accept', command), {
    code: 'DISK_FULL',
  });
  await store.close();
  const journal = decodeEnvelope(
    await readFile(path.join(f.input.projectRoot, PROJECT_JOURNAL_NAME)),
  );
  assert.equal(journal.schemaVersion, 3);
  assert.equal(journal.mode, 'operation');
  return journal;
}

describe('compact ledger/head write faults', { concurrency: 4 }, () => {
  const points = [
    ...[PROJECT_LEDGER_NAME, PROJECT_LEDGER_BACKUP_NAME].flatMap((name) =>
      ['append', 'partial', 'sync', 'appended'].map(
        (phase) => `${name}:${phase}`,
      ),
    ),
    ...[PROJECT_STATE_NAME, PROJECT_BACKUP_NAME].flatMap((name) =>
      ['temp', 'sync', 'replace'].map((phase) => `${name}:${phase}`),
    ),
  ];
  for (const point of points) {
    test(`ENOSPC at ${point} recovers exact receipt once and synchronizes both heads and ledgers`, async (t) => {
      const f = await fixture(t);
      let armed = false;
      let reached = false;
      const store = await f.create({
        checkpoint(current) {
          if (armed && current === point) {
            armed = false;
            reached = true;
            throw Object.assign(new Error('compact write disk full'), {
              code: 'ENOSPC',
            });
          }
        },
      });
      armed = true;
      await assert.rejects(
        store.execute('compact-write-fault-accept', command),
        { code: 'DISK_FULL' },
      );
      assert.ok(reached, `Checkpoint was not reached: ${point}`);
      const journal = decodeEnvelope(
        await readFile(path.join(f.input.projectRoot, PROJECT_JOURNAL_NAME)),
      );
      const expected = JSON.parse(journal.record).payload.receipt;
      await store.close();
      const recovered = await f.open();
      assert.equal(recovered.getIssue(), null);
      assert.deepEqual(
        await recovered.execute('compact-write-fault-accept', command),
        expected,
      );
      assert.deepEqual(
        await recovered.execute('compact-write-fault-accept', command),
        expected,
      );
      const state = recovered.snapshot();
      assert.equal(state.revision, 1);
      assert.equal(state.decisions.length, 1);
      assert.equal(Object.keys(state.receipts).length, 1);
      const primary = decodeEnvelope(
        await readFile(path.join(f.input.projectRoot, PROJECT_STATE_NAME)),
      );
      const backup = decodeEnvelope(
        await readFile(path.join(f.input.projectRoot, PROJECT_BACKUP_NAME)),
      );
      assert.deepEqual(primary, backup);
      assert.equal(primary.revision, expected.revision);
      const ledger = await readFile(
        path.join(f.input.projectRoot, PROJECT_LEDGER_NAME),
      );
      assert.deepEqual(
        ledger,
        await readFile(
          path.join(f.input.projectRoot, PROJECT_LEDGER_BACKUP_NAME),
        ),
      );
      assert.equal(ledger.toString(), journal.record);
      assert.equal(primary.ledgerBytes, ledger.length);
      assert.equal(
        (await readdir(f.input.projectRoot)).includes(PROJECT_JOURNAL_NAME),
        false,
      );
    });
  }
});

for (const suffix of ['partial', 'exact', 'changed', 'extra']) {
  test(`pending ledger ${suffix} suffix ${['partial', 'exact'].includes(suffix) ? 'recovers exactly' : 'fails closed'}`, async (t) => {
    const f = await fixture(t);
    const journal = await pending(f);
    const record = Buffer.from(journal.record);
    let tail =
      suffix === 'partial'
        ? record.subarray(0, Math.floor(record.length / 2))
        : Buffer.from(record);
    if (suffix === 'changed') {
      tail = Buffer.from(tail);
      tail[20] ^= 1;
    }
    if (suffix === 'extra')
      tail = Buffer.concat([tail, Buffer.from('unknown')]);
    await writeFile(path.join(f.input.projectRoot, PROJECT_LEDGER_NAME), tail);
    const output = await directoryBytes(f.input.outputRoot);
    if (suffix === 'changed' || suffix === 'extra') {
      await assertFailedOpen(f, ['JOURNAL_CONFLICT']);
      assert.deepEqual(
        await readFile(path.join(f.input.projectRoot, PROJECT_LEDGER_NAME)),
        tail,
      );
      assert.deepEqual(await directoryBytes(f.input.outputRoot), output);
    } else {
      const recovered = await f.open();
      assert.equal(recovered.getIssue(), null);
      const receipt = await recovered.execute(journal.operationId, command);
      assert.equal(receipt.decisionCount, 1);
      assert.equal(recovered.snapshot().revision, 1);
      for (const name of [PROJECT_LEDGER_NAME, PROJECT_LEDGER_BACKUP_NAME])
        assert.deepEqual(
          await readFile(path.join(f.input.projectRoot, name)),
          record,
        );
    }
  });
}

test('ledger tail without a pending journal never proves a completed operation', async (t) => {
  const f = await fixture(t);
  const store = await f.create();
  await store.close();
  await writeFile(
    path.join(f.input.projectRoot, PROJECT_LEDGER_NAME),
    'uncommitted\n',
  );
  const output = await directoryBytes(f.input.outputRoot);
  await assertFailedOpen(f, ['JOURNAL_CONFLICT']);
  assert.deepEqual(await directoryBytes(f.input.outputRoot), output);
});

async function prepared(f, kind) {
  let armed = false;
  const store = await f.create({
    checkpoint(point) {
      if (armed && point === 'prepare:after') {
        armed = false;
        throw Object.assign(new Error('prepared disk full'), {
          code: 'ENOSPC',
        });
      }
    },
  });
  let operation = command;
  if (kind !== 'accept') {
    await store.execute('compact-poison-seed-1', command);
    await store.execute('compact-poison-seed-2', {
      kind: 'accept',
      imagePath: 'photo2.jpg',
    });
    if (kind === 'undo') operation = { kind: 'undo' };
    else {
      const preview = await store.previewRestart();
      operation = {
        kind: 'restart',
        expectedRevision: preview.revision,
        previewChecksum: preview.checksum,
      };
    }
  }
  armed = true;
  await assert.rejects(store.execute('compact-poison-operation', operation), {
    code: 'DISK_FULL',
  });
  await store.close();
  const journal = decodeEnvelope(
    await readFile(path.join(f.input.projectRoot, PROJECT_JOURNAL_NAME)),
  );
  assert.equal(journal.phase, 'prepared');
  return journal;
}

for (const poison of ['missing', 'checksum', 'size']) {
  test(`poisoned prepared accept copy ${poison} blocks before JPEG and preserves output bytes`, async (t) => {
    const f = await fixture(t);
    const journal = await prepared(f, 'accept');
    const output = await directoryBytes(f.input.outputRoot);
    if (poison === 'missing') journal.copy = null;
    else if (poison === 'checksum')
      journal.copy.checksumSha256 = '0'.repeat(64);
    else journal.copy.sizeBytes++;
    await writeFile(
      path.join(f.input.projectRoot, PROJECT_JOURNAL_NAME),
      encodeEnvelope(journal),
    );
    await assertFailedOpen(f, ['JOURNAL_CORRUPT', 'JOURNAL_CONFLICT']);
    assert.deepEqual(await directoryBytes(f.input.outputRoot), output);
  });
}

for (const kind of ['undo', 'restart']) {
  for (const poison of ['missing', 'extra-owned']) {
    test(`poisoned prepared ${kind} removals ${poison} blocks before JPEG and preserves output bytes`, async (t) => {
      const f = await fixture(t);
      const journal = await prepared(f, kind);
      const output = await directoryBytes(f.input.outputRoot);
      if (poison === 'missing') journal.removals = [];
      else {
        const record = JSON.parse(
          (
            await readFile(
              path.join(f.input.projectRoot, PROJECT_LEDGER_NAME),
              'utf8',
            )
          ).split('\n')[0],
        );
        const owned = record.payload.delta.decision;
        journal.removals.push({
          outputName: owned.outputName,
          checksumSha256: owned.imageChecksumSha256,
        });
      }
      await writeFile(
        path.join(f.input.projectRoot, PROJECT_JOURNAL_NAME),
        encodeEnvelope(journal),
      );
      await assertFailedOpen(f, ['JOURNAL_CORRUPT', 'JOURNAL_CONFLICT']);
      assert.deepEqual(await directoryBytes(f.input.outputRoot), output);
    });
  }
}

for (const poison of ['head-scalar', 'recomputed-revision']) {
  test(`poisoned prepared ${poison} is rejected despite valid envelope and record checksums`, async (t) => {
    const f = await fixture(t);
    const journal = await prepared(f, 'accept');
    const output = await directoryBytes(f.input.outputRoot);
    if (poison === 'head-scalar') journal.after.scalar.nextRangeStart += 9;
    else {
      const record = JSON.parse(journal.record);
      record.payload.scalar.revision++;
      record.payload.receipt.revision++;
      journal.after.scalar.revision++;
      journal.after.revision++;
      record.checksumSha256 = checksum(
        stableStringify({
          previousHash: record.previousHash,
          payload: record.payload,
        }),
      );
      journal.record = `${stableStringify(record)}\n`;
      journal.after.ledgerHash = record.checksumSha256;
      journal.after.ledgerBytes =
        journal.before.ledgerBytes + Buffer.byteLength(journal.record);
    }
    await writeFile(
      path.join(f.input.projectRoot, PROJECT_JOURNAL_NAME),
      encodeEnvelope(journal),
    );
    await assertFailedOpen(f, ['JOURNAL_CORRUPT', 'JOURNAL_CONFLICT']);
    assert.deepEqual(await directoryBytes(f.input.outputRoot), output);
  });
}

for (const point of [
  `${PROJECT_LEDGER_NAME}:partial`,
  `${PROJECT_LEDGER_BACKUP_NAME}:append`,
  'state:after',
]) {
  test(`pending relink at ${point} preserves exact ledger bytes and changes only root bindings`, async (t) => {
    const f = await fixture(t);
    const journal = await pending(f, point);
    const movedSource = path.join(f.root, 'moved-source');
    const movedOutput = path.join(f.root, 'moved-output');
    await rename(f.input.sourceRoot, movedSource);
    await rename(f.input.outputRoot, movedOutput);
    const frozen = await f.open();
    assert.ok(frozen.getIssue());
    await frozen.execute('compact-relink-pending', {
      kind: 'relink',
      sourceRoot: movedSource,
      outputRoot: movedOutput,
    });
    assert.equal(frozen.getIssue(), null);
    const state = frozen.snapshot();
    assert.equal(state.sourceRoot, movedSource);
    assert.equal(state.outputRoot, movedOutput);
    assert.equal(state.decisions.length, 1);
    assert.equal(state.revision, 2);
    for (const name of [PROJECT_LEDGER_NAME, PROJECT_LEDGER_BACKUP_NAME]) {
      const ledger = await readFile(
        path.join(f.input.projectRoot, name),
        'utf8',
      );
      assert.equal(ledger.slice(0, journal.record.length), journal.record);
      const relink = JSON.parse(ledger.slice(journal.record.length));
      assert.equal(relink.payload.operationId, 'compact-relink-pending');
      assert.equal(relink.payload.delta.kind, 'none');
      assert.equal(relink.payload.previousRevision, 1);
      assert.equal(Object.hasOwn(relink.payload.scalar, 'sourceRoot'), false);
      assert.equal(Object.hasOwn(relink.payload.scalar, 'outputRoot'), false);
    }
    assert.deepEqual(
      await frozen.execute(journal.operationId, command),
      JSON.parse(journal.record).payload.receipt,
    );
    await frozen.close();
    const reopened = await f.open({
      expectedSourceRoot: movedSource,
      expectedProjectId: journal.projectId,
    });
    assert.equal(reopened.getIssue(), null);
    assert.deepEqual(reopened.snapshot(), state);
  });
}

test('legacy validators refuse both compact heads and upgrade intent, including fallback after primary corruption', async (t) => {
  const f = await fixture(t);
  const store = await f.create();
  const state = store.snapshot();
  const head = await f.head();
  await store.close();
  for (const name of [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME]) {
    const oldReaderInput = decodeEnvelope(
      await readFile(path.join(f.input.projectRoot, name)),
    );
    assert.throws(() => validateState(oldReaderInput), {
      code: 'UNSUPPORTED_PROJECT_SCHEMA',
    });
  }
  assert.throws(
    () => validateJournal(ProjectStorage.upgradeDescriptor(state)),
    { code: 'JOURNAL_CORRUPT' },
  );
  await writeFile(
    path.join(f.input.projectRoot, PROJECT_STATE_NAME),
    'corrupt primary',
  );
  assert.throws(() => decodeEnvelope(Buffer.from('corrupt primary')), {
    code: 'PROJECT_CORRUPT',
  });
  const fallback = decodeEnvelope(
    await readFile(path.join(f.input.projectRoot, PROJECT_BACKUP_NAME)),
  );
  assert.throws(() => validateState(fallback), {
    code: 'UNSUPPORTED_PROJECT_SCHEMA',
  });
  assert.equal(head.schemaVersion, 2);
});

for (const expectation of ['source', 'project']) {
  test(`wrong expected ${expectation} identity blocks legacy upgrade before any persisted changes`, async (t) => {
    const f = await fixture(t);
    await f.legacy();
    const before = await directoryBytes(f.input.projectRoot);
    const output = await directoryBytes(f.input.outputRoot);
    const options =
      expectation === 'source'
        ? { expectedSourceRoot: path.join(f.root, 'wrong-source') }
        : { expectedProjectId: '00000000-0000-0000-0000-000000000000' };
    await assert.rejects(f.open(options), {
      code:
        expectation === 'source'
          ? 'SOURCE_PROJECT_CONFLICT'
          : 'PROJECT_ID_CONFLICT',
    });
    assert.deepEqual(await directoryBytes(f.input.projectRoot), before);
    assert.deepEqual(await directoryBytes(f.input.outputRoot), output);
  });
}

for (const target of [
  'prepare',
  'inventory-primary',
  'inventory-backup',
  'baseline-primary',
  'baseline-backup',
  'ledger-primary',
  'ledger-backup',
  'head-primary',
  'head-backup',
  'finalize',
]) {
  test(`real process exit during upgrade ${target} leaves recoverable exact baseline`, async (t) => {
    const f = await fixture(t);
    const state = await f.legacy();
    const descriptor = ProjectStorage.upgradeDescriptor(state);
    const names = compactNames(descriptor.head);
    const resolved =
      {
        'inventory-primary': names[0],
        'inventory-backup': names[1],
        'baseline-primary': names[2],
        'baseline-backup': names[3],
        'ledger-primary': names[4],
        'ledger-backup': names[5],
        'head-primary': PROJECT_STATE_NAME,
        'head-backup': PROJECT_BACKUP_NAME,
      }[target] ?? target;
    const output = await directoryBytes(f.input.outputRoot);
    const crashed = await child(
      'upgrade-crash',
      f.input.projectRoot,
      `upgrade:${resolved}:after`,
    );
    assert.equal(crashed.code, 73, crashed.stderr);
    const recovered = await f.open();
    assert.equal(recovered.getIssue(), null);
    assert.deepEqual(recovered.snapshot(), state);
    assert.deepEqual(await directoryBytes(f.input.outputRoot), output);
  });
}

for (const point of [
  'prepare:after',
  'jpeg:after',
  `${PROJECT_LEDGER_NAME}:partial`,
  `${PROJECT_LEDGER_NAME}:appended`,
  `${PROJECT_LEDGER_BACKUP_NAME}:partial`,
  'state:after',
  'backup:after',
  'finalize:after',
]) {
  test(`real process exit at ${point} recovers once in another process with identical retry`, async (t) => {
    const f = await fixture(t);
    const store = await f.create();
    await store.close();
    const crashed = await child('operation-crash', f.input.projectRoot, point);
    assert.equal(crashed.code, 73, crashed.stderr);
    const recovered = await child('recover', f.input.projectRoot);
    assert.equal(recovered.code, 0, recovered.stderr);
    const result = JSON.parse(recovered.stdout);
    assert.equal(result.state.revision, 1);
    assert.equal(result.state.decisions.length, 1);
    assert.equal(Object.keys(result.state.receipts).length, 1);
    assert.deepEqual(
      result.receipt,
      result.state.receipts['compact-process-accept'],
    );
    const reopened = await f.open();
    assert.equal(reopened.getIssue(), null);
    assert.deepEqual(
      await reopened.execute('compact-process-accept', command),
      result.receipt,
    );
    assert.deepEqual(
      await readFile(path.join(f.input.projectRoot, PROJECT_LEDGER_NAME)),
      await readFile(
        path.join(f.input.projectRoot, PROJECT_LEDGER_BACKUP_NAME),
      ),
    );
  });
}

import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import {
  mkdir,
  mkdtemp,
  rm,
  writeFile,
  symlink,
  rename,
  lstat,
  utimes,
  readFile,
} from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  WindowsCheckWorker,
  nativeChecks,
  disposeNativeChecks,
} from '../src/native/windows-check-worker.ts';
import { SourceRegistry, scanSource } from '../src/native/source-registry.ts';
import { ProjectStore } from '../src/project/project-store.ts';
import { ProjectController } from '../src/native/project-controller.ts';
import {
  nativeProcesses,
  ProjectLock,
  PROJECT_LOCK_NAME,
} from '../src/project/project-lock.ts';
import { SecureFiles } from '../src/filesystem/secure-files.ts';
after(disposeNativeChecks);
const childPath = fileURLToPath(
  new URL('./check-worker-child.mjs', import.meta.url),
);
function fake(t, mode, options = {}) {
  const pids = [];
  const worker = new WindowsCheckWorker({
    launch: () => {
      const child = spawn(process.execPath, [childPath, mode], {
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      pids.push(child.pid);
      return child;
    },
    ...options,
  });
  t.after(async () => {
    await worker.dispose();
    for (const pid of pids)
      assert.throws(() => process.kill(pid, 0), { code: 'ESRCH' });
  });
  return worker;
}
test('typed checks use one worker and preserve FIFO and split UTF-8', async (t) => {
  const worker = fake(t, 'valid');
  const results = await Promise.all([
    worker.processIdentity(11),
    worker.processIdentity(12),
    worker.processIdentity(13),
  ]);
  assert.deepEqual(results, ['11', '12', '13']);
  assert.equal(worker.stats().spawnCount, 1);
  assert.equal(await fake(t, 'split').processIdentity(14), 'zażółć🙂');
});
for (const mode of [
  'wrong-id',
  'invalid-json',
  'wrong-type',
  'oversize',
  'stderr',
  'crash',
])
  test(`worker ${mode} rejects active and queued checks and leaves no process`, async (t) => {
    const worker = fake(t, mode);
    const results = await Promise.allSettled([
      worker.processIdentity(11),
      worker.processIdentity(12),
    ]);
    assert.ok(results.every((r) => r.status === 'rejected'));
    assert.equal(worker.stats().pending, 0);
  });
test('deadline includes queue; timeout kills worker, and shutdown rejects pending', async (t) => {
  const worker = fake(t, 'hang', { timeoutMs: 150 });
  const results = await Promise.allSettled([
    worker.processIdentity(11),
    worker.processIdentity(12),
  ]);
  assert.ok(results.every((r) => r.reason.code === 'NATIVE_CHECK_TIMEOUT'));
  const next = worker.processIdentity(13);
  const rejected = assert.rejects(next, { code: 'NATIVE_CHECK_CLOSED' });
  await worker.dispose();
  await rejected;
  await assert.rejects(worker.processIdentity(14), {
    code: 'NATIVE_CHECK_CLOSED',
  });
});
test('queue and input are bounded before dispatch', async (t) => {
  const worker = fake(t, 'hang', { maxQueue: 1 });
  const active = worker.processIdentity(11);
  const rejected = assert.rejects(active, { code: 'NATIVE_CHECK_CLOSED' });
  await assert.rejects(worker.processIdentity(12), {
    code: 'NATIVE_CHECK_BUSY',
  });
  await assert.rejects(worker.driveInfo('x'.repeat(300000)), {
    code: 'INVALID_ARGUMENT',
  });
  await assert.rejects(worker.processIdentity(-1), {
    code: 'INVALID_ARGUMENT',
  });
  await worker.dispose();
  await rejected;
});
test('a failed child is retired before the next request starts a fresh worker', async (t) => {
  let launch = 0;
  const worker = new WindowsCheckWorker({
    launch: () =>
      spawn(process.execPath, [childPath, launch++ ? 'valid' : 'crash'], {
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
      }),
  });
  t.after(() => worker.dispose());
  await assert.rejects(worker.processIdentity(11));
  assert.equal(await worker.processIdentity(12), '12');
  assert.equal(worker.stats().spawnCount, 2);
});
async function fixture(t) {
  const base = path.resolve('.tmp');
  await mkdir(base, { recursive: true });
  const root = await mkdtemp(path.join(base, 'selector-native-'));
  t.after(() => rm(root, { force: true, recursive: true }));
  const sourceRoot = path.join(root, 'source');
  await mkdir(sourceRoot);
  for (const name of ['photo1.jpg', 'photo2.jpg', 'photo3.jpg']) {
    await writeFile(
      path.join(sourceRoot, name),
      Buffer.from([255, 216, 1, 2, 255, 217]),
    );
    await utimes(path.join(sourceRoot, name), 1700000000, 1700000000.123456);
  }
  return {
    root,
    sourceRoot,
    projectRoot: path.join(root, 'project'),
    outputRoot: path.join(root, 'output'),
    firstLayout: 1,
    direction: 'ascending',
    localStorageConfirmed: true,
  };
}
test('verified source handoff keeps fractional timestamps and rejects fabricated proof', async (t) => {
  const f = await fixture(t);
  const scan = await scanSource(f.sourceRoot);
  const registry = new SourceRegistry();
  const index = await registry.registerVerifiedScan(scan);
  assert.equal(
    index.images[0].lastModified,
    (await lstat(path.join(f.sourceRoot, 'photo1.jpg'))).mtimeMs,
  );
  const stream = await registry.openImage(index.id, index.images[0].id);
  for await (const chunk of stream) assert.equal(chunk.length, 6);
  await assert.rejects(registry.registerVerifiedScan({ ...scan }), {
    code: 'SOURCE_IDENTITY_CONFLICT',
  });
});
test(
  'native worker uses fresh process and reparse evidence after indexing',
  { skip: process.platform !== 'win32' },
  async (t) => {
    const f = await fixture(t);
    const registry = new SourceRegistry();
    const source = await registry.register(f.sourceRoot);
    const worker = nativeChecks();
    const before = worker.stats().spawnCount;
    assert.ok(await nativeProcesses.identity(process.pid));
    const child = spawn(process.execPath, ['-e', 'setInterval(()=>{},1000)'], {
      windowsHide: true,
    });
    const identity = await worker.processIdentity(child.pid);
    assert.ok(identity);
    const stopped = new Promise((resolve) => child.once('close', resolve));
    child.kill();
    await stopped;
    assert.equal(await worker.processIdentity(child.pid), null);
    await rename(f.sourceRoot, `${f.sourceRoot}-moved`);
    await symlink(`${f.sourceRoot}-moved`, f.sourceRoot, 'junction');
    await assert.rejects(worker.reparseScan([f.sourceRoot], false), {
      code: 'REPARSE_POINT',
    });
    await assert.rejects(registry.openImage(source.id, source.images[0].id), {
      code: 'REPARSE_POINT',
    });
    assert.equal(worker.stats().spawnCount, before);
  },
);
test(
  'functional warm cursor, preview and accept share a worker and one verified scan',
  { skip: process.platform !== 'win32' },
  async (t) => {
    const f = await fixture(t);
    const store = await ProjectStore.create(f);
    const scan = store.getVerifiedSourceScan();
    assert.ok(scan);
    const registry = new SourceRegistry();
    const source = await registry.registerVerifiedScan(scan);
    const before = nativeChecks().stats().spawnCount;
    const started = performance.now();
    await store.execute('navigate-0001', {
      kind: 'navigate',
      imagePath: 'photo2.jpg',
    });
    const navigateMs = performance.now() - started;
    const previewStart = performance.now();
    const stream = await registry.openImage(source.id, source.images[1].id);
    for await (const chunk of stream) assert.ok(chunk.length);
    const previewMs = performance.now() - previewStart;
    const acceptStart = performance.now();
    await store.execute('accept-0001', {
      kind: 'accept',
      imagePath: 'photo2.jpg',
    });
    const acceptMs = performance.now() - acceptStart;
    assert.equal(nativeChecks().stats().spawnCount, before);
    await store.close();
    const reopened = await ProjectStore.open(f.projectRoot);
    assert.equal(reopened.snapshot().currentRelativePath, 'photo3.jpg');
    assert.equal(reopened.snapshot().decisions.length, 1);
    assert.ok(reopened.getVerifiedSourceScan());
    await reopened.close();
    t.diagnostic(
      JSON.stringify({
        fixturePhotos: 3,
        warmWorkerSpawns: 0,
        navigateMs: Math.round(navigateMs),
        previewMs: Math.round(previewMs),
        acceptMs: Math.round(acceptMs),
      }),
    );
  },
);
test('controller uses the store scan without invoking register and preserves close diagnostics', async (t) => {
  const f = await fixture(t);
  const store = await ProjectStore.create(f);
  await store.close();
  const registry = new SourceRegistry();
  registry.register = () => {
    throw new Error('second source scan');
  };
  const controller = new ProjectController(
    path.join(f.root, 'userData'),
    registry,
    {
      directory: async () => f.projectRoot,
      confirm: async () => true,
      openFolder: async () => {},
    },
  );
  const workspace = await controller.open();
  assert.equal(workspace.source.images.length, 3);
  const lockPath = path.join(f.projectRoot, 'selector-project.lock');
  const owner = JSON.parse(await readFile(lockPath, 'utf8'));
  owner.ownerId = 'foreign-controller-owner';
  const foreign = JSON.stringify(owner);
  await writeFile(lockPath, foreign);
  await controller.close();
  assert.equal(controller.getCloseIssue().code, 'LOCK_LOST');
  assert.equal(controller.snapshot(), null);
  assert.equal(await readFile(lockPath, 'utf8'), foreign);
});
test(
  'real PowerShell shutdown waits for process exit and rejects later checks',
  { skip: process.platform !== 'win32' },
  async () => {
    const worker = new WindowsCheckWorker();
    await worker.processIdentity(process.pid);
    const pid = worker.stats().pid;
    assert.ok(pid);
    await worker.dispose();
    assert.throws(() => process.kill(pid, 0), { code: 'ESRCH' });
    await assert.rejects(worker.processIdentity(process.pid), {
      code: 'NATIVE_CHECK_CLOSED',
    });
  },
);

test('identity retries only timeout with a fresh child and bounded safe diagnostics', async (t) => {
  let launches = 0;
  const diagnostics = [];
  const worker = new WindowsCheckWorker({
    timeoutMs: 200,
    diagnostics: (entry) => diagnostics.push(entry),
    launch: () =>
      spawn(process.execPath, [childPath, launches++ ? 'valid' : 'hang'], {
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
      }),
  });
  t.after(() => worker.dispose());
  assert.equal(await worker.processIdentity(12345), '12345');
  assert.equal(launches, 2);
  assert.deepEqual(
    diagnostics.map((entry) => [entry.attempt, entry.code]),
    [
      [1, 'NATIVE_CHECK_TIMEOUT'],
      [2, 'NATIVE_CHECK_OK'],
    ],
  );
  for (const entry of diagnostics) {
    assert.deepEqual(Object.keys(entry).sort(), [
      'attempt',
      'code',
      'elapsedMs',
    ]);
    assert.ok(Number.isSafeInteger(entry.elapsedMs) && entry.elapsedMs >= 0);
  }
  assert.ok(!JSON.stringify(diagnostics).includes('12345'));
});
test('two identity timeouts remain unknown and stop after exactly two attempts', async (t) => {
  const diagnostics = [];
  const worker = fake(t, 'hang', {
    timeoutMs: 150,
    diagnostics: (entry) => diagnostics.push(entry),
  });
  await assert.rejects(worker.processIdentity(11), {
    code: 'NATIVE_CHECK_TIMEOUT',
  });
  assert.equal(worker.stats().spawnCount, 2);
  assert.deepEqual(
    diagnostics.map((entry) => entry.attempt),
    [1, 2],
  );
});
for (const mode of ['wrong-id', 'crash'])
  test(`identity ${mode} never retries`, async (t) => {
    const worker = fake(t, mode);
    await assert.rejects(worker.processIdentity(11));
    assert.equal(worker.stats().spawnCount, 1);
  });
test('valid null identity is evidence and diagnostic sink failures are harmless', async (t) => {
  const script =
    "require('readline').createInterface({input:process.stdin}).on('line',line=>{const r=JSON.parse(line);console.log(JSON.stringify({version:1,id:r.id,ok:true,result:{identity:null}}))})";
  for (const diagnostics of [
    () => {
      throw new Error('sink');
    },
    async () => {
      throw new Error('sink');
    },
  ]) {
    const worker = new WindowsCheckWorker({
      diagnostics,
      launch: () =>
        spawn(process.execPath, ['-e', script], {
          windowsHide: true,
          stdio: ['pipe', 'pipe', 'pipe'],
        }),
    });
    t.after(() => worker.dispose());
    assert.equal(await worker.processIdentity(11), null);
    assert.equal(worker.stats().spawnCount, 1);
  }
});

test('identity timeout retry never reclaims or changes an existing owner lock', async (t) => {
  const f = await fixture(t);
  await mkdir(f.projectRoot);
  const worker = fake(t, 'hang', { timeoutMs: 150 });
  const ownerBytes = JSON.stringify({
    schemaVersion: 1,
    ownerId: 'existing-owner',
    host: 'test-host',
    pid: 11,
    processIdentity: 'original-identity',
    createdAt: '2026-10-12T00:00:00.000Z',
  });
  const lock = path.join(f.projectRoot, PROJECT_LOCK_NAME);
  await writeFile(lock, ownerBytes);
  const inspector = {
    host: 'test-host',
    pid: 12,
    identity: async (pid) =>
      pid === 12 ? 'own-identity' : worker.processIdentity(pid),
  };
  await assert.rejects(
    ProjectLock.acquire(new SecureFiles(f.projectRoot), inspector),
    { code: 'LOCK_OWNER_UNKNOWN' },
  );
  assert.equal(await readFile(lock, 'utf8'), ownerBytes);
  assert.equal(worker.stats().spawnCount, 2);
});

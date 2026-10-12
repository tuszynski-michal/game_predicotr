import test from 'node:test';
import assert from 'node:assert/strict';
import {
  mkdtemp,
  mkdir,
  writeFile,
  readFile,
  readdir,
  rm,
  symlink,
  rename,
} from 'node:fs/promises';
import path from 'node:path';
import fsPromises from 'node:fs/promises';
import { syncBuiltinESMExports } from 'node:module';
import { SourceRegistry } from '../src/native/source-registry.ts';
import {
  containedPath,
  safeExistingPath,
} from '../src/native/path-security.ts';
import {
  APP_URL,
  validateSender,
  validateNoArguments,
  parsePhotoUrl,
} from '../src/contracts.ts';
import { DiagnosticLog } from '../src/native/diagnostic-log.ts';

async function fixture(t) {
  const base = path.resolve('.tmp');
  await mkdir(base, { recursive: true });
  const root = await mkdtemp(path.join(base, 'selector-foundation-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  return root;
}
test('paths reject traversal, absolute paths, ADS and malformed separators', () => {
  for (const name of [
    '../secret.jpg',
    '/secret.jpg',
    'C:/secret.jpg',
    'a/../../b.jpg',
    'a\\b.jpg',
    'a:stream',
    'a//b',
    'a/./b',
  ])
    assert.throws(() => containedPath(path.resolve('root'), name));
  assert.equal(
    containedPath(path.resolve('root'), 'a/b.jpg'),
    path.resolve('root/a/b.jpg'),
  );
});
test('IPC requires the exact main document and owning window, no arguments', () => {
  validateSender(APP_URL, true, true);
  for (const [url, main, window] of [
    [APP_URL, false, true],
    [APP_URL, true, false],
    [APP_URL + '?x', true, true],
    ['https://example.org', true, true],
    ['selector://evil/index.html', true, true],
  ])
    assert.throws(() => validateSender(url, main, window));
  validateNoArguments([]);
  assert.throws(() => validateNoArguments(['C:/secret.jpg']));
  assert.throws(() => parsePhotoUrl('selector-photo://root/../secret.jpg'));
});
test('recursive JPEG index sorts naturally and reads only opaque registered IDs', async (t) => {
  const root = await fixture(t);
  await mkdir(path.join(root, 'nested'));
  for (const name of [
    'photo10.JPG',
    'photo2.jpg',
    'nested/photo1.jpeg',
    'ignored.png',
  ])
    await writeFile(path.join(root, name), name);
  const registry = new SourceRegistry();
  const index = await registry.register(root);
  assert.deepEqual(
    index.images.map((x) => x.relativePath),
    ['nested/photo1.jpeg', 'photo2.jpg', 'photo10.JPG'],
  );
  assert.ok(!JSON.stringify(index).includes(root));
  const image = index.images[1];
  const { sourceId, imageId } = parsePhotoUrl(image.url);
  const stream = await registry.openImage(sourceId, imageId);
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  assert.equal(Buffer.concat(chunks).toString(), 'photo2.jpg');
  await assert.rejects(registry.openImage(index.id, '../photo2.jpg'), {
    code: 'UNKNOWN_IMAGE',
  });
  await writeFile(path.join(root, 'photo2.jpg'), 'changed');
  await assert.rejects(registry.openImage(sourceId, imageId), {
    code: 'SOURCE_CHANGED',
  });
  await assert.rejects(registry.register(path.join(root, 'missing')));
  assert.equal(registry.getRoot(index.id), root);
});
test('junctions are rejected in selected roots, descendants and after indexing', async (t) => {
  const root = await fixture(t);
  await mkdir(path.join(root, 'source'));
  await mkdir(path.join(root, 'outside'));
  await writeFile(path.join(root, 'outside/x.jpg'), 'secret');
  await symlink(
    path.join(root, 'outside'),
    path.join(root, 'source/link'),
    process.platform === 'win32' ? 'junction' : 'dir',
  );
  await assert.rejects(
    safeExistingPath(path.join(root, 'source'), 'link/x.jpg'),
    { code: 'REPARSE_POINT' },
  );
  await assert.rejects(
    new SourceRegistry().register(path.join(root, 'source/link')),
    { code: 'REPARSE_POINT' },
  );
  await assert.rejects(
    new SourceRegistry().register(path.join(root, 'source')),
    { code: 'REPARSE_POINT' },
  );
});
test('a directory replaced by a junction after indexing cannot be read', async (t) => {
  const root = await fixture(t);
  await mkdir(path.join(root, 'source/sub'), { recursive: true });
  await mkdir(path.join(root, 'outside'));
  await writeFile(path.join(root, 'source/sub/x.jpg'), 'original');
  await writeFile(path.join(root, 'outside/x.jpg'), 'secret');
  const registry = new SourceRegistry();
  const index = await registry.register(path.join(root, 'source'));
  await rename(path.join(root, 'source/sub'), path.join(root, 'parked'));
  await symlink(
    path.join(root, 'outside'),
    path.join(root, 'source/sub'),
    process.platform === 'win32' ? 'junction' : 'dir',
  );
  await assert.rejects(registry.openImage(index.id, index.images[0].id), {
    code: 'REPARSE_POINT',
  });
});
test('empty directory is represented explicitly', async (t) => {
  const registry = new SourceRegistry();
  assert.deepEqual((await registry.register(await fixture(t))).images, []);
});
test('source index has no photo or directory-entry count ceiling', async (t) => {
  const root = await fixture(t);
  const template = path.join(root, 'template.jpg');
  await writeFile(template, 'sample metadata');
  const fileStat = await fsPromises.lstat(template);
  const originalLstat = fsPromises.lstat;
  const originalRealpath = fsPromises.realpath;
  const originalReaddir = fsPromises.readdir;
  const statCache = new Map();
  const pathCache = new Map();
  const virtualFile = (file) =>
    path.dirname(file) === root &&
    /^photo\d+\.(jpg|txt)$/.test(path.basename(file));
  // Controlled directory metadata exercises both former ceilings without creating
  // a large on-disk JPEG fixture or running a performance benchmark.
  const entries = [
    ...Array.from({ length: 100001 }, (_, i) => ({
      name: `photo${i + 1}.txt`,
    })),
    ...Array.from({ length: 30000 }, (_, i) => ({
      name: `photo${30000 - i}.jpg`,
    })),
  ];
  // This test file runs in its own process. Avoid recording a mock-call object
  // for every ancestor check; restore all bindings before subsequent tests.
  fsPromises.lstat = async (file) => {
    if (virtualFile(file)) return fileStat;
    if (!statCache.has(file)) statCache.set(file, await originalLstat(file));
    return statCache.get(file);
  };
  fsPromises.realpath = async (file) => {
    if (virtualFile(file)) return file;
    if (!pathCache.has(file)) pathCache.set(file, await originalRealpath(file));
    return pathCache.get(file);
  };
  fsPromises.readdir = (file, options) =>
    file === root ? Promise.resolve(entries) : originalReaddir(file, options);
  syncBuiltinESMExports();
  try {
    const registry = new SourceRegistry();
    const index = await registry.register(root);
    assert.equal(index.images.length, 30000);
    assert.equal(index.images[0].relativePath, 'photo1.jpg');
    assert.equal(index.images[1].relativePath, 'photo2.jpg');
    assert.equal(index.images.at(-1).relativePath, 'photo30000.jpg');
    assert.equal(new Set(index.images.map((image) => image.id)).size, 30000);
    assert.equal(registry.getRoot(index.id), root);
  } finally {
    fsPromises.lstat = originalLstat;
    fsPromises.realpath = originalRealpath;
    fsPromises.readdir = originalReaddir;
    syncBuiltinESMExports();
  }
});
test('diagnostic logs rotate serially and remain bounded across a new instance', async (t) => {
  const root = await fixture(t);
  const log = new DiagnosticLog(root, 150, 2);
  await Promise.all(
    Array.from({ length: 12 }, () => log.write('command-failed', 'IO_ERROR')),
  );
  await new DiagnosticLog(root, 150, 2).write('application-start');
  const files = await readdir(root);
  assert.deepEqual(files.sort(), [
    'selector.log',
    'selector.log.1',
    'selector.log.2',
  ]);
  assert.match(
    await readFile(path.join(root, 'selector.log'), 'utf8'),
    /application-start/,
  );
});

test('diagnostic metadata keeps only bounded safe numeric fields', async (t) => {
  const root = await fixture(t);
  const log = new DiagnosticLog(root);
  await log.write('process-identity-check', 'NATIVE_CHECK_TIMEOUT', {
    attempt: 1,
    elapsedMs: 999999999,
    pid: 12345,
    path: 'secret.jpg',
    identity: 'secret',
  });
  await log.write('process-identity-check', 'NATIVE_CHECK_OK', {
    attempt: 99,
    elapsedMs: NaN,
  });
  const lines = (await readFile(path.join(root, 'selector.log'), 'utf8'))
    .trim()
    .split('\n')
    .map(JSON.parse);
  assert.equal(lines[0].attempt, 1);
  assert.equal(lines[0].elapsedMs, 86400000);
  assert.deepEqual(Object.keys(lines[0]).sort(), [
    'attempt',
    'code',
    'elapsedMs',
    'event',
    'time',
  ]);
  assert.deepEqual(Object.keys(lines[1]).sort(), ['code', 'event', 'time']);
});

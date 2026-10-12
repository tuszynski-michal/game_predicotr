import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { Readable } from 'node:stream';
import asar from '@electron/asar';
import { hashFile } from '../scripts/release-support.mjs';
import { verifyExtractedRelease } from '../scripts/verify-release.mjs';
const build = {
  sourceCommit: 'a'.repeat(40),
  dirty: false,
  applicationSourceDirty: false,
  builtAt: '2026-10-12T00:00:00.000Z',
};
async function fixture(t, mutate = async () => {}) {
  const base = path.resolve('.tmp');
  await mkdir(base, { recursive: true });
  const root = await mkdtemp(path.join(base, 'archive-test-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const source = path.join(root, 'source');
  const program = path.join(root, 'program');
  await mkdir(path.join(source, 'dist/renderer'), { recursive: true });
  await mkdir(path.join(program, 'resources'), { recursive: true });
  await writeFile(
    path.join(source, 'package.json'),
    JSON.stringify({
      name: '@game-predictor/selector-desktop',
      productName: 'Selektor zdjec',
      version: '0.1.3',
      main: 'dist/main.cjs',
    }),
  );
  await writeFile(
    path.join(source, 'dist/build-info.json'),
    JSON.stringify(build),
  );
  for (const file of [
    'main.cjs',
    'preload.cjs',
    'renderer/app.css',
    'renderer/app.js',
    'renderer/index.html',
  ])
    await writeFile(path.join(source, 'dist', file), 'fixture');
  await mutate(source, program);
  const archive = path.join(program, 'resources/app.asar');
  await asar.createPackage(source, archive);
  const metadata = {
    schemaVersion: 1,
    applicationName: 'Selektor zdjec',
    applicationVersion: '0.1.3',
    platform: 'win32',
    architecture: 'x64',
    ...build,
    appAsarSha256: await hashFile(archive),
  };
  return { program, metadata, archive };
}
test('real archive allows only the seven runtime files and exact provenance', async (t) => {
  const f = await fixture(t);
  assert.equal((await verifyExtractedRelease(f.program, f.metadata)).files, 7);
});
for (const extra of [
  'src/secret.ts',
  'node_modules/secret.js',
  'dist/extra.js',
])
  test(`archive rejects extra ${extra}`, async (t) => {
    const f = await fixture(t, async (source) => {
      await mkdir(path.dirname(path.join(source, extra)), { recursive: true });
      await writeFile(path.join(source, extra), 'unexpected');
    });
    await assert.rejects(
      verifyExtractedRelease(f.program, f.metadata),
      /contents/,
    );
  });
for (const [key, value] of [
  ['sourceCommit', 'b'.repeat(40)],
  ['dirty', true],
  ['applicationSourceDirty', true],
  ['builtAt', '2026-10-12T01:00:00.000Z'],
  ['applicationVersion', '0.1.2'],
  ['applicationName', 'Foreign'],
])
  test(`archive rejects metadata mismatch ${key}`, async (t) => {
    const f = await fixture(t);
    await assert.rejects(
      verifyExtractedRelease(f.program, { ...f.metadata, [key]: value }),
    );
  });
test('archive rejects invalid build fields, damaged bytes and unpacked sibling', async (t) => {
  const f = await fixture(t);
  for (const mutation of [
    { sourceCommit: 'bad' },
    { dirty: 'false' },
    { applicationSourceDirty: null },
    { builtAt: 'yesterday' },
  ])
    await assert.rejects(
      verifyExtractedRelease(f.program, { ...f.metadata, ...mutation }),
    );
  await mkdir(`${f.archive}.unpacked`);
  await assert.rejects(verifyExtractedRelease(f.program, f.metadata));
  await rm(`${f.archive}.unpacked`, { recursive: true });
  await writeFile(
    f.archive,
    Buffer.concat([await readFile(f.archive), Buffer.from('changed')]),
  );
  await assert.rejects(verifyExtractedRelease(f.program, f.metadata), /SHA/);
});
test('historical dirty docs provenance remains valid when archive proof agrees', async (t) => {
  const historical = { ...build, dirty: true };
  const f = await fixture(t, async (source) => {
    await writeFile(
      path.join(source, 'dist/build-info.json'),
      JSON.stringify(historical),
    );
    const manifest = JSON.parse(
      await readFile(path.join(source, 'package.json'), 'utf8'),
    );
    await writeFile(
      path.join(source, 'package.json'),
      JSON.stringify({ ...manifest, version: '0.1.0' }),
    );
  });
  await verifyExtractedRelease(f.program, {
    ...f.metadata,
    ...historical,
    applicationVersion: '0.1.0',
  });
});

for (const type of ['link', 'unpacked'])
  test(`archive rejects allowed filename with ${type} representation`, async (t) => {
    const f = await fixture(t);
    const entries = asar
      .listPackage(f.archive)
      .map((name) => name.replace(/^[/\\]/, ''));
    const streams = entries.map((name) => {
      const entry = asar.statFile(f.archive, name, false);
      if (entry.files)
        return { path: name, type: 'directory', unpacked: false };
      const bytes = asar.extractFile(f.archive, name);
      const special = name === path.normalize('dist/renderer/app.js');
      return {
        path: name,
        type: special && type === 'link' ? 'link' : 'file',
        symlink: special && type === 'link' ? '../main.cjs' : undefined,
        unpacked: special && type === 'unpacked',
        stat: { size: bytes.length, mode: 0o644 },
        streamGenerator: () => Readable.from(bytes),
      };
    });
    const alternate = path.join(path.dirname(f.archive), 'candidate.asar');
    await asar.createPackageFromStreams(alternate, streams);
    await writeFile(f.archive, await readFile(alternate));
    asar.uncache(f.archive);
    f.metadata.appAsarSha256 = await hashFile(f.archive);
    await assert.rejects(
      verifyExtractedRelease(f.program, f.metadata),
      /Linked or unpacked/,
    );
  });

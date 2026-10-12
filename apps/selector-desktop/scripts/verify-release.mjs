import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { lstat, stat } from 'node:fs/promises';
import path from 'node:path';
import asar from '@electron/asar';
import { hashFile } from './release-support.mjs';

const files = [
  'package.json',
  'dist/main.cjs',
  'dist/preload.cjs',
  'dist/build-info.json',
  'dist/renderer/app.css',
  'dist/renderer/app.js',
  'dist/renderer/index.html',
];
const directories = ['dist', 'dist/renderer'];
const applicationPackageName = '@game-predictor/selector-desktop';
function validBuild(build) {
  assert.match(build.sourceCommit, /^[a-f0-9]{40}$/);
  assert.equal(typeof build.dirty, 'boolean');
  assert.equal(typeof build.applicationSourceDirty, 'boolean');
  assert.equal(typeof build.builtAt, 'string');
  assert.equal(new Date(build.builtAt).toISOString(), build.builtAt);
}

/** Validate the archive actually extracted from the selected ZIP, not loose dist. */
export async function verifyExtractedRelease(program, metadata) {
  assert.equal(metadata.schemaVersion, 1);
  assert.equal(metadata.platform, 'win32');
  assert.equal(metadata.architecture, 'x64');
  validBuild(metadata);
  const resources = path.join(program, 'resources');
  for (const directory of [program, resources]) {
    const info = await lstat(directory);
    assert.ok(
      info.isDirectory() && !info.isSymbolicLink(),
      'Release directory must be ordinary',
    );
  }
  const archive = path.join(resources, 'app.asar');
  const info = await lstat(archive);
  assert.ok(
    info.isFile() && !info.isSymbolicLink(),
    'app.asar must be an ordinary file',
  );
  assert.match(metadata.appAsarSha256, /^[a-f0-9]{64}$/);
  assert.equal(
    await hashFile(archive),
    metadata.appAsarSha256,
    'Extracted app.asar SHA mismatch',
  );
  await assert.rejects(lstat(`${archive}.unpacked`), { code: 'ENOENT' });
  const entries = asar
    .listPackage(archive)
    .map((name) => name.replace(/^[/\\]/, '').replaceAll('\\', '/'));
  assert.deepEqual(
    [...entries].sort(),
    [...files, ...directories].sort(),
    'Unexpected or missing app.asar contents',
  );
  for (const name of entries) {
    const entry = asar.statFile(archive, path.normalize(name), false);
    assert.ok(
      !('link' in entry) && !entry.unpacked,
      'Linked or unpacked archive entry',
    );
    if (directories.includes(name))
      assert.ok(entry.files, 'Expected archive directory');
    else
      assert.ok(
        !entry.files && Number.isSafeInteger(entry.size),
        'Expected archive file',
      );
  }
  const json = (name) =>
    JSON.parse(
      asar.extractFile(archive, path.normalize(name)).toString('utf8'),
    );
  const manifest = json('package.json');
  assert.equal(manifest.name, applicationPackageName);
  assert.equal(manifest.version, metadata.applicationVersion);
  assert.equal(manifest.productName, metadata.applicationName);
  assert.equal(manifest.main, 'dist/main.cjs');
  const build = json('dist/build-info.json');
  validBuild(build);
  for (const key of [
    'sourceCommit',
    'dirty',
    'applicationSourceDirty',
    'builtAt',
  ])
    assert.equal(
      build[key],
      metadata[key],
      `Archive build provenance mismatch: ${key}`,
    );
  return {
    files: files.length,
    sourceCommit: build.sourceCommit,
    applicationVersion: manifest.version,
  };
}

/** Destination must be absent: every verification reads a freshly extracted ZIP. */
export async function extractAndVerifyRelease(archive, program, metadata) {
  assert.equal(path.basename(archive), metadata.archiveName);
  assert.equal((await stat(archive)).size, metadata.bytes);
  assert.equal(await hashFile(archive), metadata.sha256, 'ZIP SHA mismatch');
  await assert.rejects(lstat(program), { code: 'ENOENT' });
  execFileSync(
    'powershell.exe',
    [
      '-NoProfile',
      '-NonInteractive',
      '-Command',
      'Expand-Archive -LiteralPath $env:SELECTOR_ARCHIVE -DestinationPath $env:SELECTOR_PROGRAM -ErrorAction Stop',
    ],
    {
      env: {
        ...process.env,
        SELECTOR_ARCHIVE: archive,
        SELECTOR_PROGRAM: program,
      },
      timeout: 30000,
      windowsHide: true,
    },
  );
  return verifyExtractedRelease(program, metadata);
}

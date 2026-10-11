import { execFileSync } from 'node:child_process';
import { mkdir, mkdtemp, readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { hashFile, removeOwnedTemp } from './release-support.mjs';

const manifest = JSON.parse(await readFile('package.json', 'utf8'));
const archiveName = `${manifest.productName}-win32-x64-${manifest.version}.zip`;
const archive = path.resolve('out/make/zip/win32/x64', archiveName);
const metadata = JSON.parse(await readFile(`${archive}.release.json`, 'utf8'));
assert.equal(metadata.archiveName, archiveName);
assert.equal(metadata.applicationVersion, manifest.version);
assert.equal(metadata.bytes, (await stat(archive)).size);
assert.equal(metadata.sha256, await hashFile(archive));
assert.equal(
  await readFile(`${archive}.sha256`, 'utf8'),
  `${metadata.sha256}  ${archiveName}\n`,
);
console.log('PASS: ZIP bytes and SHA-256 verified.');
const tempRoot = path.resolve('.tmp');
await mkdir(tempRoot, { recursive: true });
const fixture = await mkdtemp(path.join(tempRoot, 'release-smoke-'));
try {
  const program = path.join(fixture, 'program-original');
  // Environment variables avoid shell interpolation of Windows paths.
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
  assert.equal(
    await hashFile(path.join(program, 'resources/app.asar')),
    metadata.appAsarSha256,
  );
  console.log('PASS: ZIP extracted; app.asar SHA-256 verified.');
  execFileSync(
    process.execPath,
    [
      'scripts/run-bounded.mjs',
      process.argv.includes('--shortcuts') ? '60' : '110',
      'node',
      process.argv.includes('--shortcuts')
        ? 'scripts/smoke-shortcuts.mjs'
        : 'scripts/smoke-packaged.mjs',
      path.join(program, 'Selektor-zdjec.exe'),
      '--relocate-program',
      `--release-metadata=${archive}.release.json`,
    ],
    {
      stdio: 'inherit',
      timeout: 115000,
      windowsHide: true,
    },
  );
  console.log(
    process.argv.includes('--shortcuts')
      ? 'PASS: verified final ZIP, extracted EXE and shortcut/source-relink checks.'
      : 'PASS: verified final ZIP, extracted EXE, offline workflow, process restart, backup/restore and changed program location. Same-version update simulation; physical reboot/recipient acceptance pending.',
  );
} finally {
  await removeOwnedTemp(fixture, tempRoot);
}

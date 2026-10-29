import { execFileSync } from 'node:child_process';
import { mkdir, mkdtemp, readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {
  hashFile,
  createOwnedSmoke,
  runSmokeChild,
} from './release-support.mjs';
import { verifyExtractedRelease } from './verify-release.mjs';

const tempRoot = path.resolve('.tmp');
await mkdir(tempRoot, { recursive: true });
const fixture = await mkdtemp(path.join(tempRoot, 'release-smoke-'));
const smoke = createOwnedSmoke({ name: 'smoke-release', fixture, tempRoot });
try {
  const manifest = JSON.parse(await readFile('package.json', 'utf8'));
  const options = [
    '--shortcuts',
    '--legacy',
    '--ux',
    '--start',
    '--workflow',
    '--games',
    '--fluency',
    '--measurement',
  ].filter((flag) => process.argv.includes(flag));
  if (options.length > 1)
    throw new Error('Choose only one release smoke variant');
  const variant = options[0] ?? '--full';
  const scripts = {
    '--full': 'smoke-packaged.mjs',
    '--shortcuts': 'smoke-shortcuts.mjs',
    '--legacy': 'smoke-legacy.mjs',
    '--ux': 'smoke-ux.mjs',
    '--start': 'smoke-start.mjs',
    '--workflow': 'smoke-workflow.mjs',
    '--games': 'smoke-games.mjs',
    '--fluency': 'smoke-fluency.mjs',
    '--measurement': 'smoke-measurement.mjs',
  };
  const archiveName = `${manifest.productName}-win32-x64-${manifest.version}.zip`;
  const archive = path.resolve('out/make/zip/win32/x64', archiveName);
  const metadata = JSON.parse(
    await readFile(`${archive}.release.json`, 'utf8'),
  );
  assert.equal(metadata.archiveName, archiveName);
  assert.equal(metadata.applicationVersion, manifest.version);
  assert.equal(metadata.bytes, (await stat(archive)).size);
  assert.equal(metadata.sha256, await hashFile(archive));
  assert.equal(
    await readFile(`${archive}.sha256`, 'utf8'),
    `${metadata.sha256}  ${archiveName}\n`,
  );
  console.log('PASS: ZIP bytes and SHA-256 verified.');

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
  await verifyExtractedRelease(program, metadata);
  console.log('PASS: ZIP extracted; app.asar SHA-256 and contents verified.');
  await runSmokeChild(
    `scripts/${scripts[variant]}`,
    [
      path.join(program, 'Selektor-zdjec.exe'),
      '--relocate-program',
      `--release-metadata=${archive}.release.json`,
    ],
    {
      seconds: variant === '--shortcuts' ? 60 : 100,
      env: {
        ...process.env,
        SELECTOR_SMOKE_RUN: smoke.result.run,
        SELECTOR_SMOKE_DIAGNOSTICS_ROOT: path.resolve(
          '../../artifacts/selector-smoke-diagnostics',
        ),
      },
    },
  );
  console.log(
    variant !== '--full'
      ? `PASS: verified final ZIP, extracted EXE and ${variant.slice(2)} checks.`
      : 'PASS: verified final ZIP, extracted EXE, offline workflow, process restart, backup/restore and changed program location. Same-version update simulation; physical reboot/recipient acceptance pending.',
  );
  smoke.result.succeeded = true;
} catch (error) {
  smoke.result.error = error;
} finally {
  await smoke.finish();
}

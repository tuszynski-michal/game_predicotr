import { execFileSync } from 'node:child_process';
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import {
  hashFile,
  requireFreshArchive,
  removeOwnedTemp,
} from './release-support.mjs';
import { extractAndVerifyRelease } from './verify-release.mjs';

const manifest = JSON.parse(await readFile('package.json', 'utf8'));
const makeStartedAt = Date.now();
execFileSync(
  process.execPath,
  ['scripts/run-bounded.mjs', '280', 'npm', 'run', 'make'],
  {
    stdio: 'inherit',
    timeout: 285000,
    windowsHide: true,
  },
);
const archiveName = `${manifest.productName}-win32-x64-${manifest.version}.zip`;
const archive = path.resolve('out/make/zip/win32/x64', archiveName);
const bytes = await requireFreshArchive(archive, makeStartedAt);
const build = JSON.parse(await readFile('dist/build-info.json', 'utf8'));
const sha256 = await hashFile(archive);
const appAsarSha256 = await hashFile(
  path.resolve(
    'out',
    `${manifest.productName}-win32-x64`,
    'resources/app.asar',
  ),
);
const metadata = {
  schemaVersion: 1,
  applicationName: manifest.productName,
  applicationVersion: manifest.version,
  platform: 'win32',
  architecture: 'x64',
  archiveName,
  bytes,
  sha256,
  appAsarSha256,
  ...build,
  releasedAt: new Date().toISOString(),
  byteIdenticalRebuildGuaranteed: false,
};
const tempRoot = path.resolve('.tmp');
await mkdir(tempRoot, { recursive: true });
const verification = await mkdtemp(path.join(tempRoot, 'release-verify-'));
try {
  await extractAndVerifyRelease(
    archive,
    path.join(verification, 'program'),
    metadata,
  );
} finally {
  await removeOwnedTemp(verification, tempRoot);
}
await writeFile(`${archive}.sha256`, `${sha256}  ${archiveName}\n`, 'utf8');
await writeFile(
  `${archive}.release.json`,
  `${JSON.stringify(metadata, null, 2)}\n`,
  'utf8',
);
console.log(JSON.stringify({ archive, ...metadata }, null, 2));

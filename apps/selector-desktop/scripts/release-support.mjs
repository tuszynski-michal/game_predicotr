import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { lstat, realpath, rm, stat } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

export async function hashFile(file) {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}

export function gitBuildInfo(root) {
  const git = (...args) =>
    execFileSync('git', args, {
      cwd: root,
      encoding: 'utf8',
      timeout: 10000,
      windowsHide: true,
    }).trim();
  const sourceCommit = git('rev-parse', 'HEAD');
  if (!/^[a-f0-9]{40}$/.test(sourceCommit))
    throw new Error('Invalid Git commit');
  return {
    sourceCommit,
    dirty: git('status', '--porcelain', '--untracked-files=normal') !== '',
    applicationSourceDirty:
      git(
        'status',
        '--porcelain',
        '--untracked-files=normal',
        '--',
        'apps/selector-desktop',
        'packages/manual-image-selection-core',
        'package.json',
        'package-lock.json',
      ) !== '',
    builtAt: new Date().toISOString(),
  };
}

export async function requireFreshArchive(file, makeStartedAt) {
  const details = await stat(file);
  if (
    !details.isFile() ||
    details.size === 0 ||
    details.mtimeMs < makeStartedAt
  )
    throw new Error('Forge did not produce a fresh nonempty ZIP');
  return details.size;
}

export async function removeOwnedTemp(directory, tempRoot) {
  if ((await lstat(tempRoot)).isSymbolicLink())
    throw new Error('Cleanup temporary root must not be a link');
  const root = await realpath(tempRoot);
  const target = path.resolve(directory);
  if (path.dirname(target) !== path.resolve(tempRoot))
    throw new Error(
      'Cleanup requires a direct child of the owned temporary root',
    );
  const details = await lstat(target);
  if (!details.isDirectory() || details.isSymbolicLink())
    throw new Error('Cleanup target is not an owned ordinary directory');
  const actual = await realpath(target);
  if (path.dirname(actual) !== root)
    throw new Error('Cleanup target escapes the owned temporary root');
  await rm(actual, {
    recursive: true,
    force: true,
    maxRetries: 10,
    retryDelay: 200,
  });
}

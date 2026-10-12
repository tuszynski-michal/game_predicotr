import { lstat, realpath } from 'node:fs/promises';
import path from 'node:path';
import { SelectorError } from '../contracts.ts';
import { nativeChecks } from './windows-check-worker.ts';

export function containedPath(root: string, relative: string): string {
  if (
    !relative ||
    relative.includes('\\') ||
    relative.includes(':') ||
    relative.includes('\0') ||
    relative.split('/').some((p) => p === '..' || p === '.' || !p)
  ) {
    throw new SelectorError('UNSAFE_PATH', 'Niedozwolona ścieżka względna.');
  }
  const candidate = path.resolve(root, relative);
  const delta = path.relative(root, candidate);
  if (
    !delta ||
    delta.startsWith(`..${path.sep}`) ||
    delta === '..' ||
    path.isAbsolute(delta)
  )
    throw new SelectorError(
      'OUTSIDE_ROOT',
      'Ścieżka poza wybranym katalogiem.',
    );
  return candidate;
}
// Node lstat marks Windows junctions and symbolic reparse links as symbolic links.
// Check every ancestor, including the selected root, before trusting realpath.
export async function assertWindowsReparse(
  paths: string[],
  recursive = false,
): Promise<void> {
  if (process.platform !== 'win32') return;
  try {
    await nativeChecks().reparseScan(paths, recursive);
  } catch (error) {
    const code = (error as SelectorError).code;
    throw new SelectorError(
      code === 'REPARSE_POINT'
        ? code
        : code === 'NATIVE_CHECK_TIMEOUT'
          ? 'ATTRIBUTE_SCAN_TIMEOUT'
          : 'ATTRIBUTE_SCAN_FAILED',
      code === 'REPARSE_POINT'
        ? 'Punkty ponownej analizy nie są obsługiwane.'
        : 'Nie można sprawdzić atrybutów katalogu.',
    );
  }
}
export async function assertNoLinks(
  absolute: string,
  windowsAttributes = true,
): Promise<void> {
  const resolved = path.resolve(absolute);
  const parts = resolved
    .slice(path.parse(resolved).root.length)
    .split(path.sep)
    .filter(Boolean);
  let current = path.parse(resolved).root;
  const checked: string[] = [];
  for (const part of parts) {
    current = path.join(current, part);
    checked.push(current);
    if ((await lstat(current)).isSymbolicLink())
      throw new SelectorError(
        'REPARSE_POINT',
        'Dowiązania i punkty ponownej analizy nie są obsługiwane.',
      );
  }
  if (windowsAttributes) await assertWindowsReparse(checked);
}
export async function safeExistingPath(
  root: string,
  relative: string,
  windowsAttributes = true,
): Promise<string> {
  const candidate = containedPath(root, relative);
  await assertNoLinks(candidate, windowsAttributes);
  const [actualRoot, actualFile] = await Promise.all([
    realpath(root),
    realpath(candidate),
  ]);
  const delta = path.relative(actualRoot, actualFile);
  if (
    !delta ||
    delta === '..' ||
    delta.startsWith(`..${path.sep}`) ||
    path.isAbsolute(delta)
  )
    throw new SelectorError('OUTSIDE_ROOT', 'Plik poza wybranym katalogiem.');
  return actualFile;
}

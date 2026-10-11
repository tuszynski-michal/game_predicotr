import { lstat, realpath } from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { SelectorError } from '../contracts.ts';

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
  // One native attribute scan for the entire index, never one process per JPEG.
  // Paths travel as stdin JSON, never interpolated into executable code.
  const script = `$ErrorActionPreference='Stop'; try { $data=[Console]::In.ReadToEnd() | ConvertFrom-Json; foreach($p in $data.paths) { $item=Get-Item -LiteralPath $p -Force; if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { exit 42 }; if($data.recursive) { Get-ChildItem -LiteralPath $p -Recurse -Force | ForEach-Object { if(($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { exit 42 } } } }; exit 0 } catch { exit 43 }`;
  await new Promise<void>((resolve, reject) => {
    const child = spawn(
      'powershell.exe',
      [
        '-NoProfile',
        '-NonInteractive',
        '-EncodedCommand',
        Buffer.from(script, 'utf16le').toString('base64'),
      ],
      { windowsHide: true, stdio: ['pipe', 'ignore', 'ignore'] },
    );
    const timer = setTimeout(() => {
      child.kill();
      reject(
        new SelectorError(
          'ATTRIBUTE_SCAN_TIMEOUT',
          'Sprawdzenie katalogu przekroczyło limit czasu.',
        ),
      );
    }, 30000);
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code === 0) resolve();
      else
        reject(
          new SelectorError(
            code === 42 ? 'REPARSE_POINT' : 'ATTRIBUTE_SCAN_FAILED',
            code === 42
              ? 'Punkty ponownej analizy nie są obsługiwane.'
              : 'Nie można sprawdzić atrybutów katalogu.',
          ),
        );
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify({ paths, recursive }));
  });
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

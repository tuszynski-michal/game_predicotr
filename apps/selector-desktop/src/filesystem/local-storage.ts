import path from 'node:path';
import { spawn } from 'node:child_process';
import { SelectorError } from '../contracts.ts';

export async function powershellJson(
  script: string,
  input: unknown,
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const child = spawn(
      'powershell.exe',
      [
        '-NoProfile',
        '-NonInteractive',
        '-EncodedCommand',
        Buffer.from(script, 'utf16le').toString('base64'),
      ],
      { windowsHide: true, stdio: ['pipe', 'pipe', 'ignore'] },
    );
    let output = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(
        new SelectorError(
          'NATIVE_CHECK_TIMEOUT',
          'Sprawdzenie systemu przekroczyło limit czasu.',
        ),
      );
    }, 10000);
    child.stdout.on('data', (chunk) => {
      output += chunk.toString();
      if (output.length > 16384) {
        child.kill();
        reject(
          new SelectorError(
            'NATIVE_CHECK_FAILED',
            'Nieprawidłowa odpowiedź systemu.',
          ),
        );
      }
    });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(
          new SelectorError(
            'NATIVE_CHECK_FAILED',
            'Nie można potwierdzić tożsamości procesu lub dysku.',
          ),
        );
        return;
      }
      try {
        resolve(JSON.parse(output.replace(/^\uFEFF/, '')));
      } catch {
        reject(
          new SelectorError(
            'NATIVE_CHECK_FAILED',
            'Nieprawidłowa odpowiedź systemu.',
          ),
        );
      }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify(input));
  });
}
export async function assertLocalStorage(
  directory: string,
  confirmed: boolean,
): Promise<void> {
  if (!confirmed)
    throw new SelectorError(
      'LOCAL_STORAGE_CONFIRMATION_REQUIRED',
      'Potwierdź lokalny dysk i katalog poza synchronizacją.',
    );
  const resolved = path.resolve(directory);
  if (/^(\\\\|\/\/)/.test(directory))
    throw new SelectorError(
      'NETWORK_STORAGE',
      'Projekt i wynik wymagają lokalnego dysku.',
    );
  const knownRoots = [
    process.env.OneDrive,
    process.env.OneDriveConsumer,
    process.env.OneDriveCommercial,
    process.env.Dropbox,
    process.env.ProtonDrive,
  ].filter((value): value is string => Boolean(value));
  if (
    /(^|[\\/])(OneDrive(?: - [^\\/]+)?|Dropbox|Proton Drive|ProtonDrive|Google Drive)([\\/]|$)/i.test(
      resolved,
    ) ||
    knownRoots.some((root) => {
      const delta = path.relative(
        path.resolve(root).toLowerCase(),
        resolved.toLowerCase(),
      );
      return !delta || (!delta.startsWith('..') && !path.isAbsolute(delta));
    })
  )
    throw new SelectorError(
      'SYNC_STORAGE',
      'Projekt i aktywny wynik muszą być poza synchronizacją.',
    );
  if (process.platform !== 'win32') return;
  const root = path.parse(resolved).root;
  const result = (await powershellJson(
    "$ErrorActionPreference='Stop'; try { $d=[Console]::In.ReadToEnd() | ConvertFrom-Json; $drive=New-Object IO.DriveInfo($d.root); @{type=[int]$drive.DriveType; ready=$drive.IsReady} | ConvertTo-Json -Compress } catch { exit 1 }",
    { root },
  )) as { type: number; ready: boolean };
  if (result.type !== 3 || result.ready !== true)
    throw new SelectorError(
      'NETWORK_STORAGE',
      'Projekt i wynik wymagają gotowego lokalnego dysku stałego.',
    );
}

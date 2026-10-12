import path from 'node:path';
import { nativeChecks } from '../native/windows-check-worker.ts';
import { SelectorError } from '../contracts.ts';

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
  const result = await nativeChecks().driveInfo(root);
  if (result.type === 2)
    throw new SelectorError(
      'REMOVABLE_STORAGE',
      'Projekt i wynik nie obsługują dysków wymiennych. Wybierz lokalny dysk stały.',
    );
  if (result.type !== 3 || result.ready !== true)
    throw new SelectorError(
      'NETWORK_STORAGE',
      'Projekt i wynik wymagają gotowego lokalnego dysku stałego.',
    );
}

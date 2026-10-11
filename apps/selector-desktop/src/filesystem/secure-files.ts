import { createHash, randomUUID } from 'node:crypto';
import {
  open,
  lstat,
  readdir,
  rename,
  unlink,
  realpath,
  mkdir,
} from 'node:fs/promises';
import path from 'node:path';
import { SelectorError } from '../contracts.ts';
import {
  assertNoLinks,
  assertWindowsReparse,
  containedPath,
} from '../native/path-security.ts';

export type WriteCheckpoint = (phase: string) => void | Promise<void>;
export const noCheckpoint: WriteCheckpoint = () => {};
export function checksum(value: string | Uint8Array): string {
  return createHash('sha256').update(value).digest('hex');
}
export function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}
export function isMissing(error: unknown): boolean {
  return (error as NodeJS.ErrnoException)?.code === 'ENOENT';
}
export function ioError(error: unknown, phase: string): SelectorError {
  if (error instanceof SelectorError) return error;
  const code = (error as NodeJS.ErrnoException)?.code;
  return new SelectorError(
    code === 'ENOSPC'
      ? 'DISK_FULL'
      : code === 'EACCES' || code === 'EPERM'
        ? 'WRITE_DENIED'
        : 'WRITE_FAILED',
    `Zapis zatrzymany (${phase}). Zachowano dziennik. Wznów projekt po usunięciu przyczyny.`,
  );
}
export function assertSeparateRoots(roots: string[]): void {
  for (let i = 0; i < roots.length; i++)
    for (let j = i + 1; j < roots.length; j++) {
      const a = path.resolve(roots[i]).toLocaleLowerCase('en-US');
      const b = path.resolve(roots[j]).toLocaleLowerCase('en-US');
      const delta = path.relative(a, b);
      const reverse = path.relative(b, a);
      const contains = (s: string) =>
        !s ||
        (!s.startsWith(`..${path.sep}`) && s !== '..' && !path.isAbsolute(s));
      if (contains(delta) || contains(reverse))
        throw new SelectorError(
          'OVERLAPPING_ROOTS',
          'Źródło, projekt i wynik muszą być oddzielnymi katalogami.',
        );
    }
}
export async function ensureDirectory(directory: string): Promise<string> {
  // Only one missing leaf may be created. Its parent must already be trusted.
  try {
    await assertNoLinks(directory);
  } catch (error) {
    if (!isMissing(error)) throw error;
    await assertNoLinks(path.dirname(directory));
    try {
      await mkdir(directory);
    } catch (cause) {
      if ((cause as NodeJS.ErrnoException).code !== 'EEXIST') throw cause;
    }
    await assertNoLinks(directory);
  }
  if (!(await lstat(directory)).isDirectory())
    throw new SelectorError(
      'NOT_DIRECTORY',
      'Wybierz katalog projektu lub wyniku.',
    );
  return realpath(directory);
}

export async function canonicalDirectoryLocation(
  directory: string,
): Promise<string> {
  try {
    // This step only resolves aliases; ensureDirectory/verifyRoot perform the
    // native reparse scan before any actual creation or filesystem mutation.
    await assertNoLinks(directory, false);
    return await realpath(directory);
  } catch (error) {
    if (!isMissing(error)) throw error;
    await assertNoLinks(path.dirname(directory), false);
    return path.join(
      await realpath(path.dirname(directory)),
      path.basename(directory),
    );
  }
}
/** A transaction scans native attributes once; every access still checks all ancestors.
 * Exclusive opens and identity checks prevent following an existing leaf link.
 * These checks do not claim protection against a privileged concurrent filesystem attacker.
 */
export class SecureFiles {
  readonly root: string;
  constructor(root: string) {
    this.root = path.resolve(root);
  }
  async verifyRoot(): Promise<void> {
    await assertNoLinks(this.root, false);
    await assertWindowsReparse([this.root], true);
    if (!(await lstat(this.root)).isDirectory())
      throw new SelectorError('NOT_DIRECTORY', 'Katalog nie jest dostępny.');
  }
  async target(name: string): Promise<string> {
    const target = containedPath(this.root, name);
    // Check missing leaves without allowing a missing parent or linked ancestor.
    await assertNoLinks(path.dirname(target), false);
    try {
      await assertNoLinks(target, false);
      if (!(await lstat(target)).isFile())
        throw new SelectorError(
          'FOREIGN_CONTENT',
          'Zarządzana ścieżka nie jest zwykłym plikiem.',
        );
    } catch (error) {
      if (!isMissing(error)) throw error;
    }
    return target;
  }
  async read(name: string): Promise<Buffer | null> {
    const target = await this.target(name);
    let handle;
    try {
      handle = await open(target, 'r');
    } catch (error) {
      if (isMissing(error)) return null;
      throw error;
    }
    try {
      const [opened, current] = await Promise.all([
        handle.stat(),
        lstat(target),
      ]);
      await this.target(name);
      if (
        !opened.isFile() ||
        opened.dev !== current.dev ||
        opened.ino !== current.ino
      )
        throw new SelectorError(
          'PATH_CHANGED',
          'Plik zmienił tożsamość podczas odczytu.',
        );
      return await handle.readFile();
    } finally {
      await handle.close();
    }
  }
  async hash(name: string): Promise<string | null> {
    const target = await this.target(name);
    let handle;
    try {
      handle = await open(target, 'r');
    } catch (error) {
      if (isMissing(error)) return null;
      throw error;
    }
    try {
      const before = await handle.stat();
      const hash = createHash('sha256');
      for await (const chunk of handle.createReadStream({ autoClose: false }))
        hash.update(chunk);
      await this.target(name);
      const [after, current] = await Promise.all([
        handle.stat(),
        lstat(target),
      ]);
      if (
        !before.isFile() ||
        before.dev !== current.dev ||
        before.ino !== current.ino ||
        before.size !== after.size ||
        before.mtimeMs !== after.mtimeMs
      )
        throw new SelectorError(
          'PATH_CHANGED',
          'Plik zmienił tożsamość podczas sprawdzania.',
        );
      return hash.digest('hex');
    } finally {
      await handle.close();
    }
  }
  async names(verified = false): Promise<string[]> {
    if (!verified) await this.verifyRoot();
    return readdir(this.root);
  }
  async syncDirectory(): Promise<void> {
    // Windows cannot fsync a directory through Node. File fsync + same-directory
    // rename are the tested process-crash guarantee, not a power-loss guarantee.
    if (process.platform === 'win32') return;
    const handle = await open(this.root, 'r');
    try {
      await handle.sync();
    } finally {
      await handle.close();
    }
  }
  async clearScratch(name: string): Promise<void> {
    try {
      await unlink(await this.target(name));
    } catch (error) {
      if (!isMissing(error)) throw error;
    }
  }
  async replace(
    name: string,
    bytes: string | Uint8Array,
    checkpoint: WriteCheckpoint = noCheckpoint,
    scratchName?: string,
  ): Promise<void> {
    const temporary = scratchName ?? `.selector-${randomUUID()}.tmp`;
    const temporaryPath = await this.target(temporary);
    const handle = await open(temporaryPath, 'wx');
    try {
      try {
        await checkpoint(`${name}:temp`);
        await handle.writeFile(bytes);
        await checkpoint(`${name}:sync`);
        await handle.sync();
      } finally {
        await handle.close();
      }
      await checkpoint(`${name}:replace`);
      await this.target(temporary);
      await rename(temporaryPath, await this.target(name));
      await this.syncDirectory();
    } catch (error) {
      // In-process failures clean only this exclusively created temporary file.
      // A killed process leaves it; project-root validation permits these inert
      // scratch files, output-root validation admits only the journal's exact temp.
      await unlink(temporaryPath).catch(() => {});
      throw error;
    }
  }
  async removeOwned(name: string, expectedHash: string): Promise<void> {
    const actual = await this.hash(name);
    if (actual === null) return;
    if (actual !== expectedHash)
      throw new SelectorError(
        'OUTPUT_CHECKSUM_CONFLICT',
        'Plik wynikowy ma inną sumę kontrolną. Nie został usunięty.',
      );
    await unlink(await this.target(name));
    await this.syncDirectory();
  }
}

import { randomUUID } from 'node:crypto';
import { hostname } from 'node:os';
import { open, unlink } from 'node:fs/promises';
import { SelectorError } from '../contracts.ts';
import { SecureFiles, stableStringify } from '../filesystem/secure-files.ts';
import { nativeChecks } from '../native/windows-check-worker.ts';

export const PROJECT_LOCK_NAME = 'selector-project.lock';
const RECOVERY_LOCK_NAME = 'selector-project-lock-recovery.lock';
export interface LockOwner {
  schemaVersion: 1;
  ownerId: string;
  host: string;
  pid: number;
  processIdentity: string;
  createdAt: string;
}
export interface ProcessInspector {
  host: string;
  pid: number;
  identity(pid: number): Promise<string | null>;
}
export const nativeProcesses: ProcessInspector = {
  host: hostname(),
  pid: process.pid,
  async identity(pid) {
    if (process.platform === 'win32') {
      return nativeChecks().processIdentity(pid);
    }
    // Linux tests use the OS start tick; an inaccessible process is unknown.
    const { readFile } = await import('node:fs/promises');
    try {
      const stat = await readFile(`/proc/${pid}/stat`, 'utf8');
      return stat.slice(stat.lastIndexOf(')') + 2).split(' ')[19];
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null;
      throw error;
    }
  },
};
function parseOwner(bytes: Buffer): LockOwner {
  let owner: LockOwner;
  try {
    owner = JSON.parse(bytes.toString());
  } catch {
    throw new SelectorError(
      'LOCK_OWNER_UNKNOWN',
      'Nie można ustalić właściciela blokady.',
    );
  }
  if (
    owner.schemaVersion !== 1 ||
    typeof owner.ownerId !== 'string' ||
    !owner.ownerId ||
    typeof owner.host !== 'string' ||
    !owner.host ||
    !Number.isSafeInteger(owner.pid) ||
    owner.pid < 1 ||
    typeof owner.processIdentity !== 'string' ||
    !owner.processIdentity
  )
    throw new SelectorError(
      'LOCK_OWNER_UNKNOWN',
      'Nie można ustalić właściciela blokady.',
    );
  return owner;
}
export class ProjectLock {
  private files: SecureFiles;
  readonly owner: LockOwner;
  private constructor(files: SecureFiles, owner: LockOwner) {
    this.files = files;
    this.owner = owner;
  }
  static async acquire(
    files: SecureFiles,
    inspector: ProcessInspector = nativeProcesses,
    rootVerified = false,
  ): Promise<ProjectLock> {
    if (!rootVerified) await files.verifyRoot();
    if (await files.read(RECOVERY_LOCK_NAME))
      throw new SelectorError(
        'LOCK_OWNER_UNKNOWN',
        'Nieznana blokada odzyskiwania. Nie została usunięta ani przejęta; wymaga diagnostyki operatora.',
      );
    const identity = await inspector.identity(inspector.pid);
    if (!identity)
      throw new SelectorError(
        'LOCK_OWNER_UNKNOWN',
        'Nie można potwierdzić tożsamości procesu.',
      );
    const owner: LockOwner = {
      schemaVersion: 1,
      ownerId: randomUUID(),
      host: inspector.host,
      pid: inspector.pid,
      processIdentity: identity,
      createdAt: new Date().toISOString(),
    };
    const acquire = async () => {
      const handle = await open(await files.target(PROJECT_LOCK_NAME), 'wx');
      try {
        await handle.writeFile(stableStringify(owner));
        await handle.sync();
      } finally {
        await handle.close();
      }
      await files.syncDirectory();
      return new ProjectLock(files, owner);
    };
    try {
      return await acquire();
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error;
    }
    const existing = parseOwner((await files.read(PROJECT_LOCK_NAME))!);
    if (existing.host !== inspector.host)
      throw new SelectorError(
        'LOCK_OWNER_UNKNOWN',
        'Blokada należy do innego hosta. Nie została przejęta.',
      );
    let currentIdentity: string | null;
    try {
      currentIdentity = await inspector.identity(existing.pid);
    } catch {
      throw new SelectorError(
        'LOCK_OWNER_UNKNOWN',
        'Nie można potwierdzić zakończenia procesu właściciela.',
      );
    }
    if (currentIdentity === existing.processIdentity)
      throw new SelectorError(
        'PROJECT_LOCKED',
        'Projekt jest otwarty w innym procesie.',
      );
    // Serialize reclamation; re-read the owner under the recovery claim. No
    // heartbeat age or timeout is used as evidence that a process died.
    let recovery;
    try {
      recovery = await open(await files.target(RECOVERY_LOCK_NAME), 'wx');
    } catch {
      throw new SelectorError(
        'LOCK_OWNER_UNKNOWN',
        'Nieznana blokada odzyskiwania. Nie została usunięta ani przejęta; wymaga diagnostyki operatora.',
      );
    }
    try {
      const latest = await files.read(PROJECT_LOCK_NAME);
      if (!latest || parseOwner(latest).ownerId !== existing.ownerId)
        throw new SelectorError(
          'PROJECT_LOCKED',
          'Właściciel blokady zmienił się.',
        );
      await unlink(await files.target(PROJECT_LOCK_NAME));
      try {
        return await acquire();
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'EEXIST')
          throw new SelectorError(
            'PROJECT_LOCKED',
            'Projekt przejął inny proces.',
          );
        throw error;
      }
    } finally {
      await recovery.close();
      await unlink(await files.target(RECOVERY_LOCK_NAME));
    }
  }
  async assertOwned(): Promise<void> {
    const bytes = await this.files.read(PROJECT_LOCK_NAME);
    if (!bytes || parseOwner(bytes).ownerId !== this.owner.ownerId)
      throw new SelectorError(
        'LOCK_LOST',
        'Utracono wyłączną blokadę projektu.',
      );
  }
  async release(): Promise<void> {
    await this.assertOwned();
    await unlink(await this.files.target(PROJECT_LOCK_NAME));
    await this.files.syncDirectory();
  }
}

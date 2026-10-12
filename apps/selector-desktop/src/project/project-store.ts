import { randomUUID, createHash } from 'node:crypto';
import { open, rename, lstat } from 'node:fs/promises';
import path from 'node:path';
import {
  buildRemoteSourceManifestV1,
  rangeForStart,
  nextManualRangeStart,
  isManualSelectionRangeTerminal,
} from '@game-predictor/manual-image-selection-core';
import { SelectorError } from '../contracts.ts';
import {
  scanSource,
  type VerifiedSourceScan,
} from '../native/source-registry.ts';
import { safeExistingPath } from '../native/path-security.ts';
import {
  SecureFiles,
  checksum,
  stableStringify,
  isMissing,
  ioError,
  ensureDirectory,
  canonicalDirectoryLocation,
  assertSeparateRoots,
  noCheckpoint,
  type WriteCheckpoint,
} from '../filesystem/secure-files.ts';
import { assertLocalStorage } from '../filesystem/local-storage.ts';
import {
  OUTPUT_MANIFEST_NAME,
  projectManifest,
} from '../manifest/operator-local.ts';
import {
  ProjectLock,
  nativeProcesses,
  PROJECT_LOCK_NAME,
  type ProcessInspector,
} from './project-lock.ts';
import {
  PROJECT_STATE_NAME,
  PROJECT_BACKUP_NAME,
  PROJECT_JOURNAL_NAME,
  encodeEnvelope,
  decodeEnvelope,
  validateState,
  validateJournal,
} from './state-codec.ts';
import {
  type ProjectState,
  type ProjectJournal,
  type ProjectCreateOptions,
  type ProjectCommand,
  type OperationReceipt,
  type SourceInventoryItem,
  type RestartPreview,
  type ProjectAdoptionSeed,
  type JournalCopy,
} from './types.ts';

export interface ProjectStoreOptions {
  checkpoint?: WriteCheckpoint;
  processes?: ProcessInspector;
}
export interface ProjectIssue {
  code: string;
  message: string;
}
export async function inventoryFor(root: string): Promise<{
  inventory: SourceInventoryItem[];
  checksum: string;
  root: string;
  scan: VerifiedSourceScan;
}> {
  const scan = await scanSource(root);
  const index = scan.index;
  const inventory = index.images.map((image) => ({
    relativePath: image.relativePath,
    name: image.name,
    sizeBytes: image.size,
    lastModifiedMs: Math.trunc(image.lastModified),
    mimeType: 'image/jpeg',
  }));
  // Browser File.lastModified exposes integer milliseconds. Preserve precisely
  // that source-manifest contract instead of persisting Node's fractional mtime.
  const manifest = await buildRemoteSourceManifestV1(
    inventory,
    'directory_handle',
  );
  return {
    inventory,
    checksum: manifest.manifestChecksumSha256,
    root: scan.root,
    scan,
  };
}
function stateIdentity(state: ProjectState): string {
  return checksum(
    stableStringify({ ...state, sourceRoot: '', outputRoot: '' }),
  );
}
function accepted(state: ProjectState) {
  return state.decisions.filter((decision) => decision.action === 'accepted');
}
function scratch(journal: ProjectJournal, kind: 'jpeg' | 'manifest'): string {
  return `.selector-${checksum(`${journal.projectId}:${journal.operationId}:${kind}`)}.tmp`;
}
export class ProjectStore {
  private state: ProjectState;
  private readonly files: SecureFiles;
  private readonly lock: ProjectLock;
  private readonly checkpoint: WriteCheckpoint;
  private queue: Promise<unknown> = Promise.resolve();
  private issue: ProjectIssue | null = null;
  private closed = false;
  private sourceScan: VerifiedSourceScan | null = null;
  private closeIssue: ProjectIssue | null = null;
  private outputLease: ProjectLock | null = null;
  private outputLeaseRoot: string | null = null;
  private readonly processes: ProcessInspector;
  private constructor(
    files: SecureFiles,
    lock: ProjectLock,
    state: ProjectState,
    options: ProjectStoreOptions,
  ) {
    this.files = files;
    this.lock = lock;
    this.state = state;
    this.checkpoint = options.checkpoint ?? noCheckpoint;
    const inspector = options.processes ?? nativeProcesses;
    this.processes = {
      ...inspector,
      identity: (pid) =>
        pid === lock.owner.pid
          ? Promise.resolve(lock.owner.processIdentity)
          : inspector.identity(pid),
    };
  }
  snapshot(): ProjectState {
    return structuredClone(this.state);
  }
  getIssue(): ProjectIssue | null {
    return this.issue ? { ...this.issue } : null;
  }
  getVerifiedSourceScan(): VerifiedSourceScan | null {
    return this.sourceScan?.root === this.state.sourceRoot
      ? this.sourceScan
      : null;
  }
  getCloseIssue(): ProjectIssue | null {
    return this.closeIssue ? { ...this.closeIssue } : null;
  }
  getProjectRoot(): string {
    return this.files.root;
  }
  private serial<T>(work: () => Promise<T>): Promise<T> {
    const next = this.queue.then(work);
    this.queue = next.catch(() => {});
    return next;
  }
  static async create(
    input: ProjectCreateOptions,
    options: ProjectStoreOptions = {},
  ): Promise<ProjectStore> {
    return this.createInitial(input, options);
  }
  /** Native-only hook for a fully verified selection; new roots must be empty. */
  static async createFromSelection(
    input: ProjectCreateOptions,
    options: ProjectStoreOptions,
    seed: ProjectAdoptionSeed,
    oldOutputRoot: string,
  ): Promise<ProjectStore> {
    return this.createInitial(input, options, seed, oldOutputRoot);
  }
  private static async createInitial(
    input: ProjectCreateOptions,
    options: ProjectStoreOptions,
    adoption?: ProjectAdoptionSeed,
    oldOutputRoot?: string,
  ): Promise<ProjectStore> {
    if (input.direction !== 'ascending' && input.direction !== 'descending')
      throw new SelectorError(
        'INVALID_ARGUMENT',
        'Nieprawidłowy kierunek numeracji.',
      );
    try {
      rangeForStart(input.firstLayout, input.sequenceUpperBound ?? null);
    } catch {
      throw new SelectorError(
        'INVALID_RANGE',
        'Nieprawidłowy pierwszy zakres lub granica.',
      );
    }
    assertSeparateRoots([
      input.sourceRoot,
      input.projectRoot,
      input.outputRoot,
    ]);
    await assertLocalStorage(input.projectRoot, input.localStorageConfirmed);
    await assertLocalStorage(input.outputRoot, input.localStorageConfirmed);
    const source = await inventoryFor(input.sourceRoot);
    if (
      adoption &&
      (source.checksum !== adoption.sourceManifestChecksumSha256 ||
        stableStringify(source.inventory) !==
          stableStringify(adoption.inventory) ||
        path.basename(source.root) !== adoption.sourceDirectoryName)
    )
      throw new SelectorError(
        'SOURCE_IDENTITY_CONFLICT',
        'Źródło zmieniło się od podglądu przejęcia.',
      );
    if (!source.inventory.length)
      throw new SelectorError('EMPTY_SOURCE', 'Źródło nie zawiera zdjęć JPEG.');
    // Resolve parents before creating either leaf. An 8.3 alias must never
    // cause even an empty project directory to be created inside source.
    const projectLocation = await canonicalDirectoryLocation(input.projectRoot);
    const outputLocation = await canonicalDirectoryLocation(input.outputRoot);
    assertSeparateRoots([
      source.root,
      projectLocation,
      outputLocation,
      ...(oldOutputRoot
        ? [await canonicalDirectoryLocation(oldOutputRoot)]
        : []),
    ]);
    const projectRoot = await ensureDirectory(input.projectRoot);
    const outputRoot = await ensureDirectory(input.outputRoot);
    assertSeparateRoots([source.root, projectRoot, outputRoot]);
    const files = new SecureFiles(projectRoot);
    const output = new SecureFiles(outputRoot);
    // A new project never adopts, replaces, or cleans a nonempty directory.
    if ((await files.names()).length || (await output.names()).length)
      throw new SelectorError(
        'FOREIGN_CONTENT',
        'Nowy projekt wymaga pustego katalogu projektu i wyniku.',
      );
    const state: ProjectState = {
      schemaVersion: 1,
      projectId: randomUUID(),
      revision: 0,
      sourceRoot: source.root,
      outputRoot,
      sourceDirectoryName: path.basename(source.root),
      sourceManifestChecksumSha256: source.checksum,
      inventory: source.inventory,
      firstLayout: adoption ? adoption.firstLayout : input.firstLayout,
      direction: adoption ? adoption.direction : input.direction,
      sequenceUpperBound: adoption
        ? adoption.sequenceUpperBound
        : (input.sequenceUpperBound ?? null),
      currentRelativePath: adoption
        ? adoption.currentRelativePath
        : source.inventory[0].relativePath,
      nextRangeStart: adoption ? adoption.nextRangeStart : input.firstLayout,
      selectionComplete: adoption ? adoption.selectionComplete : false,
      selectionGeneration: adoption ? adoption.selectionGeneration : 0,
      decisions: adoption ? structuredClone(adoption.decisions) : [],
      receipts: {},
      updatedAt: new Date().toISOString(),
    };
    validateState(state);
    const lock = await ProjectLock.acquire(files, options.processes);
    const store = new ProjectStore(files, lock, state, options);
    const journal: ProjectJournal = {
      schemaVersion: adoption ? 2 : 1,
      projectId: state.projectId,
      phase: 'prepared',
      before: null,
      after: state,
      operationId: 'initial-create',
      copy: null,
      removals: [],
      ...(adoption
        ? {
            importCopies: accepted(state).map((d) => ({
              imagePath: d.imagePath!,
              outputName: d.outputName!,
              checksumSha256: d.imageChecksumSha256!,
              sizeBytes: state.inventory[d.sourceIndex].sizeBytes,
            })),
          }
        : {}),
    };
    try {
      store.sourceScan = source.scan;
      await store.prepare(journal);
      await store.applyJournal(journal);
      return store;
    } catch (error) {
      await lock.release();
      throw ioError(error, 'create');
    }
  }
  static async open(
    projectRoot: string,
    options: ProjectStoreOptions = {},
  ): Promise<ProjectStore> {
    await assertLocalStorage(projectRoot, true);
    const files = new SecureFiles(projectRoot);
    const lock = await ProjectLock.acquire(files, options.processes);
    try {
      let state: ProjectState | null = null;
      let corrupt = false;
      for (const name of [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME]) {
        const bytes = await files.read(name);
        if (!bytes) continue;
        try {
          const candidate = decodeEnvelope<ProjectState>(bytes);
          validateState(candidate);
          state = candidate;
          break;
        } catch (error) {
          if (!(error instanceof SelectorError)) throw error;
          if (error.code === 'UNSUPPORTED_PROJECT_SCHEMA') throw error;
          corrupt = true;
        }
      }
      const bytes = await files.read(PROJECT_JOURNAL_NAME);
      if (bytes) {
        const journal = decodeEnvelope<ProjectJournal>(bytes);
        validateJournal(journal);
        if (!state) state = journal.before ?? journal.after;
        if (state.projectId !== journal.projectId)
          throw new SelectorError(
            'JOURNAL_CONFLICT',
            'Dziennik i projekt mają inną tożsamość.',
          );
      }
      if (!state)
        throw new SelectorError(
          corrupt ? 'PROJECT_CORRUPT' : 'PROJECT_NOT_FOUND',
          corrupt
            ? 'Projekt i kopia zapasowa są uszkodzone.'
            : 'Nie znaleziono projektu.',
        );
      const store = new ProjectStore(files, lock, state, options);
      try {
        await store.resumeInternal();
      } catch (error) {
        if (!(error instanceof SelectorError)) throw error;
        store.issue = { code: error.code, message: error.message };
      }
      return store;
    } catch (error) {
      await lock.release();
      throw error;
    }
  }
  private async validateProjectContents(): Promise<void> {
    const allowed = new Set([
      PROJECT_STATE_NAME,
      PROJECT_BACKUP_NAME,
      PROJECT_JOURNAL_NAME,
      'selector-project.lock',
    ]);
    for (const name of await this.files.names())
      if (!allowed.has(name) && !/^\.selector-[a-f0-9-]{36}\.tmp$/.test(name))
        throw new SelectorError(
          'FOREIGN_CONTENT',
          'Katalog projektu zawiera obce dane.',
        );
  }
  private async checkSource(state: ProjectState): Promise<void> {
    this.sourceScan = null;
    let source;
    try {
      source = await inventoryFor(state.sourceRoot);
    } catch (error) {
      if (isMissing(error))
        throw new SelectorError(
          'SOURCE_MISSING',
          'Źródło jest niedostępne. Wskaż ponownie ten sam katalog.',
        );
      throw error;
    }
    if (
      source.checksum !== state.sourceManifestChecksumSha256 ||
      stableStringify(source.inventory) !== stableStringify(state.inventory)
    )
      throw new SelectorError(
        'SOURCE_IDENTITY_CONFLICT',
        'Źródło ma inne pliki lub metadane. Postęp nie został zresetowany.',
      );
    this.sourceScan = source.scan;
  }
  private async outputFiles(state: ProjectState): Promise<SecureFiles> {
    const files = new SecureFiles(state.outputRoot);
    try {
      await files.verifyRoot();
    } catch (error) {
      if (isMissing(error))
        throw new SelectorError(
          'OUTPUT_MISSING',
          'Wynik jest niedostępny. Wskaż ponownie ten sam katalog.',
        );
      throw error;
    }
    return files;
  }
  private async verifyOutput(
    before: ProjectState | null,
    after: ProjectState,
    journal?: ProjectJournal,
    hashNames: 'all' | Set<string> = 'all',
    verifiedFiles?: SecureFiles,
  ): Promise<SecureFiles> {
    const files = verifiedFiles ?? (await this.outputFiles(after));
    const beforeManifest = before
      ? stableStringify(projectManifest(before))
      : null;
    const afterManifest = stableStringify(projectManifest(after));
    const manifest = await files.read(OUTPUT_MANIFEST_NAME);
    if (manifest) {
      let serialized: string;
      try {
        serialized = stableStringify(JSON.parse(manifest.toString()));
      } catch {
        throw new SelectorError(
          'OUTPUT_MANIFEST_CONFLICT',
          'Manifest wyniku jest uszkodzony lub obcy.',
        );
      }
      if (serialized !== beforeManifest && serialized !== afterManifest)
        throw new SelectorError(
          'OUTPUT_MANIFEST_CONFLICT',
          'Manifest wyniku nie odpowiada projektowi.',
        );
    } else if (before !== null)
      throw new SelectorError(
        'OUTPUT_MANIFEST_CONFLICT',
        'Brakuje manifestu istniejącego wyniku.',
      );
    const decisions = [...(before ? accepted(before) : []), ...accepted(after)];
    const managed = new Map(
      decisions.map((decision) => [
        decision.outputName!,
        decision.imageChecksumSha256!,
      ]),
    );
    const allowed = new Set([OUTPUT_MANIFEST_NAME, ...managed.keys()]);
    if (this.outputLease && this.outputLeaseRoot === files.root)
      allowed.add(PROJECT_LOCK_NAME);
    if (journal) {
      allowed.add(scratch(journal, 'jpeg'));
      allowed.add(scratch(journal, 'manifest'));
    }
    const present = new Set(await files.names(true));
    for (const name of present)
      if (!allowed.has(name))
        throw new SelectorError(
          'FOREIGN_CONTENT',
          'Katalog wyniku zawiera obce dane. Zapis został zatrzymany.',
        );
    for (const [name, expectedHash] of managed) {
      const recoverable =
        journal?.copy?.outputName === name ||
        journal?.importCopies?.some((item) => item.outputName === name) ||
        journal?.removals.some((item) => item.outputName === name);
      if (!present.has(name) && !recoverable)
        throw new SelectorError(
          'OUTPUT_MISSING_FILE',
          'Brakuje zaakceptowanego pliku wynikowego. Przywróć jego zgodną kopię i wznów projekt.',
        );
      if (hashNames !== 'all' && !hashNames.has(name)) continue;
      const actual = await files.hash(name);
      if (actual === null) {
        const recoverable =
          journal?.copy?.outputName === name ||
          journal?.importCopies?.some((item) => item.outputName === name) ||
          journal?.removals.some((item) => item.outputName === name);
        if (!recoverable)
          throw new SelectorError(
            'OUTPUT_MISSING_FILE',
            'Brakuje zaakceptowanego pliku wynikowego.',
          );
      } else if (actual !== expectedHash)
        throw new SelectorError(
          'OUTPUT_CHECKSUM_CONFLICT',
          'Plik wynikowy ma inną sumę kontrolną. Zapis został zatrzymany.',
        );
    }
    return files;
  }
  private async prepare(journal: ProjectJournal): Promise<void> {
    validateJournal(journal);
    await this.checkpoint('prepare:before');
    await this.files.replace(
      PROJECT_JOURNAL_NAME,
      encodeEnvelope(journal),
      this.checkpoint,
    );
    await this.checkpoint('prepare:after');
  }
  private async sourceChecksum(
    state: ProjectState,
    imagePath: string,
  ): Promise<string> {
    try {
      const image = state.inventory.find(
        (item) => item.relativePath === imagePath,
      );
      if (!image)
        throw new SelectorError(
          'UNKNOWN_IMAGE',
          'Zdjęcie nie należy do źródła.',
        );
      const source = new SecureFiles(state.sourceRoot);
      const stat = await lstat(
        await safeExistingPath(state.sourceRoot, imagePath),
      );
      if (
        stat.size !== image.sizeBytes ||
        Math.trunc(stat.mtimeMs) !== image.lastModifiedMs
      )
        throw new SelectorError(
          'SOURCE_CHANGED',
          'Zdjęcie zmieniło się od utworzenia projektu.',
        );
      const hash = await source.hash(imagePath);
      if (!hash)
        throw new SelectorError(
          'SOURCE_MISSING',
          'Źródłowe zdjęcie jest niedostępne.',
        );
      const after = await lstat(await source.target(imagePath));
      if (
        after.dev !== stat.dev ||
        after.ino !== stat.ino ||
        after.size !== image.sizeBytes ||
        Math.trunc(after.mtimeMs) !== image.lastModifiedMs
      )
        throw new SelectorError(
          'SOURCE_CHANGED',
          'Zdjęcie zmieniło się podczas sprawdzania.',
        );
      return hash;
    } catch (error) {
      if (isMissing(error))
        throw new SelectorError(
          'SOURCE_MISSING',
          'Źródłowe zdjęcie jest niedostępne. Wskaż ponownie źródło.',
        );
      throw error;
    }
  }
  private async copyJpeg(
    journal: ProjectJournal,
    output: SecureFiles,
    copy: JournalCopy | null = journal.copy,
  ): Promise<void> {
    if (!copy) return;
    const sourceHash = await this.sourceChecksum(journal.after, copy.imagePath);
    if (sourceHash !== copy.checksumSha256)
      throw new SelectorError(
        'SOURCE_CHECKSUM_CONFLICT',
        'Źródłowe zdjęcie ma inną sumę kontrolną.',
      );
    if ((await output.hash(copy.outputName)) === copy.checksumSha256) return;
    const temporary = scratch(journal, 'jpeg');
    await output.clearScratch(temporary);
    const destination = await open(await output.target(temporary), 'wx');
    const source = new SecureFiles(journal.after.sourceRoot);
    let input;
    const hash = createHash('sha256');
    let size = 0;
    try {
      input = await open(await source.target(copy.imagePath), 'r');
      const opened = await input.stat();
      const current = await lstat(await source.target(copy.imagePath));
      if (
        !opened.isFile() ||
        opened.dev !== current.dev ||
        opened.ino !== current.ino
      )
        throw new SelectorError(
          'SOURCE_CHANGED',
          'Zdjęcie zmieniło tożsamość przed kopiowaniem.',
        );
      for await (const chunk of input.createReadStream({ autoClose: false })) {
        hash.update(chunk);
        size += chunk.length;
        await destination.writeFile(chunk);
        await this.checkpoint('jpeg:chunk');
      }
      await destination.sync();
      if (hash.digest('hex') !== copy.checksumSha256 || size !== copy.sizeBytes)
        throw new SelectorError(
          'SOURCE_CHECKSUM_CONFLICT',
          'Zdjęcie zmieniło się podczas kopiowania.',
        );
    } finally {
      await input?.close();
      await destination.close();
    }
    if ((await output.hash(temporary)) !== copy.checksumSha256)
      throw new SelectorError(
        'OUTPUT_CHECKSUM_CONFLICT',
        'Zapisany JPEG ma nieprawidłową sumę kontrolną.',
      );
    if ((await output.hash(copy.outputName)) !== null)
      throw new SelectorError(
        'OUTPUT_CHECKSUM_CONFLICT',
        'Plik docelowy pojawił się podczas zapisu.',
      );
    await this.checkpoint('jpeg:replace');
    await rename(
      await output.target(temporary),
      await output.target(copy.outputName),
    );
    await output.syncDirectory();
  }
  private async applyJournal(
    journal: ProjectJournal,
    recovery = false,
  ): Promise<void> {
    validateJournal(journal);
    await this.lock.assertOwned();
    await this.validateProjectContents();
    assertSeparateRoots([
      journal.after.sourceRoot,
      this.files.root,
      journal.after.outputRoot,
    ]);
    await assertLocalStorage(journal.after.outputRoot, true);
    if (recovery) await this.checkSource(journal.after);
    const touched = new Set(journal.removals.map((item) => item.outputName));
    if (journal.copy) touched.add(journal.copy.outputName);
    for (const copy of journal.importCopies ?? []) touched.add(copy.outputName);
    const output = await this.outputFiles(journal.after);
    this.outputLease = await ProjectLock.acquire(output, this.processes, true);
    this.outputLeaseRoot = output.root;
    try {
      await this.verifyOutput(
        journal.before,
        journal.after,
        journal,
        recovery ? 'all' : touched,
        output,
      );
      await this.checkpoint('jpeg:before');
      await this.copyJpeg(journal, output);
      for (const copy of journal.importCopies ?? []) {
        await this.copyJpeg(journal, output, copy);
        await this.checkpoint('import:copy');
      }
      for (const removal of journal.removals)
        await output.removeOwned(removal.outputName, removal.checksumSha256);
      await this.checkpoint('jpeg:after');
      journal.phase = 'jpeg_written';
      await this.files.replace(
        PROJECT_JOURNAL_NAME,
        encodeEnvelope(journal),
        this.checkpoint,
      );
      await this.checkpoint('state:before');
      await this.files.replace(
        PROJECT_STATE_NAME,
        encodeEnvelope(journal.after),
        this.checkpoint,
      );
      this.state = structuredClone(journal.after);
      await this.checkpoint('state:after');
      journal.phase = 'committed';
      await this.files.replace(
        PROJECT_JOURNAL_NAME,
        encodeEnvelope(journal),
        this.checkpoint,
      );
      await this.checkpoint('manifest:before');
      await this.verifyOutput(
        journal.before,
        journal.after,
        journal,
        new Set(),
        output,
      );
      await output.clearScratch(scratch(journal, 'manifest'));
      await output.replace(
        OUTPUT_MANIFEST_NAME,
        stableStringify(projectManifest(journal.after)),
        this.checkpoint,
        scratch(journal, 'manifest'),
      );
      await this.checkpoint('manifest:after');
      await this.checkpoint('backup:before');
      await this.files.replace(
        PROJECT_BACKUP_NAME,
        encodeEnvelope(journal.after),
        this.checkpoint,
      );
      await this.checkpoint('backup:after');
      await this.checkpoint('finalize:before');
      // Release while the journal still exists. A killed process can never leave
      // an unaccounted output lease after a successfully finalized transaction.
      await this.outputLease.release();
      this.outputLease = null;
      this.outputLeaseRoot = null;
      await this.files.clearScratch(PROJECT_JOURNAL_NAME);
      await this.files.syncDirectory();
      await this.checkpoint('finalize:after');
      this.issue = null;
    } finally {
      if (this.outputLease) {
        await this.outputLease.release();
        this.outputLease = null;
        this.outputLeaseRoot = null;
      }
    }
  }
  private async resumeInternal(): Promise<void> {
    if (this.closed)
      throw new SelectorError('PROJECT_CLOSED', 'Projekt jest zamknięty.');
    await this.lock.assertOwned();
    await this.validateProjectContents();
    const bytes = await this.files.read(PROJECT_JOURNAL_NAME);
    if (bytes) {
      const journal = decodeEnvelope<ProjectJournal>(bytes);
      validateJournal(journal);
      const identity = stateIdentity(this.state);
      if (
        journal.projectId !== this.state.projectId ||
        (identity !== stateIdentity(journal.after) &&
          (journal.before === null ||
            identity !== stateIdentity(journal.before)))
      )
        throw new SelectorError(
          'JOURNAL_CONFLICT',
          'Dziennik nie odpowiada rewizji projektu.',
        );
      await this.applyJournal(journal, true);
    } else {
      await this.checkSource(this.state);
      await this.verifyOutput(this.state, this.state);
      // Restore a valid backup only after proving the output still agrees.
      await this.files.replace(PROJECT_STATE_NAME, encodeEnvelope(this.state));
      await this.files.replace(PROJECT_BACKUP_NAME, encodeEnvelope(this.state));
    }
    this.issue = null;
  }
  resume(): Promise<ProjectState> {
    return this.serial(async () => {
      try {
        await this.resumeInternal();
        return this.snapshot();
      } catch (error) {
        const failure = ioError(error, 'recovery');
        this.issue = { code: failure.code, message: failure.message };
        throw failure;
      }
    });
  }
  async previewRestart(): Promise<RestartPreview> {
    return this.serial(async () => {
      if (this.issue)
        throw new SelectorError(
          'PROJECT_FROZEN',
          'Najpierw wznów projekt lub wskaż brakujący katalog.',
        );
      await this.lock.assertOwned();
      await this.verifyOutput(this.state, this.state);
      return {
        revision: this.state.revision,
        checksum: stateIdentity(this.state),
        acceptedFiles: accepted(this.state).length,
        decisions: this.state.decisions.length,
      };
    });
  }
  execute(
    operationId: string,
    command: ProjectCommand,
  ): Promise<OperationReceipt> {
    return this.serial(async () => {
      if (this.closed)
        throw new SelectorError('PROJECT_CLOSED', 'Projekt jest zamknięty.');
      if (!/^[a-zA-Z0-9_-]{8,128}$/.test(operationId))
        throw new SelectorError(
          'INVALID_OPERATION_ID',
          'Nieprawidłowy identyfikator operacji.',
        );
      const fingerprint = checksum(stableStringify(command));
      const previous = Object.hasOwn(this.state.receipts, operationId)
        ? this.state.receipts[operationId]
        : undefined;
      if (previous) {
        if (previous.fingerprint !== fingerprint)
          throw new SelectorError(
            'OPERATION_ID_CONFLICT',
            'Identyfikator operacji został użyty z innymi argumentami.',
          );
        // A receipt is confirmed only once pending manifest/backup work completes.
        if (await this.files.read(PROJECT_JOURNAL_NAME))
          await this.resumeInternal();
        return structuredClone(previous);
      }
      if (this.issue && command.kind !== 'relink')
        throw new SelectorError(
          'PROJECT_FROZEN',
          'Zapis jest zatrzymany. Wznów projekt po usunięciu przyczyny.',
        );
      try {
        if (command.kind === 'relink') await this.relinkPending(command);
        if (await this.files.read(PROJECT_JOURNAL_NAME))
          await this.resumeInternal();
        await this.lock.assertOwned();
        await this.validateProjectContents();
        const before = this.snapshot();
        const after = this.snapshot();
        const journal: ProjectJournal = {
          schemaVersion: 1,
          projectId: before.projectId,
          phase: 'prepared',
          before,
          after,
          operationId,
          copy: null,
          removals: [],
        };
        const currentIndex = before.inventory.findIndex(
          (item) => item.relativePath === before.currentRelativePath,
        );
        const moveForward = () => {
          after.currentRelativePath =
            after.inventory[
              Math.min(currentIndex + 1, after.inventory.length - 1)
            ].relativePath;
        };
        if (command.kind === 'accept' || command.kind === 'skip') {
          if (before.selectionComplete)
            throw new SelectorError(
              'SELECTION_COMPLETE',
              'Selekcja jest zakończona. Cofnij ostatnią decyzję, aby kontynuować.',
            );
          const range = rangeForStart(
            before.nextRangeStart,
            before.sequenceUpperBound,
          );
          if (
            before.decisions.some(
              (d) =>
                d.action === 'accepted' &&
                d.rangeStart <= range.end &&
                d.rangeEnd >= range.start,
            )
          )
            throw new SelectorError(
              'RANGE_CONFLICT',
              'Zakres pokrywa się z wcześniejszą decyzją.',
            );
          let hash: string | null = null;
          let outputName: string | null = null;
          if (command.kind === 'accept') {
            if (command.imagePath !== before.currentRelativePath)
              throw new SelectorError(
                'STALE_CURSOR',
                'Polecenie nie odpowiada bieżącemu zdjęciu.',
              );
            if (
              before.decisions.some(
                (d) =>
                  d.action === 'accepted' && d.imagePath === command.imagePath,
              )
            )
              throw new SelectorError(
                'IMAGE_ALREADY_ACCEPTED',
                'To zdjęcie jest już zaakceptowane. Najpierw cofnij wybór.',
              );
            hash = await this.sourceChecksum(before, command.imagePath);
            outputName = `seq_${range.start}-${range.end}.jpg`;
            journal.copy = {
              imagePath: command.imagePath,
              outputName,
              checksumSha256: hash,
              sizeBytes: before.inventory[currentIndex].sizeBytes,
            };
          }
          after.decisions.push({
            action: command.kind === 'accept' ? 'accepted' : 'skipped',
            operationId,
            fileId:
              command.kind === 'accept' ? checksum(command.imagePath) : null,
            sourceIndex: currentIndex,
            imagePath: command.kind === 'accept' ? command.imagePath : null,
            imageChecksumSha256: hash,
            outputName,
            rangeStart: range.start,
            rangeEnd: range.end,
            activeBoardCount: range.end - range.start + 1,
            selectionGeneration: before.selectionGeneration,
          });
          after.selectionComplete = isManualSelectionRangeTerminal(
            before.direction,
            range.start,
            range.end,
            before.sequenceUpperBound,
          );
          after.nextRangeStart = nextManualRangeStart(
            before.direction,
            range.start,
          );
          if (command.kind === 'accept') moveForward();
        } else if (command.kind === 'navigate') {
          if (
            !before.inventory.some(
              (item) => item.relativePath === command.imagePath,
            )
          )
            throw new SelectorError(
              'UNKNOWN_IMAGE',
              'Zdjęcie nie należy do źródła.',
            );
          after.currentRelativePath = command.imagePath;
        } else if (command.kind === 'range') {
          if (before.selectionComplete)
            throw new SelectorError(
              'SELECTION_COMPLETE',
              'Najpierw cofnij ostatnią decyzję.',
            );
          try {
            rangeForStart(command.start, before.sequenceUpperBound);
          } catch {
            throw new SelectorError('INVALID_RANGE', 'Nieprawidłowy zakres.');
          }
          after.nextRangeStart = command.start;
        } else if (command.kind === 'undo') {
          const last = after.decisions.pop();
          if (!last)
            throw new SelectorError(
              'NOTHING_TO_UNDO',
              'Brak decyzji do cofnięcia.',
            );
          if (last.action === 'accepted')
            journal.removals.push({
              outputName: last.outputName!,
              checksumSha256: last.imageChecksumSha256!,
            });
          after.currentRelativePath =
            after.inventory[last.sourceIndex].relativePath;
          after.nextRangeStart = last.rangeStart;
          after.selectionComplete = false;
        } else if (command.kind === 'restart') {
          if (
            command.expectedRevision !== before.revision ||
            command.previewChecksum !== stateIdentity(before)
          )
            throw new SelectorError(
              'STALE_RESTART_PREVIEW',
              'Projekt zmienił się od podglądu restartu.',
            );
          journal.removals = accepted(before).map((d) => ({
            outputName: d.outputName!,
            checksumSha256: d.imageChecksumSha256!,
          }));
          after.decisions = [];
          after.currentRelativePath = after.inventory[0].relativePath;
          after.nextRangeStart = after.firstLayout;
          after.selectionComplete = false;
          after.selectionGeneration++;
        } else if (command.kind === 'relink') {
          if (command.sourceRoot)
            after.sourceRoot = await canonicalDirectoryLocation(
              command.sourceRoot,
            );
          if (command.outputRoot)
            after.outputRoot = await canonicalDirectoryLocation(
              command.outputRoot,
            );
          await this.checkSource(after);
          await assertLocalStorage(after.outputRoot, true);
          assertSeparateRoots([
            after.sourceRoot,
            this.files.root,
            after.outputRoot,
          ]);
        } else
          throw new SelectorError(
            'INVALID_ARGUMENT',
            'Nieznane polecenie projektu.',
          );
        after.revision++;
        after.updatedAt = new Date().toISOString();
        const receipt: OperationReceipt = {
          fingerprint,
          revision: after.revision,
          currentRelativePath: after.currentRelativePath,
          nextRangeStart: after.nextRangeStart,
          selectionComplete: after.selectionComplete,
          decisionCount: after.decisions.length,
        };
        after.receipts = { ...after.receipts, [operationId]: receipt };
        validateState(after);
        // Check the old projection before preparing any intent. A JPEG that
        // happens to have the desired name is never adopted by a new selection.
        await this.verifyOutput(
          { ...before, outputRoot: after.outputRoot },
          { ...before, outputRoot: after.outputRoot },
          undefined,
          new Set(journal.removals.map((item) => item.outputName)),
        );
        await this.prepare(journal);
        await this.applyJournal(journal);
        return structuredClone(receipt);
      } catch (error) {
        const failure = ioError(error, command.kind);
        // Domain rejections without an intent do not freeze otherwise valid work.
        if (
          (await this.files.read(PROJECT_JOURNAL_NAME)) ||
          [
            'DISK_FULL',
            'WRITE_FAILED',
            'WRITE_DENIED',
            'SOURCE_MISSING',
            'OUTPUT_MISSING',
            'OUTPUT_MISSING_FILE',
            'LOCK_LOST',
            'SOURCE_IDENTITY_CONFLICT',
            'SOURCE_CHANGED',
            'SOURCE_CHECKSUM_CONFLICT',
            'OUTPUT_CHECKSUM_CONFLICT',
            'OUTPUT_MANIFEST_CONFLICT',
            'FOREIGN_CONTENT',
          ].includes(failure.code)
        )
          this.issue = { code: failure.code, message: failure.message };
        throw failure;
      }
    });
  }
  private async relinkPending(
    command: Extract<ProjectCommand, { kind: 'relink' }>,
  ): Promise<void> {
    if (!command.sourceRoot && !command.outputRoot)
      throw new SelectorError('INVALID_ARGUMENT', 'Wskaż źródło lub wynik.');
    const bytes = await this.files.read(PROJECT_JOURNAL_NAME);
    if (!bytes) return;
    const journal = decodeEnvelope<ProjectJournal>(bytes);
    validateJournal(journal);
    const sourceRoot = command.sourceRoot
      ? await canonicalDirectoryLocation(command.sourceRoot)
      : journal.after.sourceRoot;
    const outputRoot = command.outputRoot
      ? await canonicalDirectoryLocation(command.outputRoot)
      : journal.after.outputRoot;
    const relocate = (state: ProjectState) => ({
      ...state,
      sourceRoot,
      outputRoot,
    });
    journal.after = relocate(journal.after);
    if (journal.before) journal.before = relocate(journal.before);
    assertSeparateRoots([
      journal.after.sourceRoot,
      this.files.root,
      journal.after.outputRoot,
    ]);
    await assertLocalStorage(journal.after.outputRoot, true);
    await this.checkSource(journal.after);
    const output = await this.outputFiles(journal.after);
    this.outputLease = await ProjectLock.acquire(output, this.processes, true);
    this.outputLeaseRoot = output.root;
    try {
      await this.verifyOutput(
        journal.before,
        journal.after,
        journal,
        'all',
        output,
      );
      // Relocation changes only the durable pending intent's root bindings. The
      // journal still carries every original decision and operation receipt.
      await this.files.replace(PROJECT_JOURNAL_NAME, encodeEnvelope(journal));
    } finally {
      await this.outputLease.release();
      this.outputLease = null;
      this.outputLeaseRoot = null;
    }
    await this.resumeInternal();
  }
  close(): Promise<void> {
    return this.serial(async () => {
      if (!this.closed) {
        try {
          await this.lock.release();
        } catch (error) {
          if (!(error instanceof SelectorError) || error.code !== 'LOCK_LOST')
            throw error;
          this.closeIssue = { code: error.code, message: error.message };
        }
        this.closed = true;
        this.sourceScan = null;
      }
    });
  }
}

import { SelectorError, MAX_SEQUENCE_NUMBER } from '../contracts.ts';
import {
  SecureFiles,
  checksum,
  stableStringify,
  type FileIdentity,
  type WriteCheckpoint,
} from '../filesystem/secure-files.ts';
import {
  PROJECT_STATE_NAME,
  PROJECT_BACKUP_NAME,
  PROJECT_JOURNAL_NAME,
  encodeEnvelope,
  decodeEnvelope,
  validateState,
  validateScalar,
  validateReceipt,
  validateDiskHead,
  validateCompactJournalStructure,
  validateLedgerRecordStructure,
} from './state-codec.ts';
import type {
  ProjectState,
  ProjectScalar,
  ProjectDiskHead,
  ProjectJournal,
  ProjectCompactJournal,
  ProjectUpgradeJournal,
  ProjectLedgerRecord,
  ProjectLedgerPayload,
  ProjectDecisionDelta,
  ProjectDecision,
} from './types.ts';
import {
  rangeForStart,
  isManualSelectionRangeTerminal,
} from '@game-predictor/manual-image-selection-core';

export const PROJECT_LEDGER_NAME = 'selector-operations-v2.jsonl';
export const PROJECT_LEDGER_BACKUP_NAME = 'selector-operations-v2.backup.jsonl';
const ledgers = [PROJECT_LEDGER_NAME, PROJECT_LEDGER_BACKUP_NAME];
interface InventoryBlob {
  schemaVersion: 1;
  projectId: string;
  items: ProjectState['inventory'];
}
interface BaselineBlob {
  schemaVersion: 1;
  projectId: string;
  scalar: ProjectScalar;
  decisions: ProjectDecision[];
  receipts: ProjectState['receipts'];
}
type CompactIntent = ProjectCompactJournal | ProjectUpgradeJournal;
function conflict(
  message = 'Niezgodna historia lub tożsamość projektu.',
): never {
  throw new SelectorError('JOURNAL_CONFLICT', message);
}
function corrupt(): never {
  throw new SelectorError(
    'PROJECT_CORRUPT',
    'Obie kopie danych projektu są uszkodzone lub niezgodne.',
  );
}
export function scalarFor(state: ProjectState): ProjectScalar {
  const {
    inventory: _inventory,
    decisions: _decisions,
    receipts: _receipts,
    sourceRoot: _sourceRoot,
    outputRoot: _outputRoot,
    ...scalar
  } = state;
  void _inventory;
  void _decisions;
  void _receipts;
  void _sourceRoot;
  void _outputRoot;
  return scalar;
}
function hashValue(value: unknown): string {
  return checksum(stableStringify(value));
}
function blobNames(kind: 'inventory' | 'baseline', hash: string): string[] {
  return [
    `selector-${kind}-${hash}.json`,
    `selector-${kind}-${hash}.backup.json`,
  ];
}
export function compactNames(head: ProjectDiskHead): string[] {
  return [
    ...blobNames('inventory', head.inventoryHash),
    ...blobNames('baseline', head.baselineHash),
    ...ledgers,
  ];
}
function anchor(head: ProjectDiskHead): string {
  return hashValue({
    projectId: head.projectId,
    inventoryHash: head.inventoryHash,
    baselineHash: head.baselineHash,
  });
}
export function headIdentity(head: ProjectDiskHead): string {
  return hashValue({ ...head, sourceRoot: '', outputRoot: '' });
}
function recordFor(
  payload: ProjectLedgerPayload,
  previousHash: string,
): string {
  return `${stableStringify({ previousHash, payload, checksumSha256: hashValue({ previousHash, payload }) })}\n`;
}
function decodeRecord(bytes: string): ProjectLedgerRecord {
  try {
    const record = JSON.parse(bytes) as ProjectLedgerRecord;
    validateLedgerRecordStructure(record);
    if (
      record.checksumSha256 !==
        hashValue({
          previousHash: record.previousHash,
          payload: record.payload,
        }) ||
      `${stableStringify(record)}\n` !== bytes
    )
      conflict();
    return record;
  } catch (error) {
    if (error instanceof SelectorError) throw error;
    return corrupt();
  }
}
function deltaFor(
  before: ProjectState,
  after: ProjectState,
): ProjectDecisionDelta {
  if (
    after.selectionGeneration === before.selectionGeneration + 1 &&
    after.decisions.length === 0
  )
    return { kind: 'clear' };
  if (after.decisions === before.decisions) return { kind: 'none' };
  if (after.decisions.length === before.decisions.length + 1)
    return { kind: 'append', decision: after.decisions.at(-1)! };
  if (after.decisions.length + 1 === before.decisions.length)
    return { kind: 'pop', decision: before.decisions.at(-1)! };
  if (after.decisions.length === 0) return { kind: 'clear' };
  conflict('Nieobsługiwana zmiana historii decyzji.');
}
function validateEffects(
  journal: ProjectJournal,
  delta: ProjectDecisionDelta,
): void {
  const decision = delta.kind === 'append' ? delta.decision : null;
  const expectedCopy =
    decision?.action === 'accepted'
      ? {
          imagePath: decision.imagePath,
          outputName: decision.outputName,
          checksumSha256: decision.imageChecksumSha256,
          sizeBytes: journal.after.inventory[decision.sourceIndex]?.sizeBytes,
        }
      : null;
  const removed =
    delta.kind === 'clear'
      ? journal.before!.decisions.filter((d) => d.action === 'accepted')
      : delta.kind === 'pop' && delta.decision.action === 'accepted'
        ? [delta.decision]
        : [];
  const expectedRemovals = removed.map((d) => ({
    outputName: d.outputName,
    checksumSha256: d.imageChecksumSha256,
  }));
  if (
    stableStringify(journal.copy) !== stableStringify(expectedCopy) ||
    stableStringify(journal.removals) !== stableStringify(expectedRemovals)
  )
    throw new SelectorError(
      'JOURNAL_CORRUPT',
      'Pliki zamiaru nie odpowiadają dokładnej zmianie decyzji.',
    );
}
/** Disk authority: immutable mirrored roots and a checksummed committed ledger prefix. */
export class ProjectStorage {
  head: ProjectDiskHead;
  readonly paths: ReadonlySet<string>;
  private readonly baseline: BaselineBlob;
  private readonly inventory: ProjectState['inventory'];
  private readonly stats = new Map<string, FileIdentity>();
  private readonly repairs = new Map<string, Buffer | string>();
  private readonly files: SecureFiles;
  private constructor(
    files: SecureFiles,
    head: ProjectDiskHead,
    inventory: InventoryBlob,
    baseline: BaselineBlob,
  ) {
    this.files = files;
    this.head = head;
    this.inventory = inventory.items;
    this.baseline = baseline;
    this.paths = new Set(inventory.items.map((item) => item.relativePath));
  }
  names(): string[] {
    return compactNames(this.head);
  }
  static upgradeDescriptor(state: ProjectState): ProjectUpgradeJournal {
    validateState(state);
    const inventory: InventoryBlob = {
      schemaVersion: 1,
      projectId: state.projectId,
      items: state.inventory,
    };
    const baseline: BaselineBlob = {
      schemaVersion: 1,
      projectId: state.projectId,
      scalar: scalarFor(state),
      decisions: state.decisions,
      receipts: state.receipts,
    };
    const head: ProjectDiskHead = {
      schemaVersion: 2,
      projectId: state.projectId,
      inventoryHash: hashValue(inventory),
      baselineHash: hashValue(baseline),
      ledgerBytes: 0,
      ledgerHash: '',
      revision: state.revision,
      sourceRoot: state.sourceRoot,
      outputRoot: state.outputRoot,
      scalar: scalarFor(state),
    };
    head.ledgerHash = anchor(head);
    return {
      schemaVersion: 3,
      mode: 'upgrade',
      projectId: state.projectId,
      state,
      head,
    };
  }
  static async completeUpgrade(
    files: SecureFiles,
    journal: ProjectUpgradeJournal,
    checkpoint: WriteCheckpoint,
  ): Promise<void> {
    validateCompactJournalStructure(journal);
    const exact = ProjectStorage.upgradeDescriptor(journal.state);
    if (stableStringify(exact) !== stableStringify(journal)) conflict();
    const inventory: InventoryBlob = {
      schemaVersion: 1,
      projectId: journal.projectId,
      items: journal.state.inventory,
    };
    const baseline: BaselineBlob = {
      schemaVersion: 1,
      projectId: journal.projectId,
      scalar: scalarFor(journal.state),
      decisions: journal.state.decisions,
      receipts: journal.state.receipts,
    };
    for (const [names, value] of [
      [blobNames('inventory', journal.head.inventoryHash), inventory],
      [blobNames('baseline', journal.head.baselineHash), baseline],
    ] as const) {
      for (const name of names) {
        await checkpoint(`upgrade:${name}:before`);
        const bytes = await files.read(name);
        if (bytes) {
          if (bytes.toString() !== encodeEnvelope(value)) conflict();
        } else await files.replace(name, encodeEnvelope(value), checkpoint);
        await checkpoint(`upgrade:${name}:after`);
      }
    }
    for (const name of ledgers) {
      await checkpoint(`upgrade:${name}:before`);
      const bytes = await files.read(name);
      if (bytes && bytes.length !== 0) conflict();
      if (!bytes) await files.replace(name, '', checkpoint);
      await checkpoint(`upgrade:${name}:after`);
    }
    for (const name of [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME]) {
      await checkpoint(`upgrade:${name}:before`);
      await files.replace(name, encodeEnvelope(journal.head), checkpoint);
      await checkpoint(`upgrade:${name}:after`);
    }
    await checkpoint('upgrade:finalize:before');
    await files.clearScratch(PROJECT_JOURNAL_NAME);
    await files.syncDirectory();
    await checkpoint('upgrade:finalize:after');
  }
  static async load(
    files: SecureFiles,
    head: ProjectDiskHead,
    journal?: ProjectCompactJournal,
  ): Promise<{ storage: ProjectStorage; state: ProjectState }> {
    validateDiskHead(head);
    const repairs = new Map<string, Buffer>();
    async function blob<T>(
      kind: 'inventory' | 'baseline',
      hash: string,
    ): Promise<T> {
      const names = blobNames(kind, hash);
      let good: { bytes: Buffer; value: T } | undefined;
      const bad: string[] = [];
      for (const name of names) {
        const bytes = await files.read(name);
        try {
          if (!bytes) corrupt();
          const value = decodeEnvelope<T>(bytes);
          if (hashValue(value) !== hash) corrupt();
          good ??= { bytes, value };
        } catch (error) {
          if (!(error instanceof SelectorError)) throw error;
          bad.push(name);
        }
      }
      if (!good) corrupt();
      for (const name of bad) repairs.set(name, good.bytes);
      return good.value;
    }
    const inventory = await blob<InventoryBlob>(
      'inventory',
      head.inventoryHash,
    );
    const baseline = await blob<BaselineBlob>('baseline', head.baselineHash);
    if (
      inventory.schemaVersion !== 1 ||
      baseline.schemaVersion !== 1 ||
      inventory.projectId !== head.projectId ||
      baseline.projectId !== head.projectId ||
      !Array.isArray(inventory.items) ||
      !Array.isArray(baseline.decisions) ||
      inventory.items.some(
        (item) => !item || typeof item.relativePath !== 'string',
      ) ||
      !baseline.receipts ||
      typeof baseline.receipts !== 'object' ||
      Array.isArray(baseline.receipts)
    )
      conflict();
    const storage = new ProjectStorage(files, head, inventory, baseline);
    validateState(storage.initial(head));
    for (const [name, bytes] of repairs) storage.repairs.set(name, bytes);
    const state = await storage.replay(head, journal);
    validateState(state);
    return { storage, state };
  }
  private initial(head: ProjectDiskHead): ProjectState {
    return {
      ...this.baseline.scalar,
      inventory: this.inventory,
      decisions: [...this.baseline.decisions],
      receipts: Object.assign(Object.create(null), this.baseline.receipts),
      sourceRoot: head.sourceRoot,
      outputRoot: head.outputRoot,
    };
  }
  private applyRecord(
    state: ProjectState,
    record: ProjectLedgerRecord,
  ): ProjectState {
    const p = record.payload;
    if (
      p.projectId !== this.head.projectId ||
      p.previousRevision !== state.revision ||
      p.scalar.projectId !== state.projectId ||
      p.scalar.revision !== state.revision + 1 ||
      p.receipt.revision !== p.scalar.revision ||
      Object.hasOwn(state.receipts, p.operationId)
    )
      conflict();
    validateScalar(p.scalar, this.paths);
    validateReceipt(p.receipt, p.scalar.revision, this.paths);
    for (const key of [
      'gameName',
      'gameUpdate',
      'sourceDirectoryName',
      'sourceManifestChecksumSha256',
      'firstLayout',
    ] as const)
      if (p.scalar[key] !== state[key]) conflict();
    if (
      p.scalar.direction !== state.direction &&
      (p.delta.kind !== 'none' || p.scalar.selectionComplete)
    )
      conflict();
    if (
      p.scalar.sequenceUpperBound !== state.sequenceUpperBound &&
      (p.scalar.sequenceUpperBound !== MAX_SEQUENCE_NUMBER ||
        (state.sequenceUpperBound !== null &&
          state.sequenceUpperBound <= MAX_SEQUENCE_NUMBER) ||
        state.firstLayout > MAX_SEQUENCE_NUMBER ||
        state.decisions.some((d) => d.rangeEnd > MAX_SEQUENCE_NUMBER))
    )
      conflict();
    if (
      p.scalar.selectionGeneration !==
      state.selectionGeneration + (p.delta.kind === 'clear' ? 1 : 0)
    )
      conflict();
    if (
      p.receipt.currentRelativePath !== p.scalar.currentRelativePath ||
      p.receipt.nextRangeStart !== p.scalar.nextRangeStart ||
      p.receipt.selectionComplete !== p.scalar.selectionComplete
    )
      conflict();
    const decisions = state.decisions;
    if (p.delta.kind === 'append') {
      const d = p.delta.decision;
      const range = rangeForStart(d.rangeStart, p.scalar.sequenceUpperBound);
      if (
        d.operationId !== p.operationId ||
        d.selectionGeneration !== state.selectionGeneration ||
        d.sourceIndex >= this.inventory.length ||
        d.rangeEnd !== range.end ||
        d.rangeStart !== state.nextRangeStart ||
        (d.action === 'accepted' &&
          d.imagePath !== this.inventory[d.sourceIndex].relativePath)
      )
        conflict();
      decisions.push(d);
    } else if (p.delta.kind === 'pop') {
      if (
        stableStringify(decisions.at(-1)) !== stableStringify(p.delta.decision)
      )
        conflict();
      decisions.pop();
    } else if (p.delta.kind === 'clear') decisions.length = 0;
    if (p.receipt.decisionCount !== decisions.length) conflict();
    const last = decisions.at(-1);
    const terminal = last
      ? isManualSelectionRangeTerminal(
          p.scalar.direction,
          last.rangeStart,
          last.rangeEnd,
          p.scalar.sequenceUpperBound,
        )
      : false;
    // A range edit may reopen a terminal selection. Decisions still determine
    // completion when appended; undo and restart always reopen the cursor.
    if (
      (p.delta.kind === 'append' && p.scalar.selectionComplete !== terminal) ||
      (p.scalar.selectionComplete && !terminal) ||
      ((p.delta.kind === 'pop' || p.delta.kind === 'clear') &&
        p.scalar.selectionComplete)
    )
      conflict();
    state.receipts[p.operationId] = p.receipt;
    return { ...state, ...p.scalar };
  }
  private async replay(
    head: ProjectDiskHead,
    journal?: ProjectCompactJournal,
  ): Promise<ProjectState> {
    let result: ProjectState | undefined;
    let goodPrefix: Buffer | undefined;
    const bad: string[] = [];
    for (const name of ledgers) {
      const bytes = await this.files.read(name);
      let prefixGood = false;
      try {
        if (!bytes || bytes.length < head.ledgerBytes) corrupt();
        const prefix = bytes.subarray(0, head.ledgerBytes);
        let state = this.initial(head);
        let chain = anchor(head);
        const text = prefix.toString('utf8');
        if (text && !text.endsWith('\n')) corrupt();
        for (const line of text.split('\n').slice(0, -1)) {
          const record = decodeRecord(`${line}\n`);
          if (record.previousHash !== chain) conflict();
          state = this.applyRecord(state, record);
          chain = record.checksumSha256;
        }
        if (
          chain !== head.ledgerHash ||
          state.revision !== head.revision ||
          stableStringify(scalarFor(state)) !== stableStringify(head.scalar)
        )
          corrupt();
        prefixGood = true;
        const tail = bytes.subarray(head.ledgerBytes);
        const pending =
          journal && headIdentity(head) === headIdentity(journal.before)
            ? Buffer.from(journal.record)
            : Buffer.alloc(0);
        if (
          tail.length > pending.length ||
          !tail.equals(pending.subarray(0, tail.length))
        )
          conflict('Nieznane bajty poza zatwierdzoną historią operacji.');
        result ??= state;
        goodPrefix ??= prefix;
        this.stats.set(name, await this.files.identity(name));
      } catch (error) {
        if (!(error instanceof SelectorError)) throw error;
        if (prefixGood) throw error;
        bad.push(name);
      }
    }
    if (!result || !goodPrefix) corrupt();
    for (const name of bad) this.repairs.set(name, goodPrefix);
    return result;
  }
  async repair(checkpoint: WriteCheckpoint): Promise<void> {
    // Caller has already proved source/project identity and complete output agreement.
    for (const [name, bytes] of this.repairs) {
      await this.files.replace(name, bytes, checkpoint);
      if (ledgers.includes(name))
        this.stats.set(name, await this.files.identity(name));
    }
    this.repairs.clear();
  }
  makeJournal(
    journal: ProjectJournal,
    receipt: ProjectState['receipts'][string],
  ): ProjectCompactJournal {
    const after = journal.after;
    const record = recordFor(
      {
        projectId: after.projectId,
        operationId: journal.operationId,
        previousRevision: this.head.revision,
        receipt,
        scalar: scalarFor(after),
        delta: deltaFor(journal.before!, after),
      },
      this.head.ledgerHash,
    );
    const parsed = decodeRecord(record);
    validateEffects(journal, parsed.payload.delta);
    const head: ProjectDiskHead = {
      ...this.head,
      scalar: scalarFor(after),
      revision: after.revision,
      sourceRoot: after.sourceRoot,
      outputRoot: after.outputRoot,
      ledgerBytes: this.head.ledgerBytes + Buffer.byteLength(record),
      ledgerHash: parsed.checksumSha256,
    };
    return {
      schemaVersion: 3,
      mode: 'operation',
      projectId: after.projectId,
      phase: journal.phase,
      before: this.head,
      after: head,
      operationId: journal.operationId,
      record,
      copy: journal.copy,
      removals: journal.removals,
    };
  }
  validateJournal(journal: ProjectCompactJournal): void {
    validateCompactJournalStructure(journal);
    if (
      journal.projectId !== this.head.projectId ||
      journal.before.projectId !== journal.projectId ||
      journal.after.projectId !== journal.projectId ||
      journal.before.inventoryHash !== this.head.inventoryHash ||
      journal.before.baselineHash !== this.head.baselineHash ||
      journal.after.inventoryHash !== this.head.inventoryHash ||
      journal.after.baselineHash !== this.head.baselineHash
    )
      conflict();
    const record = decodeRecord(journal.record);
    if (
      record.previousHash !== journal.before.ledgerHash ||
      record.checksumSha256 !== journal.after.ledgerHash ||
      journal.after.ledgerBytes !==
        journal.before.ledgerBytes + Buffer.byteLength(journal.record) ||
      record.payload.projectId !== journal.projectId ||
      record.payload.operationId !== journal.operationId ||
      record.payload.previousRevision !== journal.before.revision ||
      stableStringify(record.payload.scalar) !==
        stableStringify(journal.after.scalar)
    )
      conflict();
  }
  async hydrate(journal: ProjectCompactJournal): Promise<ProjectJournal> {
    this.validateJournal(journal);
    const before = await this.replay(journal.before, journal);
    const record = decodeRecord(journal.record);
    const after = this.applyRecord(
      {
        ...before,
        decisions: [...before.decisions],
        receipts: Object.assign(Object.create(null), before.receipts),
      },
      record,
    );
    after.sourceRoot = journal.after.sourceRoot;
    after.outputRoot = journal.after.outputRoot;
    // Full validation is recovery-only, never a hot-operation scan.
    validateState(after);
    const logical: ProjectJournal = {
      schemaVersion: 1,
      projectId: journal.projectId,
      operationId: journal.operationId,
      phase: journal.phase,
      before,
      after,
      copy: journal.copy,
      removals: journal.removals,
    };
    validateEffects(logical, record.payload.delta);
    return logical;
  }
  async saveJournal(
    journal: ProjectCompactJournal,
    checkpoint: WriteCheckpoint,
  ): Promise<void> {
    this.validateJournal(journal);
    await this.files.replace(
      PROJECT_JOURNAL_NAME,
      encodeEnvelope(journal),
      checkpoint,
    );
  }
  async commit(
    journal: ProjectCompactJournal,
    checkpoint: WriteCheckpoint,
  ): Promise<void> {
    this.validateJournal(journal);
    for (const name of ledgers) {
      const stat = await this.files.appendExact(
        name,
        journal.before.ledgerBytes,
        journal.record,
        this.stats.get(name),
        checkpoint,
      );
      this.stats.set(name, stat);
    }
    await this.files.replace(
      PROJECT_STATE_NAME,
      encodeEnvelope(journal.after),
      checkpoint,
    );
    this.head = journal.after;
  }
  async backup(checkpoint: WriteCheckpoint): Promise<void> {
    await this.files.replace(
      PROJECT_BACKUP_NAME,
      encodeEnvelope(this.head),
      checkpoint,
    );
  }
}
export function isCompactIntent(
  value: ProjectJournal | CompactIntent,
): value is CompactIntent {
  return value.schemaVersion === 3;
}

import {
  rangeForStart,
  isManualSelectionRangeTerminal,
} from '@game-predictor/manual-image-selection-core';
import { SelectorError } from '../contracts.ts';
import { checksum, stableStringify } from '../filesystem/secure-files.ts';
import { containedPath } from '../native/path-security.ts';
import {
  type OperationReceipt,
  type ProjectCompactJournal,
  type ProjectDecision,
  type ProjectDiskHead,
  type ProjectJournal,
  type ProjectLedgerRecord,
  type ProjectScalar,
  type ProjectState,
  type ProjectUpgradeJournal,
} from './types.ts';

export const PROJECT_STATE_NAME = 'selector-project-v1.json';
export const PROJECT_BACKUP_NAME = 'selector-project-v1.backup.json';
export const PROJECT_JOURNAL_NAME = 'selector-journal-v1.json';
export function encodeEnvelope(value: unknown): string {
  return stableStringify({
    checksumSha256: checksum(stableStringify(value)),
    value,
  });
}
export function decodeEnvelope<T>(bytes: Buffer): T {
  try {
    const parsed = JSON.parse(bytes.toString()) as {
      checksumSha256: string;
      value: T;
    };
    if (parsed.checksumSha256 !== checksum(stableStringify(parsed.value)))
      throw new Error('checksum');
    return parsed.value;
  } catch {
    throw new SelectorError(
      'PROJECT_CORRUPT',
      'Plik projektu lub dziennika jest uszkodzony.',
    );
  }
}
export function validateState(state: ProjectState): void {
  if (
    state &&
    typeof state.schemaVersion === 'number' &&
    state.schemaVersion !== 1
  )
    throw new SelectorError(
      'UNSUPPORTED_PROJECT_SCHEMA',
      'Wersja projektu wymaga zgodnej wersji aplikacji. Projekt nie został nadpisany.',
    );
  try {
    validateStateStructure(state);
  } catch (error) {
    if (error instanceof SelectorError) throw error;
    throw new SelectorError(
      'PROJECT_CORRUPT',
      'Nieprawidłowy format projektu.',
    );
  }
}

/** Validate only scalar metadata; callers supply an already verified path index. */
export function validateScalar(
  scalar: ProjectScalar,
  pathSet?: ReadonlySet<string>,
): void {
  const invalid = () => {
    throw new SelectorError(
      'PROJECT_CORRUPT',
      'Nieprawidłowe metadane projektu.',
    );
  };
  if (
    !scalar ||
    scalar.schemaVersion !== 1 ||
    typeof scalar.projectId !== 'string' ||
    !/^[a-f0-9-]{36}$/.test(scalar.projectId) ||
    !Number.isSafeInteger(scalar.revision) ||
    scalar.revision < 0 ||
    !Number.isSafeInteger(scalar.selectionGeneration) ||
    scalar.selectionGeneration < 0 ||
    typeof scalar.sourceDirectoryName !== 'string' ||
    (scalar.gameName !== undefined &&
      (typeof scalar.gameName !== 'string' ||
        !scalar.gameName.trim() ||
        scalar.gameName !== scalar.gameName.trim() ||
        scalar.gameName.length > 80 ||
        /[\u0000-\u001f\u007f]/.test(scalar.gameName))) ||
    typeof scalar.sourceManifestChecksumSha256 !== 'string' ||
    !/^[a-f0-9]{64}$/.test(scalar.sourceManifestChecksumSha256) ||
    typeof scalar.updatedAt !== 'string' ||
    !Number.isFinite(Date.parse(scalar.updatedAt)) ||
    (scalar.direction !== 'ascending' && scalar.direction !== 'descending') ||
    typeof scalar.selectionComplete !== 'boolean' ||
    !Number.isSafeInteger(scalar.nextRangeStart) ||
    scalar.nextRangeStart < 1 ||
    typeof scalar.currentRelativePath !== 'string' ||
    (pathSet !== undefined && !pathSet.has(scalar.currentRelativePath))
  )
    invalid();
  try {
    rangeForStart(scalar.firstLayout, scalar.sequenceUpperBound);
    if (!scalar.selectionComplete)
      rangeForStart(scalar.nextRangeStart, scalar.sequenceUpperBound);
  } catch {
    invalid();
  }
}

function validateReceiptStructure(
  receipt: OperationReceipt,
  revision: number,
): void {
  if (
    !receipt ||
    typeof receipt.fingerprint !== 'string' ||
    !/^[a-f0-9]{64}$/.test(receipt.fingerprint) ||
    !Number.isSafeInteger(receipt.revision) ||
    receipt.revision < 1 ||
    receipt.revision > revision ||
    !Number.isSafeInteger(receipt.nextRangeStart) ||
    receipt.nextRangeStart < 1 ||
    !Number.isSafeInteger(receipt.decisionCount) ||
    receipt.decisionCount < 0 ||
    typeof receipt.selectionComplete !== 'boolean' ||
    typeof receipt.currentRelativePath !== 'string'
  )
    throw new SelectorError('PROJECT_CORRUPT', 'Nieprawidłowy wynik operacji.');
}

export function validateReceipt(
  receipt: OperationReceipt,
  revision: number,
  pathSet: ReadonlySet<string>,
): void {
  validateReceiptStructure(receipt, revision);
  if (!pathSet.has(receipt.currentRelativePath!))
    throw new SelectorError(
      'PROJECT_CORRUPT',
      'Wynik operacji wskazuje obce zdjęcie.',
    );
}

const scalarKeys = [
  'schemaVersion',
  'projectId',
  'revision',
  'sourceDirectoryName',
  'sourceManifestChecksumSha256',
  'firstLayout',
  'direction',
  'sequenceUpperBound',
  'currentRelativePath',
  'nextRangeStart',
  'selectionComplete',
  'selectionGeneration',
  'updatedAt',
];
const receiptKeys = [
  'fingerprint',
  'revision',
  'currentRelativePath',
  'nextRangeStart',
  'selectionComplete',
  'decisionCount',
];
const decisionKeys = [
  'action',
  'operationId',
  'fileId',
  'sourceIndex',
  'imagePath',
  'imageChecksumSha256',
  'outputName',
  'rangeStart',
  'rangeEnd',
  'selectionGeneration',
  'activeBoardCount',
];

function assertShape(
  value: unknown,
  required: string[],
  optional: string[] = [],
): void {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('object');
  const keys = Object.keys(value);
  if (
    required.some((key) => !Object.hasOwn(value, key)) ||
    keys.some((key) => !required.includes(key) && !optional.includes(key))
  )
    throw new Error('shape');
}

function isHash(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
}

function validateDiskHeadStructure(head: ProjectDiskHead): void {
  assertShape(head, [
    'schemaVersion',
    'projectId',
    'inventoryHash',
    'baselineHash',
    'ledgerBytes',
    'ledgerHash',
    'revision',
    'sourceRoot',
    'outputRoot',
    'scalar',
  ]);
  assertShape(head.scalar, scalarKeys, ['gameName']);
  validateScalar(head.scalar);
  if (
    head.schemaVersion !== 2 ||
    head.projectId !== head.scalar.projectId ||
    head.revision !== head.scalar.revision ||
    !isHash(head.inventoryHash) ||
    !isHash(head.baselineHash) ||
    !isHash(head.ledgerHash) ||
    !Number.isSafeInteger(head.ledgerBytes) ||
    head.ledgerBytes < 0 ||
    typeof head.sourceRoot !== 'string' ||
    typeof head.outputRoot !== 'string'
  )
    throw new Error('head');
}

export function validateDiskHead(head: ProjectDiskHead): void {
  try {
    validateDiskHeadStructure(head);
  } catch {
    throw new SelectorError(
      'PROJECT_CORRUPT',
      'Nieprawidłowy nagłówek projektu.',
    );
  }
}

function validateDecisionStructure(decision: ProjectDecision): void {
  assertShape(decision, decisionKeys);
  if (
    !Number.isSafeInteger(decision.sourceIndex) ||
    decision.sourceIndex < 0 ||
    typeof decision.operationId !== 'string' ||
    !Number.isSafeInteger(decision.selectionGeneration) ||
    decision.selectionGeneration < 0 ||
    !Number.isSafeInteger(decision.rangeStart) ||
    decision.rangeStart < 1 ||
    !Number.isSafeInteger(decision.rangeEnd) ||
    decision.rangeEnd < decision.rangeStart ||
    decision.rangeEnd - decision.rangeStart > 8 ||
    decision.activeBoardCount !== decision.rangeEnd - decision.rangeStart + 1
  )
    throw new Error('decision');
  if (decision.action === 'accepted') {
    if (
      typeof decision.fileId !== 'string' ||
      typeof decision.imagePath !== 'string' ||
      !isHash(decision.imageChecksumSha256) ||
      decision.outputName !==
        `seq_${decision.rangeStart}-${decision.rangeEnd}.jpg`
    )
      throw new Error('accepted');
    containedPath('.', decision.imagePath);
  } else if (
    decision.action !== 'skipped' ||
    decision.fileId !== null ||
    decision.imagePath !== null ||
    decision.imageChecksumSha256 !== null ||
    decision.outputName !== null
  )
    throw new Error('skipped');
}

function validateLedgerStructure(record: ProjectLedgerRecord): void {
  assertShape(record, ['previousHash', 'payload', 'checksumSha256']);
  if (!isHash(record.previousHash) || !isHash(record.checksumSha256))
    throw new Error('hash');
  const payload = record.payload;
  assertShape(payload, [
    'projectId',
    'operationId',
    'previousRevision',
    'receipt',
    'scalar',
    'delta',
  ]);
  assertShape(payload.scalar, scalarKeys, ['gameName']);
  validateScalar(payload.scalar);
  assertShape(payload.receipt, receiptKeys);
  validateReceiptStructure(payload.receipt, payload.scalar.revision);
  if (
    typeof payload.projectId !== 'string' ||
    !/^[a-f0-9-]{36}$/.test(payload.projectId) ||
    typeof payload.operationId !== 'string' ||
    !/^[a-zA-Z0-9_-]{8,128}$/.test(payload.operationId) ||
    !Number.isSafeInteger(payload.previousRevision) ||
    payload.previousRevision < 0 ||
    !payload.delta
  )
    throw new Error('payload');
  switch (payload.delta.kind) {
    case 'none':
    case 'clear':
      assertShape(payload.delta, ['kind']);
      break;
    case 'append':
    case 'pop':
      assertShape(payload.delta, ['kind', 'decision']);
      validateDecisionStructure(payload.delta.decision);
      break;
    default:
      throw new Error('delta');
  }
}

/** Lineage, hashes and inventory-dependent checks belong to project storage. */
export function validateLedgerRecordStructure(
  record: ProjectLedgerRecord,
): void {
  try {
    validateLedgerStructure(record);
  } catch {
    throw new SelectorError(
      'PROJECT_CORRUPT',
      'Nieprawidłowy wpis historii projektu.',
    );
  }
}

function validateCopyStructure(copy: ProjectCompactJournal['copy']): void {
  if (copy === null) return;
  assertShape(copy, ['imagePath', 'outputName', 'checksumSha256', 'sizeBytes']);
  if (
    typeof copy.imagePath !== 'string' ||
    typeof copy.outputName !== 'string' ||
    !/^seq_\d+-\d+\.jpg$/.test(copy.outputName) ||
    !isHash(copy.checksumSha256) ||
    !Number.isSafeInteger(copy.sizeBytes) ||
    copy.sizeBytes < 0
  )
    throw new Error('copy');
  containedPath('.', copy.imagePath);
}

/** Cheap structure validation; replay and ownership need verified storage context. */
export function validateCompactJournalStructure(
  journal: ProjectCompactJournal | ProjectUpgradeJournal,
): void {
  try {
    if (
      !journal ||
      journal.schemaVersion !== 3 ||
      typeof journal.projectId !== 'string' ||
      !/^[a-f0-9-]{36}$/.test(journal.projectId)
    )
      throw new Error('journal');
    if (journal.mode === 'upgrade') {
      assertShape(journal, [
        'schemaVersion',
        'mode',
        'projectId',
        'state',
        'head',
      ]);
      validateDiskHeadStructure(journal.head);
      validateScalar(journal.state);
      if (
        typeof journal.state.sourceRoot !== 'string' ||
        typeof journal.state.outputRoot !== 'string' ||
        !Array.isArray(journal.state.inventory) ||
        !Array.isArray(journal.state.decisions) ||
        !journal.state.receipts ||
        typeof journal.state.receipts !== 'object' ||
        Array.isArray(journal.state.receipts)
      )
        throw new Error('upgrade');
      return;
    }
    assertShape(journal, [
      'schemaVersion',
      'mode',
      'projectId',
      'phase',
      'before',
      'after',
      'operationId',
      'record',
      'copy',
      'removals',
    ]);
    if (
      journal.mode !== 'operation' ||
      !['prepared', 'jpeg_written', 'committed'].includes(journal.phase) ||
      typeof journal.operationId !== 'string' ||
      !/^[a-zA-Z0-9_-]{8,128}$/.test(journal.operationId) ||
      typeof journal.record !== 'string' ||
      !journal.record.endsWith('\n') ||
      !Array.isArray(journal.removals)
    )
      throw new Error('operation');
    validateDiskHeadStructure(journal.before);
    validateDiskHeadStructure(journal.after);
    const record = JSON.parse(journal.record) as ProjectLedgerRecord;
    validateLedgerStructure(record);
    if (journal.record !== `${stableStringify(record)}\n`)
      throw new Error('canonical record');
    validateCopyStructure(journal.copy);
    for (const removal of journal.removals) {
      assertShape(removal, ['outputName', 'checksumSha256']);
      if (
        typeof removal.outputName !== 'string' ||
        !/^seq_\d+-\d+\.jpg$/.test(removal.outputName) ||
        !isHash(removal.checksumSha256)
      )
        throw new Error('removal');
    }
  } catch {
    throw new SelectorError(
      'JOURNAL_CORRUPT',
      'Dziennik ma nieprawidłowy format.',
    );
  }
}

function validateStateStructure(state: ProjectState): void {
  const invalid = () => {
    throw new SelectorError(
      'PROJECT_CORRUPT',
      'Nieprawidłowy format lub spójność projektu.',
    );
  };
  validateScalar(state);
  if (
    typeof state.sourceRoot !== 'string' ||
    typeof state.outputRoot !== 'string' ||
    !Array.isArray(state.inventory) ||
    state.inventory.length < 1 ||
    !Array.isArray(state.decisions) ||
    !state.receipts ||
    typeof state.receipts !== 'object' ||
    Array.isArray(state.receipts)
  )
    invalid();
  const paths = new Set<string>();
  for (const item of state.inventory) {
    try {
      containedPath(state.sourceRoot, item.relativePath);
    } catch {
      invalid();
    }
    if (
      paths.has(item.relativePath) ||
      item.name !== item.relativePath.split('/').at(-1) ||
      !/\.jpe?g$/i.test(item.name) ||
      !Number.isSafeInteger(item.sizeBytes) ||
      item.sizeBytes < 0 ||
      !Number.isSafeInteger(item.lastModifiedMs) ||
      item.lastModifiedMs < 0 ||
      typeof item.mimeType !== 'string'
    )
      invalid();
    paths.add(item.relativePath);
  }
  for (const [operationId, receipt] of Object.entries(state.receipts)) {
    if (!/^[a-zA-Z0-9_-]{8,128}$/.test(operationId)) invalid();
    validateReceipt(receipt, state.revision, paths);
  }
  if (
    typeof state.currentRelativePath !== 'string' ||
    !paths.has(state.currentRelativePath)
  )
    invalid();
  const outputs = new Set<string>();
  const acceptedPaths = new Set<string>();
  for (const decision of state.decisions) {
    let range;
    try {
      range = rangeForStart(decision.rangeStart, state.sequenceUpperBound);
    } catch {
      invalid();
    }
    if (
      decision.rangeEnd !== range!.end ||
      decision.activeBoardCount !==
        decision.rangeEnd - decision.rangeStart + 1 ||
      !Number.isSafeInteger(decision.sourceIndex) ||
      decision.sourceIndex < 0 ||
      decision.sourceIndex >= state.inventory.length ||
      typeof decision.operationId !== 'string' ||
      !Number.isSafeInteger(decision.selectionGeneration) ||
      decision.selectionGeneration < 0
    )
      invalid();
    if (decision.action === 'accepted') {
      if (
        decision.imagePath !==
          state.inventory[decision.sourceIndex].relativePath ||
        typeof decision.fileId !== 'string' ||
        typeof decision.imageChecksumSha256 !== 'string' ||
        !/^[a-f0-9]{64}$/.test(decision.imageChecksumSha256) ||
        decision.outputName !==
          `seq_${decision.rangeStart}-${decision.rangeEnd}.jpg` ||
        outputs.has(decision.outputName) ||
        acceptedPaths.has(decision.imagePath)
      )
        invalid();
      outputs.add(decision.outputName!);
      acceptedPaths.add(decision.imagePath!);
    } else if (
      decision.action !== 'skipped' ||
      decision.fileId !== null ||
      decision.imagePath !== null ||
      decision.outputName !== null ||
      decision.imageChecksumSha256 !== null
    )
      invalid();
  }
  const last = state.decisions.at(-1);
  if (
    state.selectionComplete &&
    !(last
      ? isManualSelectionRangeTerminal(
          state.direction,
          last.rangeStart,
          last.rangeEnd,
          state.sequenceUpperBound,
        )
      : false)
  )
    invalid();
}
export function validateJournal(journal: ProjectJournal): void {
  if (
    !journal ||
    (journal.schemaVersion !== 1 && journal.schemaVersion !== 2) ||
    !['prepared', 'jpeg_written', 'committed'].includes(journal.phase) ||
    !Array.isArray(journal.removals)
  )
    throw new SelectorError(
      'JOURNAL_CORRUPT',
      'Dziennik ma nieprawidłowy format.',
    );
  validateState(journal.after);
  if (journal.before !== null) validateState(journal.before);
  if (journal.schemaVersion === 2) {
    const copies = journal.importCopies;
    const decisions = journal.after.decisions.filter(
      (d) => d.action === 'accepted',
    );
    const byOutput = new Map(decisions.map((d) => [d.outputName, d]));
    if (
      journal.before !== null ||
      journal.after.revision !== 0 ||
      Object.keys(journal.after.receipts).length !== 0 ||
      journal.copy !== null ||
      journal.removals.length ||
      !Array.isArray(copies) ||
      copies.some((c) => !c || typeof c !== 'object' || Array.isArray(c)) ||
      copies.length !== decisions.length ||
      new Set(copies.map((c) => c.outputName)).size !== copies.length ||
      copies.some(
        (c) =>
          !Number.isSafeInteger(c.sizeBytes) ||
          c.sizeBytes < 0 ||
          !(() => {
            const d = byOutput.get(c.outputName);
            return (
              d &&
              d.imagePath === c.imagePath &&
              d.imageChecksumSha256 === c.checksumSha256 &&
              journal.after.inventory[d.sourceIndex].sizeBytes === c.sizeBytes
            );
          })(),
      )
    )
      throw new SelectorError(
        'JOURNAL_CORRUPT',
        'Import nie odpowiada pełnej historii projektu.',
      );
  } else if (journal.importCopies !== undefined) {
    throw new SelectorError('JOURNAL_CORRUPT', 'Nieznany format importu.');
  }
  if (
    journal.projectId !== journal.after.projectId ||
    (journal.before !== null &&
      (journal.before.projectId !== journal.projectId ||
        journal.after.revision !== journal.before.revision + 1))
  )
    throw new SelectorError(
      'JOURNAL_CORRUPT',
      'Dziennik należy do innego projektu lub rewizji.',
    );
  if (
    journal.copy &&
    !journal.after.decisions.some(
      (d) =>
        d.action === 'accepted' &&
        d.operationId === journal.operationId &&
        d.imagePath === journal.copy!.imagePath &&
        d.outputName === journal.copy!.outputName &&
        d.imageChecksumSha256 === journal.copy!.checksumSha256,
    )
  )
    throw new SelectorError(
      'JOURNAL_CORRUPT',
      'Zamiar kopiowania nie odpowiada decyzji.',
    );
  for (const removal of journal.removals)
    if (
      !journal.before?.decisions.some(
        (d) =>
          d.action === 'accepted' &&
          d.outputName === removal.outputName &&
          d.imageChecksumSha256 === removal.checksumSha256,
      ) ||
      journal.after.decisions.some((d) => d.outputName === removal.outputName)
    )
      throw new SelectorError(
        'JOURNAL_CORRUPT',
        'Zamiar usunięcia nie ma dowodu własności.',
      );
}

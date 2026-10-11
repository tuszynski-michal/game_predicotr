import {
  rangeForStart,
  isManualSelectionRangeTerminal,
} from '@game-predictor/manual-image-selection-core';
import { SelectorError } from '../contracts.ts';
import { checksum, stableStringify } from '../filesystem/secure-files.ts';
import { containedPath } from '../native/path-security.ts';
import { type ProjectState, type ProjectJournal } from './types.ts';

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
function validateStateStructure(state: ProjectState): void {
  const invalid = () => {
    throw new SelectorError(
      'PROJECT_CORRUPT',
      'Nieprawidłowy format lub spójność projektu.',
    );
  };
  if (
    !state ||
    state.schemaVersion !== 1 ||
    !/^[a-f0-9-]{36}$/.test(state.projectId) ||
    !Number.isSafeInteger(state.revision) ||
    state.revision < 0 ||
    !Number.isSafeInteger(state.selectionGeneration) ||
    state.selectionGeneration < 0 ||
    typeof state.sourceRoot !== 'string' ||
    typeof state.outputRoot !== 'string' ||
    typeof state.sourceDirectoryName !== 'string' ||
    !/^[a-f0-9]{64}$/.test(state.sourceManifestChecksumSha256) ||
    !Array.isArray(state.inventory) ||
    state.inventory.length < 1 ||
    state.inventory.length > 15000 ||
    !Array.isArray(state.decisions) ||
    !state.receipts ||
    typeof state.receipts !== 'object' ||
    Array.isArray(state.receipts) ||
    typeof state.updatedAt !== 'string' ||
    !Number.isFinite(Date.parse(state.updatedAt)) ||
    (state.direction !== 'ascending' && state.direction !== 'descending') ||
    typeof state.selectionComplete !== 'boolean'
  )
    invalid();
  try {
    rangeForStart(state.firstLayout, state.sequenceUpperBound);
    if (!state.selectionComplete)
      rangeForStart(state.nextRangeStart, state.sequenceUpperBound);
  } catch {
    invalid();
  }
  if (!Number.isSafeInteger(state.nextRangeStart) || state.nextRangeStart < 1)
    invalid();
  for (const [operationId, receipt] of Object.entries(state.receipts)) {
    if (
      !/^[a-zA-Z0-9_-]{8,128}$/.test(operationId) ||
      !receipt ||
      !/^[a-f0-9]{64}$/.test(receipt.fingerprint) ||
      !Number.isSafeInteger(receipt.revision) ||
      receipt.revision < 1 ||
      receipt.revision > state.revision ||
      !Number.isSafeInteger(receipt.nextRangeStart) ||
      receipt.nextRangeStart < 1 ||
      !Number.isSafeInteger(receipt.decisionCount) ||
      receipt.decisionCount < 0 ||
      typeof receipt.selectionComplete !== 'boolean' ||
      typeof receipt.currentRelativePath !== 'string' ||
      !state.inventory.some(
        (item) => item.relativePath === receipt.currentRelativePath,
      )
    )
      invalid();
  }
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
    state.selectionComplete !==
    (last
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
    journal.schemaVersion !== 1 ||
    !['prepared', 'jpeg_written', 'committed'].includes(journal.phase) ||
    !Array.isArray(journal.removals)
  )
    throw new SelectorError(
      'JOURNAL_CORRUPT',
      'Dziennik ma nieprawidłowy format.',
    );
  validateState(journal.after);
  if (journal.before !== null) validateState(journal.before);
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

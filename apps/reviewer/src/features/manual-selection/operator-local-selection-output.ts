'use client';

import {
  isManualSelectionRangeTerminal,
  manualRangeActiveBoardCount,
  rangeForStart,
} from '@game-predictor/manual-image-selection-core';

import type {
  RemoteSelectionLocalBatchRecord,
  RemoteSelectionSourceItemRecord,
  RemoteSelectionWorkspaceDecision,
} from './remote-selection-store';

const OPERATOR_LOCAL_MANIFEST_NAME = 'manual-image-selection-output-v1.json';

export interface OperatorLocalOutputManifestV1 {
  readonly schemaVersion: 1;
  readonly storageMode: 'operator_local';
  readonly sessionId: string;
  readonly batchId: string;
  readonly sourceDirectoryName: string;
  readonly sourceManifestChecksumSha256?: string;
  readonly fileCount?: number;
  readonly firstLayout?: number;
  readonly direction?: 'ascending' | 'descending';
  readonly sourceTraversalSemantics?: 'natural_v2';
  readonly decisions: readonly RemoteSelectionWorkspaceDecision[];
  readonly currentIndex: number;
  readonly nextRangeStart: number;
  readonly updatedAt: string;
}

export interface OperatorLocalOutputManifestV2 {
  readonly schemaVersion: 2;
  readonly storageMode: 'operator_local';
  readonly sessionId: string;
  readonly batchId: string;
  readonly sourceDirectoryName: string;
  readonly sourceManifestChecksumSha256?: string;
  readonly fileCount?: number;
  readonly firstLayout: number;
  readonly direction: 'ascending' | 'descending';
  readonly sourceTraversalSemantics?: 'natural_v2';
  readonly sequenceUpperBound: number | null;
  readonly selectionComplete: boolean;
  readonly decisions: readonly (RemoteSelectionWorkspaceDecision & {
    readonly activeBoardCount: number;
  })[];
  readonly currentIndex: number;
  readonly nextRangeStart: number;
  readonly updatedAt: string;
}

export type OperatorLocalOutputManifest =
  OperatorLocalOutputManifestV1 | OperatorLocalOutputManifestV2;

export type OperatorLocalOutputDirectoryState =
  | { readonly kind: 'empty' }
  | {
      readonly kind: 'resumable';
      readonly manifest: OperatorLocalOutputManifest;
    };

export interface OperatorLocalOutputResult {
  readonly checksumSha256: string;
  readonly created: boolean;
  readonly name: string;
}

export async function resetOperatorLocalOutputDirectory(
  parentDirectory: FileSystemDirectoryHandle,
  outputDirectoryName: string,
  source: {
    readonly sourceDirectoryName: string;
    readonly sourceManifestChecksumSha256: string;
    readonly fileCount: number;
  },
): Promise<FileSystemDirectoryHandle> {
  let existing: FileSystemDirectoryHandle | null = null;
  try {
    existing = await parentDirectory.getDirectoryHandle(outputDirectoryName);
  } catch (cause) {
    if (!isNotFoundError(cause)) throw cause;
  }

  if (existing !== null) {
    const state = await inspectOperatorLocalOutputDirectory(existing);
    if (state.kind === 'resumable') {
      assertMatchingSource(state.manifest, source);
      for (const decision of state.manifest.decisions) {
        if (decision.action !== 'accepted') continue;
        await assertOperatorLocalSelectionChecksum(existing, decision);
      }
    }
    try {
      await parentDirectory.removeEntry(outputDirectoryName, {
        recursive: true,
      });
    } catch (cause) {
      if (!isNotFoundError(cause)) throw cause;
    }
  }

  return parentDirectory.getDirectoryHandle(outputDirectoryName, {
    create: true,
  });
}

export async function writeOperatorLocalSelection(
  outputDirectory: FileSystemDirectoryHandle,
  source: File,
  rangeStart: number,
  rangeEnd: number = rangeStart + 8,
  sequenceUpperBound: number | null = null,
): Promise<OperatorLocalOutputResult> {
  let expectedRangeEnd: number | null = null;
  try {
    expectedRangeEnd = rangeForStart(rangeStart, sequenceUpperBound).end;
  } catch {
    expectedRangeEnd = null;
  }
  if (
    !Number.isSafeInteger(rangeStart) ||
    rangeStart < 1 ||
    !Number.isSafeInteger(rangeEnd) ||
    expectedRangeEnd === null ||
    rangeEnd !== expectedRangeEnd
  ) {
    throw new Error(
      'Zakres zapisywanego zdjęcia musi obejmować od 1 do 9 plansz i respektować granicę sesji.',
    );
  }
  const checksumSha256 = await sha256File(source);
  const name = `seq_${rangeStart}-${rangeEnd}.jpg`;
  let existing: File | null = null;
  try {
    existing = await (await outputDirectory.getFileHandle(name)).getFile();
  } catch (cause) {
    if (!(cause instanceof DOMException) || cause.name !== 'NotFoundError') {
      throw cause;
    }
  }
  if (existing !== null) {
    const existingChecksum = await sha256File(existing);
    if (existingChecksum === checksumSha256) {
      return { checksumSha256, created: false, name };
    }
    throw new Error(`Plik ${name} już istnieje i ma inną zawartość.`);
  }
  const handle = await outputDirectory.getFileHandle(name, { create: true });
  const writable = await handle.createWritable();
  try {
    await writable.write(source);
    await writable.close();
  } catch (cause) {
    await writable.abort().catch(() => undefined);
    throw cause;
  }
  if ((await sha256File(await handle.getFile())) !== checksumSha256) {
    throw new Error(`Weryfikacja zapisu pliku ${name} nie powiodła się.`);
  }
  return { checksumSha256, created: true, name };
}

export async function removeOperatorLocalSelection(
  outputDirectory: FileSystemDirectoryHandle,
  decision: RemoteSelectionWorkspaceDecision,
): Promise<void> {
  if (decision.outputName === null || decision.imageChecksumSha256 === null)
    return;
  await assertOperatorLocalSelectionChecksum(outputDirectory, decision);
  await outputDirectory.removeEntry(decision.outputName);
}

export async function writeOperatorLocalManifest(
  outputDirectory: FileSystemDirectoryHandle,
  input: {
    readonly sessionId: string;
    readonly batchId: string;
    readonly sourceDirectoryName: string;
    readonly decisions: readonly RemoteSelectionWorkspaceDecision[];
    readonly currentIndex: number;
    readonly nextRangeStart: number;
    readonly sourceManifestChecksumSha256: string;
    readonly fileCount: number;
    readonly firstLayout: number;
    readonly direction: 'ascending' | 'descending';
    readonly sequenceUpperBound?: number | null;
    readonly selectionComplete?: boolean;
    readonly allowSessionAdoption?: boolean;
  },
): Promise<void> {
  const lastDecision = input.decisions.at(-1);
  const expectedSelectionComplete =
    lastDecision === undefined
      ? false
      : isManualSelectionRangeTerminal(
          input.direction,
          lastDecision.rangeStart,
          lastDecision.rangeEnd,
          input.sequenceUpperBound ?? null,
        );
  if ((input.selectionComplete === true) !== expectedSelectionComplete) {
    throw new Error('Stan zakończenia nie odpowiada ostatniej decyzji.');
  }
  try {
    const existing = await (
      await outputDirectory.getFileHandle(OPERATOR_LOCAL_MANIFEST_NAME)
    ).getFile();
    const parsed = parseOperatorLocalManifest(await existing.text());
    if (
      (parsed.sessionId !== input.sessionId ||
        parsed.batchId !== input.batchId) &&
      input.allowSessionAdoption !== true
    ) {
      throw new Error(
        'Folder wynikowy zawiera manifest należący do innej sesji.',
      );
    }
    assertMatchingSource(parsed, input);
  } catch (cause) {
    if (!(cause instanceof DOMException) || cause.name !== 'NotFoundError') {
      if (cause instanceof SyntaxError) {
        throw new Error('Folder wynikowy zawiera uszkodzony obcy manifest.');
      }
      throw cause;
    }
  }
  const handle = await outputDirectory.getFileHandle(
    OPERATOR_LOCAL_MANIFEST_NAME,
    {
      create: true,
    },
  );
  const writable = await handle.createWritable();
  try {
    await writable.write(
      JSON.stringify(
        {
          schemaVersion: 2,
          storageMode: 'operator_local',
          ...input,
          allowSessionAdoption: undefined,
          sourceTraversalSemantics: 'natural_v2',
          decisions: input.decisions.map((decision) => ({
            ...decision,
            activeBoardCount: manualRangeActiveBoardCount(
              decision.rangeStart,
              decision.rangeEnd,
            ),
          })),
          selectionComplete: input.selectionComplete === true,
          sequenceUpperBound: input.sequenceUpperBound ?? null,
          updatedAt: new Date().toISOString(),
        },
        null,
        2,
      ),
    );
    await writable.close();
  } catch (cause) {
    await writable.abort().catch(() => undefined);
    throw cause;
  }
}

export async function inspectOperatorLocalOutputDirectory(
  outputDirectory: FileSystemDirectoryHandle,
): Promise<OperatorLocalOutputDirectoryState> {
  const entries = new Map<string, FileSystemHandle>();
  for await (const [name, handle] of outputDirectory.entries()) {
    entries.set(name, handle);
  }
  if (entries.size === 0) return { kind: 'empty' };

  const manifestHandle = entries.get(OPERATOR_LOCAL_MANIFEST_NAME);
  if (manifestHandle?.kind !== 'file') {
    throw new Error(
      'Folder wynikowy nie jest pusty i nie zawiera danych pozwalających wznowić selekcję.',
    );
  }
  let manifest: OperatorLocalOutputManifest;
  try {
    manifest = parseOperatorLocalManifest(
      await (manifestHandle as FileSystemFileHandle)
        .getFile()
        .then((file) => file.text()),
    );
  } catch (cause) {
    if (cause instanceof SyntaxError) {
      throw new Error('Folder wynikowy zawiera uszkodzony manifest.');
    }
    throw cause;
  }

  const expectedNames = new Set([OPERATOR_LOCAL_MANIFEST_NAME]);
  for (const decision of manifest.decisions) {
    if (decision.action !== 'accepted' || decision.outputName === null)
      continue;
    expectedNames.add(decision.outputName);
    if (entries.get(decision.outputName)?.kind !== 'file') {
      throw new Error(
        `Folder wynikowy nie zawiera zapisanego pliku ${decision.outputName}.`,
      );
    }
  }
  const unexpected = [...entries.keys()].filter(
    (name) => !expectedNames.has(name),
  );
  if (unexpected.length > 0) {
    throw new Error(
      `Folder wynikowy zawiera obce dane: ${unexpected.slice(0, 3).join(', ')}. Wybierz pusty folder albo folder tej selekcji.`,
    );
  }
  return { kind: 'resumable', manifest };
}

/**
 * Validate a resumable result before it is adopted by another access link.
 * The light-weight inspection above is used while writing; resume additionally
 * proves that every managed JPEG still has the checksum recorded in its manifest.
 */
export async function verifyOperatorLocalOutputDirectory(
  outputDirectory: FileSystemDirectoryHandle,
): Promise<OperatorLocalOutputDirectoryState> {
  const state = await inspectOperatorLocalOutputDirectory(outputDirectory);
  if (state.kind === 'empty') return state;
  for (const decision of state.manifest.decisions) {
    if (decision.action !== 'accepted') continue;
    await assertOperatorLocalSelectionChecksum(outputDirectory, decision);
  }
  return state;
}

export async function resumeOperatorLocalBatch(
  manifest: OperatorLocalOutputManifest,
  batch: RemoteSelectionLocalBatchRecord,
  loadSourceItem: (
    ordinal: number,
  ) => Promise<RemoteSelectionSourceItemRecord | null>,
): Promise<RemoteSelectionLocalBatchRecord> {
  assertMatchingSource(manifest, batch);
  if (manifest.currentIndex >= batch.fileCount) {
    throw new Error('Zapisana pozycja zdjęcia wykracza poza folder źródłowy.');
  }
  const decisions: RemoteSelectionWorkspaceDecision[] = [];
  for (const decision of manifest.decisions) {
    if (decision.sourceIndex >= batch.fileCount) {
      throw new Error('Manifest wskazuje zdjęcie spoza folderu źródłowego.');
    }
    if (decision.action === 'skipped') {
      decisions.push(decision);
      continue;
    }
    const source = await loadSourceItem(decision.sourceIndex);
    if (source === null || source.relativePath !== decision.imagePath) {
      throw new Error(
        `Zdjęcie ${decision.imagePath} nie znajduje się na zapisanej pozycji źródła.`,
      );
    }
    decisions.push({ ...decision, fileId: source.fileId });
  }
  const direction = manifest.direction ?? batch.direction;
  const lastAcceptedDecision = [...decisions]
    .reverse()
    .find((decision) => decision.action === 'accepted');
  const cursorIndex =
    direction === 'descending' &&
    manifest.sourceTraversalSemantics !== 'natural_v2'
      ? Math.min(
          (lastAcceptedDecision?.sourceIndex ?? -1) + 1,
          batch.fileCount - 1,
        )
      : manifest.currentIndex;
  return {
    ...batch,
    cursorIndex,
    decisions,
    direction,
    firstLayout:
      manifest.firstLayout ??
      decisions[0]?.rangeStart ??
      manifest.nextRangeStart,
    hostRegistered: true,
    nextRangeStart: manifest.nextRangeStart,
    selectionComplete:
      manifest.schemaVersion === 2 ? manifest.selectionComplete : false,
    sequenceUpperBound:
      manifest.schemaVersion === 2 ? manifest.sequenceUpperBound : null,
    sourceTraversalSemantics: 'natural_v2',
    status: 'active',
    updatedAt: new Date().toISOString(),
  };
}

function parseOperatorLocalManifest(
  value: string,
): OperatorLocalOutputManifest {
  const parsed = JSON.parse(value) as Record<string, unknown>;
  if (
    (parsed.schemaVersion !== 1 && parsed.schemaVersion !== 2) ||
    parsed.storageMode !== 'operator_local' ||
    typeof parsed.sessionId !== 'string' ||
    parsed.sessionId === '' ||
    typeof parsed.batchId !== 'string' ||
    parsed.batchId === '' ||
    typeof parsed.sourceDirectoryName !== 'string' ||
    parsed.sourceDirectoryName.trim() === '' ||
    !Number.isSafeInteger(parsed.currentIndex) ||
    (parsed.currentIndex as number) < 0 ||
    !Number.isSafeInteger(parsed.nextRangeStart) ||
    (parsed.nextRangeStart as number) < 1 ||
    !Array.isArray(parsed.decisions)
  ) {
    throw new Error('Folder wynikowy zawiera nieprawidłowy manifest.');
  }
  const schemaVersion = parsed.schemaVersion as 1 | 2;
  if (
    parsed.sourceManifestChecksumSha256 !== undefined &&
    (typeof parsed.sourceManifestChecksumSha256 !== 'string' ||
      !/^[a-f0-9]{64}$/.test(parsed.sourceManifestChecksumSha256))
  ) {
    throw new Error('Manifest zawiera nieprawidłową sumę źródła.');
  }
  if (
    parsed.fileCount !== undefined &&
    (!Number.isSafeInteger(parsed.fileCount) ||
      (parsed.fileCount as number) < 1)
  ) {
    throw new Error('Manifest zawiera nieprawidłową liczbę zdjęć.');
  }
  if (
    parsed.firstLayout !== undefined &&
    (!Number.isSafeInteger(parsed.firstLayout) ||
      (parsed.firstLayout as number) < 1)
  ) {
    throw new Error('Manifest zawiera nieprawidłowy pierwszy zakres.');
  }
  if (
    parsed.direction !== undefined &&
    parsed.direction !== 'ascending' &&
    parsed.direction !== 'descending'
  ) {
    throw new Error('Manifest zawiera nieprawidłową kolejność zdjęć.');
  }
  if (
    parsed.sourceTraversalSemantics !== undefined &&
    parsed.sourceTraversalSemantics !== 'natural_v2'
  ) {
    throw new Error('Manifest zawiera nieprawidłową kolejność źródła.');
  }

  const sequenceUpperBound =
    schemaVersion === 2 ? parsed.sequenceUpperBound : null;
  if (
    schemaVersion === 2 &&
    (!Number.isSafeInteger(parsed.firstLayout) ||
      (parsed.firstLayout as number) < 1 ||
      (parsed.direction !== 'ascending' && parsed.direction !== 'descending') ||
      typeof parsed.selectionComplete !== 'boolean' ||
      !('sequenceUpperBound' in parsed) ||
      (sequenceUpperBound !== null &&
        (!Number.isSafeInteger(sequenceUpperBound) ||
          (sequenceUpperBound as number) < (parsed.firstLayout as number))))
  ) {
    throw new Error('Manifest v2 zawiera nieprawidłową granicę plansz.');
  }

  const decisions = parsed.decisions.map((decision, index) =>
    parseDecision(decision, index, schemaVersion, sequenceUpperBound),
  );
  if (schemaVersion === 2) {
    const lastDecision = decisions.at(-1);
    const expectedSelectionComplete =
      lastDecision === undefined
        ? false
        : isManualSelectionRangeTerminal(
            parsed.direction as 'ascending' | 'descending',
            lastDecision.rangeStart,
            lastDecision.rangeEnd,
            sequenceUpperBound as number | null,
          );
    if (parsed.selectionComplete !== expectedSelectionComplete) {
      throw new Error('Manifest v2 ma nieprawidłowy stan zakończenia.');
    }
  }
  return {
    ...(parsed as unknown as OperatorLocalOutputManifest),
    decisions,
  } as OperatorLocalOutputManifest;
}

function parseDecision(
  value: unknown,
  index: number,
  schemaVersion: 1 | 2,
  sequenceUpperBound: unknown,
): RemoteSelectionWorkspaceDecision & { readonly activeBoardCount?: number } {
  if (typeof value !== 'object' || value === null) {
    throw new Error(`Manifest zawiera nieprawidłową decyzję ${index + 1}.`);
  }
  const decision = value as Record<string, unknown>;
  const accepted = decision.action === 'accepted';
  if (
    (!accepted && decision.action !== 'skipped') ||
    typeof decision.operationId !== 'string' ||
    !Number.isSafeInteger(decision.sourceIndex) ||
    (decision.sourceIndex as number) < 0 ||
    !Number.isSafeInteger(decision.rangeStart) ||
    (decision.rangeStart as number) < 1 ||
    !Number.isSafeInteger(decision.rangeEnd) ||
    (decision.rangeEnd as number) < (decision.rangeStart as number) ||
    (decision.rangeEnd as number) - (decision.rangeStart as number) > 8 ||
    !Number.isSafeInteger(decision.selectionGeneration) ||
    (accepted &&
      (typeof decision.fileId !== 'string' ||
        typeof decision.imagePath !== 'string' ||
        typeof decision.outputName !== 'string' ||
        typeof decision.imageChecksumSha256 !== 'string' ||
        !/^[a-f0-9]{64}$/.test(decision.imageChecksumSha256))) ||
    (!accepted &&
      (decision.fileId !== null ||
        decision.imagePath !== null ||
        decision.outputName !== null ||
        decision.imageChecksumSha256 !== null))
  ) {
    throw new Error(`Manifest zawiera nieprawidłową decyzję ${index + 1}.`);
  }
  if (
    (schemaVersion === 1 &&
      decision.rangeEnd !== (decision.rangeStart as number) + 8) ||
    (schemaVersion === 2 &&
      (decision.rangeEnd !==
        rangeForStart(
          decision.rangeStart as number,
          sequenceUpperBound as number | null,
        ).end ||
        decision.activeBoardCount !==
          manualRangeActiveBoardCount(
            decision.rangeStart as number,
            decision.rangeEnd as number,
          )))
  ) {
    throw new Error(`Manifest zawiera nieprawidłowy zakres ${index + 1}.`);
  }
  if (
    accepted &&
    decision.outputName !==
      `seq_${decision.rangeStart}-${decision.rangeEnd}.jpg`
  ) {
    throw new Error(
      `Manifest zawiera nieprawidłową nazwę decyzji ${index + 1}.`,
    );
  }
  return decision as unknown as RemoteSelectionWorkspaceDecision & {
    readonly activeBoardCount?: number;
  };
}

function assertMatchingSource(
  existing: OperatorLocalOutputManifest,
  input: {
    readonly sourceDirectoryName: string;
    readonly sourceManifestChecksumSha256: string;
    readonly fileCount: number;
  },
): void {
  if (existing.sourceDirectoryName !== input.sourceDirectoryName) {
    throw new Error('Manifest należy do innego folderu źródłowego.');
  }
  if (
    existing.sourceManifestChecksumSha256 !== undefined &&
    existing.sourceManifestChecksumSha256 !== input.sourceManifestChecksumSha256
  ) {
    throw new Error('Folder źródłowy zmienił się od zapisania selekcji.');
  }
  if (
    existing.fileCount !== undefined &&
    existing.fileCount !== input.fileCount
  ) {
    throw new Error('Liczba zdjęć źródłowych nie zgadza się z manifestem.');
  }
}

async function sha256File(file: File): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    await file.arrayBuffer(),
  );
  return Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, '0'),
  ).join('');
}

async function assertOperatorLocalSelectionChecksum(
  outputDirectory: FileSystemDirectoryHandle,
  decision: RemoteSelectionWorkspaceDecision,
): Promise<void> {
  if (decision.outputName === null || decision.imageChecksumSha256 === null)
    return;
  const handle = await outputDirectory.getFileHandle(decision.outputName);
  if (
    (await sha256File(await handle.getFile())) !== decision.imageChecksumSha256
  ) {
    throw new Error(`Nie usuwam obcego pliku ${decision.outputName}.`);
  }
}

function isNotFoundError(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'NotFoundError';
}

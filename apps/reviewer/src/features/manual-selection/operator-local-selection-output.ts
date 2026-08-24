'use client';

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
  readonly decisions: readonly RemoteSelectionWorkspaceDecision[];
  readonly currentIndex: number;
  readonly nextRangeStart: number;
  readonly updatedAt: string;
}

export type OperatorLocalOutputDirectoryState =
  | { readonly kind: 'empty' }
  | {
      readonly kind: 'resumable';
      readonly manifest: OperatorLocalOutputManifestV1;
    };

export interface OperatorLocalOutputResult {
  readonly checksumSha256: string;
  readonly created: boolean;
  readonly name: string;
}

export async function writeOperatorLocalSelection(
  outputDirectory: FileSystemDirectoryHandle,
  source: File,
  rangeStart: number,
): Promise<OperatorLocalOutputResult> {
  const checksumSha256 = await sha256File(source);
  const name = `seq_${rangeStart}-${rangeStart + 8}.jpg`;
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
  const handle = await outputDirectory.getFileHandle(decision.outputName);
  if (
    (await sha256File(await handle.getFile())) !== decision.imageChecksumSha256
  ) {
    throw new Error(`Nie usuwam obcego pliku ${decision.outputName}.`);
  }
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
    readonly allowSessionAdoption?: boolean;
  },
): Promise<void> {
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
          schemaVersion: 1,
          storageMode: 'operator_local',
          ...input,
          allowSessionAdoption: undefined,
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
  let manifest: OperatorLocalOutputManifestV1;
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

export async function resumeOperatorLocalBatch(
  manifest: OperatorLocalOutputManifestV1,
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
  return {
    ...batch,
    cursorIndex: manifest.currentIndex,
    decisions,
    direction: manifest.direction ?? batch.direction,
    firstLayout:
      manifest.firstLayout ??
      decisions[0]?.rangeStart ??
      manifest.nextRangeStart,
    hostRegistered: true,
    nextRangeStart: manifest.nextRangeStart,
    status: 'active',
    updatedAt: new Date().toISOString(),
  };
}

function parseOperatorLocalManifest(
  value: string,
): OperatorLocalOutputManifestV1 {
  const parsed = JSON.parse(value) as Record<string, unknown>;
  if (
    parsed.schemaVersion !== 1 ||
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

  const decisions = parsed.decisions.map((decision, index) =>
    parseDecision(decision, index),
  );
  const firstLayout =
    typeof parsed.firstLayout === 'number'
      ? parsed.firstLayout
      : (decisions[0]?.rangeStart ?? (parsed.nextRangeStart as number));
  for (const [index, decision] of decisions.entries()) {
    const expectedStart = firstLayout + index * 9;
    if (
      decision.rangeStart !== expectedStart ||
      decision.rangeEnd !== expectedStart + 8
    ) {
      throw new Error('Manifest zawiera nieciągłą kolejność zakresów.');
    }
  }
  if (
    (parsed.nextRangeStart as number) !==
    firstLayout + decisions.length * 9
  ) {
    throw new Error('Manifest zawiera niespójny następny zakres.');
  }
  return {
    ...(parsed as unknown as OperatorLocalOutputManifestV1),
    decisions,
  };
}

function parseDecision(
  value: unknown,
  index: number,
): RemoteSelectionWorkspaceDecision {
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
    !Number.isSafeInteger(decision.rangeEnd) ||
    decision.rangeEnd !== (decision.rangeStart as number) + 8 ||
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
    accepted &&
    decision.outputName !==
      `seq_${decision.rangeStart}-${decision.rangeEnd}.jpg`
  ) {
    throw new Error(
      `Manifest zawiera nieprawidłową nazwę decyzji ${index + 1}.`,
    );
  }
  return decision as unknown as RemoteSelectionWorkspaceDecision;
}

function assertMatchingSource(
  existing: OperatorLocalOutputManifestV1,
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

'use client';

import type { RemoteSelectionWorkspaceDecision } from './remote-selection-store';

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
  },
): Promise<void> {
  const manifestName = 'manual-image-selection-output-v1.json';
  try {
    const existing = await (
      await outputDirectory.getFileHandle(manifestName)
    ).getFile();
    const parsed = JSON.parse(await existing.text()) as {
      readonly batchId?: unknown;
      readonly sessionId?: unknown;
      readonly storageMode?: unknown;
    };
    if (
      parsed.storageMode !== 'operator_local' ||
      parsed.sessionId !== input.sessionId ||
      parsed.batchId !== input.batchId
    ) {
      throw new Error(
        'Folder wynikowy zawiera manifest należący do innej sesji.',
      );
    }
  } catch (cause) {
    if (!(cause instanceof DOMException) || cause.name !== 'NotFoundError') {
      if (cause instanceof SyntaxError) {
        throw new Error('Folder wynikowy zawiera uszkodzony obcy manifest.');
      }
      throw cause;
    }
  }
  const handle = await outputDirectory.getFileHandle(manifestName, {
    create: true,
  });
  const writable = await handle.createWritable();
  try {
    await writable.write(
      JSON.stringify(
        {
          schemaVersion: 1,
          storageMode: 'operator_local',
          ...input,
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

async function sha256File(file: File): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    await file.arrayBuffer(),
  );
  return Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, '0'),
  ).join('');
}

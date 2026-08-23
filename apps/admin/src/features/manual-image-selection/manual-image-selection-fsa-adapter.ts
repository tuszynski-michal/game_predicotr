'use client';

import {
  createManualSelectionOutputManifest,
  createManualSelectionTraceManifest,
  isSupportedManualImage,
  naturalCompare,
  type ManualImageDescriptor,
  type ManualOutputFileResult,
  type ManualSelectionDecision,
  type ManualSelectionOutputPort,
  type ManualSelectionSessionMetadata,
  type ManualSelectionSourcePort,
  type ManualSelectionState,
  type ManualSelectionTraceEvent,
} from '@game-predictor/manual-image-selection-core';

export interface ManualImageFile extends ManualImageDescriptor {
  readonly handle: FileSystemFileHandle;
}

export interface ManualSelectionSessionRecord extends ManualSelectionSessionMetadata {
  readonly outputDirectory: FileSystemDirectoryHandle;
  readonly sourceDirectory: FileSystemDirectoryHandle;
  readonly state: ManualSelectionState;
}

export function isMissingManualDirectoryHandleError(cause: unknown): boolean {
  if (typeof cause !== 'object' || cause === null) return false;
  const name =
    'name' in cause && typeof cause.name === 'string' ? cause.name : '';
  const message =
    'message' in cause && typeof cause.message === 'string'
      ? cause.message
      : '';
  return (
    name === 'NotFoundError' ||
    message
      .toLowerCase()
      .includes('requested file or directory could not be found')
  );
}

export function relinkManualSelectionSession(
  record: ManualSelectionSessionRecord,
  sourceDirectory: FileSystemDirectoryHandle,
  outputDirectory: FileSystemDirectoryHandle,
): ManualSelectionSessionRecord {
  return {
    ...record,
    outputDirectory,
    sourceDirectory,
    sourceDirectoryName: sourceDirectory.name,
  };
}

export class FileSystemManualSelectionSourceAdapter implements ManualSelectionSourcePort<ManualImageFile> {
  private readonly directory: FileSystemDirectoryHandle;

  constructor(directory: FileSystemDirectoryHandle) {
    this.directory = directory;
  }

  async listImages(): Promise<ManualImageFile[]> {
    const files: ManualImageFile[] = [];

    async function visit(
      current: FileSystemDirectoryHandle,
      prefix: string,
    ): Promise<void> {
      for await (const [name, entry] of current.entries()) {
        const relativePath = prefix === '' ? name : `${prefix}/${name}`;
        if (entry.kind === 'directory') {
          await visit(entry, relativePath);
          continue;
        }
        if (entry.kind !== 'file' || !isSupportedManualImage(name)) continue;
        files.push({
          handle: entry,
          name,
          relativePath,
        });
      }
    }

    await visit(this.directory, '');
    return files.sort((left, right) => {
      const pathOrder = naturalCompare(left.relativePath, right.relativePath);
      return pathOrder === 0
        ? left.relativePath.localeCompare(right.relativePath)
        : pathOrder;
    });
  }
}

export class FileSystemManualSelectionOutputAdapter implements ManualSelectionOutputPort<ManualImageFile> {
  private readonly outputDirectory: FileSystemDirectoryHandle;

  constructor(outputDirectory: FileSystemDirectoryHandle) {
    this.outputDirectory = outputDirectory;
  }

  async writeAcceptedOutput(
    source: ManualImageFile,
    rangeStart: number,
    rangeEnd: number,
    options: { readonly allowReplace?: boolean } = {},
  ): Promise<ManualOutputFileResult> {
    const sourceFile = await source.handle.getFile();
    const checksum = await sha256Hex(sourceFile);
    const name = `seq_${rangeStart}-${rangeEnd}.jpg`;
    let existing: File | null = null;
    try {
      existing = await (
        await this.outputDirectory.getFileHandle(name)
      ).getFile();
    } catch (error) {
      if (!(error instanceof DOMException) || error.name !== 'NotFoundError') {
        throw error;
      }
    }
    if (existing !== null) {
      const existingChecksum = await sha256Hex(existing);
      if (existingChecksum === checksum) {
        return { checksum, created: false, name };
      }
      if (!options.allowReplace) {
        throw new Error(`Plik ${name} już istnieje i ma inną zawartość.`);
      }
    }
    const target = await this.outputDirectory.getFileHandle(name, {
      create: true,
    });
    const writable = await target.createWritable();
    try {
      await writable.write(sourceFile);
      await writable.close();
    } catch (error) {
      await writable.abort().catch(() => undefined);
      throw error;
    }
    const written = await target.getFile();
    const writtenChecksum = await sha256Hex(written);
    if (writtenChecksum !== checksum) {
      throw new Error(`Weryfikacja zapisu pliku ${name} nie powiodła się.`);
    }
    return { checksum, created: true, name };
  }

  async removeManagedOutput(decision: ManualSelectionDecision): Promise<void> {
    if (decision.outputName === null || decision.imageChecksum === null) return;
    const target = await this.outputDirectory.getFileHandle(
      decision.outputName,
    );
    const existingChecksum = await sha256Hex(await target.getFile());
    if (existingChecksum !== decision.imageChecksum) {
      throw new Error(`Nie usuwam obcego pliku ${decision.outputName}.`);
    }
    await this.outputDirectory.removeEntry(decision.outputName);
  }

  async writeOutputManifest(
    record: ManualSelectionSessionMetadata,
  ): Promise<void> {
    await writeOwnedJsonFile(
      this.outputDirectory,
      'manual-image-selection-output-v1.json',
      createManualSelectionOutputManifest(record),
      record.key,
    );
  }

  async writeTraceManifest(
    record: ManualSelectionSessionMetadata,
    events: readonly ManualSelectionTraceEvent[],
  ): Promise<void> {
    await writeOwnedJsonFile(
      this.outputDirectory,
      'manual-image-selection-trace-v1.json',
      createManualSelectionTraceManifest(record, events),
      record.key,
    );
  }
}

export async function listManualImages(
  directory: FileSystemDirectoryHandle,
): Promise<ManualImageFile[]> {
  return new FileSystemManualSelectionSourceAdapter(directory).listImages();
}

export async function sha256Hex(value: Blob): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    await value.arrayBuffer(),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

export async function writeManualOutput(
  outputDirectory: FileSystemDirectoryHandle,
  source: ManualImageFile,
  rangeStart: number,
  rangeEnd: number,
  options: { readonly allowReplace?: boolean } = {},
): Promise<ManualOutputFileResult> {
  return new FileSystemManualSelectionOutputAdapter(
    outputDirectory,
  ).writeAcceptedOutput(source, rangeStart, rangeEnd, options);
}

export async function removeManagedManualOutput(
  outputDirectory: FileSystemDirectoryHandle,
  decision: ManualSelectionDecision,
): Promise<void> {
  return new FileSystemManualSelectionOutputAdapter(
    outputDirectory,
  ).removeManagedOutput(decision);
}

export async function writeManualOutputManifest(
  outputDirectory: FileSystemDirectoryHandle,
  record: ManualSelectionSessionRecord,
): Promise<void> {
  return new FileSystemManualSelectionOutputAdapter(
    outputDirectory,
  ).writeOutputManifest(record);
}

export async function writeManualTraceManifest(
  outputDirectory: FileSystemDirectoryHandle,
  record: ManualSelectionSessionRecord,
  events: readonly ManualSelectionTraceEvent[],
): Promise<void> {
  return new FileSystemManualSelectionOutputAdapter(
    outputDirectory,
  ).writeTraceManifest(record, events);
}

async function writeOwnedJsonFile(
  outputDirectory: FileSystemDirectoryHandle,
  name: string,
  value: object,
  sessionKey: string,
): Promise<void> {
  try {
    const existing = await (
      await outputDirectory.getFileHandle(name)
    ).getFile();
    const parsed: unknown = JSON.parse(await existing.text());
    if (
      typeof parsed !== 'object' ||
      parsed === null ||
      !('sessionKey' in parsed) ||
      typeof parsed.sessionKey !== 'string' ||
      parsed.sessionKey !== sessionKey
    ) {
      throw new Error(`Plik ${name} należy do innej sesji ręcznej selekcji.`);
    }
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'NotFoundError')) {
      throw error;
    }
  }
  const target = await outputDirectory.getFileHandle(name, { create: true });
  const writable = await target.createWritable();
  try {
    await writable.write(`${JSON.stringify(value, null, 2)}\n`);
    await writable.close();
  } catch (error) {
    await writable.abort().catch(() => undefined);
    throw error;
  }
}

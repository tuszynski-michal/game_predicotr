'use client';

import {
  buildRemoteSourceManifestV1,
  compareRemoteSourceManifestV1,
  isSupportedManualImage,
  normalizeRemoteSourcePath,
  type RemoteSourceKind,
  type RemoteSourceManifestEntryV1,
  type RemoteSourceManifestV1,
} from '@game-predictor/manual-image-selection-core';
import type {
  RemoteSelectionSourceItemRecord,
  RemoteSourcePermissionState,
} from './remote-selection-store';

export const REMOTE_SOURCE_DEFAULT_PAGE_SIZE = 250;
export const REMOTE_SOURCE_MAX_PAGE_SIZE = 500;

type PermissionDescriptor = { readonly mode: 'read' };

export interface ReadableDirectoryHandle extends FileSystemDirectoryHandle {
  queryPermission?(descriptor: PermissionDescriptor): Promise<PermissionState>;
  requestPermission?(
    descriptor: PermissionDescriptor,
  ): Promise<PermissionState>;
}

export interface RemoteSourceFileDescriptor extends Omit<
  RemoteSourceManifestEntryV1,
  'ordinal'
> {
  readonly handle: FileSystemFileHandle | null;
  readonly fallbackFile: File | null;
}

export interface RemoteSourceIndexResult {
  readonly sourceDirectoryName: string;
  readonly sourceHandle: FileSystemDirectoryHandle | null;
  readonly manifest: RemoteSourceManifestV1;
  readonly descriptors: readonly RemoteSourceFileDescriptor[];
}

export interface RemoteSourceFileReader {
  fileForEntry(entry: RemoteSourceManifestEntryV1): Promise<File> | File;
}

export type RemoteSourceCapabilityMode =
  'directory_handle' | 'webkitdirectory_reselect' | 'unsupported';

export class RemoteSourceAdapterError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'RemoteSourceAdapterError';
    this.code = code;
  }
}

export class DirectoryHandleRemoteSourceAdapter {
  readonly sourceKind = 'directory_handle' as const;
  private readonly directory: ReadableDirectoryHandle;

  constructor(directory: ReadableDirectoryHandle) {
    this.directory = directory;
  }

  async permissionState(): Promise<RemoteSourcePermissionState> {
    return queryRemoteSourcePermission(this.directory);
  }

  async requestPermission(): Promise<RemoteSourcePermissionState> {
    return requestRemoteSourcePermission(this.directory);
  }

  async index(): Promise<RemoteSourceIndexResult> {
    const permission = await this.permissionState();
    if (permission !== 'granted' && permission !== 'unsupported') {
      throw sourceError(
        'REMOTE_SELECTION_SOURCE_PERMISSION_REQUIRED',
        'Read permission is required before indexing the source directory.',
      );
    }
    const descriptors: RemoteSourceFileDescriptor[] = [];
    await visitDirectory(this.directory, '', descriptors);
    return buildIndexResult(
      this.directory.name,
      this.directory,
      descriptors,
      this.sourceKind,
    );
  }

  async fileForEntry(entry: RemoteSourceManifestEntryV1): Promise<File> {
    try {
      const normalized = normalizeRemoteSourcePath(entry.relativePath);
      const segments = normalized.split('/');
      let directory: FileSystemDirectoryHandle = this.directory;
      for (const segment of segments.slice(0, -1)) {
        directory = await directory.getDirectoryHandle(segment);
      }
      const handle = await directory.getFileHandle(segments.at(-1) ?? '');
      const file = await handle.getFile();
      assertUnchangedFile(file, entry);
      return file;
    } catch (cause) {
      if (cause instanceof RemoteSourceAdapterError) throw cause;
      throw sourceError(
        'REMOTE_SELECTION_SOURCE_FILE_MISSING',
        'The indexed source file is no longer available.',
      );
    }
  }
}

export class WebkitDirectoryRemoteSourceAdapter {
  readonly sourceKind = 'webkitdirectory_reselect' as const;
  private readonly files: readonly File[];

  constructor(files: readonly File[]) {
    this.files = files;
  }

  async index(): Promise<RemoteSourceIndexResult> {
    const descriptors = this.files
      .map((file) => descriptorFromFallbackFile(file))
      .filter((entry): entry is RemoteSourceFileDescriptor => entry !== null);
    const sourceDirectoryName = fallbackDirectoryName(descriptors);
    return buildIndexResult(
      sourceDirectoryName,
      null,
      descriptors,
      this.sourceKind,
    );
  }

  fileForEntry(entry: RemoteSourceManifestEntryV1): File {
    const normalized = normalizeRemoteSourcePath(entry.relativePath);
    const candidate = this.files.find(
      (file) => fallbackRelativePath(file) === normalized,
    );
    if (candidate === undefined) {
      throw sourceError(
        'REMOTE_SELECTION_SOURCE_FILE_MISSING',
        'The selected source file is no longer available.',
      );
    }
    assertUnchangedFile(candidate, entry);
    return candidate;
  }
}

export async function* pagedRemoteSourceDescriptors(
  descriptors: readonly RemoteSourceFileDescriptor[],
  pageSize = REMOTE_SOURCE_DEFAULT_PAGE_SIZE,
): AsyncGenerator<readonly RemoteSourceFileDescriptor[]> {
  const size = normalizedPageSize(pageSize);
  for (let offset = 0; offset < descriptors.length; offset += size) {
    yield descriptors.slice(offset, offset + size);
    await Promise.resolve();
  }
}

export function createRemoteSourceItemRecords(
  sessionId: string,
  batchId: string,
  manifest: RemoteSourceManifestV1,
  createId: () => string = () => crypto.randomUUID(),
): RemoteSelectionSourceItemRecord[] {
  return manifest.entries.map((entry) => ({
    schemaVersion: 1,
    ...entry,
    batchId,
    fileId: createId(),
    sessionId,
  }));
}

export function detectRemoteSourceMode(
  scope: Pick<typeof globalThis, 'isSecureContext'> & {
    readonly showDirectoryPicker?: unknown;
    readonly HTMLInputElement?: { readonly prototype?: object };
  } = globalThis,
): RemoteSourceCapabilityMode {
  if (
    scope.isSecureContext === true &&
    typeof scope.showDirectoryPicker === 'function'
  ) {
    return 'directory_handle';
  }
  if (
    scope.HTMLInputElement?.prototype !== undefined &&
    'webkitdirectory' in scope.HTMLInputElement.prototype
  ) {
    return 'webkitdirectory_reselect';
  }
  return 'unsupported';
}

export async function queryRemoteSourcePermission(
  directory: ReadableDirectoryHandle,
): Promise<RemoteSourcePermissionState> {
  if (typeof directory.queryPermission !== 'function') return 'unsupported';
  try {
    return await directory.queryPermission({ mode: 'read' });
  } catch {
    return 'error';
  }
}

export async function requestRemoteSourcePermission(
  directory: ReadableDirectoryHandle,
): Promise<RemoteSourcePermissionState> {
  const current = await queryRemoteSourcePermission(directory);
  if (current === 'granted') return current;
  if (typeof directory.requestPermission !== 'function') return 'unsupported';
  try {
    return await directory.requestPermission({ mode: 'read' });
  } catch {
    return 'error';
  }
}

export function validateRemoteSourceRelink(
  expected: RemoteSourceManifestV1,
  candidate: RemoteSourceManifestV1,
): void {
  const comparison = compareRemoteSourceManifestV1(expected, candidate);
  if (comparison.status === 'same') return;
  throw sourceError(
    comparison.status === 'incompatible'
      ? 'REMOTE_SELECTION_SOURCE_RELINK_INCOMPATIBLE'
      : 'REMOTE_SELECTION_SOURCE_CHANGED',
    comparison.status === 'incompatible'
      ? 'The selected directory is not compatible with the saved source.'
      : `The selected directory differs in ${comparison.changedFileCount} source items.`,
  );
}

async function visitDirectory(
  directory: FileSystemDirectoryHandle,
  prefix: string,
  output: RemoteSourceFileDescriptor[],
): Promise<void> {
  for await (const [name, handle] of directory.entries()) {
    const relativePath = prefix === '' ? name : `${prefix}/${name}`;
    if (handle.kind === 'directory') {
      await visitDirectory(handle, relativePath, output);
      continue;
    }
    if (handle.kind !== 'file' || !isSupportedManualImage(name)) continue;
    const file = await handle.getFile();
    output.push({
      fallbackFile: null,
      handle,
      lastModifiedMs: file.lastModified,
      mimeType: file.type,
      name,
      relativePath: normalizeRemoteSourcePath(relativePath),
      sizeBytes: file.size,
    });
  }
}

function descriptorFromFallbackFile(
  file: File,
): RemoteSourceFileDescriptor | null {
  const relativePath = fallbackRelativePath(file);
  const name = relativePath.split('/').at(-1) ?? file.name;
  if (!isSupportedManualImage(name)) return null;
  return {
    fallbackFile: file,
    handle: null,
    lastModifiedMs: file.lastModified,
    mimeType: file.type,
    name,
    relativePath,
    sizeBytes: file.size,
  };
}

function fallbackRelativePath(file: File): string {
  const raw =
    'webkitRelativePath' in file && file.webkitRelativePath !== ''
      ? file.webkitRelativePath
      : file.name;
  return normalizeRemoteSourcePath(raw);
}

function fallbackDirectoryName(
  descriptors: readonly RemoteSourceFileDescriptor[],
): string {
  const first = descriptors[0]?.relativePath.split('/')[0];
  return first === undefined ||
    !descriptors.some((item) => item.relativePath.includes('/'))
    ? 'Wybrany folder'
    : first;
}

async function buildIndexResult(
  sourceDirectoryName: string,
  sourceHandle: FileSystemDirectoryHandle | null,
  descriptors: readonly RemoteSourceFileDescriptor[],
  sourceKind: RemoteSourceKind,
): Promise<RemoteSourceIndexResult> {
  const manifest = await buildRemoteSourceManifestV1(
    descriptors.map((descriptor) => ({
      lastModifiedMs: descriptor.lastModifiedMs,
      mimeType: descriptor.mimeType,
      name: descriptor.name,
      relativePath: descriptor.relativePath,
      sizeBytes: descriptor.sizeBytes,
    })),
    sourceKind,
  );
  const descriptorByPath = new Map(
    descriptors.map((entry) => [entry.relativePath, entry]),
  );
  return {
    descriptors: manifest.entries.map((entry) => {
      const descriptor = descriptorByPath.get(entry.relativePath);
      if (descriptor === undefined) {
        throw sourceError(
          'REMOTE_SELECTION_SOURCE_INDEX_INVALID',
          'The source index is internally inconsistent.',
        );
      }
      return descriptor;
    }),
    manifest,
    sourceDirectoryName,
    sourceHandle,
  };
}

function assertUnchangedFile(
  file: File,
  entry: RemoteSourceManifestEntryV1,
): void {
  if (
    file.name !== entry.name ||
    file.size !== entry.sizeBytes ||
    file.lastModified !== entry.lastModifiedMs
  ) {
    throw sourceError(
      'REMOTE_SELECTION_SOURCE_CHANGED',
      'The source file changed after it was indexed.',
    );
  }
}

function normalizedPageSize(value: number): number {
  if (
    !Number.isSafeInteger(value) ||
    value < 1 ||
    value > REMOTE_SOURCE_MAX_PAGE_SIZE
  ) {
    throw sourceError(
      'REMOTE_SELECTION_SOURCE_PAGE_INVALID',
      `Source page size must be between 1 and ${REMOTE_SOURCE_MAX_PAGE_SIZE}.`,
    );
  }
  return value;
}

function sourceError(code: string, message: string): RemoteSourceAdapterError {
  return new RemoteSourceAdapterError(code, message);
}

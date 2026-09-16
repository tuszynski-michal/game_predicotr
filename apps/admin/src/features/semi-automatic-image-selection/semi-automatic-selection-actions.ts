'use client';

import type {
  AdminApiClient,
  SemiAutomaticSelectionCreateResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import { pickLocalDirectory } from '../../lib/local-directory-picker.ts';

import type {
  SemiAutomaticOutputDirectoryHandle,
  SemiAutomaticSourceDirectoryHandle,
} from './semi-automatic-selection-output-storage.ts';

const MAX_UPLOAD_CONCURRENCY = 4;
const MAX_FILE_ATTEMPTS = 3;
const NATURAL_PATH_ORDER = new Intl.Collator('en', {
  numeric: true,
  sensitivity: 'base',
});

interface BrowserFileHandle {
  readonly kind: 'file';
  readonly name?: string;
  getFile(): Promise<File>;
}

export interface BrowserDirectoryHandle extends SemiAutomaticSourceDirectoryHandle {
  readonly kind: 'directory';
  entries(): AsyncIterableIterator<readonly [string, BrowserDirectoryEntry]>;
}

type BrowserDirectoryEntry = BrowserFileHandle | BrowserDirectoryHandle;

export interface SemiAutomaticSourceFile {
  readonly file: File;
  readonly handle: FileSystemFileHandle;
  readonly relativePath: string;
}

export interface SemiAutomaticReviewSourceFile {
  readonly handle: FileSystemFileHandle;
  readonly relativePath: string;
}

export interface SemiAutomaticLocalSourceSelection {
  readonly displayName: string;
  readonly path: string;
  readonly selectionToken: string;
  readonly supportedFileCount: number;
}

export interface SemiAutomaticSelectionUploadProgress {
  readonly totalBytes: number;
  readonly totalFiles: number;
  readonly uploadedBytes: number;
  readonly uploadedFiles: number;
}

export interface ResumableSemiAutomaticSelectionUpload {
  readonly files: readonly SemiAutomaticSourceFile[];
  readonly sourceDirectory: BrowserDirectoryHandle;
  readonly uploadId: string;
}

export type SemiAutomaticSelectionClient = Pick<
  AdminApiClient,
  | 'cancelBrowserImageSelection'
  | 'createBrowserImageSelection'
  | 'createSemiAutomaticImageSelection'
  | 'finalizeBrowserImageSelection'
  | 'getBrowserImageSelection'
  | 'getSemiAutomaticImageSelectionSourceAsset'
  | 'listSemiAutomaticImageSelectionSources'
  | 'selectSemiAutomaticImageSelectionSourceFolder'
  | 'uploadBrowserImageSelectionFile'
>;

export async function selectSemiAutomaticLocalSource(
  api: SemiAutomaticSelectionClient,
): Promise<SemiAutomaticLocalSourceSelection | null> {
  const result = await api.selectSemiAutomaticImageSelectionSourceFolder();
  if (result.error !== undefined || result.data === undefined) {
    throw new Error(
      apiErrorMessage(
        result.error,
        'Nie udało się wybrać katalogu źródłowego.',
      ),
    );
  }
  if (result.data.status === 'cancelled') return null;
  const path = result.data.path;
  const selectionToken = result.data.selectionToken;
  const supportedFileCount = result.data.supportedFileCount;
  if (
    path === null ||
    path === undefined ||
    selectionToken === null ||
    selectionToken === undefined ||
    supportedFileCount === undefined ||
    supportedFileCount < 1
  ) {
    throw new Error('Wybrany katalog nie zawiera plików JPEG.');
  }
  const displayName = path.split(/[\\/]/u).filter(Boolean).at(-1) ?? path;
  return { displayName, path, selectionToken, supportedFileCount };
}

export async function createSemiAutomaticSelectionFromLocalSource(input: {
  readonly api: SemiAutomaticSelectionClient;
  readonly direction: 'ascending' | 'descending';
  readonly firstSequenceNumber: number;
  readonly lastSequenceNumber: number;
  readonly recognizerVariant: 'default_v3' | 'five_anchor_v6';
  readonly source: SemiAutomaticLocalSourceSelection;
}): Promise<SemiAutomaticSelectionCreateResponse> {
  const result = await input.api.createSemiAutomaticImageSelection({
    direction: input.direction,
    firstSequenceNumber: input.firstSequenceNumber,
    lastSequenceNumber: input.lastSequenceNumber,
    mode: 'selection',
    recognizerVariant: input.recognizerVariant,
    selectionToken: input.source.selectionToken,
  });
  if (result.error !== undefined || result.data === undefined) {
    throw new Error(
      apiErrorMessage(
        result.error,
        'Nie udało się utworzyć półautomatycznego procesu selekcji.',
      ),
    );
  }
  return result.data;
}

export async function loadSemiAutomaticReviewSourceFiles(
  api: SemiAutomaticSelectionClient,
  runId: string,
): Promise<readonly SemiAutomaticReviewSourceFile[]> {
  const files: SemiAutomaticReviewSourceFile[] = [];
  let afterSourceIndex: number | undefined;
  do {
    const page = await api.listSemiAutomaticImageSelectionSources(
      runId,
      afterSourceIndex,
    );
    if (page.error !== undefined || page.data === undefined) {
      throw new Error(
        apiErrorMessage(
          page.error,
          'Nie udało się odczytać listy zdjęć źródłowych.',
        ),
      );
    }
    for (const source of page.data.items) {
      files.push({
        handle: {
          kind: 'file',
          name: source.relativePath.split('/').at(-1),
          async getFile(): Promise<File> {
            const asset = await api.getSemiAutomaticImageSelectionSourceAsset(
              runId,
              source.sourceIndex,
              source.checksumSha256,
            );
            if (asset.error !== undefined || asset.data === undefined) {
              throw new Error('Nie udało się odczytać zdjęcia źródłowego.');
            }
            const blob = toBlob(asset.data);
            if (blob === null) {
              throw new Error(
                'Odpowiedź zdjęcia źródłowego jest nieprawidłowa.',
              );
            }
            return new File(
              [blob],
              source.relativePath.split('/').at(-1) ?? 'source.jpg',
              {
                lastModified: 0,
                type: blob.type || 'image/jpeg',
              },
            );
          },
        } as unknown as FileSystemFileHandle,
        relativePath: source.relativePath,
      });
    }
    afterSourceIndex = page.data.nextAfterSourceIndex ?? undefined;
  } while (afterSourceIndex !== undefined);
  return files;
}

export type SemiAutomaticSelectionUploadResult =
  | {
      readonly created: SemiAutomaticSelectionCreateResponse;
      readonly ok: true;
    }
  | {
      readonly error: string;
      readonly ok: false;
      readonly resume: ResumableSemiAutomaticSelectionUpload | null;
    };

export async function pickSemiAutomaticSourceDirectory(): Promise<BrowserDirectoryHandle> {
  return (await pickLocalDirectory({
    id: 'gp-semi-source',
    mode: 'read',
  })) as unknown as BrowserDirectoryHandle;
}

export async function pickSemiAutomaticOutputDirectory(): Promise<SemiAutomaticOutputDirectoryHandle> {
  return (await pickLocalDirectory({
    id: 'gp-semi-output',
    mode: 'readwrite',
  })) as unknown as SemiAutomaticOutputDirectoryHandle;
}

export async function collectSemiAutomaticSourceFiles(
  directory: BrowserDirectoryHandle,
): Promise<readonly SemiAutomaticSourceFile[]> {
  const files: SemiAutomaticSourceFile[] = [];
  await collectDirectoryFiles(directory, '', files);
  return files.sort((left, right) =>
    NATURAL_PATH_ORDER.compare(left.relativePath, right.relativePath),
  );
}

export async function uploadSemiAutomaticSelectionFolder(input: {
  readonly api: SemiAutomaticSelectionClient;
  readonly direction: 'ascending' | 'descending';
  readonly files: readonly SemiAutomaticSourceFile[];
  readonly firstSequenceNumber: number;
  readonly lastSequenceNumber: number;
  readonly mode: 'filename_verification';
  readonly onProgress?: (
    progress: SemiAutomaticSelectionUploadProgress,
  ) => void;
  readonly resume?: ResumableSemiAutomaticSelectionUpload | null;
  readonly sourceDirectory: BrowserDirectoryHandle;
}): Promise<SemiAutomaticSelectionUploadResult> {
  const files = input.resume?.files ?? input.files;
  if (files.length === 0) {
    return {
      error: 'Wybrany folder nie zawiera plików JPEG.',
      ok: false,
      resume: null,
    };
  }
  if (
    !Number.isInteger(input.firstSequenceNumber) ||
    !Number.isInteger(input.lastSequenceNumber) ||
    input.firstSequenceNumber < 1 ||
    input.lastSequenceNumber < input.firstSequenceNumber
  ) {
    return {
      error: 'Podaj poprawny, rosnący zakres numerów plansz.',
      ok: false,
      resume: null,
    };
  }

  const totalBytes = files.reduce((total, item) => total + item.file.size, 0);
  let uploadId = input.resume?.uploadId ?? null;
  const resumable = (
    resolvedUploadId: string,
  ): ResumableSemiAutomaticSelectionUpload => ({
    files,
    sourceDirectory: input.sourceDirectory,
    uploadId: resolvedUploadId,
  });

  try {
    const staging =
      uploadId === null
        ? await input.api.createBrowserImageSelection({
            displayName: input.sourceDirectory.name || 'Zdjęcia',
            expectedFileCount: files.length,
            expectedTotalBytes: totalBytes,
            gameId: null,
            purpose: 'semi_automatic_selection',
          })
        : await input.api.getBrowserImageSelection(uploadId);
    if (staging.error !== undefined || staging.data === undefined) {
      return {
        error: apiErrorMessage(
          staging.error,
          'Nie udało się rozpocząć lub wznowić przesyłania folderu.',
        ),
        ok: false,
        resume: uploadId === null ? null : resumable(uploadId),
      };
    }
    uploadId = staging.data.uploadId;
    if (
      staging.data.gameId !== null ||
      staging.data.purpose !== 'semi_automatic_selection' ||
      staging.data.expectedFileCount !== files.length ||
      staging.data.expectedTotalBytes !== totalBytes
    ) {
      return {
        error: 'Istniejący staging nie pasuje do wybranego folderu.',
        ok: false,
        resume: null,
      };
    }

    const completed = new Set(staging.data.uploadedFileIndexes);
    const pendingIndexes = files
      .map((_item, index) => index)
      .filter((index) => !completed.has(index));
    let uploadedFiles = staging.data.uploadedFileCount;
    let uploadedBytes = staging.data.uploadedBytes;
    input.onProgress?.({
      totalBytes,
      totalFiles: files.length,
      uploadedBytes,
      uploadedFiles,
    });

    let cursor = 0;
    let failedIndex: number | null = null;
    async function uploadWorker(): Promise<void> {
      while (failedIndex === null) {
        const pendingPosition = cursor;
        cursor += 1;
        const fileIndex = pendingIndexes[pendingPosition];
        if (fileIndex === undefined) return;
        const item = files[fileIndex];
        if (item === undefined) return;
        let uploadSucceeded = false;
        for (let attempt = 1; attempt <= MAX_FILE_ATTEMPTS; attempt += 1) {
          try {
            const uploaded = await input.api.uploadBrowserImageSelectionFile(
              uploadId as string,
              fileIndex,
              item.relativePath,
              item.file,
            );
            if (uploaded.error === undefined && uploaded.data !== undefined) {
              uploadedFiles = Math.max(
                uploadedFiles,
                uploaded.data.uploadedFileCount,
              );
              uploadedBytes = Math.max(
                uploadedBytes,
                uploaded.data.uploadedBytes,
              );
              input.onProgress?.({
                totalBytes,
                totalFiles: files.length,
                uploadedBytes,
                uploadedFiles,
              });
              uploadSucceeded = true;
              break;
            }
          } catch {
            // The final attempt reports one bounded resumable failure below.
          }
        }
        if (!uploadSucceeded) failedIndex = fileIndex;
      }
    }

    await Promise.all(
      Array.from(
        { length: Math.min(MAX_UPLOAD_CONCURRENCY, pendingIndexes.length) },
        () => uploadWorker(),
      ),
    );
    if (failedIndex !== null) {
      return {
        error: `Nie udało się przesłać pliku ${failedIndex + 1} z ${files.length}.`,
        ok: false,
        resume: resumable(uploadId),
      };
    }

    const finalized = await input.api.finalizeBrowserImageSelection(uploadId);
    if (
      finalized.error !== undefined ||
      finalized.data?.selectionToken === undefined ||
      finalized.data.selectionToken === null
    ) {
      return {
        error: apiErrorMessage(
          finalized.error,
          'Nie udało się sfinalizować stagingu wybranego folderu.',
        ),
        ok: false,
        resume: resumable(uploadId),
      };
    }
    const created = await input.api.createSemiAutomaticImageSelection({
      direction: input.direction,
      firstSequenceNumber: input.firstSequenceNumber,
      lastSequenceNumber: input.lastSequenceNumber,
      mode: input.mode,
      uploadId,
    });
    if (created.error !== undefined || created.data === undefined) {
      return {
        error: apiErrorMessage(
          created.error,
          'Nie udało się utworzyć półautomatycznego procesu selekcji.',
        ),
        ok: false,
        resume: resumable(uploadId),
      };
    }
    return { created: created.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
      resume: uploadId === null ? null : resumable(uploadId),
    };
  }
}

export async function cancelSemiAutomaticSelectionUpload(
  api: SemiAutomaticSelectionClient,
  upload: ResumableSemiAutomaticSelectionUpload,
): Promise<void> {
  await api.cancelBrowserImageSelection(upload.uploadId);
}

async function collectDirectoryFiles(
  directory: BrowserDirectoryHandle,
  prefix: string,
  target: SemiAutomaticSourceFile[],
): Promise<void> {
  for await (const [name, entry] of directory.entries()) {
    const relativePath = prefix === '' ? name : `${prefix}/${name}`;
    if (entry.kind === 'directory') {
      await collectDirectoryFiles(entry, relativePath, target);
      continue;
    }
    if (!/\.jpe?g$/iu.test(name)) continue;
    target.push({
      file: await entry.getFile(),
      handle: entry as unknown as FileSystemFileHandle,
      relativePath,
    });
  }
}

function toBlob(value: unknown): Blob | null {
  if (value instanceof Blob) return value;
  if (value instanceof ArrayBuffer) return new Blob([value]);
  if (ArrayBuffer.isView(value)) {
    const bytes = new Uint8Array(value.byteLength);
    bytes.set(new Uint8Array(value.buffer, value.byteOffset, value.byteLength));
    return new Blob([bytes]);
  }
  return null;
}

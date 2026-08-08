import type {
  AdminApiClient,
  ImageSelectionCreateResponse,
  ImageSelectionGroupResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

const MAX_UPLOAD_CONCURRENCY = 4;
const MAX_FILE_ATTEMPTS = 3;
const NATURAL_PATH_ORDER = new Intl.Collator('en', {
  numeric: true,
  sensitivity: 'base',
});

export type ImageSelectionClient = Pick<
  AdminApiClient,
  | 'createBrowserImageSelection'
  | 'getBrowserImageSelection'
  | 'uploadBrowserImageSelectionFile'
  | 'finalizeBrowserImageSelection'
  | 'cancelBrowserImageSelection'
  | 'createImageSelection'
  | 'rerunImageSelection'
  | 'getImageSelection'
  | 'getImageSelectionOutput'
  | 'getImageSelectionOutputFile'
  | 'getImageSelectionSelectedGroupFile'
  | 'handoffImageSelection'
  | 'listImageSelectionGroups'
  | 'listImageSelectionGroupCandidates'
  | 'uploadManualImageSelectionFile'
  | 'approveManualImageSelection'
  | 'continueImageSelectionWithoutImage'
>;

export interface ImageSelectionUploadProgress {
  readonly totalBytes: number;
  readonly totalFiles: number;
  readonly uploadedBytes: number;
  readonly uploadedFiles: number;
}

export interface ResumableImageSelectionUpload {
  readonly displayName: string;
  readonly files: readonly File[];
  readonly gameId: string;
  readonly uploadId: string;
}

interface WritableOutputFile {
  abort(): Promise<void>;
  close(): Promise<void>;
  write(data: Blob): Promise<void>;
}

interface OutputFileHandle {
  createWritable(): Promise<WritableOutputFile>;
  getFile(): Promise<File>;
}

export interface OutputDirectoryHandle {
  readonly name?: string;
  getFileHandle(
    name: string,
    options?: { readonly create?: boolean },
  ): Promise<OutputFileHandle>;
}

type DirectoryPickerWindow = Window & {
  showDirectoryPicker?: (options: {
    readonly mode: 'readwrite';
  }) => Promise<OutputDirectoryHandle>;
};

export interface ImageSelectionOutputSaveResult {
  readonly cancelled: boolean;
  readonly error: string | null;
  readonly savedCount: number;
}

type ImageSelectionUploadResult =
  | {
      readonly created: ImageSelectionCreateResponse;
      readonly ok: true;
    }
  | {
      readonly error: string;
      readonly ok: false;
      readonly resume: ResumableImageSelectionUpload | null;
    };

export function orderImageSelectionFiles(files: readonly File[]): File[] {
  return [...files].sort((left, right) =>
    NATURAL_PATH_ORDER.compare(relativePath(left), relativePath(right)),
  );
}

export async function uploadPhotoSelectionFolder(
  api: ImageSelectionClient,
  gameId: string,
  sourceFiles: readonly File[],
  options: {
    readonly onProgress?: (progress: ImageSelectionUploadProgress) => void;
    readonly resume?: ResumableImageSelectionUpload | null;
    readonly sequenceDirection?: 'ascending' | 'descending';
    readonly firstSequenceNumber?: number | null;
  } = {},
): Promise<ImageSelectionUploadResult> {
  const files = options.resume?.files ?? orderImageSelectionFiles(sourceFiles);
  if (files.length === 0) {
    return {
      error: 'Wybrany folder nie zawiera plików JPEG.',
      ok: false,
      resume: null,
    };
  }
  const totalBytes = files.reduce((total, file) => total + file.size, 0);
  const firstPath = relativePath(files[0]);
  const displayName =
    (options.resume?.displayName ?? firstPath.split('/')[0]) || 'Zdjęcia';
  let uploadId = options.resume?.uploadId ?? null;

  try {
    const state =
      uploadId === null
        ? await api.createBrowserImageSelection({
            displayName,
            expectedFileCount: files.length,
            expectedTotalBytes: totalBytes,
            gameId,
            purpose: 'photo_selection',
          })
        : await api.getBrowserImageSelection(uploadId);
    if (state.error !== undefined || state.data === undefined) {
      return {
        error: apiErrorMessage(
          state.error,
          'Nie udało się rozpocząć lub wznowić przesyłania folderu.',
        ),
        ok: false,
        resume:
          uploadId === null ? null : { displayName, files, gameId, uploadId },
      };
    }
    uploadId = state.data.uploadId;
    if (
      state.data.gameId !== gameId ||
      state.data.purpose !== 'photo_selection' ||
      state.data.expectedFileCount !== files.length ||
      state.data.expectedTotalBytes !== totalBytes
    ) {
      return {
        error: 'Stan uploadu nie pasuje do aktywnej gry lub wybranego folderu.',
        ok: false,
        resume: null,
      };
    }

    let uploadedFiles = state.data.uploadedFileCount;
    let uploadedBytes = state.data.uploadedBytes;
    const completed = new Set(state.data.uploadedFileIndexes);
    const pendingIndexes = files
      .map((_file, index) => index)
      .filter((index) => !completed.has(index));
    options.onProgress?.({
      totalBytes,
      totalFiles: files.length,
      uploadedBytes,
      uploadedFiles,
    });

    let cursor = 0;
    let uploadError = '';
    async function worker(): Promise<void> {
      while (uploadError === '') {
        const pendingPosition = cursor;
        cursor += 1;
        const fileIndex = pendingIndexes[pendingPosition];
        if (fileIndex === undefined) return;
        const file = files[fileIndex];
        if (file === undefined) return;
        let lastError: unknown;
        for (let attempt = 1; attempt <= MAX_FILE_ATTEMPTS; attempt += 1) {
          try {
            const result = await api.uploadBrowserImageSelectionFile(
              uploadId as string,
              fileIndex,
              relativePath(file),
              file,
            );
            if (result.error === undefined && result.data !== undefined) {
              uploadedFiles = Math.max(
                uploadedFiles,
                result.data.uploadedFileCount,
              );
              uploadedBytes = Math.max(
                uploadedBytes,
                result.data.uploadedBytes,
              );
              options.onProgress?.({
                totalBytes,
                totalFiles: files.length,
                uploadedBytes,
                uploadedFiles,
              });
              lastError = undefined;
              break;
            }
            lastError = result.error;
          } catch (error) {
            lastError = error;
          }
        }
        if (lastError !== undefined) {
          uploadError = `Nie udało się przesłać pliku ${fileIndex + 1} z ${files.length}.`;
        }
      }
    }

    await Promise.all(
      Array.from(
        { length: Math.min(MAX_UPLOAD_CONCURRENCY, pendingIndexes.length) },
        () => worker(),
      ),
    );
    if (uploadError !== '') {
      return {
        error: uploadError,
        ok: false,
        resume: { displayName, files, gameId, uploadId },
      };
    }

    const finalized = await api.finalizeBrowserImageSelection(uploadId);
    if (
      finalized.error !== undefined ||
      finalized.data?.selectionToken == null
    ) {
      return {
        error: apiErrorMessage(
          finalized.error,
          'Nie udało się sfinalizować stagingu wybranego folderu.',
        ),
        ok: false,
        resume: { displayName, files, gameId, uploadId },
      };
    }
    const created = await api.createImageSelection({
      contractVersion: 1,
      firstSequenceNumber: options.firstSequenceNumber ?? null,
      gameId,
      sequenceDirection: options.sequenceDirection ?? 'ascending',
      selectionToken: finalized.data.selectionToken,
    });
    if (created.error !== undefined || created.data === undefined) {
      return {
        error: apiErrorMessage(
          created.error,
          'Nie udało się utworzyć procesu selekcji zdjęć.',
        ),
        ok: false,
        resume: { displayName, files, gameId, uploadId },
      };
    }
    return { created: created.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
      resume:
        uploadId === null ? null : { displayName, files, gameId, uploadId },
    };
  }
}

export async function saveFinalizedImageSelectionGroups(
  api: ImageSelectionClient,
  runId: string,
  groups: readonly ImageSelectionGroupResponse[],
  directory: OutputDirectoryHandle,
  savedGroupOrders: Set<number>,
): Promise<{ readonly error: string | null; readonly savedCount: number }> {
  let savedCount = 0;
  const ready = groups
    .filter(
      (group) =>
        !savedGroupOrders.has(group.groupOrder) &&
        group.selectedCandidateId !== null &&
        group.rangeStart !== null &&
        group.rangeEnd !== null &&
        (group.status === 'auto_selected' ||
          group.status === 'manually_selected'),
    )
    .sort((left, right) => left.groupOrder - right.groupOrder);
  for (const group of ready) {
    const fileName = `seq_${group.rangeStart}-${group.rangeEnd}.jpg`;
    const downloaded = await api.getImageSelectionSelectedGroupFile(
      runId,
      group.id,
    );
    if (downloaded.error !== undefined || downloaded.data === undefined) {
      return {
        error: `Nie udało się pobrać wybranego zdjęcia ${fileName}.`,
        savedCount,
      };
    }
    const blob = toBlob(downloaded.data);
    if (blob === null) {
      return { error: `Nieprawidłowe dane pliku ${fileName}.`, savedCount };
    }
    let fileHandle: OutputFileHandle;
    try {
      fileHandle = await directory.getFileHandle(fileName);
      const existing = await fileHandle.getFile();
      if ((await sha256(existing)) !== (await sha256(blob))) {
        return {
          error: `Plik ${fileName} już istnieje i ma inną zawartość. Nie został nadpisany.`,
          savedCount,
        };
      }
      savedGroupOrders.add(group.groupOrder);
      continue;
    } catch (error) {
      if (!(error instanceof DOMException) || error.name !== 'NotFoundError') {
        return { error: `Nie udało się sprawdzić ${fileName}.`, savedCount };
      }
      fileHandle = await directory.getFileHandle(fileName, { create: true });
    }
    const writable = await fileHandle.createWritable();
    try {
      await writable.write(blob);
      await writable.close();
      savedGroupOrders.add(group.groupOrder);
      savedCount += 1;
    } catch {
      await writable.abort().catch(() => undefined);
      return { error: `Nie udało się zapisać ${fileName}.`, savedCount };
    }
  }
  return { error: null, savedCount };
}

export async function cancelPhotoSelectionUpload(
  api: ImageSelectionClient,
  upload: ResumableImageSelectionUpload,
): Promise<void> {
  await api.cancelBrowserImageSelection(upload.uploadId);
}

export async function loadManualImageSelectionGroups(
  api: ImageSelectionClient,
  runId: string,
): Promise<ImageSelectionGroupResponse[]> {
  const groups = await loadAllImageSelectionGroups(api, runId);
  return groups
    .filter(
      (group) =>
        group.status === 'manual_required' ||
        group.status === 'manually_selected' ||
        group.status === 'missing_image',
    )
    .map((group) => suggestBoundedMissingRange(group, groups));
}

export async function loadAllImageSelectionGroups(
  api: ImageSelectionClient,
  runId: string,
): Promise<ImageSelectionGroupResponse[]> {
  const groups: ImageSelectionGroupResponse[] = [];
  let afterGroupOrder: number | undefined;
  do {
    const result = await api.listImageSelectionGroups(runId, {
      ...(afterGroupOrder === undefined ? {} : { afterGroupOrder }),
      limit: 100,
    });
    if (result.error !== undefined || result.data === undefined) {
      throw new Error('IMAGE_SELECTION_GROUPS_UNAVAILABLE');
    }
    groups.push(...result.data.items);
    afterGroupOrder = result.data.nextAfterGroupOrder ?? undefined;
  } while (afterGroupOrder !== undefined);
  return groups;
}

export async function continueWithAutomaticallySelectedImages(
  api: ImageSelectionClient,
  runId: string,
  groups: readonly ImageSelectionGroupResponse[],
  idempotencyKeyFactory: () => string = () => crypto.randomUUID(),
): Promise<{
  readonly error: string | null;
  readonly skippedCount: number;
  readonly updatedGroups: readonly ImageSelectionGroupResponse[];
}> {
  const unresolved = groups.filter(
    (group) => group.status === 'manual_required',
  );
  const updatedGroups: ImageSelectionGroupResponse[] = [];
  for (const group of unresolved) {
    const result = await api.continueImageSelectionWithoutImage(
      runId,
      group.id,
      {
        idempotencyKey: idempotencyKeyFactory(),
      },
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pominąć nierozpoznanego zestawu zdjęć.',
        ),
        skippedCount: updatedGroups.length,
        updatedGroups,
      };
    }
    updatedGroups.push(result.data.group);
  }
  return {
    error: null,
    skippedCount: updatedGroups.length,
    updatedGroups,
  };
}

export async function saveImageSelectionOutputToFolder(
  api: ImageSelectionClient,
  runId: string,
  options: {
    readonly pickDirectory?: () => Promise<OutputDirectoryHandle>;
  } = {},
): Promise<ImageSelectionOutputSaveResult> {
  let directory: OutputDirectoryHandle;
  try {
    directory = await (options.pickDirectory ?? pickOutputDirectory)();
  } catch (error) {
    return isPickerCancellation(error)
      ? { cancelled: true, error: null, savedCount: 0 }
      : {
          cancelled: false,
          error:
            'Ta przeglądarka nie pozwala wybrać folderu docelowego. Użyj aktualnej wersji Chrome lub Edge.',
          savedCount: 0,
        };
  }

  const output = await api.getImageSelectionOutput(runId);
  if (output.error !== undefined || output.data === undefined) {
    return {
      cancelled: false,
      error: apiErrorMessage(
        output.error,
        'Nie udało się zweryfikować listy wybranych zdjęć. Uruchom ponownie lokalne Admin API i spróbuj ponownie.',
      ),
      savedCount: 0,
    };
  }

  let savedCount = 0;
  for (const file of output.data.files) {
    const downloaded = await api.getImageSelectionOutputFile(
      runId,
      file.fileName,
    );
    if (downloaded.error !== undefined || downloaded.data === undefined) {
      return {
        cancelled: false,
        error: `Nie udało się pobrać ${file.fileName}. Zapisano ${savedCount} z ${output.data.files.length} zdjęć.`,
        savedCount,
      };
    }
    const blob = toBlob(downloaded.data);
    if (blob === null || (await sha256(blob)) !== file.checksumSha256) {
      return {
        cancelled: false,
        error: `Plik ${file.fileName} nie przeszedł weryfikacji integralności. Zapis został przerwany.`,
        savedCount,
      };
    }
    const fileHandle = await directory.getFileHandle(file.fileName, {
      create: true,
    });
    const writable = await fileHandle.createWritable();
    try {
      await writable.write(blob);
      await writable.close();
      savedCount += 1;
    } catch {
      await writable.abort().catch(() => undefined);
      return {
        cancelled: false,
        error: `Nie udało się zapisać ${file.fileName}. Zapisano ${savedCount} z ${output.data.files.length} zdjęć.`,
        savedCount,
      };
    }
  }
  return { cancelled: false, error: null, savedCount };
}

function suggestBoundedMissingRange(
  group: ImageSelectionGroupResponse,
  allGroups: readonly ImageSelectionGroupResponse[],
): ImageSelectionGroupResponse {
  if (
    group.status !== 'manual_required' ||
    group.rangeStart !== null ||
    group.rangeEnd !== null
  ) {
    return group;
  }
  const resolved = allGroups.filter(
    (candidate) =>
      candidate.rangeStart !== null &&
      candidate.rangeEnd !== null &&
      (candidate.status === 'auto_selected' ||
        candidate.status === 'manually_selected' ||
        candidate.status === 'missing_image'),
  );
  const previous = resolved
    .filter((candidate) => candidate.groupOrder < group.groupOrder)
    .sort((left, right) => right.groupOrder - left.groupOrder)[0];
  const next = resolved
    .filter((candidate) => candidate.groupOrder > group.groupOrder)
    .sort((left, right) => left.groupOrder - right.groupOrder)[0];
  if (previous?.rangeEnd == null || next?.rangeStart == null) return group;
  const rangeStart = previous.rangeEnd + 1;
  const rangeEnd = next.rangeStart - 1;
  if (rangeStart > rangeEnd || rangeEnd - rangeStart + 1 > 9) return group;
  const unresolvedInGap = allGroups.filter(
    (candidate) =>
      candidate.status === 'manual_required' &&
      candidate.rangeStart === null &&
      candidate.rangeEnd === null &&
      candidate.groupOrder > previous.groupOrder &&
      candidate.groupOrder < next.groupOrder,
  );
  if (unresolvedInGap.length !== 1 || unresolvedInGap[0]?.id !== group.id) {
    return group;
  }
  return { ...group, rangeEnd, rangeStart };
}

function relativePath(file: File | undefined): string {
  return file?.webkitRelativePath || file?.name || '';
}

export function pickImageSelectionOutputDirectory(): Promise<OutputDirectoryHandle> {
  const picker = (window as DirectoryPickerWindow).showDirectoryPicker;
  if (picker === undefined) {
    throw new Error('DIRECTORY_PICKER_UNAVAILABLE');
  }
  return picker({ mode: 'readwrite' });
}

function pickOutputDirectory(): Promise<OutputDirectoryHandle> {
  return pickImageSelectionOutputDirectory();
}

function isPickerCancellation(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
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

async function sha256(blob: Blob): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    await blob.arrayBuffer(),
  );
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

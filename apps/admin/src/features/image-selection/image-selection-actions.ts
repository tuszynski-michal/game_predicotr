import type {
  AdminApiClient,
  ImageSelectionCreateResponse,
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
  | 'getImageSelection'
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
  } = {},
): Promise<ImageSelectionUploadResult> {
  const files = options.resume?.files ?? orderImageSelectionFiles(sourceFiles);
  if (files.length === 0) {
    return { error: 'Wybrany folder nie zawiera plików JPEG.', ok: false, resume: null };
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
        resume: null,
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
    options.onProgress?.({ totalBytes, totalFiles: files.length, uploadedBytes, uploadedFiles });

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
              uploadedFiles = Math.max(uploadedFiles, result.data.uploadedFileCount);
              uploadedBytes = Math.max(uploadedBytes, result.data.uploadedBytes);
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
      gameId,
      selectionToken: finalized.data.selectionToken,
    });
    if (created.error !== undefined || created.data === undefined) {
      return {
        error: apiErrorMessage(
          created.error,
          'Nie udało się utworzyć procesu selekcji zdjęć.',
        ),
        ok: false,
        resume: null,
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

export async function cancelPhotoSelectionUpload(
  api: ImageSelectionClient,
  upload: ResumableImageSelectionUpload,
): Promise<void> {
  await api.cancelBrowserImageSelection(upload.uploadId);
}

function relativePath(file: File | undefined): string {
  return file?.webkitRelativePath || file?.name || '';
}

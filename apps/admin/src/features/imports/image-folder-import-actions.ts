import type {
  AdminApiClient,
  ImageFolderSelectionResponse,
  JobResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type ImageFolderImportClient = Pick<
  AdminApiClient,
  | 'createImageFolderImport'
  | 'createBrowserImageSelection'
  | 'uploadBrowserImageSelectionFile'
  | 'finalizeBrowserImageSelection'
  | 'cancelBrowserImageSelection'
  | 'getImageDatasetCompleteness'
  | 'getImageSequenceSourceSelection'
  | 'registerCuratedImageImportSource'
  | 'listCuratedImageImportSources'
  | 'createNextCuratedImageImportBatch'
  | 'listJobs'
  | 'reprocessManagedImageImport'
  | 'selectImageSequenceSource'
>;

type Failure = { readonly error: string; readonly ok: false };

export async function uploadImageFolder(
  api: ImageFolderImportClient,
  files: readonly File[],
  onProgress?: (uploaded: number, total: number) => void,
): Promise<
  | {
      readonly displayName: string;
      readonly ok: true;
      readonly selection: ImageFolderSelectionResponse;
    }
  | Failure
> {
  let uploadId: string | null = null;
  try {
    const totalBytes = files.reduce((total, file) => total + file.size, 0);
    const firstRelativePath = files[0]?.webkitRelativePath || files[0]?.name;
    const displayName = firstRelativePath?.split('/')[0] || 'Wybrane pliki';
    const created = await api.createBrowserImageSelection({
      displayName,
      expectedFileCount: files.length,
      expectedTotalBytes: totalBytes,
    });
    if (created.error !== undefined || created.data === undefined) {
      return {
        error: apiErrorMessage(
          created.error,
          'Nie udało się rozpocząć przesyłania wybranego folderu.',
        ),
        ok: false,
      };
    }
    uploadId = created.data.uploadId;
    for (const [index, file] of files.entries()) {
      const uploaded = await api.uploadBrowserImageSelectionFile(
        uploadId,
        index,
        file.webkitRelativePath || file.name,
        file,
      );
      if (uploaded.error !== undefined || uploaded.data === undefined) {
        await cancelBrowserUpload(api, uploadId);
        return {
          error: apiErrorMessage(
            uploaded.error,
            `Nie udało się przesłać pliku ${index + 1} z ${files.length}.`,
          ),
          ok: false,
        };
      }
      onProgress?.(index + 1, files.length);
    }
    const finalized = await api.finalizeBrowserImageSelection(uploadId);
    if (finalized.error !== undefined || finalized.data === undefined) {
      await cancelBrowserUpload(api, uploadId);
      return {
        error: apiErrorMessage(
          finalized.error,
          'Nie udało się zweryfikować przesłanego folderu zdjęć.',
        ),
        ok: false,
      };
    }
    uploadId = null;
    return { displayName, ok: true, selection: finalized.data };
  } catch {
    if (uploadId !== null) {
      await cancelBrowserUpload(api, uploadId);
    }
    return {
      error: 'Przesyłanie folderu do lokalnego Admin API zostało przerwane.',
      ok: false,
    };
  }
}

async function cancelBrowserUpload(
  api: ImageFolderImportClient,
  uploadId: string,
): Promise<void> {
  try {
    await api.cancelBrowserImageSelection(uploadId);
  } catch {
    // The original upload failure remains the actionable error for the owner.
  }
}

export async function createImageFolderImport(
  api: ImageFolderImportClient,
  gameId: string,
  selectionToken: string,
): Promise<{ readonly job: JobResponse; readonly ok: true } | Failure> {
  try {
    const result = await api.createImageFolderImport({
      gameId,
      selectionToken,
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć importu zdjęć.',
        ),
        ok: false,
      };
    }
    return { job: result.data.job, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function reprocessImageFolderImport(
  api: ImageFolderImportClient,
  sourceJobId: string,
): Promise<{ readonly job: JobResponse; readonly ok: true } | Failure> {
  try {
    const result = await api.reprocessManagedImageImport(sourceJobId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się ponownie przetworzyć zachowanych oryginałów.',
        ),
        ok: false,
      };
    }
    return { job: result.data.job, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

import type {
  AdminApiClient,
  BrowserImageImportPreflightResponse,
  BrowserImageImportStartResponse,
  BrowserReadySelectionResponse,
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
  | 'listReadyBrowserImageSelections'
  | 'previewReadyBrowserImageImport'
  | 'startReadyBrowserImageImport'
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
  gameIdOrProgress?: string | ((uploaded: number, total: number) => void),
  progressCallback?: (uploaded: number, total: number) => void,
): Promise<
  | {
      readonly displayName: string;
      readonly ok: true;
      readonly selection: ImageFolderSelectionResponse;
      readonly uploadId: string;
    }
  | Failure
> {
  let uploadId: string | null = null;
  try {
    const gameId =
      typeof gameIdOrProgress === 'string' ? gameIdOrProgress : undefined;
    const onProgress =
      typeof gameIdOrProgress === 'function'
        ? gameIdOrProgress
        : progressCallback;
    const totalBytes = files.reduce((total, file) => total + file.size, 0);
    const firstRelativePath = files[0]?.webkitRelativePath || files[0]?.name;
    const displayName = firstRelativePath?.split('/')[0] || 'Wybrane pliki';
    const created = await api.createBrowserImageSelection({
      displayName,
      expectedFileCount: files.length,
      expectedTotalBytes: totalBytes,
      ...(gameId === undefined ? {} : { gameId }),
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
    const finalizedUploadId = uploadId;
    uploadId = null;
    return {
      displayName,
      ok: true,
      selection: finalized.data,
      uploadId: finalizedUploadId,
    };
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

export async function listReadyBrowserImageSelections(
  api: ImageFolderImportClient,
): Promise<
  | {
      readonly data: readonly BrowserReadySelectionResponse[];
      readonly ok: true;
    }
  | Failure
> {
  try {
    const result = await api.listReadyBrowserImageSelections();
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać gotowych stagingów importu layoutów.',
        ),
        ok: false,
      };
    }
    return { data: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function previewReadyBrowserImageImport(
  api: ImageFolderImportClient,
  uploadId: string,
  gameId: string,
): Promise<
  | { readonly data: BrowserImageImportPreflightResponse; readonly ok: true }
  | Failure
> {
  try {
    const result = await api.previewReadyBrowserImageImport(uploadId, {
      gameId,
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się przygotować raportu przed importem layoutów.',
        ),
        ok: false,
      };
    }
    return { data: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function startReadyBrowserImageImport(
  api: ImageFolderImportClient,
  uploadId: string,
  gameId: string,
  manifestChecksumSha256: string,
  preflightChecksumSha256: string,
  symbolModelInferenceFingerprint?: string,
  gridProfileInferenceFingerprint?: string,
): Promise<
  | { readonly data: BrowserImageImportStartResponse; readonly ok: true }
  | Failure
> {
  try {
    const result = await api.startReadyBrowserImageImport(uploadId, {
      gameId,
      manifestChecksumSha256,
      preflightChecksumSha256,
      ...(symbolModelInferenceFingerprint === undefined
        ? {}
        : { symbolModelInferenceFingerprint }),
      ...(gridProfileInferenceFingerprint === undefined
        ? {}
        : { gridProfileInferenceFingerprint }),
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć importu layoutów.',
        ),
        ok: false,
      };
    }
    return { data: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
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

import type {
  AdminApiClient,
  BrowserImageImportPreflightResponse,
  BrowserImageImportStart,
  BrowserImageImportStartResponse,
  BrowserImageUploadPlanResponse,
  BrowserPageGeometryPreflightResponse,
  BrowserReadySelectionResponse,
  ImageFolderSelectionResponse,
  JobResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type ImageFolderImportClient = Pick<
  AdminApiClient,
  | 'createImageFolderImport'
  | 'createBrowserImageSelection'
  | 'planBrowserImageSelectionUpload'
  | 'uploadBrowserImageSelectionFile'
  | 'finalizeBrowserImageSelection'
  | 'listReadyBrowserImageSelections'
  | 'previewReadyBrowserImageImport'
  | 'startReadyBrowserImageImport'
  | 'startBrowserPageGeometryPreflight'
  | 'listBrowserPageGeometryReviewSources'
  | 'createBrowserPageGeometryOverride'
  | 'cancelBrowserImageSelection'
  | 'getImageDatasetCompleteness'
  | 'getImageSequenceSourceSelection'
  | 'registerCuratedImageImportSource'
  | 'listCuratedImageImportSources'
  | 'createNextCuratedImageImportBatch'
  | 'listJobs'
  | 'getJob'
  | 'reprocessManagedImageImport'
  | 'selectImageSequenceSource'
  | 'getImageImportEnginePolicy'
  | 'previewImageImportEnginePolicy'
  | 'updateImageImportEnginePolicy'
>;

type Failure = { readonly error: string; readonly ok: false };

const UPLOAD_PROGRESS_PAINT_INTERVAL = 25;

export function filterImageFolderImportFiles(
  files: readonly File[],
): readonly File[] {
  return files.filter((file) => /\.jpe?g$/iu.test(file.name));
}

async function yieldForUploadProgressPaint(uploadedFileCount: number) {
  if (
    uploadedFileCount !== 1 &&
    uploadedFileCount % UPLOAD_PROGRESS_PAINT_INTERVAL !== 0
  ) {
    return;
  }
  await new Promise<void>((resolve) => globalThis.setTimeout(resolve, 0));
}

export type BoardCellProcessingMode = NonNullable<
  BrowserImageImportStart['boardCellProcessingMode']
>;

export async function uploadImageFolder(
  api: ImageFolderImportClient,
  files: readonly File[],
  gameIdOrProgress?: string | ((uploaded: number, total: number) => void),
  progressCallback?: (uploaded: number, total: number) => void,
): Promise<
  | {
      readonly displayName: string;
      readonly kind: 'uploaded';
      readonly ok: true;
      readonly selection: ImageFolderSelectionResponse;
      readonly uploadId: string;
      readonly uploadPlan: BrowserImageUploadPlanResponse | null;
    }
  | {
      readonly displayName: string;
      readonly kind: 'nothing_to_upload';
      readonly ok: true;
      readonly uploadPlan: BrowserImageUploadPlanResponse;
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
    let filesToUpload = files;
    let uploadPlan: BrowserImageUploadPlanResponse | null = null;
    if (typeof gameId === 'string') {
      const planned = await api.planBrowserImageSelectionUpload({
        gameId,
        files: files.map((file, sourceIndex) => ({
          relativePath: file.webkitRelativePath || file.name,
          sizeBytes: file.size,
          sourceIndex,
        })),
      });
      if (planned.error !== undefined || planned.data === undefined) {
        return {
          error: apiErrorMessage(
            planned.error,
            'Nie udało się sprawdzić, które zdjęcia wymagają importu.',
          ),
          ok: false,
        };
      }
      uploadPlan = planned.data;
      filesToUpload = planned.data.filesToUpload.map((item) => {
        const file = files[item.sourceIndex];
        if (file === undefined) {
          throw new Error('Plan uploadu wskazuje nieistniejący plik lokalny.');
        }
        return file;
      });
      if (filesToUpload.length === 0) {
        return {
          displayName:
            (
              files[0]?.webkitRelativePath ||
              files[0]?.name ||
              'Wybrane pliki'
            ).split('/')[0] || 'Wybrane pliki',
          kind: 'nothing_to_upload',
          ok: true,
          uploadPlan,
        };
      }
    }
    const totalBytes = filesToUpload.reduce(
      (total, file) => total + file.size,
      0,
    );
    const firstRelativePath = files[0]?.webkitRelativePath || files[0]?.name;
    const displayName = firstRelativePath?.split('/')[0] || 'Wybrane pliki';
    const created = await api.createBrowserImageSelection({
      displayName,
      expectedFileCount: filesToUpload.length,
      expectedTotalBytes: totalBytes,
      ...(gameId === undefined ? {} : { gameId }),
      ...(uploadPlan === null
        ? {}
        : {
            skippedCanonicalRanges: uploadPlan.skippedCompleteSources.map(
              (source) => ({
                sequenceRangeEnd: source.sequenceRangeEnd,
                sequenceRangeStart: source.sequenceRangeStart,
              }),
            ),
            uploadPlanChecksumSha256: uploadPlan.planChecksumSha256,
          }),
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
    for (const [index, file] of filesToUpload.entries()) {
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
            `Nie udało się przesłać pliku ${index + 1} z ${filesToUpload.length}.`,
          ),
          ok: false,
        };
      }
      onProgress?.(
        uploaded.data.uploadedFileCount,
        uploaded.data.expectedFileCount,
      );
      // A large local folder can produce thousands of very fast sequential
      // fetch completions. Yield a macrotask after the first acknowledgement
      // and then periodically so React can paint server-confirmed progress.
      await yieldForUploadProgressPaint(uploaded.data.uploadedFileCount);
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
      kind: 'uploaded',
      ok: true,
      selection: finalized.data,
      uploadId: finalizedUploadId,
      uploadPlan,
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
          'Nie udało się pobrać gotowych stagingów importu plansz.',
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
          'Nie udało się przygotować raportu przed importem plansz.',
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
  geometryPreflightJobId: string | undefined,
  geometryManifestChecksumSha256: string | undefined,
  boardCellProcessingMode: BoardCellProcessingMode,
  imageEnginePolicyRevision: number,
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
      ...(geometryPreflightJobId === undefined
        ? {}
        : { geometryPreflightJobId }),
      ...(geometryManifestChecksumSha256 === undefined
        ? {}
        : { geometryManifestChecksumSha256 }),
      boardCellProcessingMode,
      imageEnginePolicy: boardCellProcessingMode,
      ...(imageEnginePolicyRevision === undefined
        ? {}
        : { imageEnginePolicyRevision }),
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć importu plansz.',
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

export async function startBrowserPageGeometryPreflight(
  api: ImageFolderImportClient,
  uploadId: string,
  gameId: string,
): Promise<
  | { readonly data: BrowserPageGeometryPreflightResponse; readonly ok: true }
  | Failure
> {
  try {
    const result = await api.startBrowserPageGeometryPreflight(uploadId, {
      gameId,
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć preflightu geometrii stron.',
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

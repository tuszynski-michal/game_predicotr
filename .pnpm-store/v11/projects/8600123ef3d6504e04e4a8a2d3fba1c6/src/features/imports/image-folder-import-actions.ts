import type {
  AdminApiClient,
  ImageFolderSelectionResponse,
  JobResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type ImageFolderImportClient = Pick<
  AdminApiClient,
  | 'createImageFolderImport'
  | 'getImageDatasetCompleteness'
  | 'getImageSequenceSourceSelection'
  | 'listJobs'
  | 'selectImageSequenceSource'
  | 'selectLocalImageFolder'
>;

type Failure = { readonly error: string; readonly ok: false };

export async function selectImageFolder(
  api: ImageFolderImportClient,
): Promise<
  | { readonly ok: true; readonly selection: ImageFolderSelectionResponse }
  | Failure
> {
  try {
    const result = await api.selectLocalImageFolder();
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się otworzyć lub zweryfikować folderu zdjęć.',
        ),
        ok: false,
      };
    }
    return { ok: true, selection: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
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

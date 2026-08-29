import type {
  AdminApiClient,
  ImageGridReviewGeometryResponse,
  ImageGridReviewItemResponse,
  ImageGridReviewPageResponse,
  ImageGridReviewView,
  OperationalImageReviewResolutionCommand,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '@/features/catalog/catalog-api-error';

import {
  GRID_REVIEW_PAGE_LIMIT,
  GRID_REVIEW_SOURCE_PAGE_LIMIT,
  gridReviewApprovalCommand,
  gridReviewGeometryCommand,
  gridReviewGeometryPreviewCommand,
  type GridReviewNavigation,
} from './grid-review-state';
import type { OperationalReviewGeometryCorners } from '../operational-reviews/operational-review-state';

export type GridReviewsClient = Pick<
  AdminApiClient,
  | 'approveImageGridReviewGeometry'
  | 'createImageGridReviewGeometryRevision'
  | 'getImageGridReviewSourceAsset'
  | 'imageGridReviewSourceAssetUrl'
  | 'listImageGridReviews'
  | 'previewImageGridReviewGeometry'
  | 'resolveOperationalImageReviewItem'
>;

export type GridReviewActionFailure = {
  readonly error: string;
  readonly isConflict: boolean;
  readonly ok: false;
};

export async function loadGridReviewPage(
  api: GridReviewsClient,
  input: {
    readonly gameId: string;
    readonly importJobId: string;
    readonly navigation?: GridReviewNavigation;
    readonly view: ImageGridReviewView;
  },
): Promise<
  | { readonly ok: true; readonly page: ImageGridReviewPageResponse }
  | GridReviewActionFailure
> {
  return loadGridReviewList(api, {
    ...input,
    limit: GRID_REVIEW_PAGE_LIMIT,
  });
}

export async function loadGridReviewSource(
  api: GridReviewsClient,
  input: {
    readonly gameId: string;
    readonly importJobId: string;
    readonly sourceImageId: string;
  },
): Promise<
  | { readonly ok: true; readonly page: ImageGridReviewPageResponse }
  | GridReviewActionFailure
> {
  return loadGridReviewList(api, {
    ...input,
    limit: GRID_REVIEW_SOURCE_PAGE_LIMIT,
    view: 'all',
  });
}

async function loadGridReviewList(
  api: GridReviewsClient,
  input: {
    readonly gameId: string;
    readonly importJobId: string;
    readonly limit: number;
    readonly navigation?: GridReviewNavigation;
    readonly sourceImageId?: string;
    readonly view: ImageGridReviewView;
  },
): Promise<
  | { readonly ok: true; readonly page: ImageGridReviewPageResponse }
  | GridReviewActionFailure
> {
  try {
    const result = await api.listImageGridReviews({
      gameId: input.gameId,
      importJobId: input.importJobId,
      limit: input.limit,
      sourceImageId: input.sourceImageId,
      view: input.view,
      ...input.navigation,
    });
    if (result.error !== undefined || result.data === undefined) {
      return failure(
        result.error,
        'Nie udało się pobrać kolejki walidacji siatki.',
      );
    }
    return { ok: true, page: result.data };
  } catch {
    return disconnected();
  }
}

export async function approveGridReview(
  api: GridReviewsClient,
  item: ImageGridReviewItemResponse,
) {
  try {
    const result = await api.approveImageGridReviewGeometry(
      item.reviewItemId,
      item.gameId,
      gridReviewApprovalCommand(item),
    );
    if (result.error !== undefined || result.data === undefined) {
      return failure(result.error, 'Nie udało się zatwierdzić cięcia siatki.');
    }
    return { item: result.data.item, ok: true as const };
  } catch {
    return disconnected();
  }
}

export async function rejectGridReview(
  api: GridReviewsClient,
  item: ImageGridReviewItemResponse,
) {
  const command: OperationalImageReviewResolutionCommand = {
    action: 'rejected',
    expectedRevision: item.resolutionRevision,
    geometryRevision: item.geometryRevision,
    idempotencyKey: globalThis.crypto.randomUUID(),
    rejectionReason: 'geometry_source_rejected',
    resolvedBy: 'local-admin',
  };
  try {
    const result = await api.resolveOperationalImageReviewItem(
      item.reviewItemId,
      { gameId: item.gameId, importJobId: item.importJobId },
      command,
    );
    if (result.error !== undefined || result.data === undefined) {
      return failure(
        result.error,
        'Nie udało się odrzucić planszy z tego źródła.',
      );
    }
    return { ok: true as const };
  } catch {
    return disconnected();
  }
}

export async function previewGridReviewGeometry(
  api: GridReviewsClient,
  item: ImageGridReviewItemResponse,
  corners: OperationalReviewGeometryCorners,
) {
  try {
    const result = await api.previewImageGridReviewGeometry(
      item.reviewItemId,
      { gameId: item.gameId, importJobId: item.importJobId },
      gridReviewGeometryPreviewCommand(item, corners),
    );
    if (result.error !== undefined || !(result.data instanceof Blob)) {
      return failure(
        result.error,
        'Nie udało się wygenerować podglądu poprawionej siatki.',
      );
    }
    return { blob: result.data, ok: true as const };
  } catch {
    return disconnected();
  }
}

export async function saveGridReviewGeometry(
  api: GridReviewsClient,
  item: ImageGridReviewItemResponse,
  corners: OperationalReviewGeometryCorners,
  idempotencyKey: string,
): Promise<
  | {
      readonly geometry: ImageGridReviewGeometryResponse;
      readonly ok: true;
    }
  | GridReviewActionFailure
> {
  try {
    const result = await api.createImageGridReviewGeometryRevision(
      item.reviewItemId,
      { gameId: item.gameId, importJobId: item.importJobId },
      gridReviewGeometryCommand(item, corners, idempotencyKey),
    );
    if (result.error !== undefined || result.data === undefined) {
      return failure(result.error, 'Nie udało się zapisać poprawionej siatki.');
    }
    return { geometry: result.data, ok: true };
  } catch {
    return disconnected();
  }
}

function failure(error: unknown, fallback: string): GridReviewActionFailure {
  return {
    error: apiErrorMessage(error, fallback),
    isConflict:
      hasCode(error, 'IMAGE_REVIEW_REVISION_CONFLICT') ||
      hasCode(error, 'IMAGE_REVIEW_GEOMETRY_REVISION_CONFLICT') ||
      hasCode(error, 'IMAGE_GRID_REVIEW_CURSOR_INVALID') ||
      hasCode(error, 'IMAGE_GRID_REVIEW_CURSOR_SCOPE_INVALID'),
    ok: false,
  };
}

function disconnected(): GridReviewActionFailure {
  return {
    error: 'Połączenie z lokalnym Admin API zostało przerwane.',
    isConflict: false,
    ok: false,
  };
}

function hasCode(error: unknown, code: string): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    (error as { readonly code?: unknown }).code === code
  );
}

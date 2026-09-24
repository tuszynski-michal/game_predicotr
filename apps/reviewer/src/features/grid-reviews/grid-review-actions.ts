import type {
  AdminApiClient,
  ImageGridReviewGeometryResponse,
  ImageGridReviewItemResponse,
  ImageGridReviewPageResponse,
  ImageGridReviewView,
  GeometryQualificationPayload,
  OperationalImageReviewResolutionCommand,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

import {
  GRID_REVIEW_PAGE_LIMIT,
  GRID_REVIEW_SOURCE_PAGE_LIMIT,
  gridReviewApprovalCommand,
  gridReviewCorners,
  gridReviewQualification,
  gridReviewGeometryCommand,
  gridReviewGeometryPreviewCommand,
  type GridReviewNavigation,
} from './grid-review-state.ts';
import type { OperationalReviewGeometryCorners } from '../operational-reviews/operational-review-state.ts';

export type GridReviewsClient = Pick<
  AdminApiClient,
  | 'approveImageGridReviewGeometry'
  | 'approveImageGridReviewSourceGeometry'
  | 'createImageGridReviewGeometryRevision'
  | 'createImageGridReviewSourceGeometryRevision'
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
  if (item.reviewItemId === null) {
    return {
      error: 'Brakująca plansza wymaga zapisania geometrii całego zdjęcia.',
      isConflict: false,
      ok: false as const,
    };
  }
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

export async function approveGridReviewSource(
  api: GridReviewsClient,
  items: readonly ImageGridReviewItemResponse[],
) {
  const first = items[0];
  if (first === undefined) {
    return {
      error: 'Nie ma aktywnych plansz do zatwierdzenia.',
      isConflict: false,
      ok: false as const,
    };
  }
  const pendingItems = items.filter((item) => item.reviewItemId === null);
  if (
    pendingItems.some(
      (item) =>
        (item.automaticPartialProposal == null &&
          item.automaticFrameProposal == null) ||
        item.symbolGridQuad == null,
    )
  ) {
    return {
      error:
        'Brakujące plansze wymagają zapisania kompletnej geometrii zdjęcia.',
      isConflict: false,
      ok: false as const,
    };
  }
  if (pendingItems.length > 0) {
    const qualifications = new Map(
      items.flatMap((item) => {
        const qualification = gridReviewQualification(item);
        return qualification === undefined
          ? []
          : ([[item.slotId, qualification]] as const);
      }),
    );
    const result = await saveGridReviewSourceGeometry(api, {
      cornersByReviewItemId: new Map(
        items.map((item) => [item.slotId, gridReviewCorners(item)]),
      ),
      idempotencyKey: globalThis.crypto.randomUUID(),
      items,
      qualificationBySlotId:
        qualifications.size > 0 ? qualifications : undefined,
    });
    return result.ok
      ? {
          approval: { changedCount: result.changedCount },
          ok: true as const,
        }
      : result;
  }
  try {
    const result = await api.approveImageGridReviewSourceGeometry(
      first.gameId,
      {
        sourceImageId: first.sourceImageId,
        targets: items.map((item) => ({
          expectedGeometryRevision: item.geometryRevision,
          expectedGridColumns: item.gridColumns,
          expectedGridRows: item.gridRows,
          expectedResolutionRevision: item.resolutionRevision,
          expectedSourceChecksumSha256: item.sourceChecksumSha256,
          expectedSourceHeight: item.sourceHeight,
          expectedSourceWidth: item.sourceWidth,
          reviewItemId: item.reviewItemId!,
        })),
      },
    );
    if (result.error !== undefined || result.data === undefined) {
      return failure(result.error, 'Nie udało się zatwierdzić całego zdjęcia.');
    }
    return { approval: result.data, ok: true as const };
  } catch {
    return disconnected();
  }
}

export async function rejectGridReview(
  api: GridReviewsClient,
  item: ImageGridReviewItemResponse,
) {
  if (item.reviewItemId === null) {
    return {
      error: 'Brakującej planszy nie można pominąć. Wyznacz jej geometrię.',
      isConflict: false,
      ok: false as const,
    };
  }
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

/** Maps the reason `source-asset` refused a grid-review original to a
 * distinguishable operator message. Called only after the `<img>` element
 * itself failed to load, to explain why — never to source the image. */
export async function describeGridSourceAssetFailure(
  api: GridReviewsClient,
  item: {
    readonly gameId: string;
    readonly slotId: string;
    readonly sourceChecksumSha256: string;
  },
): Promise<string> {
  try {
    const result = await api.getImageGridReviewSourceAsset(
      item.slotId,
      item.gameId,
      item.sourceChecksumSha256,
    );
    if (result.error === undefined) {
      return 'Nie udało się zdekodować obrazu źródłowego.';
    }
    if (hasCode(result.error, 'IMAGE_REVIEW_ASSET_NOT_FOUND')) {
      return 'Brak pliku oryginału w magazynie aplikacji.';
    }
    if (
      hasCode(result.error, 'IMAGE_REVIEW_ASSET_CHECKSUM_DRIFT') ||
      hasCode(result.error, 'IMAGE_GRID_REVIEW_SOURCE_DRIFT')
    ) {
      return 'Oryginał zmienił się od wczytania kolejki — odśwież.';
    }
    if (hasCode(result.error, 'IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE')) {
      return 'Projekcja symboli tej gry nie jest gotowa.';
    }
    if (hasCode(result.error, 'IMAGE_GRID_REVIEW_ITEM_NOT_FOUND')) {
      return 'Plansza nie jest już aktualna — odśwież kolejkę.';
    }
    return apiErrorMessage(
      result.error,
      'Nie udało się wczytać oryginalnego obrazu źródłowego.',
    );
  } catch {
    return disconnected().error;
  }
}

export async function previewGridReviewGeometry(
  api: GridReviewsClient,
  item: ImageGridReviewItemResponse,
  corners: OperationalReviewGeometryCorners,
) {
  if (item.reviewItemId === null) {
    return {
      error: 'Podgląd powstanie po zapisaniu kompletnej geometrii zdjęcia.',
      isConflict: false,
      ok: false as const,
    };
  }
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
  if (item.reviewItemId === null) {
    return {
      error: 'Brakującą planszę zapisz razem z kompletem plansz zdjęcia.',
      isConflict: false,
      ok: false,
    };
  }
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

export async function saveGridReviewSourceGeometry(
  api: GridReviewsClient,
  input: {
    readonly items: readonly ImageGridReviewItemResponse[];
    readonly cornersByReviewItemId: ReadonlyMap<
      string,
      OperationalReviewGeometryCorners
    >;
    readonly idempotencyKey: string;
    readonly qualificationBySlotId?: ReadonlyMap<
      string,
      GeometryQualificationPayload
    >;
  },
): Promise<
  | {
      readonly changedCount: number;
      readonly ok: true;
    }
  | GridReviewActionFailure
> {
  const first = input.items[0];
  if (first === undefined) {
    return {
      error: 'Nie ma aktywnych plansz do zapisania.',
      isConflict: false,
      ok: false,
    };
  }
  const targets = [] as Array<
    Parameters<
      typeof api.createImageGridReviewSourceGeometryRevision
    >[2]['targets'][number]
  >;
  for (const item of input.items) {
    const corners = input.cornersByReviewItemId.get(item.slotId);
    if (corners === undefined) {
      return {
        error: 'Wyznacz po cztery narożniki dla każdej planszy zdjęcia.',
        isConflict: false,
        ok: false,
      };
    }
    targets.push({
      ...gridReviewGeometryPreviewCommand(item, corners),
      ...(input.qualificationBySlotId
        ? {
            geometryQualification: input.qualificationBySlotId.get(item.slotId),
          }
        : {}),
      pendingGeometryId: item.pendingGeometryId,
      reviewItemId: item.reviewItemId,
    });
  }
  try {
    const result = await api.createImageGridReviewSourceGeometryRevision(
      first.gameId,
      { gameId: first.gameId, importJobId: first.importJobId },
      {
        idempotencyKey: input.idempotencyKey,
        sourceImageId: first.sourceImageId,
        targets,
      },
    );
    if (result.error !== undefined || result.data === undefined) {
      return failure(
        result.error,
        'Nie udało się zapisać geometrii wszystkich plansz zdjęcia.',
      );
    }
    return {
      changedCount: result.data.created
        ? result.data.geometryRevisions.length
        : 0,
      ok: true,
    };
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

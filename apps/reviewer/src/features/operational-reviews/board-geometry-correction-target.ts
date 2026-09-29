import type {
  AdminApiClient,
  BoardCellGeometryCorrectionContextResponse,
  ImageGridReviewItemResponse,
  OperationalImageReviewGeometryPoint,
} from '@game-predictor/admin-api-client';
import {
  completeManualGridFlags,
  manualGridFlagsFromQualification,
  manualGridQualification,
  type ManualGridFlags,
} from '@game-predictor/manual-image-selection-core/manual-grid-qualification';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import {
  gridReviewCorners,
  gridReviewGeometryPreviewCommand,
  gridReviewQualification,
} from '../grid-reviews/grid-review-state.ts';

import {
  type DeferredBoardCellGeometryClient,
  type DeferredBoardCellGeometryFailure,
  loadDeferredBoardCellGeometryContext,
  previewDeferredBoardCellGeometry,
  resolveDeferredBoardCellGeometry,
} from './deferred-board-cell-geometry-actions.ts';
import {
  deferredBoardCellGeometryCommandKey,
  deferredBoardCellGeometryCorners,
  deferredBoardCellGeometryPreviewCommand,
  deferredBoardCellGeometryReasonLabel,
  deferredBoardCellGeometryResolutionCommand,
  deferredBoardCellGeometrySourceUrl,
} from './deferred-board-cell-geometry-state.ts';
import type { OperationalReviewGeometryCorners } from './operational-review-state.ts';

/**
 * One board whose grid a human corrects on the single-board screen (D-462).
 * The editor never knows whether the board is a deferred slot or a current
 * board with a `Zła siatka` report; both save exactly this one board.
 */
export interface BoardGeometryCorrectionView {
  /** The board's persisted qualification, so a partial board stays partial. */
  readonly initialFlags: ManualGridFlags;
  readonly kind: 'deferred' | 'reported';
  readonly metadata: readonly BoardGeometryCorrectionFact[];
  readonly reportedCellIndices: readonly number[];
  readonly saveHint: string;
  readonly sourceHeight: number;
  readonly sourceUrl: string;
  readonly sourceWidth: number;
  readonly suggestedCorners: OperationalReviewGeometryCorners;
  readonly supportsPartial: boolean;
}

export interface BoardGeometryCorrectionFact {
  readonly label: string;
  readonly title?: string;
  readonly value: string;
}

export type BoardGeometryCorrectionFailure = DeferredBoardCellGeometryFailure;

export interface BoardGeometryCorrectionTarget {
  /** Stable identity of the board version the editor was opened for. */
  readonly key: string;
  load(): Promise<
    | { readonly ok: true; readonly view: BoardGeometryCorrectionView }
    | BoardGeometryCorrectionFailure
  >;
  /** Throws when the flags do not describe a valid partial board. */
  commandKey(
    corners: OperationalReviewGeometryCorners,
    flags: ManualGridFlags,
  ): string;
  preview(
    corners: OperationalReviewGeometryCorners,
    flags: ManualGridFlags,
  ): Promise<
    { readonly blob: Blob; readonly ok: true } | BoardGeometryCorrectionFailure
  >;
  save(
    corners: OperationalReviewGeometryCorners,
    flags: ManualGridFlags,
    idempotencyKey: string,
  ): Promise<
    | { readonly ok: true; readonly reviewItemId: string | null }
    | BoardGeometryCorrectionFailure
  >;
}

export function deferredBoardGeometryTarget(input: {
  readonly api: DeferredBoardCellGeometryClient;
  readonly apiBaseUrl: string;
  readonly pendingId: string;
  readonly scope: { readonly gameId: string; readonly importJobId: string };
}): BoardGeometryCorrectionTarget {
  let context: BoardCellGeometryCorrectionContextResponse | null = null;
  const loaded = (): BoardCellGeometryCorrectionContextResponse => {
    if (context === null)
      throw new Error('Kontekst planszy nie jest wczytany.');
    return context;
  };
  return {
    key: `deferred:${input.pendingId}`,
    async load() {
      const result = await loadDeferredBoardCellGeometryContext(
        input.api,
        input.scope,
        input.pendingId,
      );
      if (!result.ok) return result;
      context = result.context;
      const item = result.context.item;
      return {
        ok: true,
        view: {
          initialFlags: completeManualGridFlags,
          kind: 'deferred',
          metadata: [
            {
              label: 'Numer planszy',
              value: item.sequenceNumber.toLocaleString('pl-PL'),
            },
            {
              label: 'Pozycja na stronie',
              value: `${item.positionIndex + 1} / 9`,
            },
            {
              label: 'Powód odroczenia',
              value: deferredBoardCellGeometryReasonLabel(item.reasonCode),
            },
            {
              label: 'Plik',
              title: item.sourceRelativePath,
              value: item.sourceRelativePath,
            },
          ],
          reportedCellIndices: [],
          saveHint:
            'Zapis utworzy zwykłą planszę; jej symbole trafią do Weryfikacji symboli. Nie zatwierdzi ich automatycznie.',
          sourceHeight: result.context.sourceHeight,
          sourceUrl: deferredBoardCellGeometrySourceUrl(input.apiBaseUrl, item),
          sourceWidth: result.context.sourceWidth,
          suggestedCorners: deferredBoardCellGeometryCorners(result.context),
          supportsPartial: true,
        },
      };
    },
    commandKey(corners, flags) {
      return deferredBoardCellGeometryCommandKey(loaded(), corners, flags);
    },
    preview(corners, flags) {
      return previewDeferredBoardCellGeometry(
        input.api,
        input.scope,
        input.pendingId,
        deferredBoardCellGeometryPreviewCommand(loaded(), corners, flags),
      );
    },
    async save(corners, flags, idempotencyKey) {
      const result = await resolveDeferredBoardCellGeometry(
        input.api,
        input.scope,
        input.pendingId,
        deferredBoardCellGeometryResolutionCommand(
          loaded(),
          corners,
          idempotencyKey,
          flags,
        ),
      );
      return result.ok
        ? { ok: true, reviewItemId: result.resolution.reviewItemId }
        : result;
    },
  };
}

export type ReportedBoardGeometryClient = Pick<
  AdminApiClient,
  | 'createImageGridReviewGeometryRevision'
  | 'imageGridReviewSourceAssetUrl'
  | 'previewImageGridReviewGeometry'
>;

/** A current board routed to correction by `Zła siatka` reports. */
export function reportedBoardGeometryTarget(input: {
  readonly api: ReportedBoardGeometryClient;
  readonly item: ImageGridReviewItemResponse;
}): BoardGeometryCorrectionTarget {
  const { api, item } = input;
  const reviewItemId = item.reviewItemId;
  const scope = { gameId: item.gameId, importJobId: item.importJobId };
  const virtualSource = item.assetMode === 'virtual_source';
  const persistedQualification = virtualSource
    ? gridReviewQualification(item)
    : undefined;
  const command = (
    corners: OperationalReviewGeometryCorners,
    flags: ManualGridFlags,
  ) => {
    // A board that already carries a qualification must keep sending one
    // (also `complete`); only managed virtual sources accept it at all.
    const qualified =
      virtualSource &&
      (persistedQualification !== undefined || flags.partial || flags.exclude);
    return {
      ...gridReviewGeometryPreviewCommand(item, corners),
      geometryQualification: qualified
        ? manualGridQualification(
            flags,
            corners,
            item.sourceWidth,
            item.sourceHeight,
          )
        : null,
    };
  };
  const reported = [...(item.reportedCellIndices ?? [])].sort((a, b) => a - b);
  return {
    key: `review:${item.slotId}:${item.geometryRevision}:${item.resolutionRevision}`,
    async load() {
      if (reviewItemId === null) {
        return missingReviewItem();
      }
      return {
        ok: true,
        view: {
          initialFlags: manualGridFlagsFromQualification(
            persistedQualification,
          ),
          kind: 'reported',
          metadata: [
            {
              label: 'Numer planszy',
              value: item.sequenceNumber.toLocaleString('pl-PL'),
            },
            {
              label: 'Pozycja na stronie',
              value: `${item.positionIndex + 1} / 9`,
            },
            {
              label: 'Zgłoszone pola',
              value:
                reported.length === 0
                  ? '—'
                  : reported.map((index) => String(index + 1)).join(', '),
            },
          ],
          reportedCellIndices: reported,
          saveHint:
            'Zapis usuwa zgłoszenia „Zła siatka”. Pola ze zmienionym wycinkiem wrócą do Weryfikacji symboli; niezmienione zachowają weryfikację.',
          sourceHeight: item.sourceHeight,
          sourceUrl: api.imageGridReviewSourceAssetUrl(
            reviewItemId,
            item.gameId,
            item.sourceChecksumSha256,
          ),
          sourceWidth: item.sourceWidth,
          suggestedCorners: copyCorners(gridReviewCorners(item)),
          supportsPartial: virtualSource,
        },
      };
    },
    commandKey(corners, flags) {
      return JSON.stringify(command(corners, flags));
    },
    async preview(corners, flags) {
      if (reviewItemId === null) return missingReviewItem();
      try {
        const result = await api.previewImageGridReviewGeometry(
          reviewItemId,
          scope,
          command(corners, flags),
        );
        if (result.error !== undefined || !(result.data instanceof Blob)) {
          return failure(
            result.error,
            'Nie udało się wygenerować podglądu poprawionej siatki.',
          );
        }
        return { blob: result.data, ok: true };
      } catch {
        return disconnected();
      }
    },
    async save(corners, flags, idempotencyKey) {
      if (reviewItemId === null) return missingReviewItem();
      try {
        const result = await api.createImageGridReviewGeometryRevision(
          reviewItemId,
          scope,
          { ...command(corners, flags), idempotencyKey },
        );
        if (result.error !== undefined || result.data === undefined) {
          return failure(
            result.error,
            'Nie udało się zapisać poprawionej siatki.',
          );
        }
        return { ok: true, reviewItemId };
      } catch {
        return disconnected();
      }
    },
  };
}

export function copyCorners(
  corners: OperationalReviewGeometryCorners,
): OperationalReviewGeometryCorners {
  return corners.map((point: OperationalImageReviewGeometryPoint) => ({
    x: point.x,
    y: point.y,
  })) as unknown as OperationalReviewGeometryCorners;
}

function missingReviewItem(): BoardGeometryCorrectionFailure {
  return {
    error: 'Plansza nie ma bieżącej pozycji weryfikacji. Pomiń ją.',
    isConflict: false,
    ok: false,
  };
}

/**
 * Only codes meaning "the board changed under the operator" reload the
 * queue. Permanent failures (missing asset, drifted source or render
 * configuration, invalid qualification) stay on screen, otherwise the first
 * board would reload forever.
 */
const QUEUE_CHANGED_CODES: ReadonlySet<string> = new Set([
  'IMAGE_GRID_REVIEW_CURRENT_OWNER_CONFLICT',
  'IMAGE_GRID_REVIEW_GEOMETRY_REVISION_CONFLICT',
  'IMAGE_GRID_REVIEW_ITEM_NOT_FOUND',
  'IMAGE_GRID_REVIEW_REVISION_CONFLICT',
  'IMAGE_REVIEW_GEOMETRY_REVISION_CONFLICT',
  'IMAGE_REVIEW_ITEM_NOT_FOUND',
  'IMAGE_REVIEW_REVISION_CONFLICT',
  'IMAGE_REVIEW_SUPERSEDED',
]);

function failure(
  error: unknown,
  fallback: string,
): BoardGeometryCorrectionFailure {
  return {
    error: apiErrorMessage(error, fallback),
    isConflict: isCorrectionConflict(error),
    ok: false,
  };
}

function disconnected(): BoardGeometryCorrectionFailure {
  return {
    error: 'Połączenie z lokalnym Admin API zostało przerwane.',
    isConflict: false,
    ok: false,
  };
}

/** The board changed under the operator; the queue must be reloaded. */
function isCorrectionConflict(error: unknown): boolean {
  if (typeof error !== 'object' || error === null || !('code' in error)) {
    return false;
  }
  const code = (error as { readonly code?: unknown }).code;
  return typeof code === 'string' && QUEUE_CHANGED_CODES.has(code);
}

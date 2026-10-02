import type {
  AdminApiClient,
  BoardCellGeometryCorrectionContextResponse,
  GeometryQualificationPayload,
  GridCorrectionCellSymbolPayload,
  GridCorrectionCellSymbolSuggestionResponse,
  ImageGridReviewItemResponse,
  OperationalImageReviewGeometryPoint,
  OperationalImageReviewGeometryResponse,
  OperationalImageReviewItemResponse,
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
  parseGeometryCorners,
} from './board-geometry-correction-state.ts';

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
import {
  previewOperationalReviewGeometry,
  saveOperationalReviewGeometry,
  type OperationalReviewsClient,
} from './operational-review-actions.ts';
import {
  buildOperationalReviewGeometryCommand,
  buildOperationalReviewGeometryPreviewCommand,
  operationalReviewAssetUrl,
  operationalReviewGeometryCorners,
  type OperationalReviewGeometryCorners,
} from './operational-review-state.ts';

/**
 * One board whose grid a human corrects on the single-board screen (D-462).
 * The editor never knows whether the board is a deferred slot or a current
 * board with a `Zła siatka` report; both save exactly this one board.
 */
export interface BoardGeometryCorrectionView {
  /** The board's persisted qualification, so a partial board stays partial. */
  readonly initialFlags: ManualGridFlags;
  readonly kind: 'deferred' | 'operational' | 'reported';
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
  /**
   * Symbols known for the previewed cut (D-488): stored ones for a reported
   * board, the pinned model's prediction for a deferred slot. Absent when the
   * target cannot assign symbols; never writes anything.
   */
  symbols?(
    corners: OperationalReviewGeometryCorners,
    flags: ManualGridFlags,
  ): Promise<
    | {
        readonly cells: readonly GridCorrectionCellSymbolSuggestionResponse[];
        readonly ok: true;
      }
    | BoardGeometryCorrectionFailure
  >;
  /**
   * `cellSymbols` are the symbols the operator assigned on the preview
   * (D-488); the backend approves them in the transaction of the geometry.
   */
  save(
    corners: OperationalReviewGeometryCorners,
    flags: ManualGridFlags,
    idempotencyKey: string,
    cellSymbols?: readonly GridCorrectionCellSymbolPayload[],
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
  readonly symbolsApi?: Pick<
    AdminApiClient,
    'previewPendingBoardCellGeometrySymbols'
  >;
}): BoardGeometryCorrectionTarget {
  const { symbolsApi } = input;
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
            'Zapis utworzy zwykłą planszę; jej symbole trafią do Weryfikacji symboli. Zatwierdzi tylko symbole, które wskażesz na kafelkach.',
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
    ...(symbolsApi === undefined
      ? {}
      : {
          async symbols(
            corners: OperationalReviewGeometryCorners,
            flags: ManualGridFlags,
          ) {
            try {
              const result =
                await symbolsApi.previewPendingBoardCellGeometrySymbols(
                  input.pendingId,
                  input.scope,
                  deferredBoardCellGeometryPreviewCommand(
                    loaded(),
                    corners,
                    flags,
                  ),
                );
              if (result.error !== undefined || result.data === undefined) {
                return failure(
                  result.error,
                  'Nie udało się pobrać podpowiedzi symboli.',
                );
              }
              return { cells: result.data.cells, ok: true as const };
            } catch {
              return disconnected();
            }
          },
        }),
    async save(corners, flags, idempotencyKey, cellSymbols) {
      const result = await resolveDeferredBoardCellGeometry(
        input.api,
        input.scope,
        input.pendingId,
        {
          ...deferredBoardCellGeometryResolutionCommand(
            loaded(),
            corners,
            idempotencyKey,
            flags,
          ),
          ...operatorCellSymbols(cellSymbols),
        },
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
  readonly symbolsApi?: Pick<
    AdminApiClient,
    'getImageGridReviewCorrectionSymbols'
  >;
}): BoardGeometryCorrectionTarget {
  const { api, item, symbolsApi } = input;
  const reviewItemId = item.reviewItemId;
  const scope = { gameId: item.gameId, importJobId: item.importJobId };
  // D-467 S6: every board is `virtual_source`, so every board accepts a
  // qualification and a partial grid.
  const persistedQualification = gridReviewQualification(item);
  const command = (
    corners: OperationalReviewGeometryCorners,
    flags: ManualGridFlags,
  ) => ({
    ...gridReviewGeometryPreviewCommand(item, corners),
    geometryQualification: correctionGeometryQualification(
      persistedQualification,
      flags,
      corners,
      item.sourceWidth,
      item.sourceHeight,
    ),
  });
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
            'Zapis usuwa zgłoszenia „Zła siatka”. Pola ze zmienionym wycinkiem wrócą do Weryfikacji symboli; niezmienione zachowają weryfikację, a symbole wskazane na kafelkach zostaną zatwierdzone.',
          sourceHeight: item.sourceHeight,
          sourceUrl: api.imageGridReviewSourceAssetUrl(
            reviewItemId,
            item.gameId,
            item.sourceChecksumSha256,
          ),
          sourceWidth: item.sourceWidth,
          suggestedCorners: copyCorners(gridReviewCorners(item)),
          supportsPartial: true,
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
    ...(symbolsApi === undefined
      ? {}
      : {
          async symbols() {
            if (reviewItemId === null) return missingReviewItem();
            try {
              const result =
                await symbolsApi.getImageGridReviewCorrectionSymbols(
                  reviewItemId,
                  item.gameId,
                );
              if (result.error !== undefined || result.data === undefined) {
                return failure(
                  result.error,
                  'Nie udało się pobrać symboli planszy.',
                );
              }
              return { cells: result.data.cells, ok: true as const };
            } catch {
              return disconnected();
            }
          },
        }),
    async save(corners, flags, idempotencyKey, cellSymbols) {
      if (reviewItemId === null) return missingReviewItem();
      try {
        const result = await api.createImageGridReviewGeometryRevision(
          reviewItemId,
          scope,
          {
            ...command(corners, flags),
            idempotencyKey,
            ...operatorCellSymbols(cellSymbols),
          },
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

/**
 * The qualification one correction command sends (shared by every target).
 * A board that already carries a qualification keeps sending one (also
 * `complete`), so a partial board can never silently become complete; a
 * plain board stays unqualified unless the operator marks it partial or
 * excluded. Throws when the flags do not describe a valid partial board.
 */
export function correctionGeometryQualification(
  persisted: GeometryQualificationPayload | undefined,
  flags: ManualGridFlags,
  corners: OperationalReviewGeometryCorners,
  sourceWidth: number,
  sourceHeight: number,
): GeometryQualificationPayload | null {
  const qualified = persisted !== undefined || flags.partial || flags.exclude;
  return qualified
    ? manualGridQualification(flags, corners, sourceWidth, sourceHeight)
    : null;
}

export type OperationalBoardGeometryClient = Pick<
  OperationalReviewsClient,
  | 'createOperationalImageReviewGeometryRevision'
  | 'previewOperationalImageReviewGeometry'
>;

export interface OperationalBoardGeometryTarget extends BoardGeometryCorrectionTarget {
  /** The response of the last successful save, read once by the dialog. */
  takeSavedGeometry(): OperationalImageReviewGeometryResponse | null;
}

/**
 * The board open in the operational review (TASK-0798). It corrects through
 * the operational routes `image-review-items/{id}/geometry-preview` and
 * `.../geometry-revisions` (same allowlist and Reviewer session), but with
 * the same flags, qualification and validation as the correction queue.
 */
export function operationalBoardGeometryTarget(input: {
  readonly api: OperationalBoardGeometryClient;
  readonly apiBaseUrl: string;
  readonly importJobId: string;
  readonly item: OperationalImageReviewItemResponse;
}): OperationalBoardGeometryTarget {
  const { api, item } = input;
  let savedGeometry: OperationalImageReviewGeometryResponse | null = null;
  const scope = { gameId: item.gameId, importJobId: input.importJobId };
  const persistedQualification = item.geometryQualification ?? undefined;
  const sourceSize = (): { width: number; height: number } => {
    if (item.sourceWidth == null || item.sourceHeight == null) {
      throw new Error('Plansza nie ma wymiarów zdjęcia źródłowego.');
    }
    return { height: item.sourceHeight, width: item.sourceWidth };
  };
  const command = (
    corners: OperationalReviewGeometryCorners,
    flags: ManualGridFlags,
  ) => {
    const size = sourceSize();
    return {
      ...buildOperationalReviewGeometryPreviewCommand(item, corners),
      geometryQualification: correctionGeometryQualification(
        persistedQualification,
        flags,
        corners,
        size.width,
        size.height,
      ),
    };
  };
  const sequenceNumber = item.sequenceNumber ?? item.suggestedSequenceNumber;
  return {
    key: `operational:${item.id}:${item.geometryRevision}:${item.resolutionRevision}`,
    async load() {
      if (item.sourceWidth == null || item.sourceHeight == null) {
        return {
          error:
            'Plansza nie ma wymiarów zdjęcia źródłowego. Odśwież kolejkę i spróbuj ponownie.',
          isConflict: false,
          ok: false,
        };
      }
      const width = item.sourceWidth;
      const height = item.sourceHeight;
      return {
        ok: true,
        view: {
          initialFlags: manualGridFlagsFromQualification(
            persistedQualification,
          ),
          kind: 'operational',
          metadata: [
            {
              label: 'Numer planszy',
              value:
                sequenceNumber == null
                  ? '—'
                  : sequenceNumber.toLocaleString('pl-PL'),
            },
            {
              label: 'Pozycja na stronie',
              value: `${item.positionIndex + 1} / 9`,
            },
            {
              label: 'Rewizja geometrii',
              value: String(item.geometryRevision),
            },
          ],
          reportedCellIndices: [],
          saveHint:
            'Zapis utworzy nową rewizję append-only, zachowa poprzednią geometrię i ponownie otworzy symbole zależne od zmienionych cropów.',
          sourceHeight: height,
          sourceUrl: operationalReviewAssetUrl(
            input.apiBaseUrl,
            scope,
            item.id,
            'source',
            {
              usage: 'board-cell-geometry-editor-v19-v1',
              version: item.sourceChecksumSha256,
            },
          ),
          sourceWidth: width,
          suggestedCorners:
            parseGeometryCorners(
              item.geometry,
              persistedQualification?.completenessStatus === 'pending_partial',
            ) ?? operationalReviewGeometryCorners(item, width, height),
          supportsPartial: true,
        },
      };
    },
    commandKey(corners, flags) {
      return JSON.stringify(command(corners, flags));
    },
    async preview(corners, flags) {
      const result = await previewOperationalReviewGeometry(api, {
        command: command(corners, flags),
        gameId: item.gameId,
        importJobId: input.importJobId,
        reviewItemId: item.id,
      });
      return result.ok
        ? result
        : {
            error: result.error,
            isConflict: result.isRevisionConflict,
            ok: false,
          };
    },
    async save(corners, flags, idempotencyKey) {
      const result = await saveOperationalReviewGeometry(api, {
        command: {
          ...buildOperationalReviewGeometryCommand(
            item,
            corners,
            idempotencyKey,
          ),
          geometryQualification: command(corners, flags).geometryQualification,
        },
        gameId: item.gameId,
        importJobId: input.importJobId,
        reviewItemId: item.id,
      });
      if (!result.ok) {
        return {
          error: result.error,
          isConflict: result.isRevisionConflict,
          ok: false,
        };
      }
      savedGeometry = result.geometry;
      return { ok: true, reviewItemId: item.id };
    },
    takeSavedGeometry() {
      const geometry = savedGeometry;
      savedGeometry = null;
      return geometry;
    },
  };
}

/** The command field is sent only when the operator assigned a symbol. */
function operatorCellSymbols(
  cellSymbols: readonly GridCorrectionCellSymbolPayload[] | undefined,
): { cellSymbols?: GridCorrectionCellSymbolPayload[] } {
  return cellSymbols === undefined || cellSymbols.length === 0
    ? {}
    : { cellSymbols: [...cellSymbols] };
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

import type {
  AdminApiClient,
  BoardCellGeometryCorrectionContextResponse,
  GeometryQualificationPayload,
  GridAuditProposalResponse,
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
  boardLatticeUnavailable,
  boardLatticeQualification,
  boardLatticeTransportCorners,
  boardLatticePayload,
  type BoardLatticeNodes,
} from './board-lattice-state.ts';
import {
  gridAuditClassLabel,
  gridAuditPreviewCommandsEqual,
  gridAuditSuggestedCorners,
} from './grid-audit-correction-state.ts';
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
  readonly kind: 'audit' | 'deferred' | 'operational' | 'reported';
  readonly metadata: readonly BoardGeometryCorrectionFact[];
  /**
   * TASK-0840: the board's current grid, drawn as a thin outline when the
   * suggestion is something else (the audit network proposal).
   */
  readonly referenceCorners?: OperationalReviewGeometryCorners;
  /** Shown above the canvas, e.g. that the suggestion is a proposal. */
  readonly suggestionNotice?: string;
  readonly reportedCellIndices: readonly number[];
  readonly saveHint: string;
  readonly sourceHeight: number;
  readonly sourceUrl: string;
  readonly sourceWidth: number;
  readonly suggestedCorners: OperationalReviewGeometryCorners;
  /** Full source lattice; absent for the established four-corner workflow. */
  readonly suggestedLatticeNodes?: BoardLatticeNodes;
  readonly draftBindingKey?: string;
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
  /** Audit only: review preselected proposals and confirm them with Save. */
  readonly prefillSymbolSuggestions?: boolean;
  load(): Promise<
    | { readonly ok: true; readonly view: BoardGeometryCorrectionView }
    | BoardGeometryCorrectionFailure
  >;
  /** Throws when the flags do not describe a valid partial board. */
  commandKey(
    corners: OperationalReviewGeometryCorners,
    flags: ManualGridFlags,
    latticeNodes?: BoardLatticeNodes,
  ): string;
  preview(
    corners: OperationalReviewGeometryCorners,
    flags: ManualGridFlags,
    latticeNodes?: BoardLatticeNodes,
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
    latticeNodes?: BoardLatticeNodes,
  ): Promise<
    | {
        readonly cells: readonly GridCorrectionCellSymbolSuggestionResponse[];
        readonly tentativeCellIndices?: readonly number[];
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
    latticeNodes?: BoardLatticeNodes,
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
          initialFlags:
            result.context.latticeNodes == null
              ? completeManualGridFlags
              : {
                  ...completeManualGridFlags,
                  partial:
                    boardLatticeUnavailable(
                      result.context.latticeNodes,
                      result.context.sourceWidth,
                      result.context.sourceHeight,
                    ).length > 0,
                },
          kind: 'deferred',
          metadata: [
            {
              label: 'Numer planszy',
              value: item.sequenceNumber.toLocaleString('pl-PL'),
            },
            {
              label: 'Pozycja na stronie',
              value:
                result.context.latticeNodes == null
                  ? `${item.positionIndex + 1} / 9`
                  : String(item.positionIndex + 1),
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
          ...(result.context.latticeNodes == null
            ? {}
            : {
                suggestedLatticeNodes: result.context.latticeNodes,
                draftBindingKey: JSON.stringify({
                  manifest: item.processingManifestChecksumSha256,
                  geometry: item.expectedGeometryRevision,
                  resolution: item.expectedReviewResolutionRevision,
                  proposal: result.context.expectedProposalChecksumSha256,
                }),
              }),
          supportsPartial: true,
        },
      };
    },
    commandKey(corners, flags, latticeNodes) {
      return deferredBoardCellGeometryCommandKey(
        loaded(),
        corners,
        flags,
        latticeNodes,
      );
    },
    preview(corners, flags, latticeNodes) {
      return previewDeferredBoardCellGeometry(
        input.api,
        input.scope,
        input.pendingId,
        deferredBoardCellGeometryPreviewCommand(
          loaded(),
          corners,
          flags,
          latticeNodes,
        ),
      );
    },
    ...(symbolsApi === undefined
      ? {}
      : {
          async symbols(
            corners: OperationalReviewGeometryCorners,
            flags: ManualGridFlags,
            latticeNodes?: BoardLatticeNodes,
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
                    latticeNodes,
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
    async save(corners, flags, idempotencyKey, cellSymbols, latticeNodes) {
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
            latticeNodes,
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
    latticeNodes?: BoardLatticeNodes,
  ) => ({
    ...gridReviewGeometryPreviewCommand(item, corners, latticeNodes),
    geometryQualification: correctionGeometryQualification(
      persistedQualification,
      flags,
      corners,
      item.sourceWidth,
      item.sourceHeight,
      latticeNodes,
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
              value:
                item.latticeNodes == null
                  ? `${item.positionIndex + 1} / 9`
                  : String(item.positionIndex + 1),
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
          ...(item.latticeNodes == null
            ? {}
            : {
                suggestedLatticeNodes: item.latticeNodes,
                draftBindingKey: item.expectedProposalChecksumSha256 ?? '',
              }),
          supportsPartial: true,
        },
      };
    },
    commandKey(corners, flags, latticeNodes) {
      return JSON.stringify(command(corners, flags, latticeNodes));
    },
    async preview(corners, flags, latticeNodes) {
      if (reviewItemId === null) return missingReviewItem();
      try {
        const result = await api.previewImageGridReviewGeometry(
          reviewItemId,
          scope,
          command(corners, flags, latticeNodes),
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
    async save(corners, flags, idempotencyKey, cellSymbols, latticeNodes) {
      if (reviewItemId === null) return missingReviewItem();
      try {
        const result = await api.createImageGridReviewGeometryRevision(
          reviewItemId,
          scope,
          {
            ...command(corners, flags, latticeNodes),
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
 * TASK-0840: a current board from the grid-audit list. It is the reported
 * board target (same preview, symbols and save route, so the save has exactly
 * the effects of a manual correction), opened with the network grid of the
 * audit as the suggestion and the current grid as a thin outline.
 */
export function gridAuditBoardGeometryTarget(input: {
  readonly api: ReportedBoardGeometryClient;
  readonly proposal: GridAuditProposalResponse;
  readonly symbolsApi?: Pick<
    AdminApiClient,
    'getImageGridReviewCorrectionSymbols'
  >;
}): BoardGeometryCorrectionTarget {
  const { proposal } = input;
  const item = proposal.reviewItem;
  const grid = proposal.proposal;
  if (item === null || grid === null) {
    return unavailableAuditTarget(proposal.item.itemId);
  }
  const base = reportedBoardGeometryTarget({
    api: input.api,
    item,
  });
  const audit = proposal.item;
  const suggestions = proposal.symbolSuggestions;
  return {
    ...base,
    prefillSymbolSuggestions: true,
    key: `audit:${audit.itemId}:${item.slotId}:${item.geometryRevision}:${item.resolutionRevision}:${suggestions?.artifactSha256 ?? 'no-symbols'}`,
    async symbols(corners, flags) {
      if (suggestions == null) {
        return {
          ok: false,
          isConflict: false,
          error:
            'Nowe podpowiedzi symboli nie są jeszcze przygotowane dla tej planszy.',
        };
      }
      const command = {
        ...gridReviewGeometryPreviewCommand(item, corners),
        geometryQualification: correctionGeometryQualification(
          gridReviewQualification(item),
          flags,
          corners,
          item.sourceWidth,
          item.sourceHeight,
        ),
      };
      if (!gridAuditPreviewCommandsEqual(command, suggestions.previewCommand)) {
        return {
          ok: false,
          isConflict: false,
          error:
            'Zmieniono cięcie siatki. Podpowiedzi z poprzedniego cięcia zostały ukryte; wskaż symbole ręcznie.',
        };
      }
      return {
        ok: true,
        cells: suggestions.cells,
        tentativeCellIndices: suggestions.tentativeCellIndices ?? [],
      };
    },
    async load() {
      const result = await base.load();
      if (!result.ok) return result;
      const view = result.view;
      const suggested = gridAuditSuggestedCorners(
        grid.corners,
        item.sourceWidth,
        item.sourceHeight,
        view.initialFlags.partial,
      );
      return {
        ok: true,
        view: {
          ...view,
          kind: 'audit',
          metadata: [
            ...view.metadata,
            {
              label: 'Audyt siatek',
              title: `${audit.itemId}, ${audit.verdictSource === 'operator' ? 'werdykt operatora' : 'reguła z werdyktów operatora'}`,
              value: `${gridAuditClassLabel(audit.auditClass)} · ${audit.itemId}`,
            },
            {
              label: 'Nowe podpowiedzi symboli',
              value:
                suggestions == null
                  ? 'Oczekują na rozpoznanie'
                  : `${suggestions.cells.filter((cell) => cell.symbolId !== null).length} / ${suggestions.cells.length} · niepewne: ${suggestions.tentativeCellIndices?.length ?? 0}`,
            },
          ],
          referenceCorners: copyCorners(gridReviewCorners(item)),
          saveHint:
            'Sprawdź propozycje i zmień błędne symbole. Zapis zatwierdzi wszystkie wybrane symbole, również niezmienione propozycje, razem z korektą siatki.',
          suggestedCorners: suggested.corners,
          suggestedLatticeNodes: undefined,
          suggestionNotice: suggested.clamped
            ? 'Siatka sieci (propozycja) wychodziła poza zdjęcie — narożniki przycięto do krawędzi. Czerwony kontur to obecna, zapisana siatka.'
            : 'Żółta siatka to propozycja sieci z audytu. Czerwony kontur to obecna, zapisana siatka.',
        },
      };
    },
  };
}

function unavailableAuditTarget(itemId: string): BoardGeometryCorrectionTarget {
  const unavailable = (): BoardGeometryCorrectionFailure => ({
    error:
      'Ta plansza zmieniła się po audycie albo nie jest już bieżąca — propozycja sieci nie jest dostępna. Pomiń ją.',
    isConflict: false,
    ok: false,
  });
  return {
    key: `audit-unavailable:${itemId}`,
    commandKey: () => '',
    load: async () => unavailable(),
    preview: async () => unavailable(),
    save: async () => unavailable(),
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
  latticeNodes?: BoardLatticeNodes,
): GeometryQualificationPayload | null {
  const qualified = persisted !== undefined || flags.partial || flags.exclude;
  return qualified
    ? latticeNodes === undefined
      ? manualGridQualification(flags, corners, sourceWidth, sourceHeight)
      : boardLatticeQualification(
          flags,
          latticeNodes,
          sourceWidth,
          sourceHeight,
        )
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
    latticeNodes?: BoardLatticeNodes,
  ) => {
    const size = sourceSize();
    return {
      ...buildOperationalReviewGeometryPreviewCommand(
        item,
        latticeNodes === undefined
          ? corners
          : boardLatticeTransportCorners(latticeNodes),
      ),
      ...(latticeNodes === undefined
        ? {}
        : { latticeNodes: boardLatticePayload(latticeNodes) }),
      ...(item.expectedProposalChecksumSha256 == null
        ? {}
        : {
            expectedProposalChecksumSha256: item.expectedProposalChecksumSha256,
          }),
      geometryQualification: correctionGeometryQualification(
        persistedQualification,
        flags,
        corners,
        size.width,
        size.height,
        latticeNodes,
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
              value:
                item.latticeNodes == null
                  ? `${item.positionIndex + 1} / 9`
                  : String(item.positionIndex + 1),
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
          ...(item.latticeNodes == null
            ? {}
            : {
                suggestedLatticeNodes: item.latticeNodes,
                draftBindingKey: JSON.stringify([
                  item.geometryRevision,
                  item.resolutionRevision,
                  item.expectedProposalChecksumSha256,
                ]),
              }),
          suggestedCorners:
            parseGeometryCorners(
              item.geometry,
              persistedQualification?.completenessStatus === 'pending_partial',
            ) ?? operationalReviewGeometryCorners(item, width, height),
          supportsPartial: true,
        },
      };
    },
    commandKey(corners, flags, latticeNodes) {
      return JSON.stringify(command(corners, flags, latticeNodes));
    },
    async preview(corners, flags, latticeNodes) {
      const result = await previewOperationalReviewGeometry(api, {
        command: command(corners, flags, latticeNodes),
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
    async save(corners, flags, idempotencyKey, _cellSymbols, latticeNodes) {
      const result = await saveOperationalReviewGeometry(api, {
        command: {
          ...buildOperationalReviewGeometryCommand(
            item,
            corners,
            idempotencyKey,
          ),
          ...command(corners, flags, latticeNodes),
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

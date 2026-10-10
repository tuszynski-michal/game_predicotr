import type {
  AdminApiClient,
  GridShadowResultResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

import {
  type BoardGeometryCorrectionTarget,
  type BoardGeometryCorrectionFailure,
  deferredBoardGeometryTarget,
  reportedBoardGeometryTarget,
} from './board-geometry-correction-target.ts';
import { gridAuditSuggestedCorners } from './grid-audit-correction-state.ts';

type ShadowSlot = GridShadowResultResponse['output']['slots'][number];
export type GridShadowCorrectionClient = Pick<
  AdminApiClient,
  | 'getGridShadowResult'
  | 'getPendingBoardCellGeometryCorrectionContext'
  | 'listPendingBoardCellGeometry'
  | 'previewPendingBoardCellGeometryCorrection'
  | 'resolvePendingBoardCellGeometryManually'
  | 'previewPendingBoardCellGeometrySymbols'
  | 'createImageGridReviewGeometryRevision'
  | 'getImageGridReviewCorrectionSymbols'
  | 'imageGridReviewSourceAssetUrl'
  | 'previewImageGridReviewGeometry'
>;

const staleFailure = (): BoardGeometryCorrectionFailure => ({
  ok: false,
  isConflict: true,
  error:
    'Propozycja jest nieaktualna. Źródło albo geometria zmieniły się — odśwież wynik porównania.',
});

export function gridShadowCornerProposal(
  nodes: readonly { readonly x: number; readonly y: number }[],
) {
  if (
    nodes.length !== 24 ||
    nodes.some(({ x, y }) => !Number.isFinite(x) || !Number.isFinite(y))
  )
    return null;
  return [nodes[0], nodes[5], nodes[23], nodes[18]];
}

function sameBinding(
  previous: ShadowSlot,
  current: ShadowSlot | undefined,
): boolean {
  const a = previous.reviewItem;
  const b = current?.reviewItem;
  return (
    a != null &&
    b != null &&
    a.gameId === b.gameId &&
    a.importJobId === b.importJobId &&
    a.sourceImageId === b.sourceImageId &&
    a.positionIndex === b.positionIndex &&
    a.sequenceNumber === b.sequenceNumber &&
    a.gridColumns === b.gridColumns &&
    a.gridRows === b.gridRows &&
    a.slotId === b.slotId &&
    a.reviewItemId === b.reviewItemId &&
    a.pendingGeometryId === b.pendingGeometryId &&
    a.geometryRevision === b.geometryRevision &&
    a.resolutionRevision === b.resolutionRevision &&
    a.sourceChecksumSha256 === b.sourceChecksumSha256 &&
    a.sourceWidth === b.sourceWidth &&
    a.sourceHeight === b.sourceHeight
  );
}

/** One current proposal, routed through the ordinary geometry correction commands. */
export function gridShadowBoardGeometryTarget({
  api,
  apiBaseUrl,
  result,
  slot,
}: {
  readonly api: GridShadowCorrectionClient;
  readonly apiBaseUrl: string;
  readonly result: GridShadowResultResponse;
  readonly slot: ShadowSlot;
}): BoardGeometryCorrectionTarget | null {
  const item = slot.reviewItem;
  const corners = gridShadowCornerProposal(slot.neuralNodes24 ?? []);
  if (result.stale || item == null) return null;
  const base =
    item.slotKind === 'deferred_geometry' && item.pendingGeometryId
      ? deferredBoardGeometryTarget({
          api,
          apiBaseUrl,
          pendingId: item.pendingGeometryId,
          scope: { gameId: item.gameId, importJobId: item.importJobId },
          symbolsApi: api,
        })
      : reportedBoardGeometryTarget({ api, item, symbolsApi: api });
  // An already submitted command may have committed even when its response
  // was lost. Let the existing replay-first correction API resolve that exact
  // retry; a changed command still needs a current shadow binding.
  const submittedCommands = new Map<string, string>();

  async function check(): Promise<BoardGeometryCorrectionFailure | null> {
    try {
      const read = await api.getGridShadowResult(result.gameId, result.id);
      if (read.error !== undefined || !read.data)
        return {
          ok: false,
          isConflict: false,
          error: apiErrorMessage(
            read.error,
            'Nie udało się sprawdzić aktualności propozycji.',
          ),
        };
      if (
        read.data.stale ||
        read.data.sourceChecksumSha256 !== result.sourceChecksumSha256 ||
        read.data.sourceGeometryRevisionId !==
          result.sourceGeometryRevisionId ||
        read.data.sourceGeometryRevision !== result.sourceGeometryRevision ||
        !sameBinding(
          slot,
          read.data.output.slots.find(
            (candidate) => candidate.positionIndex === slot.positionIndex,
          ),
        )
      )
        return staleFailure();
      return null;
    } catch {
      return {
        ok: false,
        isConflict: false,
        error:
          'Nie udało się sprawdzić aktualności propozycji. Spróbuj ponownie.',
      };
    }
  }

  return {
    ...base,
    key: `shadow:${result.id}:${slot.positionIndex}:${base.key}`,
    async load() {
      const failure = await check();
      if (failure) return failure;
      const loaded = await base.load();
      if (!loaded.ok) return loaded;
      const view = loaded.view;
      if (corners === null || slot.state === 'invalid')
        return {
          ok: true,
          view: {
            ...view,
            suggestionNotice:
              'Sieć nie podała poprawnej pełnej siatki dla tej planszy. Popraw zwykłą sugestię lub zapisaną siatkę. Numer planszy pozostaje bez zmian.',
          },
        };
      const suggestion = gridAuditSuggestedCorners(
        corners,
        result.sourceWidth,
        result.sourceHeight,
        view.initialFlags.partial,
      );
      return {
        ok: true,
        view: {
          ...view,
          referenceCorners: view.suggestedCorners,
          suggestedCorners: suggestion.corners,
          // Keep the established shadow corner sketch separate from a saved
          // full lattice inherited through the ordinary target.
          suggestedLatticeNodes: undefined,
          suggestionNotice:
            'Szkic do korekty utworzony z czterech zewnętrznych narożników sieci. Edytor odtwarza regularną siatkę; nie zachowuje pełnych 24 węzłów. Pełną propozycję zobaczysz w porównaniu w Adminie.' +
            (suggestion.clamped
              ? ' Narożniki poza zdjęciem przycięto do krawędzi; dla uciętej planszy zaznacz „Niepełna plansza”.'
              : ''),
          metadata: [
            ...view.metadata,
            {
              label: 'Model sieci',
              value: `${result.modelProfile} · ${result.modelVersion}`,
            },
            {
              label: 'Powody przeglądu',
              value: 'Wymagane ręczne sprawdzenie',
              title: [...result.reasons, ...(slot.reasonCodes ?? [])].join(
                ', ',
              ),
            },
          ],
        },
      };
    },
    async preview(...args) {
      const failure = await check();
      return failure ?? base.preview(...args);
    },
    ...(base.symbols
      ? {
          async symbols(
            ...args: Parameters<
              NonNullable<BoardGeometryCorrectionTarget['symbols']>
            >
          ) {
            const failure = await check();
            return failure ?? base.symbols!(...args);
          },
        }
      : {}),
    async save(...args) {
      const command = JSON.stringify(args);
      const idempotencyKey = args[2];
      if (submittedCommands.get(idempotencyKey) !== command) {
        const failure = await check();
        if (failure) return failure;
        submittedCommands.set(idempotencyKey, command);
      }
      return base.save(...args);
    },
  };
}

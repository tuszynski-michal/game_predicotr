import {
  validManualGridFlags,
  type ManualGridFlags,
} from '@game-predictor/manual-image-selection-core/manual-grid-qualification';
import {
  parseBoardLattice,
  type BoardLatticeNodes,
} from './board-lattice-state.ts';
import type { OperationalReviewGeometryCorners } from './operational-review-state.ts';
import type { DeferredBoardCellGeometryIdempotency } from './deferred-board-cell-geometry-state.ts';

export interface BoardLatticeDraftScope {
  readonly targetKey: string;
  readonly sourceUrl: string;
  readonly width: number;
  readonly height: number;
}
export interface BoardLatticeDraft {
  readonly corners: OperationalReviewGeometryCorners;
  readonly latticeNodes: BoardLatticeNodes | null;
  readonly flags: ManualGridFlags;
  readonly symbols: Readonly<Record<number, string | null | undefined>>;
  readonly idempotency: DeferredBoardCellGeometryIdempotency | null;
}
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem' | 'removeItem'>;
export function boardLatticeDraftKey(scope: BoardLatticeDraftScope) {
  return `board-lattice-draft-v1:${scope.targetKey}`;
}
export function writeBoardLatticeDraft(
  storage: Storage,
  scope: BoardLatticeDraftScope,
  draft: BoardLatticeDraft,
): void {
  storage.setItem(
    boardLatticeDraftKey(scope),
    JSON.stringify({ version: 1, scope, draft }),
  );
}
export function clearBoardLatticeDraft(
  storage: Storage,
  scope: BoardLatticeDraftScope,
): void {
  storage.removeItem(boardLatticeDraftKey(scope));
}
export function readBoardLatticeDraft(
  storage: Storage,
  scope: BoardLatticeDraftScope,
): BoardLatticeDraft | null {
  const text = storage.getItem(boardLatticeDraftKey(scope));
  if (text === null) return null;
  const raw = JSON.parse(text);
  const draft = raw?.draft as BoardLatticeDraft | undefined;
  if (
    raw?.version !== 1 ||
    JSON.stringify(raw.scope) !== JSON.stringify(scope) ||
    !draft ||
    !Array.isArray(draft.corners) ||
    draft.corners.length !== 4 ||
    draft.corners.some(
      (p) => !p || !Number.isFinite(p.x) || !Number.isFinite(p.y),
    ) ||
    (draft.latticeNodes !== null &&
      parseBoardLattice(draft.latticeNodes) === null) ||
    !validManualGridFlags(draft.flags) ||
    !draft.symbols ||
    typeof draft.symbols !== 'object' ||
    Object.entries(draft.symbols).some(
      ([i, symbol]) =>
        !/^([0-9]|1[0-4])$/.test(i) ||
        (symbol !== null && typeof symbol !== 'string'),
    ) ||
    (draft.idempotency !== null &&
      (!draft.idempotency ||
        typeof draft.idempotency.commandKey !== 'string' ||
        typeof draft.idempotency.idempotencyKey !== 'string'))
  )
    throw new Error(
      'Zapisany szkic dotyczy innego źródła lub zawiera nieprawidłową siatkę. Przywróć sugestię przed zapisem.',
    );
  return draft;
}

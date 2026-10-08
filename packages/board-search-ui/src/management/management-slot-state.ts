import type {
  ManagementStake,
  ManagementStakeResponse,
  SearchGameBoardsOptions,
} from '@game-predictor/admin-api-client';
import type { BoardSearchSavedSelection } from '../index';

export const MANAGEMENT_STAKES: readonly ManagementStake[] = [
  2000, 1000, 600, 400, 200, 120,
];
export type ManagementCardState = {
  slot: ManagementStakeResponse;
  status: 'checking' | 'current' | 'stale' | 'empty';
  error?: string;
};

/** A response may only replace the same observed revision, never a newer Save/Clear. */
export function applyManagementRefresh(
  cards: readonly ManagementCardState[],
  expected: ManagementStakeResponse,
  replacement: ManagementCardState,
): readonly ManagementCardState[] {
  if (
    replacement.slot.machineId !== expected.machineId ||
    replacement.slot.gameId !== expected.gameId ||
    replacement.slot.stakeGrosze !== expected.stakeGrosze
  )
    return cards;
  return cards.map((card) =>
    card.slot.machineId === expected.machineId &&
    card.slot.gameId === expected.gameId &&
    card.slot.stakeGrosze === expected.stakeGrosze &&
    card.slot.revision === expected.revision &&
    replacement.slot.revision >= expected.revision
      ? replacement
      : card,
  );
}

/** Read unknown JSON without creating a second API response model. */
export function managementSavedSelection(
  slot: ManagementStakeResponse,
): BoardSearchSavedSelection | null {
  if (
    slot.empty ||
    slot.startSequenceNumber == null ||
    slot.spinCount == null ||
    slot.searchContextId == null
  )
    return null;
  const query = slot.query;
  if (!query || !Array.isArray(query.cells))
    throw new Error('Zapisany wzór wyszukiwania jest nieprawidłowy.');
  const cells: SearchGameBoardsOptions['cells'] = query.cells.map(
    (value: unknown) => {
      if (
        !value ||
        typeof value !== 'object' ||
        !('cellIndex' in value) ||
        typeof value.cellIndex !== 'number' ||
        !Number.isInteger(value.cellIndex) ||
        value.cellIndex < 0 ||
        value.cellIndex > 14 ||
        !('symbolCode' in value) ||
        !(value.symbolCode === null || typeof value.symbolCode === 'string')
      )
        throw new Error('Zapisane pole wzoru jest nieprawidłowe.');
      return { cellIndex: value.cellIndex, symbolCode: value.symbolCode };
    },
  );
  if (
    new Set(cells.map((cell) => cell.cellIndex)).size !== cells.length ||
    (query.scope !== undefined &&
      query.scope !== 'all_searchable' &&
      query.scope !== 'approved_only') ||
    (query.limit !== undefined &&
      (typeof query.limit !== 'number' ||
        !Number.isInteger(query.limit) ||
        query.limit < 1 ||
        query.limit > 100))
  )
    throw new Error('Zapisane parametry wyszukiwania są nieprawidłowe.');
  return {
    id: `${slot.machineId}:${slot.gameId}:${slot.stakeGrosze}:${slot.revision}`,
    query: {
      cells,
      scope:
        query.scope === 'approved_only' ? 'approved_only' : 'all_searchable',
      limit: typeof query.limit === 'number' ? query.limit : 15,
    },
    searchContextId: slot.searchContextId,
    startSequenceNumber: slot.startSequenceNumber,
    spinCount: slot.spinCount,
    pinnedSpinPositions: slot.pinnedSpinPositions ?? [],
  };
}

/** Two workers share one cursor; obsolete scopes stop launching further requests. */
export async function refreshManagementQueue<T>(
  items: readonly T[],
  signal: AbortSignal,
  refresh: (item: T) => Promise<void>,
): Promise<void> {
  let cursor = 0;
  const worker = async () => {
    while (!signal.aborted && cursor < items.length) {
      const item = items[cursor++];
      await refresh(item);
    }
  };
  await Promise.all([worker(), worker()]);
}

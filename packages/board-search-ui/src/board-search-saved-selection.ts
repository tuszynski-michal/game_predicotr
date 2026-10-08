import type { SearchGameBoardsOptions } from '@game-predictor/admin-api-client';

/** Complete draft; only an explicit host Save callback may persist it. */
export type BoardSearchDraft = {
  readonly query: SearchGameBoardsOptions;
  readonly searchContextId: string | null;
  readonly startSequenceNumber: number | null;
  readonly spinCount: number;
  readonly pinnedSpinPositions: readonly number[];
};

export type BoardSearchSavedSelection = BoardSearchDraft & {
  /** Change this identity when opening another saved slot. */
  readonly id: string;
};

export function boardSearchDraftKey(draft: BoardSearchDraft): string {
  return JSON.stringify({
    query: {
      cells: [...draft.query.cells].sort((a, b) => a.cellIndex - b.cellIndex),
      scope: draft.query.scope ?? 'all_searchable',
      limit: draft.query.limit ?? 15,
    },
    searchContextId: draft.searchContextId,
    startSequenceNumber: draft.startSequenceNumber,
    spinCount: draft.spinCount,
    pinnedSpinPositions: [...draft.pinnedSpinPositions].sort((a, b) => a - b),
  });
}

/** Hosts use this for internal navigation; beforeunload covers page exits. */
export function confirmBoardSearchDiscardDraft(dirty: boolean): boolean {
  return (
    !dirty ||
    window.confirm('Masz niezapisane zmiany układu. Opuścić bez zapisu?')
  );
}

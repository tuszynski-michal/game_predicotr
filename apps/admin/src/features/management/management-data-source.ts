import type {
  ManagementStake,
  ManagementStakeResponse,
  SearchGameBoardsOptions,
} from '@game-predictor/admin-api-client';
import type { BoardSearchDataSource } from '@game-predictor/board-search-ui';
import {
  type ManagementGameClient,
  managementError,
} from './management-client';
import {
  ManagementSlotRecovery,
  type ManagementSlotOperation,
} from './management-slot-operation';

/** Uses management-scoped search and human writer so every operation is journalled. */
export function createManagementDataSource(options: {
  api: ManagementGameClient;
  machineId: string;
  gameId: string;
  stake: ManagementStake;
  recovery: ManagementSlotRecovery;
  initialSearchContextId?: string | null;
  getRevision: () => number;
  onCommitted: () => void;
  onSearchCommitted?: () => void;
  onConflict: () => void;
  canWrite?: () => boolean;
  writeAllowed?: boolean;
}) {
  const { api, machineId, gameId, stake, recovery } = options;
  const controller = new AbortController();
  let searchContextId = options.initialSearchContextId ?? null;
  const target = { machineId, gameId, stake };
  const conflict = (error: unknown) => {
    if (
      error &&
      typeof error === 'object' &&
      'conflict' in error &&
      error.conflict === true
    )
      options.onConflict();
  };
  const client: BoardSearchDataSource = {
    listSymbols: api.listSymbols,
    symbolImageAssetUrl: api.symbolImageAssetUrl,
    boardSearchBoardViewUrl: api.boardSearchBoardViewUrl,
    getBoardSearchBoardDetail: (_game, sequence) =>
      api.getManagementBoardDetail(
        machineId,
        gameId,
        sequence,
        controller.signal,
      ),
    getBoardSearchApproximateWin: (_game, range) =>
      api.getManagementApproximateWin(machineId, gameId, {
        ...range,
        signal: controller.signal,
      }),
    searchGameBoards: async (_game, query: SearchGameBoardsOptions) => {
      if (options.canWrite?.() === false)
        throw new Error('Gra dostępna tylko do odczytu.');
      const body = {
        cells: [...query.cells],
        scope: query.scope,
        limit: query.limit,
        stakeGrosze: stake,
        expectedRevision: options.getRevision(),
      };
      const pending = recovery.pending;
      const sameSearch =
        pending?.kind === 'search' &&
        pending.machineId === machineId &&
        pending.gameId === gameId &&
        pending.stake === stake &&
        JSON.stringify({ ...pending.body, operationId: undefined }) ===
          JSON.stringify({ ...body, operationId: undefined });
      const operation: ManagementSlotOperation = sameSearch
        ? pending
        : {
            ...target,
            kind: 'search',
            body: { ...body, operationId: crypto.randomUUID() },
          };
      if (operation.kind !== 'search')
        throw new Error('Nieprawidłowa operacja wyszukiwania.');
      try {
        const result = await recovery.run(operation, () =>
          api.searchManagementBoards(
            machineId,
            gameId,
            operation.body,
            controller.signal,
          ),
        );
        searchContextId = result.searchContextId;
        options.onSearchCommitted?.();
        return { data: result.search, searchContextId: result.searchContextId };
      } catch (cause) {
        conflict(cause);
        throw cause;
      }
    },
    hasPendingBoardSearchCell: (_game, sequence) =>
      recovery.pending?.kind === 'correction' &&
      recovery.pending.machineId === machineId &&
      recovery.pending.gameId === gameId &&
      recovery.pending.stake === stake &&
      recovery.pending.sequence === sequence,
    retryBoardSearchCell: async (_game, sequence) => {
      const operation = recovery.pending;
      if (
        operation?.kind !== 'correction' ||
        operation.machineId !== machineId ||
        operation.gameId !== gameId ||
        operation.stake !== stake ||
        operation.sequence !== sequence
      )
        return { error: { message: 'Brak zapisu do potwierdzenia.' } };
      try {
        const data = await recovery.run(operation, () =>
          api.correctManagementBoardCell(
            machineId,
            gameId,
            stake,
            operation.sequence,
            operation.cell,
            operation.body,
          ),
        );
        options.onCommitted();
        return { data };
      } catch (cause) {
        conflict(cause);
        return {
          error: {
            message: managementError(
              cause,
              'Nieznany wynik korekty. Sprawdź ostatni zapis.',
            ),
          },
        };
      }
    },
    correctBoardSearchCell: async (_game, sequence, cell, request) => {
      if (options.canWrite?.() === false)
        return { error: { message: 'Gra dostępna tylko do odczytu.' } };
      const { stakeGrosze: _stake, ...body } = request;
      void _stake;
      const operation: ManagementSlotOperation = {
        ...target,
        kind: 'correction',
        sequence,
        cell,
        body: {
          ...body,
          searchContextId,
          operationId: crypto.randomUUID(),
          expectedRevision: options.getRevision(),
        },
      };
      try {
        const data = await recovery.run(operation, () =>
          api.correctManagementBoardCell(
            machineId,
            gameId,
            stake,
            sequence,
            cell,
            operation.body,
          ),
        );
        options.onCommitted();
        return { data };
      } catch (cause) {
        conflict(cause);
        return {
          error: {
            message: managementError(
              cause,
              'Nieznany wynik korekty. Sprawdź ostatni zapis.',
            ),
          },
        };
      }
    },
  };
  return {
    client:
      options.writeAllowed === false
        ? {
            ...client,
            correctBoardSearchCell: undefined,
            retryBoardSearchCell: undefined,
            hasPendingBoardSearchCell: undefined,
          }
        : client,
    abort: () => controller.abort(),
  };
}

export function managementSlotsAvailable(value: unknown): value is {
  listManagementStakes: ManagementGameClient['listManagementStakes'];
} {
  return (
    !!value &&
    typeof value === 'object' &&
    'listManagementStakes' in value &&
    typeof value.listManagementStakes === 'function'
  );
}

export function managementSlotWritesAllowed(
  pointArchived: boolean,
  machineArchived: boolean,
  assignment: { attached: boolean; gameStatus: string },
): boolean {
  return (
    !pointArchived &&
    !machineArchived &&
    assignment.attached &&
    assignment.gameStatus === 'active'
  );
}

export function managementSlotFor(
  cards: readonly { slot: ManagementStakeResponse }[],
  stake: ManagementStake,
) {
  return cards.find((card) => card.slot.stakeGrosze === stake)?.slot;
}

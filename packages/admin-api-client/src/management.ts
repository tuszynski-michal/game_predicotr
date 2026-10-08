import { createClient } from './generated/client';
import {
  getPublicManagementSnapshot,
  listPublicManagementStakes,
  getPublicManagementStake,
  getPublicManagementResult,
  searchPublicManagementBoards,
  savePublicManagementStake,
  clearPublicManagementStake,
  refreshPublicManagementStake,
  listPublicManagementJournal,
  getPublicManagementBoardDetail,
  correctPublicManagementBoardCell,
  getPublicManagementApproximateWin,
  createPublicManagementPoint,
  updatePublicManagementPoint,
  createPublicManagementMachine,
  updatePublicManagementMachine,
  updatePublicManagementAssignments,
  createManagementSession,
  listManagementSessions,
  revokeManagementSession,
  unlockManagementSession,
  getManagementSessionContext,
  listPublicManagementSymbols,
} from './generated/sdk.gen';
import type {
  ManagementStake,
  ManagementSearchCommand,
  ManagementSaveCommand,
  ManagementClearCommand,
  ManagementRefreshCommand,
  ManagementCorrectionCommand,
  ManagementPointCommand,
  ManagementMachineCommand,
  ManagementAssignmentCommand,
  ManagementSessionCreate,
} from './generated/types.gen';

export function createManagementLinkClient(options: {
  baseUrl: string;
  fetch?: typeof fetch;
}) {
  const client = createClient({
    baseUrl: options.baseUrl,
    headers: { 'X-Admin-Intent': 'local-owner' },
    ...(options.fetch ? { fetch: options.fetch } : {}),
  });
  const confirmation = (target: string) => ({
    'X-Admin-Confirmation': 'confirmed' as const,
    'X-Admin-Target': target,
  });
  return {
    createManagementSession: (body: ManagementSessionCreate) =>
      createManagementSession({
        client,
        body,
        headers: confirmation('management-session:new'),
      }),
    listManagementSessions: () => listManagementSessions({ client }),
    revokeManagementSession: (sessionId: string) =>
      revokeManagementSession({
        client,
        path: { session_id: sessionId },
        headers: confirmation(`management-session:${sessionId}`),
      }),
  };
}
export function createManagementPublicApiClient(options: {
  baseUrl: string;
  sessionId: string;
  fetch?: typeof fetch;
}) {
  const client = createClient({
    baseUrl: options.baseUrl,
    credentials: 'same-origin',
    headers: { 'X-Management-Session': options.sessionId },
    ...(options.fetch ? { fetch: options.fetch } : {}),
  });
  const asset = (
    machineId: string,
    gameId: string,
    suffix: string,
    query: Record<string, string>,
  ) =>
    `${options.baseUrl.replace(/\/$/, '')}/api/v1/management-public/machines/${encodeURIComponent(machineId)}/game/${encodeURIComponent(gameId)}/${suffix}?${new URLSearchParams({ ...query, expectedSessionId: options.sessionId })}`;
  return {
    unlockManagementSession: (accessCode: string) =>
      unlockManagementSession({
        client,
        path: { session_id: options.sessionId },
        body: { accessCode },
      }),
    getManagementSessionContext: () => getManagementSessionContext({ client }),
    getManagementSnapshot: () => getPublicManagementSnapshot({ client }),
    listManagementStakes: (
      machineId: string,
      gameId: string,
      signal?: AbortSignal,
    ) =>
      listPublicManagementStakes({
        client,
        path: { machine_id: machineId, game_id: gameId },
        signal,
      }),
    getManagementStake: (
      machineId: string,
      gameId: string,
      stake: ManagementStake,
      signal?: AbortSignal,
    ) =>
      getPublicManagementStake({
        client,
        path: { machine_id: machineId, game_id: gameId, stake },
        signal,
      }),
    getManagementResult: (
      machineId: string,
      gameId: string,
      versionId: string,
      signal?: AbortSignal,
    ) =>
      getPublicManagementResult({
        client,
        path: { machine_id: machineId, game_id: gameId, version_id: versionId },
        signal,
      }),
    searchManagementBoards: (
      machineId: string,
      gameId: string,
      body: ManagementSearchCommand,
      signal?: AbortSignal,
    ) =>
      searchPublicManagementBoards({
        client,
        path: { machine_id: machineId, game_id: gameId },
        body,
        signal,
      }),
    saveManagementStake: (
      machineId: string,
      gameId: string,
      stake: ManagementStake,
      body: ManagementSaveCommand,
      signal?: AbortSignal,
    ) =>
      savePublicManagementStake({
        client,
        path: { machine_id: machineId, game_id: gameId, stake },
        body,
        signal,
      }),
    clearManagementStake: (
      machineId: string,
      gameId: string,
      stake: ManagementStake,
      body: ManagementClearCommand,
      signal?: AbortSignal,
    ) =>
      clearPublicManagementStake({
        client,
        path: { machine_id: machineId, game_id: gameId, stake },
        body,
        signal,
      }),
    refreshManagementStake: (
      machineId: string,
      gameId: string,
      stake: ManagementStake,
      body: ManagementRefreshCommand,
      signal?: AbortSignal,
    ) =>
      refreshPublicManagementStake({
        client,
        path: { machine_id: machineId, game_id: gameId, stake },
        body,
        signal,
      }),
    listManagementJournal: (
      machineId: string,
      options: {
        gameId?: string;
        stakeGrosze?: ManagementStake;
        before?: string;
        limit?: number;
        signal?: AbortSignal;
      } = {},
    ) =>
      listPublicManagementJournal({
        client,
        path: { machine_id: machineId },
        query: {
          gameId: options.gameId,
          stakeGrosze: options.stakeGrosze,
          before: options.before,
          limit: options.limit,
        },
        signal: options.signal,
      }),
    getManagementBoardDetail: (
      machineId: string,
      gameId: string,
      sequence: number,
      signal?: AbortSignal,
    ) =>
      getPublicManagementBoardDetail({
        client,
        path: { machine_id: machineId, game_id: gameId, sequence },
        signal,
      }),
    correctManagementBoardCell: (
      machineId: string,
      gameId: string,
      stake: ManagementStake,
      sequence: number,
      cell: number,
      body: ManagementCorrectionCommand,
      signal?: AbortSignal,
    ) =>
      correctPublicManagementBoardCell({
        client,
        path: { machine_id: machineId, game_id: gameId, stake, sequence, cell },
        body,
        signal,
      }),
    getManagementApproximateWin: (
      machineId: string,
      gameId: string,
      options: {
        startSequenceNumber: number;
        spinCount: number;
        signal?: AbortSignal;
      },
    ) =>
      getPublicManagementApproximateWin({
        client,
        path: { machine_id: machineId, game_id: gameId },
        query: {
          startSequenceNumber: options.startSequenceNumber,
          spinCount: options.spinCount,
        },
        signal: options.signal,
      }),
    createManagementPoint: (body: ManagementPointCommand) =>
      createPublicManagementPoint({ client, body }),
    updateManagementPoint: (pointId: string, body: ManagementPointCommand) =>
      updatePublicManagementPoint({
        client,
        body,
        path: { point_id: pointId },
      }),
    createManagementMachine: (
      pointId: string,
      body: ManagementMachineCommand,
    ) =>
      createPublicManagementMachine({
        client,
        body,
        path: { point_id: pointId },
      }),
    updateManagementMachine: (
      pointId: string,
      machineId: string,
      body: ManagementMachineCommand,
    ) =>
      updatePublicManagementMachine({
        client,
        body,
        path: { point_id: pointId, machine_id: machineId },
      }),
    updateManagementAssignments: (
      machineId: string,
      body: ManagementAssignmentCommand,
    ) =>
      updatePublicManagementAssignments({
        client,
        body,
        path: { machine_id: machineId },
      }),
    listPublicSymbols: (machineId: string, gameId: string) =>
      listPublicManagementSymbols({
        client,
        path: { machine_id: machineId, game_id: gameId },
      }),
    symbolImageUrl: (
      machineId: string,
      gameId: string,
      symbolId: string,
      revision: string,
    ) =>
      asset(
        machineId,
        gameId,
        `symbols/${encodeURIComponent(symbolId)}/image`,
        { revision },
      ),
    boardImageUrl: (
      machineId: string,
      gameId: string,
      sequence: number,
      checksum: string,
      revision?: string,
    ) =>
      asset(machineId, gameId, `boards/${sequence}/view`, {
        expectedBoardChecksumSha256: checksum,
        ...(revision ? { viewRevision: revision } : {}),
      }),
  };
}
export type ManagementPublicApiClient = ReturnType<
  typeof createManagementPublicApiClient
>;
export type ManagementLinkClient = ReturnType<
  typeof createManagementLinkClient
>;

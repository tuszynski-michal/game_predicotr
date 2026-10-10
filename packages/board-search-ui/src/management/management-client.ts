import type { AdminApiClient } from '@game-predictor/admin-api-client';

/** Transport injection point; public panel adapters implement the same backend contracts. */
type ManagementPorts<T> = {
  [Key in keyof T]: T[Key] extends (
    ...args: infer Args
  ) => Promise<infer Result>
    ? (...args: Args) => Promise<{
        data?: Result extends { data: infer Data } ? Data : never;
        error?: unknown;
        response?: { status: number };
      }>
    : T[Key];
};

export type ManagementGameClient = ManagementPorts<
  Pick<
    AdminApiClient,
    | 'listManagementStakes'
    | 'getManagementStake'
    | 'getManagementResult'
    | 'searchManagementBoards'
    | 'saveManagementStake'
    | 'clearManagementStake'
    | 'refreshManagementStake'
    | 'listManagementJournal'
    | 'getManagementBoardDetail'
    | 'correctManagementBoardCell'
    | 'getManagementApproximateWin'
    | 'listSymbols'
    | 'symbolImageAssetUrl'
    | 'boardSearchBoardViewUrl'
  >
>;

export type ManagementStructureClient = ManagementPorts<
  Pick<
    AdminApiClient,
    | 'getManagementSnapshot'
    | 'createManagementPoint'
    | 'updateManagementPoint'
    | 'createManagementMachine'
    | 'updateManagementMachine'
    | 'updateManagementAssignments'
    | 'previewManagementPointDeletion'
    | 'deleteManagementPoint'
    | 'previewManagementMachineDeletion'
    | 'deleteManagementMachine'
    | 'previewManagementMachineUpdate'
  >
>;

export function managementError(error: unknown, fallback: string): string {
  if (error instanceof Error) return error.message;
  if (
    error &&
    typeof error === 'object' &&
    'message' in error &&
    typeof error.message === 'string'
  )
    return error.message;
  return fallback;
}

export function managementSessionStorage(): Storage | undefined {
  try {
    return typeof window === 'undefined' ? undefined : window.sessionStorage;
  } catch {
    return undefined;
  }
}

import type { AdminApiClient } from '@game-predictor/admin-api-client';

/** Transport injection point; public panel adapters implement the same backend contracts. */
export type ManagementGameClient = Pick<
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
>;

export type ManagementStructureClient = Pick<
  AdminApiClient,
  | 'getManagementSnapshot'
  | 'createManagementPoint'
  | 'updateManagementPoint'
  | 'createManagementMachine'
  | 'updateManagementMachine'
  | 'updateManagementAssignments'
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

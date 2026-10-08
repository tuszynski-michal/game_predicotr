import type {
  ManagementStake,
  ManagementSaveCommand,
  ManagementClearCommand,
  ManagementSearchCommand,
  ManagementCorrectionCommand,
} from '@game-predictor/admin-api-client';
import { managementError } from './management-client';

type Target = { machineId: string; gameId: string; stake: ManagementStake };
export type ManagementSlotOperation = Target &
  (
    | { kind: 'save'; body: ManagementSaveCommand }
    | { kind: 'clear'; body: ManagementClearCommand }
    | { kind: 'search'; body: ManagementSearchCommand }
    | {
        kind: 'correction';
        sequence: number;
        cell: number;
        body: ManagementCorrectionCommand;
      }
  );
type OperationStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
export const managementSlotPendingKey = (namespace: string) =>
  `game-predictor:management:stake-pending:${namespace}:v1`;

export function readManagementSlotOperation(
  storage: OperationStorage | undefined,
  namespace: string,
): ManagementSlotOperation | null {
  const raw = storage?.getItem(managementSlotPendingKey(namespace));
  if (!raw) return null;
  const value: unknown = JSON.parse(raw);
  if (
    !value ||
    typeof value !== 'object' ||
    !('kind' in value) ||
    !['save', 'clear', 'search', 'correction'].includes(String(value.kind)) ||
    !('machineId' in value) ||
    typeof value.machineId !== 'string' ||
    !('gameId' in value) ||
    typeof value.gameId !== 'string' ||
    !('stake' in value) ||
    ![2000, 1000, 600, 400, 200, 120].includes(Number(value.stake)) ||
    !('body' in value) ||
    !value.body ||
    typeof value.body !== 'object' ||
    !('operationId' in value.body) ||
    typeof value.body.operationId !== 'string'
  )
    throw new Error('Nieprawidłowy zapis oczekującej operacji układu.');
  const body = value.body;
  if (
    value.kind === 'save' &&
    (!('expectedRevision' in body) ||
      !('searchContextId' in body) ||
      !('startSequenceNumber' in body) ||
      !('spinCount' in body))
  )
    throw new Error('Niepełny zapis oczekującego układu.');
  if (
    value.kind === 'clear' &&
    (!('expectedRevision' in body) ||
      !('confirmed' in body) ||
      body.confirmed !== true)
  )
    throw new Error('Nieprawidłowe potwierdzenie oczekującego wyczyszczenia.');
  if (
    value.kind === 'search' &&
    (!('cells' in body) || !Array.isArray(body.cells))
  )
    throw new Error('Nieprawidłowe oczekujące wyszukiwanie.');
  if (
    value.kind === 'correction' &&
    (!('sequence' in value) ||
      typeof value.sequence !== 'number' ||
      !('cell' in value) ||
      typeof value.cell !== 'number' ||
      !('expectedCellVersion' in body))
  )
    throw new Error('Nieprawidłowa oczekująca korekta.');
  return value as ManagementSlotOperation;
}

export class ManagementMutationError extends Error {
  constructor(
    message: string,
    readonly definite: boolean,
    readonly conflict: boolean,
  ) {
    super(message);
  }
}

/** Persist before sending; only a definitive receipt/rejection retires this identity. */
export class ManagementSlotRecovery {
  pending: ManagementSlotOperation | null;
  readonly readError: string | null;
  private busy = false;
  constructor(
    private readonly storage: OperationStorage | undefined,
    private readonly namespace: string,
    private readonly changed: () => void,
    private readonly canAccess: () => boolean = () => true,
  ) {
    try {
      this.pending = readManagementSlotOperation(storage, namespace);
      this.readError = null;
    } catch (cause) {
      this.pending = null;
      this.readError = managementError(
        cause,
        'Nie można odczytać oczekującej operacji.',
      );
    }
  }
  async run<T>(
    operation: ManagementSlotOperation,
    send: () => Promise<{
      data?: T;
      error?: unknown;
      response?: { status: number };
    }>,
    canAcceptReceipt: () => boolean = () => true,
  ): Promise<T> {
    if (!this.canAccess() || !canAcceptReceipt())
      throw new Error('Dostęp do panelu został zakończony.');
    if (this.busy) throw new Error('Zapis jest już w toku.');
    if (this.readError) throw new Error(this.readError);
    if (
      this.pending &&
      JSON.stringify(this.pending) !== JSON.stringify(operation)
    )
      throw new Error(
        'Najpierw sprawdź ostatni zapis. Jego wynik może być już zatwierdzony.',
      );
    if (!this.storage)
      throw new Error(
        'Przeglądarka nie pozwala zachować operacji do ponowienia. Włącz pamięć sesji.',
      );
    this.storage.setItem(
      managementSlotPendingKey(this.namespace),
      JSON.stringify(operation),
    );
    this.pending = operation;
    this.busy = true;
    this.changed();
    try {
      const result = await send();
      if (!this.canAccess() || !canAcceptReceipt())
        throw new Error(
          'Dostęp zakończony podczas zapisu. Zachowano oczekującą operację.',
        );
      if (result.data === undefined || result.error !== undefined) {
        const definite =
          result.response !== undefined &&
          result.response.status >= 400 &&
          result.response.status < 500 &&
          ![401, 403, 429].includes(result.response.status);
        if (definite) this.finish();
        throw new ManagementMutationError(
          managementError(
            result.error,
            'Nieznany wynik zapisu. Ponów tę samą operację.',
          ),
          definite,
          result.response?.status === 409,
        );
      }
      this.finish();
      return result.data;
    } finally {
      this.busy = false;
      this.changed();
    }
  }
  private finish() {
    this.storage!.removeItem(managementSlotPendingKey(this.namespace));
    this.pending = null;
  }
}

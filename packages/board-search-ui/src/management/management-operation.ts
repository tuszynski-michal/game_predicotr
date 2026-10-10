import type {
  ManagementPointCommand,
  ManagementMachineCommand,
  ManagementAssignmentCommand,
  ManagementDeleteCommand,
} from '@game-predictor/admin-api-client';
import type { ManagementClient } from './management-workspace';

export type ManagementOperation =
  | { kind: 'point'; pointId?: string; body: ManagementPointCommand }
  | {
      kind: 'machine';
      pointId: string;
      machineId?: string;
      body: ManagementMachineCommand;
    }
  | {
      kind: 'assignments';
      machineId: string;
      body: ManagementAssignmentCommand;
    }
  | { kind: 'delete-point'; pointId: string; body: ManagementDeleteCommand }
  | {
      kind: 'delete-machine';
      pointId: string;
      machineId: string;
      body: ManagementDeleteCommand;
    };

export const managementPendingKey = (namespace = 'local-owner') =>
  `game-predictor:management:pending-${namespace}:v1`;
export const MANAGEMENT_PENDING_KEY = managementPendingKey();

export function executeManagementOperation(
  client: ManagementClient,
  operation: ManagementOperation,
) {
  if (operation.kind === 'point')
    return operation.pointId
      ? client.updateManagementPoint(operation.pointId, operation.body)
      : client.createManagementPoint(operation.body);
  if (operation.kind === 'machine')
    return operation.machineId
      ? client.updateManagementMachine(
          operation.pointId,
          operation.machineId,
          operation.body,
        )
      : client.createManagementMachine(operation.pointId, operation.body);
  if (operation.kind === 'delete-point')
    return client.deleteManagementPoint(operation.pointId, operation.body);
  if (operation.kind === 'delete-machine')
    return client.deleteManagementMachine(
      operation.pointId,
      operation.machineId,
      operation.body,
    );
  return client.updateManagementAssignments(
    operation.machineId,
    operation.body,
  );
}

export function readManagementOperation(
  storage: Pick<Storage, 'getItem'>,
  namespace = 'local-owner',
): ManagementOperation | null {
  const raw = storage.getItem(managementPendingKey(namespace));
  if (!raw) return null;
  const operation: unknown = JSON.parse(raw);
  if (
    !operation ||
    typeof operation !== 'object' ||
    !('kind' in operation) ||
    !('body' in operation)
  )
    throw new Error('Nieprawidłowy zapis oczekującej operacji.');
  const body = operation.body;
  if (
    !body ||
    typeof body !== 'object' ||
    !('operationId' in body) ||
    typeof body.operationId !== 'string' ||
    !('expectedRevision' in body) ||
    typeof body.expectedRevision !== 'number'
  )
    throw new Error('Nieprawidłowa tożsamość operacji.');
  if (
    operation.kind === 'delete-point' &&
    'pointId' in operation &&
    typeof operation.pointId === 'string' &&
    'previewToken' in body &&
    typeof body.previewToken === 'string' &&
    'confirmed' in body &&
    body.confirmed === true
  )
    return operation as ManagementOperation;
  if (
    operation.kind === 'delete-machine' &&
    'pointId' in operation &&
    typeof operation.pointId === 'string' &&
    'machineId' in operation &&
    typeof operation.machineId === 'string' &&
    'previewToken' in body &&
    typeof body.previewToken === 'string' &&
    'confirmed' in body &&
    body.confirmed === true
  )
    return operation as ManagementOperation;
  if (
    operation.kind === 'point' &&
    'name' in body &&
    typeof body.name === 'string' &&
    'city' in body &&
    typeof body.city === 'string' &&
    'street' in body &&
    typeof body.street === 'string' &&
    (!('pointId' in operation) || typeof operation.pointId === 'string')
  )
    return operation as ManagementOperation;
  if (
    operation.kind === 'machine' &&
    'pointId' in operation &&
    typeof operation.pointId === 'string' &&
    'name' in body &&
    typeof body.name === 'string' &&
    (!('machineId' in operation) || typeof operation.machineId === 'string')
  )
    return operation as ManagementOperation;
  if (
    operation.kind === 'assignments' &&
    'machineId' in operation &&
    typeof operation.machineId === 'string' &&
    'gameIds' in body &&
    Array.isArray(body.gameIds) &&
    body.gameIds.every((id) => typeof id === 'string')
  )
    return operation as ManagementOperation;
  throw new Error('Nieprawidłowy typ oczekującej operacji.');
}

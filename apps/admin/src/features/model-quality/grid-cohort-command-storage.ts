import type {
  GridCohortPrepareCommand,
  GridCohortPageCommand,
  GridCohortFreezeCommand,
  GridCohortRevisionCommand,
  GridSourceIdentityCompleteCommand,
} from '@game-predictor/admin-api-client';

export type GridCohortCommand =
  | { kind: 'prepare'; body: GridCohortPrepareCommand }
  | {
      kind: 'prepare-page' | 'materialize-page';
      cohortId: string;
      body: GridCohortPageCommand;
    }
  | { kind: 'freeze'; cohortId: string; body: GridCohortFreezeCommand }
  | { kind: 'cancel'; cohortId: string; body: GridCohortRevisionCommand }
  | { kind: 'complete'; body: GridSourceIdentityCompleteCommand };

export type GridCohortStorage = Pick<
  Storage,
  'getItem' | 'setItem' | 'removeItem'
>;
export const cohortUuid =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const sha = /^[0-9a-f]{64}$/;
export const gridCohortCommandKey = (api: string, game: string) =>
  `grid-cohort-command-v1:${encodeURIComponent(api)}:${game}`;
export const gridCohortSelectionKey = (api: string, game: string) =>
  `${gridCohortCommandKey(api, game)}:selection`;
const uuid = (value: unknown) =>
  typeof value === 'string' && cohortUuid.test(value);
const hash = (value: unknown) => typeof value === 'string' && sha.test(value);
const revision = (value: unknown) =>
  Number.isInteger(value) && Number(value) >= 0;

function valid(command: GridCohortCommand): boolean {
  if (!command || !command.body || !uuid(command.body.idempotencyKey))
    return false;
  if (command.kind === 'prepare') {
    const b = command.body;
    const ids = b.selector?.sourceIds;
    return (
      uuid(b.familyId) &&
      uuid(b.baseVersionId) &&
      ['grid-only', 'screen+grid'].includes(b.mode) &&
      ((Array.isArray(ids) &&
        ids.length > 0 &&
        ids.length <= 200 &&
        ids.every(uuid) &&
        new Set(ids).size === ids.length &&
        !b.selector.importJobId) ||
        (!ids && uuid(b.selector?.importJobId))) &&
      Array.isArray(b.recordings) &&
      b.recordings.length <= 200 &&
      b.recordings.every(
        (r) =>
          uuid(r.groupId) &&
          ['TRAIN', 'VALIDATION', 'REGRESSION'].includes(r.role),
      ) &&
      new Set(b.recordings.map((r) => r.groupId)).size === b.recordings.length
    );
  }
  if (command.kind === 'complete')
    return (
      Array.isArray(command.body.sources) &&
      command.body.sources.length > 0 &&
      command.body.sources.length <= 5 &&
      new Set(command.body.sources.map((s) => s.sourceId)).size ===
        command.body.sources.length &&
      command.body.sources.every(
        (s) =>
          uuid(s.sourceId) &&
          hash(s.expectedSourceSha256) &&
          uuid(s.expectedSourceGeometryRevisionId) &&
          hash(s.expectedGeometrySha256),
      )
    );
  if (
    !('cohortId' in command) ||
    !uuid(command.cohortId) ||
    !revision(command.body.expectedRevision)
  )
    return false;
  if (command.kind === 'cancel') return true;
  if (command.kind === 'freeze')
    return (
      hash(command.body.expectedPreviewSha256) &&
      hash(command.body.expectedManifestSha256)
    );
  return (
    ['prepare-page', 'materialize-page'].includes(command.kind) &&
    revision(command.body.cursor)
  );
}

export function readGridCohortCommand(
  storage: GridCohortStorage,
  api: string,
  game: string,
): GridCohortCommand | null {
  const raw = storage.getItem(gridCohortCommandKey(api, game));
  if (raw === null) return null;
  try {
    const saved = JSON.parse(raw);
    if (saved.api !== api || saved.game !== game || !valid(saved.command))
      throw new Error();
    return saved.command;
  } catch {
    throw new Error(
      'Zapisane polecenie kohorty jest uszkodzone. Zachowano je do jawnego porzucenia.',
    );
  }
}

export function reserveGridCohortCommand(
  storage: GridCohortStorage,
  api: string,
  game: string,
  command: GridCohortCommand,
): void {
  if (storage.getItem(gridCohortCommandKey(api, game)) !== null)
    throw new Error('Najpierw ponów albo jawnie porzuć zapisane polecenie.');
  if (!valid(command)) throw new Error('Niepoprawne polecenie kohorty.');
  storage.setItem(
    gridCohortCommandKey(api, game),
    JSON.stringify({ api, game, command }),
  );
}

export function clearGridCohortCommand(
  storage: GridCohortStorage,
  api: string,
  game: string,
  key: string,
): void {
  if (readGridCohortCommand(storage, api, game)?.body.idempotencyKey === key)
    storage.removeItem(gridCohortCommandKey(api, game));
}

export function discardGridCohortCommand(
  storage: GridCohortStorage,
  api: string,
  game: string,
): void {
  const key = gridCohortCommandKey(api, game),
    raw = storage.getItem(key);
  if (raw === null) return;
  storage.setItem(`${key}:discarded:${Date.now()}:${crypto.randomUUID()}`, raw);
  storage.removeItem(key);
}

import type {
  GridReinferenceCommand,
  GridReinferenceFreeze,
  GridReinferencePilotAck,
  GridReinferencePrepare,
  GridReinferenceResume,
  GridReinferenceStart,
} from '@game-predictor/admin-api-client';

export type GridCommand =
  | { kind: 'prepare'; operationId: null; body: GridReinferencePrepare }
  | { kind: 'freeze'; operationId: string; body: GridReinferenceFreeze }
  | { kind: 'ack'; operationId: string; body: GridReinferencePilotAck }
  | { kind: 'start'; operationId: string; body: GridReinferenceStart }
  | { kind: 'resume'; operationId: string; body: GridReinferenceResume }
  | { kind: 'cancel'; operationId: string; body: GridReinferenceCommand };
export type GridCommandStorage = Pick<
  Storage,
  'getItem' | 'setItem' | 'removeItem'
>;
export const gridCommandKey = (api: string, game: string) =>
  `grid-reinference-command-v1:${encodeURIComponent(api)}:${game}`;
export const gridViewKey = (api: string, game: string) =>
  `${gridCommandKey(api, game)}:view`;

export function readGridCommand(
  storage: GridCommandStorage,
  api: string,
  game: string,
): GridCommand | null {
  const raw = storage.getItem(gridCommandKey(api, game));
  if (raw === null) return null;
  const value = JSON.parse(raw);
  if (
    value.api !== api ||
    value.game !== game ||
    !value.command ||
    !['prepare', 'freeze', 'ack', 'start', 'resume', 'cancel'].includes(
      value.command.kind,
    ) ||
    typeof value.command.body?.idempotencyKey !== 'string' ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      value.command.body.idempotencyKey,
    ) ||
    (value.command.kind === 'prepare'
      ? value.command.operationId !== null
      : typeof value.command.operationId !== 'string')
  ) {
    throw new Error(
      'Zapisane polecenie jest uszkodzone. Zachowano je do jawnego porzucenia.',
    );
  }
  return value.command as GridCommand;
}

export function saveGridCommand(
  storage: GridCommandStorage,
  api: string,
  game: string,
  command: GridCommand,
): GridCommand {
  const existing = readGridCommand(storage, api, game);
  if (existing !== null)
    throw new Error('Najpierw ponów albo porzuć zapisane polecenie.');
  storage.setItem(
    gridCommandKey(api, game),
    JSON.stringify({ api, game, command }),
  );
  return command;
}

export function clearGridCommand(
  storage: GridCommandStorage,
  api: string,
  game: string,
  command: GridCommand,
): void {
  const current = readGridCommand(storage, api, game);
  if (current?.body.idempotencyKey === command.body.idempotencyKey)
    storage.removeItem(gridCommandKey(api, game));
}

/** Archive the exact raw record, including malformed entries, before removing it. */
export function discardGridCommand(
  storage: GridCommandStorage,
  api: string,
  game: string,
  confirmed: boolean,
): void {
  if (!confirmed) return;
  const key = gridCommandKey(api, game);
  const raw = storage.getItem(key);
  if (raw === null) return;
  const time = new Date().toISOString();
  let operationId: string | null = null;
  let idempotencyKey: string | null = null;
  let kind: string | null = null;
  try {
    const command = JSON.parse(raw)?.command;
    if (typeof command?.operationId === 'string')
      operationId = command.operationId;
    if (typeof command?.body?.idempotencyKey === 'string')
      idempotencyKey = command.body.idempotencyKey;
    if (typeof command?.kind === 'string') kind = command.kind;
  } catch {
    // Malformed raw records must remain archivable without interpreting them.
  }
  storage.setItem(
    `${key}:archive:${crypto.randomUUID()}`,
    JSON.stringify({
      api,
      apiNamespace: api,
      game,
      namespace: key,
      operationId,
      idempotencyKey,
      kind,
      time,
      raw,
    }),
  );
  storage.removeItem(key);
}

import type {
  ContentBlindWrite,
  ContentSessionAdvance,
  ContentSessionCreate,
  ContentWriteCommand,
} from '@game-predictor/admin-api-client';

export type ContentCells = ContentBlindWrite['cells'];
export type ContentNodes = ContentBlindWrite['measuredNodes'];
export type ContentPoint = ContentNodes[number];
export type ContentCell = ContentCells[number];
export type ContentMode = 'ordinary' | 'blind';

export type ContentCommand =
  | { kind: 'create'; body: ContentSessionCreate }
  | { kind: 'observe'; sessionId: string; body: ContentBlindWrite }
  | { kind: 'advance'; sessionId: string; body: ContentSessionAdvance }
  | { kind: 'reference'; body: ContentWriteCommand };

export const contentUuid =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const sha = /^[0-9a-f]{64}$/;
export const contentStateLabels: Record<ContentCell['state'], string> = {
  visible: 'Widoczny w całości',
  occluded: 'Zasłonięty',
  out_of_frame: 'Poza kadrem',
  unknown: 'Nie wiadomo',
};
export function contentRoleLabel(role: string | null): string {
  if (role === null) return 'Przed przypisaniem roli';
  return (
    (
      {
        TRAIN: 'Zdjęcia treningowe',
        A: 'Zdjęcia do wyboru modelu',
        B: 'Zdjęcia testowe do kalibracji',
        REGRESSION: 'Końcowe zdjęcia testowe',
      } as Record<string, string>
    )[role] ?? 'Nieustalona rola zdjęcia'
  );
}

export function emptyContentCells(): ContentCells {
  return Array.from({ length: 15 }, () => ({
    state: 'unknown' as const,
  })) as ContentCells;
}

export function convexContentQuad(quad: number[][]): boolean {
  if (
    quad.length !== 4 ||
    quad.some((p) => p.length !== 2 || p.some((n) => !Number.isFinite(n)))
  )
    return false;
  const cross = quad.map((a, i) => {
    const b = quad[(i + 1) % 4],
      c = quad[(i + 2) % 4];
    return (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]);
  });
  return cross.every((v) => v > 0) || cross.every((v) => v < 0);
}

export function validContentCells(value: unknown): value is ContentCells {
  return (
    Array.isArray(value) &&
    value.length === 15 &&
    value.every((cell) => {
      if (
        !cell ||
        typeof cell !== 'object' ||
        !(cell.state in contentStateLabels)
      )
        return false;
      if (cell.quad == null) return cell.state !== 'visible';
      return Array.isArray(cell.quad) && convexContentQuad(cell.quad);
    })
  );
}

export function validContentNodes(value: unknown): value is ContentNodes {
  return (
    Array.isArray(value) &&
    value.length === 24 &&
    value.every(
      (p) =>
        Array.isArray(p) &&
        p.length === 2 &&
        p.every((n) => typeof n === 'number' && Number.isFinite(n)),
    )
  );
}

/** Only an operator's four new corners may seed a manually adjustable lattice. */
export function manualContentLattice(corners: ContentPoint[]): ContentNodes {
  if (!convexContentQuad(corners))
    throw new Error(
      'Zaznacz cztery wypukłe narożniki w kolejności wokół planszy.',
    );
  const [tl, tr, br, bl] = corners;
  return Array.from({ length: 24 }, (_, i) => {
    const x = (i % 6) / 5,
      y = Math.floor(i / 6) / 3;
    return [
      (1 - y) * ((1 - x) * tl[0] + x * tr[0]) +
        y * ((1 - x) * bl[0] + x * br[0]),
      (1 - y) * ((1 - x) * tl[1] + x * tr[1]) +
        y * ((1 - x) * bl[1] + x * br[1]),
    ];
  }) as ContentNodes;
}

export function contentCommandKey(
  api: string,
  gameId: string,
  mode: ContentMode,
): string {
  return `grid-content-command-v1:${encodeURIComponent(api)}:${gameId}:${mode}`;
}

function validCommand(
  value: unknown,
  mode: ContentMode,
): value is ContentCommand {
  if (
    !value ||
    typeof value !== 'object' ||
    !('kind' in value) ||
    !('body' in value)
  )
    return false;
  const command = value as ContentCommand;
  const body = command.body;
  if (!body || !contentUuid.test(body.idempotencyKey)) return false;
  if (mode === 'ordinary') {
    if (command.kind !== 'reference') return false;
    return (
      contentUuid.test(command.body.sourceId) &&
      sha.test(command.body.expectedSourceSha256) &&
      sha.test(command.body.expectedPixelSha256) &&
      Number.isInteger(command.body.sequenceNumber) &&
      command.body.sequenceNumber > 0 &&
      Number.isInteger(command.body.expectedRevision) &&
      command.body.expectedRevision >= 0 &&
      command.body.origin === 'manual' &&
      typeof command.body.humanApproval === 'boolean' &&
      validContentCells(command.body.cells) &&
      Number.isInteger(command.body.positionIndex) &&
      command.body.positionIndex >= 0 &&
      command.body.positionIndex <= 8
    );
  }
  if (command.kind === 'create') {
    return (
      contentUuid.test(command.body.cohortId) &&
      sha.test(command.body.expectedManifestSha256) &&
      command.body.sourceIds.length > 0 &&
      command.body.sourceIds.length <= 100 &&
      command.body.sourceIds.every((id) => contentUuid.test(id))
    );
  }
  if (command.kind !== 'observe' && command.kind !== 'advance') return false;
  if (
    !contentUuid.test(command.sessionId) ||
    !Number.isInteger(command.body.expectedSessionRevision) ||
    command.body.expectedSessionRevision < 1
  )
    return false;
  return (
    command.kind === 'advance' ||
    (command.body.humanApproval === true &&
      (command.body.passNumber === 1 || command.body.passNumber === 2) &&
      contentUuid.test(command.body.sourceId) &&
      Number.isInteger(command.body.positionIndex) &&
      command.body.positionIndex >= 0 &&
      command.body.positionIndex <= 8 &&
      validContentCells(command.body.cells) &&
      validContentNodes(command.body.measuredNodes))
  );
}

export function readContentCommand(
  storage: Pick<Storage, 'getItem'>,
  key: string,
  gameId: string,
  mode: ContentMode,
): ContentCommand | null {
  const raw = storage.getItem(key);
  if (raw === null) return null;
  const envelope = JSON.parse(raw);
  if (
    envelope?.version !== 1 ||
    envelope.gameId !== gameId ||
    envelope.mode !== mode ||
    !validCommand(envelope.command, mode)
  )
    throw new Error(
      'Nieczytelne zapisane polecenie. Zachowaj je i odłóż przed nowym zapisem.',
    );
  return envelope.command;
}

export function saveContentCommand(
  storage: Pick<Storage, 'getItem' | 'setItem'>,
  key: string,
  gameId: string,
  mode: ContentMode,
  command: ContentCommand,
): void {
  if (storage.getItem(key) !== null)
    throw new Error('Najpierw rozstrzygnij poprzednie polecenie.');
  if (!validCommand(command, mode))
    throw new Error('Niepoprawne polecenie etykietowania.');
  storage.setItem(key, JSON.stringify({ version: 1, gameId, mode, command }));
}

export function clearContentCommand(
  storage: Pick<Storage, 'getItem' | 'removeItem'>,
  key: string,
  id: string,
): void {
  const raw = storage.getItem(key);
  if (raw !== null && JSON.parse(raw)?.command?.body?.idempotencyKey === id)
    storage.removeItem(key);
}

export function archiveContentCommand(
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>,
  key: string,
): void {
  const raw = storage.getItem(key);
  if (raw !== null)
    storage.setItem(`${key}:archive:${crypto.randomUUID()}`, raw);
  storage.removeItem(key);
}

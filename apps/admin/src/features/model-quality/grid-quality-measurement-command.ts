import type {
  GeometryApprovalCommand,
  QualityAssessCommand,
  QualityCaptureCommand,
} from '@game-predictor/admin-api-client';
import { measurementUuid } from './grid-quality-measurement-state.ts';

export type MeasurementCommand =
  | { kind: 'capture'; body: QualityCaptureCommand }
  | { kind: 'assess'; measurementId: string; body: QualityAssessCommand }
  | {
      kind: 'approve';
      reviewItemId: string;
      importJobId: string;
      body: GeometryApprovalCommand;
    };
type CommandStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
const isUuid = (value: unknown): value is string =>
  typeof value === 'string' && measurementUuid.test(value);
const isSha = (value: unknown): value is string =>
  typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
export const measurementCommandKey = (api: string, game: string) =>
  `grid-quality-measurement-command-v1:${encodeURIComponent(api)}:${game}`;

export function readMeasurementCommand(
  storage: CommandStorage,
  api: string,
  game: string,
): MeasurementCommand | null {
  const raw = storage.getItem(measurementCommandKey(api, game));
  if (raw === null) return null;
  try {
    const saved = JSON.parse(raw);
    const c = saved.command;
    if (
      saved.api !== api ||
      saved.game !== game ||
      !c ||
      !isUuid(c.body?.idempotencyKey)
    )
      throw new Error();
    if (c.kind === 'capture') {
      if (
        typeof c.body.seed !== 'string' ||
        !c.body.seed.trim() ||
        c.body.seed.length > 200 ||
        !Number.isInteger(c.body.sampleSize) ||
        c.body.sampleSize < 1 ||
        c.body.sampleSize > 100 ||
        !Array.isArray(c.body.hardSourceIds) ||
        c.body.hardSourceIds.length > 100 ||
        c.body.hardSourceIds.some((id: unknown) => !isUuid(id)) ||
        new Set(c.body.hardSourceIds).size !== c.body.hardSourceIds.length
      )
        throw new Error();
    } else if (c.kind === 'assess' || c.kind === 'approve') {
      if (
        !isUuid(c.body.sourceId) ||
        !['random', 'hard'].includes(c.body.sampleKind) ||
        !isSha(c.body.manifestSha256)
      )
        throw new Error();
      if (c.kind === 'assess') {
        if (
          !isUuid(c.measurementId) ||
          !Number.isInteger(c.body.expectedRevision) ||
          c.body.expectedRevision < 0 ||
          !Array.isArray(c.body.positions) ||
          c.body.positions.length !== 9 ||
          new Set(
            c.body.positions.map(
              (p: { positionIndex: number }) => p.positionIndex,
            ),
          ).size !== 9 ||
          c.body.positions.some(
            (p: {
              positionIndex: number;
              geometry: string;
              detection: string;
              sequence: string;
            }) =>
              !Number.isInteger(p.positionIndex) ||
              p.positionIndex < 0 ||
              p.positionIndex > 8 ||
              ![
                'correct',
                'incorrect',
                'not_assessable',
                'unreviewed',
              ].includes(p.geometry) ||
              !['correct', 'incorrect', 'unknown', 'unreviewed'].includes(
                p.detection,
              ) ||
              !['correct', 'incorrect', 'unknown', 'unreviewed'].includes(
                p.sequence,
              ),
          ) ||
          !Array.isArray(c.body.unexpected) ||
          c.body.unexpected.length > 100 ||
          c.body.unexpected.some(
            (p: { index: number; verdict: string }) =>
              !Number.isInteger(p.index) ||
              p.index < 0 ||
              !['correct', 'incorrect', 'unknown', 'unreviewed'].includes(
                p.verdict,
              ),
          ) ||
          new Set(c.body.unexpected.map((p: { index: number }) => p.index))
            .size !== c.body.unexpected.length
        )
          throw new Error();
      } else if (
        !isUuid(c.reviewItemId) ||
        !isUuid(c.importJobId) ||
        !isUuid(c.body.measurementId) ||
        !Number.isInteger(c.body.positionIndex) ||
        c.body.positionIndex < 0 ||
        c.body.positionIndex > 8 ||
        !isSha(c.body.targetSha256)
      )
        throw new Error();
    } else throw new Error();
    return c as MeasurementCommand;
  } catch {
    throw new Error(
      'Zapisane polecenie jest uszkodzone. Zachowano je do jawnego porzucenia.',
    );
  }
}

export function saveMeasurementCommand(
  storage: CommandStorage,
  api: string,
  game: string,
  command: MeasurementCommand,
): void {
  if (storage.getItem(measurementCommandKey(api, game)) !== null)
    throw new Error('Najpierw ponów albo porzuć zapisane polecenie.');
  storage.setItem(
    measurementCommandKey(api, game),
    JSON.stringify({ api, game, command }),
  );
}

export function clearMeasurementCommand(
  storage: CommandStorage,
  api: string,
  game: string,
  command: MeasurementCommand,
): void {
  const saved = readMeasurementCommand(storage, api, game);
  if (JSON.stringify(saved) === JSON.stringify(command))
    storage.removeItem(measurementCommandKey(api, game));
}

/** Archive even invalid JSON verbatim. A failed archive never clears the record. */
export function discardMeasurementCommand(
  storage: CommandStorage,
  api: string,
  game: string,
  confirmed: boolean,
): void {
  if (!confirmed) return;
  const key = measurementCommandKey(api, game),
    raw = storage.getItem(key);
  if (raw === null) return;
  storage.setItem(
    `${key}:archive:${crypto.randomUUID()}`,
    JSON.stringify({ api, game, raw, archivedAt: new Date().toISOString() }),
  );
  storage.removeItem(key);
}

import { validManualGridFlags } from '@game-predictor/manual-image-selection-core/manual-grid-qualification';
import type { GuardQuad } from './geometry-guard-resolution-state.ts';

export interface GuardBoardDraft {
  readonly disposition: 'corrected_full' | 'partial' | 'rejected';
  readonly dirty: boolean;
  readonly quad: GuardQuad | null;
  readonly unavailable: readonly number[];
  readonly excludeGeometry: boolean;
  readonly baseRevision: number;
}
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem' | 'removeItem'>;
export function guardDraftKey(
  game: string,
  upload: string,
  job: string,
  checksum: string,
) {
  return `guard-geometry-draft-v1:${game}:${upload}:${job}:${checksum}`;
}
export function writeGuardDraft(
  storage: Storage,
  key: string,
  position: number,
  draft: GuardBoardDraft,
) {
  storage.setItem(
    `${key}:${position}:${draft.baseRevision}`,
    JSON.stringify(draft),
  );
  storage.setItem(`${key}:${position}:current`, String(draft.baseRevision));
}
export function clearGuardDraft(
  storage: Storage,
  key: string,
  position: number,
) {
  const pointer = `${key}:${position}:current`;
  const revision = storage.getItem(pointer);
  if (revision !== null && /^\d+$/.test(revision))
    storage.removeItem(`${key}:${position}:${revision}`);
  storage.removeItem(pointer);
}
export function clearCommittedGuardDraft(
  storage: Storage,
  key: string,
  position: number,
  submitted: GuardBoardDraft,
) {
  const entry = `${key}:${position}:${submitted.baseRevision}`;
  if (storage.getItem(entry) !== JSON.stringify(submitted)) return;
  storage.removeItem(entry);
  const pointer = `${key}:${position}:current`;
  if (storage.getItem(pointer) === String(submitted.baseRevision))
    storage.removeItem(pointer);
}

export function readGuardDraft(
  storage: Storage,
  key: string,
  position: number,
  revision: number,
  width: number,
  height: number,
): GuardBoardDraft | null {
  const pointer = storage.getItem(`${key}:${position}:current`);
  if (pointer === null) return null;
  if (pointer !== String(revision))
    throw new Error(
      'Szkic rozliczenia dotyczy starszej rewizji. Resetuj przed zapisem.',
    );
  const text = storage.getItem(`${key}:${position}:${revision}`);
  if (!text)
    throw new Error(
      'Brak danych lokalnego szkicu rozliczenia. Resetuj przed zapisem.',
    );
  const raw = JSON.parse(text) as GuardBoardDraft;
  if (
    !raw ||
    raw.baseRevision !== revision ||
    raw.dirty !== true ||
    !['corrected_full', 'partial', 'rejected'].includes(raw.disposition) ||
    !validManualGridFlags({
      partial: raw.disposition === 'partial' || raw.disposition === 'rejected',
      exclude: raw.excludeGeometry,
      manualUnavailable: raw.unavailable,
    }) ||
    !(
      raw.quad === null ||
      (Array.isArray(raw.quad) &&
        raw.quad.length === 4 &&
        raw.quad.every(
          (p) =>
            p &&
            Number.isFinite(p.x) &&
            Number.isFinite(p.y) &&
            p.x >= -width &&
            p.y >= -height &&
            p.x <= 2 * width &&
            p.y <= 2 * height,
        ))
    )
  )
    throw new Error('Uszkodzony szkic rozliczenia. Resetuj przed zapisem.');
  return raw;
}

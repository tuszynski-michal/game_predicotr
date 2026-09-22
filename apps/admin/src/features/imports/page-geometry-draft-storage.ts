import {
  completeManualGridFlags,
  validManualGridFlags,
  type ManualGridFlags,
} from '@game-predictor/manual-image-selection-core/manual-grid-qualification';
import type {
  PageGeometryPoint,
  PageGeometryQuad,
} from './page-geometry-mesh.ts';

export interface PageGeometryDraftScope {
  readonly gameId: string;
  readonly uploadId: string;
  readonly preflightJobId: string;
  readonly checksum: string;
  readonly revision: number;
  readonly width: number;
  readonly height: number;
  readonly count: number;
}
export interface PageGeometryDraft {
  readonly quads: readonly PageGeometryQuad[];
  readonly flags: readonly ManualGridFlags[];
  readonly pageCorners: PageGeometryQuad;
  readonly cornerPlacement: readonly PageGeometryPoint[] | null;
  readonly boardCornerPlacement: readonly PageGeometryPoint[] | null;
  readonly v12?: {
    readonly activeLayer: 'boardFrame' | 'symbolGrid';
    readonly boardFrameQuads: readonly PageGeometryQuad[];
    readonly frameConfirmed: boolean;
    readonly symbolGridQuads: readonly PageGeometryQuad[];
  };
}
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem' | 'removeItem'>;
export class PageGeometryDraftConflict extends Error {}

function prefix(scope: PageGeometryDraftScope) {
  return `page-geometry-draft-v1:${scope.gameId}:${scope.uploadId}:${scope.preflightJobId}:${scope.checksum}`;
}
export function pageGeometryDraftKey(scope: PageGeometryDraftScope) {
  return `${prefix(scope)}:${scope.revision}`;
}
export function writePageGeometryDraft(
  storage: Storage,
  scope: PageGeometryDraftScope,
  draft: PageGeometryDraft,
) {
  const key = pageGeometryDraftKey(scope);
  storage.setItem(key, serializePageGeometryDraft(scope, draft));
  storage.setItem(`${prefix(scope)}:current`, key);
}
export function serializePageGeometryDraft(
  scope: PageGeometryDraftScope,
  draft: PageGeometryDraft,
) {
  return JSON.stringify({
    version: draft.v12 === undefined ? 1 : 2,
    scope,
    draft,
  });
}
export function clearPageGeometryDraft(
  storage: Storage,
  scope: PageGeometryDraftScope,
) {
  const pointer = `${prefix(scope)}:current`;
  const key = storage.getItem(pointer);
  if (key?.startsWith(`${prefix(scope)}:`)) storage.removeItem(key);
  storage.removeItem(pageGeometryDraftKey(scope));
  storage.removeItem(pointer);
}

export function clearCommittedPageGeometryDraft(
  storage: Storage,
  scope: PageGeometryDraftScope,
  submittedText: string | null,
) {
  const key = pageGeometryDraftKey(scope);
  if (submittedText === null || storage.getItem(key) !== submittedText) return;
  storage.removeItem(key);
  const pointer = `${prefix(scope)}:current`;
  if (storage.getItem(pointer) === key) storage.removeItem(pointer);
}
export function readPageGeometryDraft(
  storage: Storage,
  scope: PageGeometryDraftScope,
): PageGeometryDraft | null {
  const key = pageGeometryDraftKey(scope);
  const pointer = storage.getItem(`${prefix(scope)}:current`);
  if (pointer && pointer !== key)
    throw new PageGeometryDraftConflict(
      'Szkic dotyczy wcześniejszej rewizji. Resetuj do zapisanej geometrii przed edycją.',
    );
  const text = storage.getItem(key);
  if (!text) return null;
  const parsed = JSON.parse(text);
  if (
    (parsed.version !== 1 && parsed.version !== 2) ||
    JSON.stringify(parsed.scope) !== JSON.stringify(scope)
  )
    throw new PageGeometryDraftConflict('Szkic ma inne źródło lub rewizję.');
  const draft = parsed.draft as PageGeometryDraft;
  const points = (raw: unknown, max: number): boolean =>
    Array.isArray(raw) &&
    raw.length <= max &&
    raw.every(
      (p) =>
        p &&
        Number.isFinite(p.x) &&
        Number.isFinite(p.y) &&
        p.x >= -scope.width &&
        p.y >= -scope.height &&
        p.x <= 2 * scope.width &&
        p.y <= 2 * scope.height,
    );
  if (
    !draft ||
    !Array.isArray(draft.quads) ||
    draft.quads.length !== scope.count ||
    !draft.quads.every((q) => points(q, 4) && q.length === 4) ||
    !Array.isArray(draft.flags) ||
    draft.flags.length !== scope.count ||
    !draft.flags.every(validManualGridFlags) ||
    !points(draft.pageCorners, 4) ||
    draft.pageCorners.length !== 4 ||
    !(draft.cornerPlacement === null || points(draft.cornerPlacement, 4)) ||
    !(
      draft.boardCornerPlacement === null ||
      points(draft.boardCornerPlacement, scope.count * 4)
    )
  )
    throw new Error('Uszkodzony szkic geometrii. Resetuj do stanu serwera.');
  if (
    parsed.version === 2 &&
    (!draft.v12 ||
      (draft.v12.activeLayer !== 'boardFrame' &&
        draft.v12.activeLayer !== 'symbolGrid') ||
      typeof draft.v12.frameConfirmed !== 'boolean' ||
      !Array.isArray(draft.v12.boardFrameQuads) ||
      draft.v12.boardFrameQuads.length !== scope.count ||
      !draft.v12.boardFrameQuads.every(
        (quad) => points(quad, 4) && quad.length === 4,
      ) ||
      !Array.isArray(draft.v12.symbolGridQuads) ||
      draft.v12.symbolGridQuads.length !== scope.count ||
      !draft.v12.symbolGridQuads.every(
        (quad) => points(quad, 4) && quad.length === 4,
      ))
  )
    throw new Error(
      'Uszkodzony szkic geometrii V1.2. Resetuj do stanu serwera.',
    );
  if (parsed.version === 1 && draft.v12 !== undefined)
    throw new Error('Uszkodzony szkic geometrii. Resetuj do stanu serwera.');
  return {
    ...draft,
    flags: draft.flags.map((value) => ({
      ...completeManualGridFlags,
      ...value,
    })),
  };
}

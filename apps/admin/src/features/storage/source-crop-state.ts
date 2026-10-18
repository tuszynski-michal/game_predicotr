import type {
  SourceCropPreviewCreate,
  SourceCropRunResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type SourceCropKind = SourceCropRunResponse['kind'];
export type SourceCropStatus = SourceCropRunResponse['status'];
export type SourceCropScope = NonNullable<SourceCropPreviewCreate['scope']>;

export const SOURCE_CROP_MAX_CHECKSUMS = 500;
export const SOURCE_CROP_MAX_LIMIT = 1_000_000;
export const SUPERSEDED_ERROR_CODE = 'SOURCE_CROP_PREVIEW_SUPERSEDED';

export type ScopeMode = 'all' | 'game' | 'checksums';

export interface ScopeDraft {
  readonly mode: ScopeMode;
  readonly gameId: string;
  readonly checksumsText: string;
  readonly limitText: string;
}

export const EMPTY_SCOPE_DRAFT: ScopeDraft = {
  checksumsText: '',
  gameId: '',
  limitText: '',
  mode: 'all',
};

export type ScopeResult =
  | { readonly ok: true; readonly scope: SourceCropScope }
  | { readonly ok: false; readonly error: string };

const SHA256 = /^[0-9a-f]{64}$/;

/** Splits pasted checksums on whitespace, commas and semicolons. */
export function parseChecksumList(text: string): string[] {
  const seen = new Set<string>();
  for (const part of text.split(/[\s,;]+/)) {
    const value = part.trim().toLowerCase();
    if (value !== '') seen.add(value);
  }
  return [...seen];
}

/** Builds the API scope from the operator draft or explains what is wrong. */
export function buildScope(draft: ScopeDraft): ScopeResult {
  const scope: SourceCropScope = {};
  if (draft.mode === 'game') {
    if (draft.gameId.trim() === '') {
      return { error: 'Wybierz grę, której dotyczy przebieg.', ok: false };
    }
    scope.gameId = draft.gameId.trim();
  }
  if (draft.mode === 'checksums') {
    const checksums = parseChecksumList(draft.checksumsText);
    if (checksums.length === 0) {
      return { error: 'Wklej co najmniej jedną sumę SHA-256.', ok: false };
    }
    if (checksums.length > SOURCE_CROP_MAX_CHECKSUMS) {
      return {
        error: `Lista może mieć najwyżej ${SOURCE_CROP_MAX_CHECKSUMS} różnych sum SHA-256.`,
        ok: false,
      };
    }
    const invalid = checksums.find((value) => !SHA256.test(value));
    if (invalid !== undefined) {
      return {
        error: `Niepoprawna suma SHA-256 (64 znaki szesnastkowe): ${invalid.slice(0, 20)}…`,
        ok: false,
      };
    }
    scope.onlyChecksums = checksums;
  }
  const limitText = draft.limitText.trim();
  if (limitText !== '') {
    const limit = Number(limitText);
    if (
      !/^\d+$/.test(limitText) ||
      !Number.isSafeInteger(limit) ||
      limit < 1 ||
      limit > SOURCE_CROP_MAX_LIMIT
    ) {
      return {
        error: `Limit musi być liczbą całkowitą od 1 do ${SOURCE_CROP_MAX_LIMIT.toLocaleString('pl-PL')}.`,
        ok: false,
      };
    }
    scope.limit = limit;
  }
  return { ok: true, scope };
}

export function scopeLabel(scope: SourceCropScope): string {
  const parts: string[] = [];
  if (scope.gameId != null) parts.push(`gra ${scope.gameId}`);
  if (scope.onlyChecksums != null) {
    parts.push(`${scope.onlyChecksums.length} sum SHA-256`);
  }
  if (parts.length === 0) parts.push('wszystkie gry');
  if (scope.limit != null) {
    parts.push(`limit ${scope.limit.toLocaleString('pl-PL')}`);
  }
  return parts.join(' · ');
}

const STATUS_LABELS: Record<SourceCropStatus, string> = {
  cancelled: 'Anulowany',
  completed: 'Zakończony',
  created: 'W kolejce',
  failed: 'Błąd',
  planning: 'Planowanie',
  previewed: 'Podgląd gotowy',
  processing: 'W toku',
};

export function statusLabel(status: SourceCropStatus): string {
  return STATUS_LABELS[status] ?? status;
}

/** The worker is still building the preview. */
export function isPlanning(run: SourceCropRunResponse): boolean {
  return run.status === 'planning';
}

/** The run executes (queued or running) and must be polled. */
export function isExecuting(run: SourceCropRunResponse): boolean {
  return run.status === 'created' || run.status === 'processing';
}

export function needsPolling(run: SourceCropRunResponse): boolean {
  return isPlanning(run) || isExecuting(run);
}

export function isFinished(run: SourceCropRunResponse): boolean {
  return (
    run.status === 'completed' ||
    run.status === 'failed' ||
    run.status === 'cancelled'
  );
}

/** A previewed run carries everything the start request needs. */
export function isStartable(run: SourceCropRunResponse): boolean {
  return (
    run.status === 'previewed' &&
    run.manifestChecksumSha256 != null &&
    run.previewToken != null
  );
}

export function canStartRun(
  run: SourceCropRunResponse,
  acknowledged: boolean,
): boolean {
  if (!isStartable(run) || run.eligibleCount <= 0) return false;
  return run.kind === 'original_deletion' ? acknowledged : true;
}

export function progressPercent(run: SourceCropRunResponse): number {
  if (run.status === 'completed') return 100;
  if (run.eligibleCount <= 0) return 0;
  return Math.min(
    100,
    Math.max(0, Math.floor((run.processedCount / run.eligibleCount) * 100)),
  );
}

const EXCLUSION_LABELS: Record<string, string> = {
  ACTIVE_IMAGE_JOB: 'Aktywne zadanie obrazu',
  ALREADY_CROPPED: 'Już przycięte',
  ALREADY_DELETED: 'Oryginał już usunięty',
  BOARD_GEOMETRY_MISSING: 'Brak geometrii planszy',
  BOARD_NOT_COMPLETE: 'Plansza niekompletna',
  CROP_PLAN_INVALID: 'Niepoprawny plan przycięcia',
  GAME_STORAGE_NOT_ACTIVE: 'Magazyn gry nieaktywny',
  GEOMETRY_INCOMPLETE: 'Geometria niekompletna',
  GEOMETRY_NOT_APPROVED: 'Geometria niezatwierdzona',
  GRID_ISSUE: 'Problem z siatką',
  IDENTITY_MISMATCH: 'Niezgodna tożsamość pliku',
  IMPORT_NOT_SETTLED: 'Import w toku, przerwany albo anulowany',
  IMPORT_NOT_COMPLETED: 'Import niezakończony',
  NOT_CROPPED: 'Nieprzycięte (brak zweryfikowanego cropu)',
  NO_ACTIVE_BOARDS: 'Brak aktywnych plansz',
  NO_COORDINATE_METADATA: 'Brak metadanych współrzędnych',
  NO_PROTECTED_QUADS: 'Brak chronionych obszarów',
  ORIENTATION_UNSUPPORTED: 'Nieobsługiwana orientacja',
  ORIGINAL_HEADER_MISMATCH: 'Nagłówek oryginału niezgodny',
  ORIGINAL_MISSING: 'Brak pliku oryginału',
  PAGE_REGISTRATION_ANCHOR: 'Kotwica rejestracji strony',
  PAGE_SOURCE_EXCLUDED: 'Źródło strony wykluczone',
  PENDING_GEOMETRY_CORRECTION: 'Oczekująca korekta geometrii',
  PENDING_GRID_PROPOSAL: 'Oczekująca propozycja siatki',
  PROTECTED_QUADS_INVALID: 'Niepoprawne chronione obszary',
  SOURCE_REVISION_NOT_ACCEPTED: 'Rewizja źródła niezaakceptowana',
  UNMANAGED_PATH: 'Ścieżka poza zarządzanym magazynem',
};

/** Readable Polish reason with the raw code kept for support. */
export function exclusionLabel(code: string): string {
  const text = EXCLUSION_LABELS[code];
  return text === undefined ? code : `${text} (${code})`;
}

export function exclusionRows(
  run: SourceCropRunResponse,
): readonly (readonly [string, number])[] {
  return Object.entries(run.exclusionCounts)
    .filter(([, count]) => count > 0)
    .sort(([leftCode, left], [rightCode, right]) =>
      right !== left ? right - left : leftCode.localeCompare(rightCode),
    );
}

const OUTCOME_LABELS: Record<string, string> = {
  alreadyCropped: 'Już przycięte',
  alreadyDeleted: 'Już usunięte',
  cropChanged: 'Crop zmieniony',
  cropped: 'Przycięte',
  deleted: 'Usunięte',
  failed: 'Błędy',
  notBeneficial: 'Bez oszczędności',
  notCropped: 'Nieprzycięte',
  notEligible: 'Niekwalifikujące się',
};

export function outcomeLabel(code: string): string {
  return OUTCOME_LABELS[code] ?? code;
}

const OUTCOME_ORDER: Record<SourceCropKind, readonly string[]> = {
  crop: ['cropped', 'alreadyCropped', 'notEligible', 'notBeneficial', 'failed'],
  original_deletion: [
    'deleted',
    'notCropped',
    'alreadyDeleted',
    'cropChanged',
    'notEligible',
    'failed',
  ],
};

/** Known outcomes first (always shown), unknown worker outcomes appended. */
export function outcomeRows(
  run: SourceCropRunResponse,
): readonly (readonly [string, number])[] {
  const known = OUTCOME_ORDER[run.kind];
  const rows: (readonly [string, number])[] = known.map(
    (code) => [code, run.outcomeCounts[code] ?? 0] as const,
  );
  for (const [code, count] of Object.entries(run.outcomeCounts)) {
    if (!known.includes(code)) rows.push([code, count]);
  }
  return rows;
}

const ERROR_MESSAGES: Record<string, string> = {
  SOURCE_CROP_CONFIRMATION_REQUIRED:
    'Brak wymaganego potwierdzenia. Potwierdź uruchomienie jeszcze raz.',
  SOURCE_CROP_PREVIEW_STALE:
    'Podgląd wygasł albo został zastąpiony. Zaplanuj przebieg ponownie.',
  SOURCE_CROP_RUN_ACTIVE:
    'Inny przebieg przycinania jest już aktywny. Poczekaj, aż się zakończy.',
  SOURCE_CROP_SCOPE_INVALID:
    'Zakres przebiegu jest niepoprawny. Popraw grę, listę sum albo limit.',
  SOURCE_ORIGINAL_DELETION_ACKNOWLEDGEMENT_REQUIRED:
    'Usunięcie oryginałów wymaga potwierdzenia, że operacji nie można cofnąć.',
};

function errorCode(error: unknown): string | null {
  return typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string'
    ? error.code
    : null;
}

/** Polish message with the stable API code for the error codes of the runs. */
export function sourceCropErrorMessage(
  error: unknown,
  fallback: string,
): string {
  const code = errorCode(error);
  const known = code === null ? undefined : ERROR_MESSAGES[code];
  if (code !== null && known !== undefined) return `${known} (${code})`;
  return apiErrorMessage(error, fallback);
}

/**
 * Picks the run worth showing again after a reload: the newest run of the
 * kind, except previews that a newer preview superseded.
 */
export function pickResumableRun(
  runs: readonly SourceCropRunResponse[],
  kind: SourceCropKind,
): SourceCropRunResponse | null {
  const candidates = runs
    .filter(
      (run) => run.kind === kind && run.errorCode !== SUPERSEDED_ERROR_CODE,
    )
    .sort((left, right) =>
      (right.createdAt ?? '').localeCompare(left.createdAt ?? ''),
    );
  return candidates[0] ?? null;
}

export function shortChecksum(value: string): string {
  return value.length > 16 ? `${value.slice(0, 16)}…` : value;
}

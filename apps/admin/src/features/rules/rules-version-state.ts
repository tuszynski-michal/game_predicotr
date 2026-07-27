import type {
  GameResponse,
  RulesVersionResponse,
  RulesVersionStatus,
} from '@game-predictor/admin-api-client';

const MAX_SMALLINT = 32767;
const MAX_INTEGER = 2_147_483_647;

export interface RulesVersionDraft {
  readonly columns: string;
  readonly rows: string;
  readonly spinCost: string;
}

export interface ValidatedRulesVersionDraft {
  readonly columns: number;
  readonly rows: number;
  readonly spinCost: number;
}

export type RulesVersionDraftValidation =
  | { readonly valid: true; readonly value: ValidatedRulesVersionDraft }
  | { readonly error: string; readonly valid: false };

export const DEFAULT_RULES_VERSION_DRAFT: RulesVersionDraft = {
  columns: '5',
  rows: '3',
  spinCost: '10',
};

export const RULES_VERSION_STATUS_LABELS: Record<RulesVersionStatus, string> = {
  archived: 'Zarchiwizowana',
  draft: 'Draft',
  published: 'Opublikowana',
};

export function rulesVersionToDraft(
  rulesVersion: RulesVersionResponse,
): RulesVersionDraft {
  return {
    columns: String(rulesVersion.columns),
    rows: String(rulesVersion.rows),
    spinCost: String(rulesVersion.spinCost),
  };
}

export function validateRulesVersionDraft(
  draft: RulesVersionDraft,
): RulesVersionDraftValidation {
  const rows = parseInteger(draft.rows);
  const columns = parseInteger(draft.columns);
  const spinCost = parseInteger(draft.spinCost);

  if (rows === null || rows < 1 || rows > MAX_SMALLINT) {
    return {
      error: 'Liczba rzędów musi być liczbą całkowitą od 1 do 32767.',
      valid: false,
    };
  }
  if (columns === null || columns < 1 || columns > MAX_SMALLINT) {
    return {
      error: 'Liczba kolumn musi być liczbą całkowitą od 1 do 32767.',
      valid: false,
    };
  }
  if (spinCost === null || spinCost < 0 || spinCost > MAX_INTEGER) {
    return {
      error: 'Koszt spinu musi być liczbą całkowitą od 0 do 2147483647.',
      valid: false,
    };
  }
  return { valid: true, value: { columns, rows, spinCost } };
}

export function selectRulesGameId(
  games: readonly GameResponse[],
  currentGameId: string | null,
): string | null {
  if (currentGameId && games.some((game) => game.id === currentGameId)) {
    return currentGameId;
  }
  return (
    games.find((game) => game.status !== 'archived')?.id ?? games[0]?.id ?? null
  );
}

export function upsertRulesVersion(
  rulesVersions: readonly RulesVersionResponse[],
  saved: RulesVersionResponse,
): readonly RulesVersionResponse[] {
  const updated = rulesVersions.some((item) => item.id === saved.id)
    ? rulesVersions.map((item) => (item.id === saved.id ? saved : item))
    : [...rulesVersions, saved];
  return [...updated].sort(
    (left, right) =>
      right.version - left.version || left.id.localeCompare(right.id),
  );
}

function parseInteger(value: string): number | null {
  const normalized = value.trim();
  if (!/^\d+$/.test(normalized)) {
    return null;
  }
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

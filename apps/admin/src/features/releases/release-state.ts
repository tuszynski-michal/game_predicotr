import type {
  DatasetVersionResponse,
  GameResponse,
  MobileReleaseCreate,
  MobileReleaseResponse,
  MobileReleaseStatus,
  RulesVersionResponse,
} from '@game-predictor/admin-api-client';

export interface ReleaseGameSource {
  readonly datasets: readonly DatasetVersionResponse[];
  readonly game: GameResponse;
  readonly rulesVersions: readonly RulesVersionResponse[];
}

export interface ReleaseGameSelection {
  readonly datasetVersionId: string;
  readonly gameId: string;
  readonly included: boolean;
  readonly rulesVersionId: string;
}

export interface ReleaseDraft {
  readonly selections: readonly ReleaseGameSelection[];
  readonly version: string;
}

export type ReleaseDraftValidation =
  | { readonly body: MobileReleaseCreate; readonly valid: true }
  | { readonly error: string; readonly valid: false };

const RELEASE_VERSION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/;

const RELEASE_STATUS_LABELS: Readonly<Record<MobileReleaseStatus, string>> = {
  archived: 'Zarchiwizowane',
  building: 'Budowanie',
  draft: 'Draft',
  failed: 'Błąd',
  ready: 'Gotowe',
};

export function releaseStatusLabel(status: MobileReleaseStatus): string {
  return RELEASE_STATUS_LABELS[status];
}

export function createInitialSelections(
  sources: readonly ReleaseGameSource[],
): readonly ReleaseGameSelection[] {
  return sources.map((source) => {
    const pair = newestCompatiblePair(source);
    return {
      datasetVersionId: pair?.dataset.id ?? '',
      gameId: source.game.id,
      included: false,
      rulesVersionId: pair?.rules.id ?? '',
    };
  });
}

export function publishedDatasets(
  source: ReleaseGameSource,
): readonly DatasetVersionResponse[] {
  return source.datasets
    .filter((dataset) => dataset.status === 'published')
    .toSorted(
      (left, right) =>
        right.version - left.version || left.id.localeCompare(right.id),
    );
}

export function publishedRules(
  source: ReleaseGameSource,
): readonly RulesVersionResponse[] {
  return source.rulesVersions
    .filter((rules) => rules.status === 'published')
    .toSorted(
      (left, right) =>
        right.version - left.version || left.id.localeCompare(right.id),
    );
}

export function compatibleRules(
  source: ReleaseGameSource,
  datasetVersionId: string,
): readonly RulesVersionResponse[] {
  const dataset = source.datasets.find(
    (item) => item.id === datasetVersionId && item.status === 'published',
  );
  if (dataset === undefined) return [];
  return publishedRules(source).filter(
    (rules) => rules.rows === dataset.rows && rules.columns === dataset.columns,
  );
}

export function compatibleDatasets(
  source: ReleaseGameSource,
  rulesVersionId: string,
): readonly DatasetVersionResponse[] {
  const rules = source.rulesVersions.find(
    (item) => item.id === rulesVersionId && item.status === 'published',
  );
  if (rules === undefined) return [];
  return publishedDatasets(source).filter(
    (dataset) =>
      dataset.rows === rules.rows &&
      dataset.columns === rules.columns &&
      dataset.layoutCount > 0,
  );
}

export function hasCompatibleReleasePair(source: ReleaseGameSource): boolean {
  return newestCompatiblePair(source) !== null;
}

export function validateReleaseDraft(
  draft: ReleaseDraft,
  sources: readonly ReleaseGameSource[],
): ReleaseDraftValidation {
  const version = draft.version.trim();
  if (!RELEASE_VERSION_PATTERN.test(version)) {
    return {
      error:
        'Wersja musi mieć 1–100 znaków ASCII: litery, cyfry, kropki, myślniki lub podkreślenia.',
      valid: false,
    };
  }
  const included = draft.selections.filter((selection) => selection.included);
  if (included.length < 1 || included.length > 15) {
    return {
      error: 'Wybierz od 1 do 15 gier dla wydania.',
      valid: false,
    };
  }
  if (
    new Set(included.map((selection) => selection.gameId)).size !==
    included.length
  ) {
    return { error: 'Każda gra może wystąpić tylko raz.', valid: false };
  }

  const games = [];
  for (const selection of included) {
    const source = sources.find(
      (item) =>
        item.game.id === selection.gameId && item.game.status === 'active',
    );
    if (source === undefined) {
      return {
        error: 'Jedna z wybranych gier nie jest już aktywna.',
        valid: false,
      };
    }
    const dataset = source.datasets.find(
      (item) =>
        item.id === selection.datasetVersionId &&
        item.status === 'published' &&
        item.layoutCount > 0,
    );
    const rules = source.rulesVersions.find(
      (item) =>
        item.id === selection.rulesVersionId && item.status === 'published',
    );
    if (dataset === undefined || rules === undefined) {
      return {
        error: `Gra ${source.game.code} wymaga opublikowanego datasetu i reguł.`,
        valid: false,
      };
    }
    if (dataset.rows !== rules.rows || dataset.columns !== rules.columns) {
      return {
        error: `Dataset i reguły gry ${source.game.code} mają różne wymiary.`,
        valid: false,
      };
    }
    games.push({
      datasetVersionId: dataset.id,
      gameId: source.game.id,
      rulesVersionId: rules.id,
    });
  }

  return { body: { games, version }, valid: true };
}

export function upsertRelease(
  releases: readonly MobileReleaseResponse[],
  updated: MobileReleaseResponse,
): readonly MobileReleaseResponse[] {
  return [
    updated,
    ...releases.filter((release) => release.id !== updated.id),
  ].toSorted(
    (left, right) =>
      Date.parse(right.createdAt) - Date.parse(left.createdAt) ||
      left.id.localeCompare(right.id),
  );
}

export function formatReleaseTimestamp(value: string | null): string {
  if (value === null) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return 'Nieprawidłowa data';
  return new Intl.DateTimeFormat('pl-PL', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(parsed);
}

function newestCompatiblePair(source: ReleaseGameSource): {
  readonly dataset: DatasetVersionResponse;
  readonly rules: RulesVersionResponse;
} | null {
  for (const dataset of publishedDatasets(source)) {
    const rules = compatibleRules(source, dataset.id)[0];
    if (dataset.layoutCount > 0 && rules !== undefined) {
      return { dataset, rules };
    }
  }
  return null;
}

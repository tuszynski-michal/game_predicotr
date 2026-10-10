import type {
  BoardSearchCountMatchResponse,
  RulesVersionResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';

/**
 * Admin-only draft preview (D-535, TASK-0932): the lines modal and the
 * approximate win can evaluate a chosen draft or published rules version of
 * the game instead of the latest published one. Only a data source that can
 * list rules versions (the Admin client) offers the choice; the online share
 * and the management panel never do, and their API refuses the parameter.
 */
export interface BoardSearchRulesVersionOption {
  readonly id: string;
  readonly version: number;
  readonly status: 'draft' | 'published';
}

/** Draft and published versions, newest first; archived ones are hidden. */
export function selectableBoardSearchRulesVersions(
  versions: readonly Pick<RulesVersionResponse, 'id' | 'status' | 'version'>[],
): readonly BoardSearchRulesVersionOption[] {
  return versions
    .flatMap((version) =>
      version.status === 'draft' || version.status === 'published'
        ? [{ id: version.id, status: version.status, version: version.version }]
        : [],
    )
    .sort((a, b) => b.version - a.version);
}

export function boardSearchRulesVersionLabel(
  option: BoardSearchRulesVersionOption,
): string {
  return option.status === 'draft'
    ? `v${option.version} · draft`
    : `v${option.version} · opublikowana`;
}

/** The value of the select: an empty string is the latest published version. */
export const LATEST_PUBLISHED_RULES_VALUE = '';

export function rulesVersionFromSelectValue(value: string): string | null {
  return value === LATEST_PUBLISHED_RULES_VALUE ? null : value;
}

/** `Mumia ×3 → 20`: one count payout of a super game trigger symbol. */
export function boardCountMatchLabel(
  match: Pick<BoardSearchCountMatchResponse, 'count' | 'symbolCode'>,
  symbols: readonly Pick<SymbolResponse, 'code' | 'name'>[],
): string {
  const name =
    symbols.find((symbol) => symbol.code === match.symbolCode)?.name ??
    match.symbolCode;
  return `${name} ×${match.count}`;
}

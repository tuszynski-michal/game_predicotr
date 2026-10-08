'use client';

import { useEffect, useState } from 'react';

import type { BoardSearchDataSource } from './board-search-data-source';
import {
  type BoardSearchRulesVersionOption,
  LATEST_PUBLISHED_RULES_VALUE,
  boardSearchRulesVersionLabel,
  rulesVersionFromSelectValue,
  selectableBoardSearchRulesVersions,
} from './board-search-rules-versions';

/**
 * The game's draft and published rules versions when the data source can
 * list them (the Admin), otherwise `null`: the online share and the
 * management panel have no rules version choice (D-535).
 */
export function useBoardSearchRulesVersions(
  api: Pick<BoardSearchDataSource, 'listRulesVersions'>,
  gameId: string,
): readonly BoardSearchRulesVersionOption[] | null {
  const list = api.listRulesVersions;
  const [loaded, setLoaded] = useState<{
    readonly gameId: string;
    readonly options: readonly BoardSearchRulesVersionOption[];
  } | null>(null);
  useEffect(() => {
    if (list === undefined) return;
    let cancelled = false;
    void Promise.resolve(list(gameId))
      .then((result) => {
        if (cancelled || result.data === undefined) return;
        setLoaded({
          gameId,
          options: selectableBoardSearchRulesVersions(result.data),
        });
      })
      // Without the list the select only offers the latest published rules.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [list, gameId]);
  if (list === undefined) return null;
  return loaded !== null && loaded.gameId === gameId ? loaded.options : [];
}

/** „Wersja reguł”: latest published (default) or a chosen draft/published version. */
export function BoardSearchRulesVersionSelect({
  disabled = false,
  onChange,
  options,
  value,
}: {
  readonly disabled?: boolean;
  readonly onChange: (rulesVersionId: string | null) => void;
  readonly options: readonly BoardSearchRulesVersionOption[];
  readonly value: string | null;
}) {
  const selected = options.find((option) => option.id === value);
  return (
    <label className="boardSearchRulesVersion">
      <span>Wersja reguł</span>
      <select
        aria-label="Wersja reguł"
        disabled={disabled}
        onChange={(event) =>
          onChange(rulesVersionFromSelectValue(event.currentTarget.value))
        }
        value={value ?? LATEST_PUBLISHED_RULES_VALUE}
      >
        <option value={LATEST_PUBLISHED_RULES_VALUE}>
          Najnowsza opublikowana
        </option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {boardSearchRulesVersionLabel(option)}
          </option>
        ))}
      </select>
      {selected?.status === 'draft' ? (
        <small className="boardSearchRulesVersionDraftNote">
          Podgląd wersji roboczej: wynik nie jest opublikowany.
        </small>
      ) : null}
    </label>
  );
}

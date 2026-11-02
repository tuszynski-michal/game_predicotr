'use client';

import {
  type BoardSearchRulesVersionOption,
  LATEST_PUBLISHED_RULES_VALUE,
  boardSearchRulesVersionLabel,
  rulesVersionFromSelectValue,
} from './board-search-rules-versions';

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

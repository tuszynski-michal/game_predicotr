interface BoardCellProcessingModePickerProps {
  readonly disabled: boolean;
  readonly mode: 'verified_v19' | 'structured_shadow' | 'structured_default';
  readonly onChange: (mode: 'verified_v19' | 'structured_default') => void;
}

export function BoardCellProcessingModePicker({
  disabled,
  mode,
  onChange,
}: BoardCellProcessingModePickerProps) {
  return (
    <fieldset className="boardCellProcessingModePicker" disabled={disabled}>
      <legend>Silnik cięcia siatki symboli</legend>
      <p className="mutedText">
        Ustawienie dotyczy wyłącznie nowych importów tej gry. Nie zmienia
        istniejących jobów ani zatwierdzonych plansz.
      </p>
      <div className="boardCellProcessingModeOptions">
        <label className={`boardCellProcessingModeOption ${mode === 'verified_v19' ? 'selected' : ''}`}>
          <input checked={mode === 'verified_v19'} name="engine-policy" onChange={() => onChange('verified_v19')} type="radio" />
          <span>
            <strong>v20 — geometria i cropy v19</strong>
            <small>
              Każda plansza otrzymuje 15 zweryfikowanych cropów source-direct
              albo bezpieczne odroczenie bez inferencji. Nie ma fallbacku do
              v18.
            </small>
          </span>
        </label>
        <label
          className={`boardCellProcessingModeOption ${mode === 'structured_default' ? 'selected' : ''}`}
        >
          <input
            checked={mode === 'structured_default'}
            name="engine-policy"
            onChange={() => onChange('structured_default')}
            type="radio"
          />
          <span>
            <strong>v0.10 — główny silnik strukturalny</strong>
            <small>
              Nowe importy zapisują bieżącą geometrię i cropy jako wirtualne
              assety source-direct. Można je bezpośrednio zatwierdzać w
              Weryfikacji symboli.
            </small>
          </span>
        </label>
      </div>
      {mode === 'structured_shadow' ? (
        <p className="feedbackBanner" role="status">
          Ta gra ma historyczny tryb pomiarowy v0.10. Wybierz główny silnik
          v0.10, aby nowe importy zapisywały aktualne cropy wirtualne.
        </p>
      ) : null}
    </fieldset>
  );
}

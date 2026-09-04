interface BoardCellProcessingModePickerProps {
  readonly disabled: boolean;
  readonly mode:
    | 'verified_v19'
    | 'structured_shadow'
    | 'structured_default'
    | 'structured_lattice_v3';
  readonly onChange: (
    mode: 'verified_v19' | 'structured_default' | 'structured_lattice_v3',
  ) => void;
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
        <label
          className={`boardCellProcessingModeOption ${mode === 'verified_v19' ? 'selected' : ''}`}
        >
          <input
            checked={mode === 'verified_v19'}
            name="engine-policy"
            onChange={() => onChange('verified_v19')}
            type="radio"
          />
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
            <strong>v0.10 v2 — stabilny silnik strukturalny</strong>
            <small>
              Nowe importy zapisują bieżącą geometrię i cropy jako wirtualne
              assety source-direct. Można je bezpośrednio zatwierdzać w
              Weryfikacji symboli.
            </small>
          </span>
        </label>
        <label
          className={`boardCellProcessingModeOption ${mode === 'structured_lattice_v3' ? 'selected' : ''}`}
        >
          <input
            checked={mode === 'structured_lattice_v3'}
            name="engine-policy"
            onChange={() => onChange('structured_lattice_v3')}
            type="radio"
          />
          <span>
            <strong>v0.10 v3 — precyzyjna siatka symboli</strong>
            <small>
              Każdą planszę dopasowuje niezależnie do układu symboli. W razie
              niepewności kieruje ją do ręcznej korekty zamiast używać ramki
              planszy jako siatki.
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
      {mode === 'structured_lattice_v3' ? (
        <p className="feedbackBanner" role="status">
          Wariant zaakceptowany na 450 ręcznych geometriach: 98,44% bezpiecznych
          siatek, mediana błędu 2,46 px. Ustawienie obejmie tylko nowe runy.
        </p>
      ) : null}
    </fieldset>
  );
}

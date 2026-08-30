interface BoardCellProcessingModePickerProps {
  readonly disabled: boolean;
  readonly mode: 'verified_v19' | 'structured_shadow';
  readonly onChange: (mode: 'verified_v19' | 'structured_shadow') => void;
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
        <label className={`boardCellProcessingModeOption ${mode === 'structured_shadow' ? 'selected' : ''}`}>
          <input checked={mode === 'structured_shadow'} name="engine-policy" onChange={() => onChange('structured_shadow')} type="radio" />
          <span>
            <strong>0.10 — nowy silnik w cieniu</strong>
            <small>
              Nowa geometria jest mierzona i audytowana, ale stabilny wynik
              pozostaje nadrzędny. Tryb nie aktywuje Geometry v2 produkcyjnie.
            </small>
          </span>
        </label>
      </div>
    </fieldset>
  );
}

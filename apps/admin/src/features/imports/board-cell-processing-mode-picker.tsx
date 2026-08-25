interface BoardCellProcessingModePickerProps {
  readonly disabled: boolean;
}

export function BoardCellProcessingModePicker({
  disabled,
}: BoardCellProcessingModePickerProps) {
  return (
    <fieldset className="boardCellProcessingModePicker" disabled={disabled}>
      <legend>Silnik cięcia siatki symboli</legend>
      <p className="mutedText">
        Nowe importy zawsze przypinają v20 z geometrią i cropami v19. Ten wybór
        nie zmienia istniejących jobów.
      </p>
      <div className="boardCellProcessingModeOptions">
        <div className="boardCellProcessingModeOption selected">
          <span>
            <strong>v20 — geometria i cropy v19</strong>
            <small>
              Każda plansza otrzymuje 15 zweryfikowanych cropów source-direct
              albo bezpieczne odroczenie bez inferencji. Nie ma fallbacku do
              v18.
            </small>
          </span>
        </div>
      </div>
    </fieldset>
  );
}

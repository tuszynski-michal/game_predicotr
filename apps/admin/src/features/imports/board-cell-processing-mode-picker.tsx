'use client';

import type { BoardCellProcessingMode } from './image-folder-import-actions';

interface BoardCellProcessingModePickerProps {
  readonly disabled: boolean;
  readonly mode: BoardCellProcessingMode;
  readonly onModeChange: (mode: BoardCellProcessingMode) => void;
  readonly onVerifiedV19ConfirmationChange: (confirmed: boolean) => void;
  readonly verifiedV19Confirmed: boolean;
}

export function BoardCellProcessingModePicker({
  disabled,
  mode,
  onModeChange,
  onVerifiedV19ConfirmationChange,
  verifiedV19Confirmed,
}: BoardCellProcessingModePickerProps) {
  return (
    <fieldset className="boardCellProcessingModePicker" disabled={disabled}>
      <legend>Silnik cięcia siatki symboli</legend>
      <p className="mutedText">
        Wybór jest przypinany do joba. Nie zmienia istniejących importów ani
        globalnego trybu domyślnego.
      </p>
      <div className="boardCellProcessingModeOptions">
        <label
          className={
            mode === 'historical_v18'
              ? 'boardCellProcessingModeOption selected'
              : 'boardCellProcessingModeOption'
          }
        >
          <input
            checked={mode === 'historical_v18'}
            name="board-cell-processing-mode"
            onChange={() => onModeChange('historical_v18')}
            type="radio"
            value="historical_v18"
          />
          <span>
            <strong>Historyczny v18 — domyślny</strong>
            <small>
              Dotychczasowy pipeline i zachowanie istniejących jobów.
            </small>
          </span>
        </label>
        <label
          className={
            mode === 'verified_v19'
              ? 'boardCellProcessingModeOption selected'
              : 'boardCellProcessingModeOption'
          }
        >
          <input
            checked={mode === 'verified_v19'}
            name="board-cell-processing-mode"
            onChange={() => onModeChange('verified_v19')}
            type="radio"
            value="verified_v19"
          />
          <span>
            <strong>v20 z geometrią v19 — jawny opt-in</strong>
            <small>
              15 zweryfikowanych cropów source-direct albo bezpieczne odroczenie
              bez inferencji.
            </small>
          </span>
        </label>
      </div>

      {mode === 'verified_v19' ? (
        <div className="boardCellProcessingModeWarning" role="status">
          <strong>Tryb eksperymentalny nie jest domyślnym rolloutem.</strong>
          <p>
            Przypięty benchmark osiągnął 93,78% automatycznego pokrycia przy
            wymaganej bramce 98%. Nieudana geometria nie wróci do v18 — utworzy
            trwały element do końcowej korekty w Reviewerze.
          </p>
          <label>
            <input
              checked={verifiedV19Confirmed}
              onChange={(event) =>
                onVerifiedV19ConfirmationChange(event.target.checked)
              }
              type="checkbox"
            />
            Rozumiem ograniczenia i świadomie uruchamiam ten staging w v20.
          </label>
        </div>
      ) : null}
    </fieldset>
  );
}

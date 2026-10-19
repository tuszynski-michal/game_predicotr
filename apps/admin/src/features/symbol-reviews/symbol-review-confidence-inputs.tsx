import { useId, useState } from 'react';

import {
  parseSymbolReviewConfidenceRange,
  type SymbolReviewConfidenceFilter,
} from './symbol-review-state';
import styles from './symbol-review-workspace.module.css';

export function SymbolReviewConfidenceInputs({
  confidence,
  disabled,
  onApply,
}: {
  readonly confidence: SymbolReviewConfidenceFilter;
  readonly disabled: boolean;
  readonly onApply: (confidence: SymbolReviewConfidenceFilter) => void;
}) {
  const [from, setFrom] = useState(
    String(confidence === 'all' ? 0 : confidence.min),
  );
  const [to, setTo] = useState(
    String(confidence === 'all' ? 100 : confidence.max),
  );
  const [error, setError] = useState('');
  const errorId = useId();

  function apply() {
    const range = parseSymbolReviewConfidenceRange(from, to);
    if (!range) {
      setError(
        'Podaj liczby całkowite od 0 do 100. Wartość Od nie może przekraczać Do.',
      );
      return;
    }
    setError('');
    onApply(range);
  }

  return (
    <fieldset className={styles.confidenceRange} disabled={disabled}>
      <legend>Pewność rozpoznania</legend>
      <div className={styles.confidenceRangeControls}>
        <label>
          Od (%)
          <input
            aria-describedby={error ? errorId : undefined}
            aria-invalid={!!error}
            type="number"
            min={0}
            max={100}
            step={1}
            inputMode="numeric"
            value={from}
            onChange={(event) => setFrom(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                event.stopPropagation();
                apply();
              }
            }}
          />
        </label>
        <label>
          Do (%)
          <input
            aria-describedby={error ? errorId : undefined}
            aria-invalid={!!error}
            type="number"
            min={0}
            max={100}
            step={1}
            inputMode="numeric"
            value={to}
            onChange={(event) => setTo(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                event.stopPropagation();
                apply();
              }
            }}
          />
        </label>
        <button className="primaryButton" type="button" onClick={apply}>
          Zastosuj pewność
        </button>
        <button
          className="secondaryButton"
          type="button"
          onClick={() => {
            setFrom('0');
            setTo('100');
            setError('');
            onApply('all');
          }}
        >
          Wszystkie
        </button>
        <span className={styles.confidenceRangeStatus}>
          Aktywny zakres:{' '}
          {confidence === 'all'
            ? 'Wszystkie'
            : `${confidence.min}–${confidence.max}%`}
        </span>
      </div>
      {error && (
        <p id={errorId} role="alert">
          {error}
        </p>
      )}
    </fieldset>
  );
}

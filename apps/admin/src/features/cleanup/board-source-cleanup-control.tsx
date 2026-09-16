'use client';

import type {
  AdminApiClient,
  CleanupPreviewResponse,
  CleanupResultResponse,
} from '@game-predictor/admin-api-client';
import { useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

type BoardSourceCleanupClient = Pick<
  AdminApiClient,
  'deleteBoardSourceRanges' | 'previewBoardSourceCleanup'
>;

interface BoardSourceCleanupControlProps {
  readonly apiBaseUrl: string;
  readonly client?: BoardSourceCleanupClient;
  readonly gameId: string;
  readonly onCompleted: (result: CleanupResultResponse) => void;
}

function parseSequenceNumbers(value: string): number[] | null {
  const rawValues = value
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (rawValues.length === 0 || rawValues.length > 500) return null;
  const numbers = rawValues.map(Number);
  if (
    numbers.some(
      (number) => !Number.isSafeInteger(number) || number <= 0,
    )
  ) {
    return null;
  }
  return [...new Set(numbers)].sort((left, right) => left - right);
}

function warningMessage(warning: string): string {
  if (warning === 'SYMBOL_MODEL_ACTIVATION_REQUIRED') {
    return 'Niezależny model kandydacki pozostanie w bazie. Przed kolejnym importem trzeba go ręcznie aktywować.';
  }
  if (warning === 'SYMBOL_MODEL_BOOTSTRAP_AVAILABLE') {
    return 'Po usunięciu nie pozostanie aktywny ani kandydacki model symboli; następny import uruchomi dozwolony bootstrap.';
  }
  return warning;
}

export function BoardSourceCleanupControl({
  apiBaseUrl,
  client,
  gameId,
  onCompleted,
}: BoardSourceCleanupControlProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [numbersInput, setNumbersInput] = useState('');
  const [preview, setPreview] = useState<CleanupPreviewResponse | null>(null);
  const [typedTarget, setTypedTarget] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState('');
  const [completed, setCompleted] = useState<CleanupResultResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const submitting = useRef(false);

  const selectedNumbers = useMemo(
    () => parseSequenceNumbers(numbersInput),
    [numbersInput],
  );
  const canExecute =
    preview !== null &&
    preview.blockers.length === 0 &&
    acknowledged &&
    typedTarget === preview.confirmationTarget &&
    !executing;

  async function loadPreview() {
    if (loading || executing) return;
    if (selectedNumbers === null) {
      setError(
        'Podaj od 1 do 500 dodatnich numerów plansz, rozdzielonych spacją, przecinkiem lub nową linią.',
      );
      return;
    }
    setLoading(true);
    setError('');
    setCompleted(null);
    setPreview(null);
    setTypedTarget('');
    setAcknowledged(false);
    try {
      const response = await api.previewBoardSourceCleanup(gameId, {
        sequenceNumbers: selectedNumbers,
      });
      if (response.error !== undefined || response.data === undefined) {
        setError(
          apiErrorMessage(
            response.error,
            'Nie udało się ustalić źródeł dla wskazanych plansz.',
          ),
        );
        return;
      }
      setPreview(response.data);
    } catch {
      setError('API jest niedostępne. Sprawdź serwer i spróbuj ponownie.');
    } finally {
      setLoading(false);
    }
  }

  async function execute() {
    if (
      !canExecute ||
      preview === null ||
      selectedNumbers === null ||
      submitting.current
    ) {
      return;
    }
    submitting.current = true;
    setExecuting(true);
    setError('');
    try {
      const response = await api.deleteBoardSourceRanges(gameId, {
        confirmationTarget: preview.confirmationTarget,
        confirmed: true,
        previewToken: preview.previewToken,
        sequenceNumbers: selectedNumbers,
      });
      if (response.error !== undefined || response.data === undefined) {
        setError(
          apiErrorMessage(
            response.error,
            'Usuwanie nie zostało wykonane. Odśwież podgląd i spróbuj ponownie.',
          ),
        );
        return;
      }
      setCompleted(response.data);
      setPreview(null);
      onCompleted(response.data);
    } catch {
      setError('API jest niedostępne. Nie potwierdzono usunięcia danych.');
    } finally {
      submitting.current = false;
      setExecuting(false);
    }
  }

  return (
    <section className="cleanupControl" data-cleanup-kind="board-source-ranges">
      <div className="cleanupControlHeader">
        <div>
          <p className="eyebrow">Usuwanie źródeł</p>
          <h3>Usuń całe źródła plansz</h3>
          <p>
            Wpisz numery plansz. Dla bezpieczeństwa system usuwa wyłącznie
            pełne zakresy jednego zdjęcia, np. cały zakres <code>456789–456797</code>.
          </p>
        </div>
        <button
          className="dangerButton"
          disabled={loading || executing}
          onClick={() => void loadPreview()}
          type="button"
        >
          {loading ? 'Analizuję zależności…' : 'Pokaż zakres usuwania'}
        </button>
      </div>

      <label className="boardSourceCleanupInput">
        Numery plansz
        <textarea
          aria-describedby="board-source-cleanup-help"
          onChange={(event) => setNumbersInput(event.target.value)}
          placeholder={'456789, 456790, 456791\n456792'}
          rows={4}
          value={numbersInput}
        />
      </label>
      <p id="board-source-cleanup-help">
        Możesz wkleić listę z przecinkami, spacjami lub nowymi liniami. Zakres
        musi obejmować wszystkie plansze należące do danego zdjęcia.
      </p>

      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}

      {completed !== null ? (
        <p className="feedbackBanner" role="status">
          {completed.alreadyCompleted
            ? 'Operacja była już ukończona; odtworzono zapisany wynik.'
            : `Usunięto dane ${completed.deletedCounts
                .filter((item) => item.count > 0)
                .map((item) => `${item.count.toLocaleString('pl-PL')} ${item.name}`)
                .join(', ')}.`}
        </p>
      ) : null}

      {preview !== null ? (
        <div className="cleanupPreview">
          <div className="cleanupPreviewSummary">
            <strong>{preview.targetLabel}</strong>
            <dl>
              {preview.counts
                .filter((entry) => entry.count > 0)
                .map((entry) => (
                  <div key={entry.name}>
                    <dt>{entry.name}</dt>
                    <dd>{entry.count.toLocaleString('pl-PL')}</dd>
                  </div>
                ))}
            </dl>
          </div>

          {preview.warnings.length > 0 ? (
            <div className="cleanupWarnings" role="status">
              <strong>Wpływ na model symboli</strong>
              <ul>
                {preview.warnings.map((warning) => (
                  <li key={warning}>{warningMessage(warning)}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {preview.blockers.length > 0 ? (
            <div className="cleanupBlockers" role="alert">
              <strong>Operacja jest obecnie zablokowana</strong>
              <ul>
                {preview.blockers.map((blocker) => (
                  <li key={blocker}>{blocker}</li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="cleanupConfirmation">
              <label>
                Wpisz dokładnie identyfikator zakresu
                <code>{preview.confirmationTarget}</code>
                <input
                  autoComplete="off"
                  onChange={(event) => setTypedTarget(event.target.value)}
                  spellCheck={false}
                  value={typedTarget}
                />
              </label>
              <label className="cleanupAcknowledgement">
                <input
                  checked={acknowledged}
                  onChange={(event) => setAcknowledged(event.target.checked)}
                  type="checkbox"
                />
                Rozumiem, że usuwam źródła, wszystkie ich plansze oraz dane
                zależne bez kosza.
              </label>
              <div className="rowActions">
                <button
                  className="secondaryButton"
                  disabled={executing}
                  onClick={() => setPreview(null)}
                  type="button"
                >
                  Anuluj
                </button>
                <button
                  className="dangerButton"
                  disabled={!canExecute}
                  onClick={() => void execute()}
                  type="button"
                >
                  {executing ? 'Usuwanie…' : 'Usuń źródła'}
                </button>
              </div>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}

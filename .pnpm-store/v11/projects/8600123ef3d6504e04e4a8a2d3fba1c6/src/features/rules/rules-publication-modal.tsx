'use client';

import type {
  RulesPublicationIssueResponse,
  RulesPublicationReadinessResponse,
  RulesVersionResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  loadPublicationReadiness,
  publishRulesVersion,
  type RulesVersionsClient,
} from '@/features/rules/rules-version-actions';

type LoadState = 'loading' | 'ready' | 'error';

interface RulesPublicationModalProps {
  readonly api: RulesVersionsClient;
  readonly onClose: () => void;
  readonly onPublished: (rulesVersion: RulesVersionResponse) => void;
  readonly rulesVersion: RulesVersionResponse;
}

const ISSUE_LABELS: Readonly<Record<string, string>> = {
  DUPLICATE_ACTIVE_PAYOUT_RULE:
    'Symbol ma więcej niż jedną aktywną wypłatę dla tej samej długości.',
  INCOMPLETE_PAYOUT_RULES:
    'Uzupełnij wypłatę dla każdej długości od minimum do liczby kolumn.',
  INVALID_ACTIVE_PAYLINE: 'Aktywny wzorzec nie pasuje do wymiarów tej wersji.',
  INVALID_MINIMUM_MATCH_LENGTH:
    'Aktywny symbol ma nieprawidłową minimalną długość wygranej.',
  INVALID_PAYOUT_CREDITS: 'Wypłata ma nieprawidłową liczbę kredytów.',
  INVALID_PAYOUT_MATCH_LENGTH:
    'Aktywna wypłata ma długość spoza dozwolonego zakresu.',
  INVALID_RULE_SYMBOL: 'Aktywny symbol nie należy do wybranej gry.',
  NO_ACTIVE_ORDINARY_SYMBOLS: 'Dodaj co najmniej jeden aktywny zwykły symbol.',
  NO_ACTIVE_PAYLINES: 'Dodaj co najmniej jeden aktywny wzorzec.',
  NO_ACTIVE_RULE_SYMBOLS:
    'Dodaj co najmniej jedną aktywną konfigurację symbolu.',
  NON_INCREASING_PAYOUT: 'Wypłaty symbolu muszą rosnąć wraz z długością ciągu.',
  PAYOUT_FOR_INACTIVE_SYMBOL: 'Aktywna wypłata należy do nieaktywnego symbolu.',
  RULES_VERSION_NOT_DRAFT: 'Publikować można wyłącznie wersję draft.',
  WILDCARD_MINIMUM_NOT_ALLOWED:
    'Joker nie może mieć minimalnej długości wygranej.',
  WILDCARD_PAYOUT_NOT_ALLOWED: 'Joker nie może mieć własnych wypłat.',
};

export function publicationIssueLabel(
  issue: RulesPublicationIssueResponse,
): string {
  return ISSUE_LABELS[issue.code] ?? issue.message;
}

export function RulesPublicationModal({
  api,
  onClose,
  onPublished,
  rulesVersion,
}: RulesPublicationModalProps) {
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [readiness, setReadiness] =
    useState<RulesPublicationReadinessResponse | null>(null);
  const [error, setError] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const requestId = useRef(0);
  const mutationInProgress = useRef(false);

  const loadReadiness = useCallback(
    async (clearError = true) => {
      const currentRequest = ++requestId.current;
      setLoadState('loading');
      if (clearError) setError('');
      setConfirmed(false);
      const result = await loadPublicationReadiness(api, rulesVersion.id);
      if (currentRequest !== requestId.current) return;
      if (!result.ok) {
        setError(result.error);
        setLoadState('error');
        return;
      }
      setReadiness(result.readiness);
      setLoadState('ready');
    },
    [api, rulesVersion.id],
  );

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void loadReadiness();
    });
    return () => {
      cancelled = true;
      requestId.current += 1;
    };
  }, [loadReadiness]);

  async function confirmPublication() {
    if (mutationInProgress.current || !confirmed || readiness?.ready !== true) {
      return;
    }
    mutationInProgress.current = true;
    setIsPublishing(true);
    setError('');
    const result = await publishRulesVersion(api, rulesVersion.id);
    mutationInProgress.current = false;
    setIsPublishing(false);
    if (!result.ok) {
      setError(result.error);
      await loadReadiness(false);
      return;
    }
    onPublished(result.rulesVersion);
  }

  return (
    <dialog
      aria-labelledby="rules-publication-title"
      aria-modal="true"
      className="paylineDialog"
      open
    >
      <div className="paylineDialogCard publicationDialogCard">
        <header className="paylineDialogHeader">
          <div>
            <p className="eyebrow">
              Wersja {rulesVersion.version} · {rulesVersion.rows} ×{' '}
              {rulesVersion.columns}
            </p>
            <h2 id="rules-publication-title">Publikacja wersji reguł</h2>
          </div>
          <button
            aria-label="Zamknij modal publikacji"
            className="iconButton"
            disabled={isPublishing}
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>

        {loadState === 'loading' ? (
          <div className="modalState">
            <span className="loadingMark" />
            <div>
              <h3>Sprawdzanie gotowości</h3>
              <p>Weryfikuję wzorce, symbole i pełną tabelę wypłat…</p>
            </div>
          </div>
        ) : loadState === 'error' ? (
          <div className="modalState">
            <span className="stateIcon">!</span>
            <div>
              <h3>Nie udało się sprawdzić wersji</h3>
              <p role="alert">{error}</p>
              <button
                className="secondaryButton"
                onClick={() => void loadReadiness()}
                type="button"
              >
                Spróbuj ponownie
              </button>
            </div>
          </div>
        ) : readiness?.ready ? (
          <div className="publicationSummary publicationSummaryReady">
            <div>
              <p className="eyebrow">Gotowa do publikacji</p>
              <h3>Walidacja zakończona powodzeniem</h3>
              <p>
                Po publikacji wersja stanie się niezmienna. Dalsze poprawki
                wymagają utworzenia nowego draftu.
              </p>
            </div>
            {error ? (
              <p className="feedbackBanner feedbackBannerError" role="alert">
                {error}
              </p>
            ) : null}
            <label className="publicationConfirmation">
              <input
                checked={confirmed}
                disabled={isPublishing}
                onChange={(event) => setConfirmed(event.target.checked)}
                type="checkbox"
              />
              Rozumiem, że tej wersji nie będzie można edytować.
            </label>
            <div className="formActions">
              <button
                className="textButton"
                disabled={isPublishing}
                onClick={onClose}
                type="button"
              >
                Anuluj
              </button>
              <button
                className="primaryButton"
                disabled={!confirmed || isPublishing}
                onClick={() => void confirmPublication()}
                type="button"
              >
                {isPublishing ? 'Publikowanie…' : 'Opublikuj wersję'}
              </button>
            </div>
          </div>
        ) : (
          <div className="publicationSummary">
            <div>
              <p className="eyebrow">Wymaga poprawek</p>
              <h3>Wersja nie jest gotowa do publikacji</h3>
              <p>Usuń wszystkie poniższe blokady i sprawdź wersję ponownie.</p>
            </div>
            <ul className="publicationIssueList">
              {readiness?.issues.map((issue, index) => (
                <li key={`${issue.code}-${index}`}>
                  <strong>{publicationIssueLabel(issue)}</strong>
                  <code>{issue.code}</code>
                </li>
              ))}
            </ul>
            <div className="formActions">
              <button className="textButton" onClick={onClose} type="button">
                Zamknij
              </button>
              <button
                className="secondaryButton"
                onClick={() => void loadReadiness()}
                type="button"
              >
                Sprawdź ponownie
              </button>
            </div>
          </div>
        )}
      </div>
    </dialog>
  );
}

'use client';

import type {
  PayoutRuleResponse,
  RulesVersionResponse,
  RulesVersionSymbolResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import {
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';

import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  type PayoutRulesClient,
  savePayoutConfiguration,
} from '@/features/rules/payout-rules-actions';
import {
  changePayoutCredits,
  changePayoutMinimum,
  type PayoutConfigurationDraft,
  payoutConfigurationToDraft,
  requiredMatchLengths,
  upsertPayoutRules,
  upsertRulesSymbol,
  validatePayoutConfiguration,
} from '@/features/rules/payout-rules-state';

type LoadState = 'loading' | 'ready' | 'error';

interface PayoutRulesManagerModalProps {
  readonly api: PayoutRulesClient;
  readonly onClose: () => void;
  readonly rulesVersion: RulesVersionResponse;
}

export function PayoutRulesManagerModal({
  api,
  onClose,
  rulesVersion,
}: PayoutRulesManagerModalProps) {
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [configurations, setConfigurations] = useState<
    readonly RulesVersionSymbolResponse[]
  >([]);
  const [payoutRules, setPayoutRules] = useState<readonly PayoutRuleResponse[]>(
    [],
  );
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadError, setLoadError] = useState('');
  const [editingSymbolId, setEditingSymbolId] = useState<string | null>(null);
  const [draft, setDraft] = useState<PayoutConfigurationDraft | null>(null);
  const [formError, setFormError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const requestId = useRef(0);
  const mutationInProgress = useRef(false);
  const canMutate = rulesVersion.status === 'draft';

  const load = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setLoadState('loading');
    setLoadError('');
    try {
      const [symbolsResult, configurationsResult, payoutsResult] =
        await Promise.all([
          api.listSymbols(rulesVersion.gameId),
          api.listRulesVersionSymbols(rulesVersion.id),
          api.listPayoutRules(rulesVersion.id),
        ]);
      if (currentRequest !== requestId.current) return;
      const failed =
        symbolsResult.error !== undefined ||
        symbolsResult.data === undefined ||
        configurationsResult.error !== undefined ||
        configurationsResult.data === undefined ||
        payoutsResult.error !== undefined ||
        payoutsResult.data === undefined;
      if (failed) {
        setLoadError(
          apiErrorMessage(
            symbolsResult.error ??
              configurationsResult.error ??
              payoutsResult.error,
            'Nie udało się pobrać konfiguracji payoutów.',
          ),
        );
        setLoadState('error');
        return;
      }
      setSymbols(symbolsResult.data);
      setConfigurations(configurationsResult.data);
      setPayoutRules(payoutsResult.data);
      setLoadState('ready');
    } catch {
      if (currentRequest === requestId.current) {
        setLoadError('Brak połączenia z lokalnym Admin API.');
        setLoadState('error');
      }
    }
  }, [api, rulesVersion.gameId, rulesVersion.id]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void load();
    });
    return () => {
      cancelled = true;
      requestId.current += 1;
    };
  }, [load]);

  function openEditor(symbol: SymbolResponse) {
    const configuration = configurations.find(
      (item) => item.symbolId === symbol.id,
    );
    setEditingSymbolId(symbol.id);
    setDraft(
      payoutConfigurationToDraft(
        symbol,
        configuration,
        payoutRules,
        rulesVersion.columns,
      ),
    );
    setFormError('');
    setFeedback('');
  }

  function closeEditor() {
    if (isSubmitting) return;
    setEditingSymbolId(null);
    setDraft(null);
    setFormError('');
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      mutationInProgress.current ||
      editingSymbolId === null ||
      draft === null
    ) {
      return;
    }
    const symbol = symbols.find((item) => item.id === editingSymbolId);
    if (symbol === undefined) return;
    const validation = validatePayoutConfiguration(
      symbol,
      draft,
      rulesVersion.columns,
    );
    if (!validation.valid) {
      setFormError(validation.error);
      return;
    }
    mutationInProgress.current = true;
    setIsSubmitting(true);
    setFormError('');
    const result = await savePayoutConfiguration(
      api,
      rulesVersion.id,
      symbol.id,
      payoutRules,
      validation.value,
    );
    mutationInProgress.current = false;
    setIsSubmitting(false);
    if (!result.ok) {
      setFormError(result.error);
      void load();
      return;
    }
    setConfigurations((current) =>
      upsertRulesSymbol(current, result.configuration),
    );
    setPayoutRules((current) => {
      const minimum = result.configuration.minimumMatchLength;
      const withArchivedBelow = current.map((item) =>
        item.symbolId === symbol.id &&
        minimum !== null &&
        item.matchLength < minimum
          ? { ...item, isActive: false }
          : item,
      );
      return upsertPayoutRules(withArchivedBelow, result.payoutRules);
    });
    setEditingSymbolId(null);
    setDraft(null);
    setFeedback(`Zapisano konfigurację symbolu „${symbol.name}”.`);
  }

  const editingSymbol =
    symbols.find((item) => item.id === editingSymbolId) ?? null;
  const parsedMinimum =
    draft && /^\d+$/.test(draft.minimumMatchLength)
      ? Number(draft.minimumMatchLength)
      : null;
  const visibleLengths =
    parsedMinimum !== null &&
    parsedMinimum >= 2 &&
    parsedMinimum <= rulesVersion.columns
      ? requiredMatchLengths(parsedMinimum, rulesVersion.columns)
      : [];

  return (
    <dialog
      aria-labelledby="payout-manager-title"
      aria-modal="true"
      className="paylineDialog"
      open
    >
      <div className="paylineDialogCard payoutManagerPanel">
        <header className="paylineDialogHeader">
          <div>
            <p className="eyebrow">Wersja {rulesVersion.version}</p>
            <h2 id="payout-manager-title">Progi i payouty symboli</h2>
            <p>
              Ciąg zawsze zaczyna się w pierwszej kolumnie. Uzupełnij kredyty od
              minimum symbolu do długości {rulesVersion.columns}.
            </p>
          </div>
          <button
            aria-label="Zamknij konfigurację payoutów"
            className="iconButton"
            disabled={isSubmitting}
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>

        {!canMutate ? (
          <p className="readOnlyBanner">
            Ta wersja jest niezmienna. Konfigurację można tylko przeglądać.
          </p>
        ) : null}
        {feedback ? <p className="feedbackBanner">{feedback}</p> : null}

        {loadState === 'loading' ? (
          <ModalState
            title="Wczytywanie konfiguracji"
            text="Pobieram symbole i payouty…"
          />
        ) : loadState === 'error' ? (
          <ModalState
            error
            onRetry={() => void load()}
            text={loadError}
            title="Nie udało się wczytać payoutów"
          />
        ) : symbols.length === 0 ? (
          <ModalState
            text="Najpierw dodaj symbole do wybranej gry."
            title="Brak symboli"
          />
        ) : editingSymbol && draft ? (
          <form className="payoutEditor" onSubmit={onSubmit}>
            <div className="editorHeader">
              <div>
                <p className="eyebrow">
                  {editingSymbol.code} · mobile {editingSymbol.mobileCode}
                </p>
                <h3>{editingSymbol.name}</h3>
              </div>
              <button
                className="textButton"
                disabled={isSubmitting}
                onClick={closeEditor}
                type="button"
              >
                Wróć do listy
              </button>
            </div>
            <label className="checkboxLabel">
              <input
                checked={draft.isActive}
                onChange={(event) =>
                  setDraft((current) =>
                    current
                      ? { ...current, isActive: event.target.checked }
                      : current,
                  )
                }
                type="checkbox"
              />
              Aktywna konfiguracja symbolu
            </label>
            {editingSymbol.isWildcard ? (
              <div className="wildcardNotice">
                <strong>Joker</strong>
                <span>
                  Joker nie ma minimum ani własnych wypłat. Zapis utrwala
                  wartość `null` w tej wersji reguł.
                </span>
              </div>
            ) : rulesVersion.columns < 2 ? (
              <p className="formError" role="alert">
                Wersja ma mniej niż dwie kolumny i nie może otrzymać poprawnej
                konfiguracji zwykłego symbolu.
              </p>
            ) : (
              <>
                <label>
                  Minimalna długość wygranej
                  <select
                    onChange={(event) =>
                      setDraft((current) =>
                        current
                          ? changePayoutMinimum(current, event.target.value)
                          : current,
                      )
                    }
                    value={draft.minimumMatchLength}
                  >
                    {requiredMatchLengths(2, rulesVersion.columns).map(
                      (length) => (
                        <option key={length} value={length}>
                          {length} symbole
                        </option>
                      ),
                    )}
                  </select>
                </label>
                <div className="payoutFields">
                  {visibleLengths.map((matchLength) => (
                    <label key={matchLength}>
                      {matchLength} kolejnych symboli
                      <input
                        inputMode="numeric"
                        min="0"
                        onChange={(event) =>
                          setDraft((current) =>
                            current
                              ? changePayoutCredits(
                                  current,
                                  matchLength,
                                  event.target.value,
                                )
                              : current,
                          )
                        }
                        placeholder="Kredyty"
                        type="number"
                        value={draft.credits[matchLength] ?? ''}
                      />
                    </label>
                  ))}
                </div>
                <p className="fieldHint">
                  Każda kolejna długość musi mieć większą wypłatę od
                  poprzedniej.
                </p>
              </>
            )}
            {formError ? (
              <p className="formError" role="alert">
                {formError}
              </p>
            ) : null}
            <div className="formActions">
              <button
                className="textButton"
                disabled={isSubmitting}
                onClick={closeEditor}
                type="button"
              >
                Anuluj
              </button>
              <button
                className="primaryButton"
                disabled={
                  isSubmitting ||
                  (rulesVersion.columns < 2 && !editingSymbol.isWildcard)
                }
                type="submit"
              >
                {isSubmitting ? 'Zapisywanie…' : 'Zapisz konfigurację'}
              </button>
            </div>
          </form>
        ) : (
          <div className="payoutSymbolList">
            {symbols.map((symbol) => {
              const configuration = configurations.find(
                (item) => item.symbolId === symbol.id,
              );
              const activeRules = payoutRules.filter(
                (item) => item.symbolId === symbol.id && item.isActive,
              );
              return (
                <article className="payoutSymbolRow" key={symbol.id}>
                  <div>
                    <div className="gameTitleLine">
                      <h3>{symbol.name}</h3>
                      {symbol.isWildcard ? (
                        <span className="gameStatus">Joker</span>
                      ) : null}
                    </div>
                    <p>
                      {symbol.code} · mobile {symbol.mobileCode}
                    </p>
                    <p className="rulesMetadata">
                      {symbol.isWildcard
                        ? 'Bez minimum i payoutów'
                        : configuration
                          ? `Minimum ${configuration.minimumMatchLength} · ${activeRules.length} aktywnych wypłat`
                          : 'Niezapisana konfiguracja · domyślnie minimum 3'}
                    </p>
                  </div>
                  {canMutate ? (
                    <button
                      className="secondaryButton"
                      onClick={() => openEditor(symbol)}
                      type="button"
                    >
                      {configuration ? 'Edytuj' : 'Skonfiguruj'}
                    </button>
                  ) : (
                    <span className="immutableLabel">Tylko do odczytu</span>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </div>
    </dialog>
  );
}

function ModalState({
  error = false,
  onRetry,
  text,
  title,
}: {
  readonly error?: boolean;
  readonly onRetry?: () => void;
  readonly text: string;
  readonly title: string;
}) {
  return (
    <div className={`statePanel ${error ? 'statePanelError' : ''}`}>
      <span
        className={
          title.startsWith('Wczytywanie') ? 'loadingMark' : 'stateIcon'
        }
      >
        {title.startsWith('Wczytywanie') ? '' : error ? '!' : '0'}
      </span>
      <div>
        <h3>{title}</h3>
        <p>{text}</p>
        {onRetry ? (
          <button className="secondaryButton" onClick={onRetry} type="button">
            Spróbuj ponownie
          </button>
        ) : null}
      </div>
    </div>
  );
}

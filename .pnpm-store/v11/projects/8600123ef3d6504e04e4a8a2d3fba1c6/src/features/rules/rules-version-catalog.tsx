'use client';

import type {
  GameResponse,
  RulesVersionResponse,
} from '@game-predictor/admin-api-client';
import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import { PaylineManagerModal } from '@/features/rules/payline-manager-modal';
import { PayoutRulesManagerModal } from '@/features/rules/payout-rules-manager-modal';
import { PayoutComputationPanel } from '@/features/rules/payout-computation-panel';
import {
  createEditableRulesDraft,
  saveRulesVersion,
  type RulesVersionsClient,
} from '@/features/rules/rules-version-actions';
import { RulesPublicationModal } from '@/features/rules/rules-publication-modal';
import {
  DEFAULT_RULES_VERSION_DRAFT,
  RULES_VERSION_STATUS_LABELS,
  rulesVersionToDraft,
  selectCurrentRulesVersion,
  selectRulesGameId,
  type RulesVersionDraft,
  upsertRulesVersion,
  validateRulesVersionDraft,
} from '@/features/rules/rules-version-state';

type LoadState = 'loading' | 'ready' | 'error';
type EditorState =
  | { readonly mode: 'closed' }
  | { readonly mode: 'create' }
  | { readonly mode: 'edit'; readonly rulesVersion: RulesVersionResponse };

interface RulesVersionCatalogProps {
  readonly apiBaseUrl: string;
  readonly client?: RulesVersionsClient;
  readonly gameId?: string;
  readonly gamesRevision?: number;
}

export function RulesVersionCatalog({
  apiBaseUrl,
  client,
  gameId,
  gamesRevision = 0,
}: RulesVersionCatalogProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [gamesState, setGamesState] = useState<LoadState>('loading');
  const [uncontrolledGameId, setSelectedGameId] = useState<string | null>(null);
  const selectedGameId = gameId ?? uncontrolledGameId;
  const [rulesVersions, setRulesVersions] = useState<
    readonly RulesVersionResponse[]
  >([]);
  const [rulesState, setRulesState] = useState<LoadState>('ready');
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [editor, setEditor] = useState<EditorState>({ mode: 'closed' });
  const [draft, setDraft] = useState<RulesVersionDraft>(
    DEFAULT_RULES_VERSION_DRAFT,
  );
  const [formError, setFormError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [managedRulesVersion, setManagedRulesVersion] =
    useState<RulesVersionResponse | null>(null);
  const [managedPayoutRulesVersion, setManagedPayoutRulesVersion] =
    useState<RulesVersionResponse | null>(null);
  const [publicationRulesVersion, setPublicationRulesVersion] =
    useState<RulesVersionResponse | null>(null);
  const [isCreatingDraft, setIsCreatingDraft] = useState(false);
  const gamesRequestId = useRef(0);
  const rulesRequestId = useRef(0);
  const mutationInProgress = useRef(false);

  const loadGames = useCallback(async () => {
    const requestId = ++gamesRequestId.current;
    setGamesState('loading');
    setError('');
    try {
      const result = await api.listGames();
      if (requestId !== gamesRequestId.current) return;
      if (result.error !== undefined || result.data === undefined) {
        setError(apiErrorMessage(result.error, 'Nie udało się pobrać gier.'));
        setGamesState('error');
        return;
      }
      setGames(result.data);
      setSelectedGameId((current) =>
        gameId === undefined ? selectRulesGameId(result.data, current) : gameId,
      );
      setGamesState('ready');
    } catch {
      if (requestId === gamesRequestId.current) {
        setError('Brak połączenia z lokalnym Admin API.');
        setGamesState('error');
      }
    }
  }, [api, gameId]);

  const loadRulesVersions = useCallback(
    async (gameId: string) => {
      const requestId = ++rulesRequestId.current;
      setRulesState('loading');
      setError('');
      try {
        const result = await api.listRulesVersions(gameId);
        if (requestId !== rulesRequestId.current) return;
        if (result.error !== undefined || result.data === undefined) {
          setError(
            apiErrorMessage(result.error, 'Nie udało się pobrać wersji reguł.'),
          );
          setRulesState('error');
          return;
        }
        setRulesVersions(result.data);
        setRulesState('ready');
      } catch {
        if (requestId === rulesRequestId.current) {
          setError('Brak połączenia z lokalnym Admin API.');
          setRulesState('error');
        }
      }
    },
    [api],
  );

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) {
        void loadGames();
      }
    });
    return () => {
      cancelled = true;
      gamesRequestId.current += 1;
    };
  }, [gamesRevision, loadGames]);

  useEffect(() => {
    let cancelled = false;
    if (selectedGameId === null) {
      queueMicrotask(() => {
        if (!cancelled) {
          setRulesVersions([]);
          setRulesState('ready');
        }
      });
    } else {
      queueMicrotask(() => {
        if (!cancelled) {
          void loadRulesVersions(selectedGameId);
        }
      });
    }
    return () => {
      cancelled = true;
      rulesRequestId.current += 1;
    };
  }, [loadRulesVersions, selectedGameId]);

  function chooseGame(gameId: string) {
    setSelectedGameId(gameId || null);
    setEditor({ mode: 'closed' });
    setFormError('');
    setFeedback('');
    setManagedRulesVersion(null);
    setManagedPayoutRulesVersion(null);
    setPublicationRulesVersion(null);
  }

  function openCreate() {
    setDraft(DEFAULT_RULES_VERSION_DRAFT);
    setFormError('');
    setFeedback('');
    setEditor({ mode: 'create' });
  }

  function openEdit(rulesVersion: RulesVersionResponse) {
    setDraft(rulesVersionToDraft(rulesVersion));
    setFormError('');
    setFeedback('');
    setEditor({ mode: 'edit', rulesVersion });
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      mutationInProgress.current ||
      editor.mode === 'closed' ||
      (editor.mode === 'create' && selectedGameId === null)
    ) {
      return;
    }
    const validation = validateRulesVersionDraft(draft);
    if (!validation.valid) {
      setFormError(validation.error);
      return;
    }
    mutationInProgress.current = true;
    setIsSubmitting(true);
    setFormError('');
    const result = await saveRulesVersion(
      api,
      editor.mode === 'create'
        ? { gameId: selectedGameId!, mode: 'create' }
        : {
            mode: 'edit',
            rulesVersionId: editor.rulesVersion.id,
          },
      validation.value,
    );
    mutationInProgress.current = false;
    setIsSubmitting(false);
    if (!result.ok) {
      setFormError(result.error);
      return;
    }
    setRulesVersions((current) =>
      upsertRulesVersion(current, result.rulesVersion),
    );
    setEditor({ mode: 'closed' });
    setFeedback(
      editor.mode === 'create'
        ? 'Utworzono pierwszą konfigurację reguł.'
        : 'Zapisano bieżące reguły.',
    );
  }

  function onPublished(rulesVersion: RulesVersionResponse) {
    setRulesVersions((current) => upsertRulesVersion(current, rulesVersion));
    setPublicationRulesVersion(null);
    setFeedback(
      'Opublikowano reguły. Konfiguracja jest teraz tylko do odczytu.',
    );
  }

  const selectedGame = games.find((game) => game.id === selectedGameId) ?? null;
  const currentRulesVersion = selectCurrentRulesVersion(rulesVersions);

  async function beginPublishedEdit(rulesVersion: RulesVersionResponse) {
    if (mutationInProgress.current) return;
    mutationInProgress.current = true;
    setIsCreatingDraft(true);
    setError('');
    setFeedback('');
    const result = await createEditableRulesDraft(api, rulesVersion.id);
    mutationInProgress.current = false;
    setIsCreatingDraft(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setRulesVersions((current) =>
      upsertRulesVersion(current, result.rulesVersion),
    );
    openEdit(result.rulesVersion);
    setFeedback(
      'Przygotowano kopię roboczą. Opublikowana konfiguracja pozostała bez zmian.',
    );
  }

  return (
    <section className="catalogSection" id="rules">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">M2.3 · bieżąca konfiguracja</p>
          <h1>Reguły gry</h1>
          <p className="lead">
            Zarządzaj wymiarami, kosztem spinu, wzorcami i payoutami w jednym
            miejscu. Wersjonowanie działa wewnętrznie i chroni opublikowane
            konfiguracje.
          </p>
        </div>
      </header>

      {feedback ? <p className="feedbackBanner">{feedback}</p> : null}
      {error && gamesState === 'ready' && rulesState === 'ready' ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}

      {gamesState === 'loading' ? (
        <StatePanel title="Wczytywanie gier" text="Pobieram katalog gier…" />
      ) : gamesState === 'error' ? (
        <StatePanel
          error
          onRetry={() => void loadGames()}
          text={error}
          title="Nie udało się wczytać gier"
        />
      ) : games.length === 0 ? (
        <StatePanel
          text="Najpierw utwórz grę w pierwszej sekcji panelu."
          title="Brak gry dla wersji reguł"
        />
      ) : (
        <>
          {gameId === undefined ? (
            <div className="gameSelectorPanel">
              <label htmlFor="rules-game">Gra</label>
              <select
                id="rules-game"
                onChange={(event) => chooseGame(event.target.value)}
                value={selectedGameId ?? ''}
              >
                {games.map((game) => (
                  <option key={game.id} value={game.id}>
                    {game.name} · {game.code}
                  </option>
                ))}
              </select>
              <p>
                {selectedGame
                  ? `Konfigurujesz reguły gry „${selectedGame.name}”.`
                  : 'Wybierz grę.'}
              </p>
            </div>
          ) : null}

          {editor.mode !== 'closed' ? (
            <form className="editorPanel rulesForm" onSubmit={onSubmit}>
              <div className="editorHeader">
                <div>
                  <p className="eyebrow">
                    {editor.mode === 'create'
                      ? 'Pierwsza konfiguracja'
                      : 'Edycja bieżących reguł'}
                  </p>
                  <h2>Wymiary i ekonomia spinu</h2>
                </div>
                <button
                  aria-label="Zamknij formularz"
                  className="iconButton"
                  disabled={isSubmitting}
                  onClick={() => setEditor({ mode: 'closed' })}
                  type="button"
                >
                  ×
                </button>
              </div>
              <label>
                Liczba rzędów
                <input
                  inputMode="numeric"
                  min="1"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      rows: event.target.value,
                    }))
                  }
                  type="number"
                  value={draft.rows}
                />
              </label>
              <label>
                Liczba kolumn
                <input
                  inputMode="numeric"
                  min="1"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      columns: event.target.value,
                    }))
                  }
                  type="number"
                  value={draft.columns}
                />
              </label>
              <label>
                Koszt spinu w kredytach
                <input
                  inputMode="numeric"
                  min="0"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      spinCost: event.target.value,
                    }))
                  }
                  type="number"
                  value={draft.spinCost}
                />
              </label>
              {formError ? (
                <p className="formError" role="alert">
                  {formError}
                </p>
              ) : null}
              <div className="formActions">
                <button
                  className="textButton"
                  disabled={isSubmitting}
                  onClick={() => setEditor({ mode: 'closed' })}
                  type="button"
                >
                  Anuluj
                </button>
                <button
                  className="primaryButton"
                  disabled={isSubmitting}
                  type="submit"
                >
                  {isSubmitting ? 'Zapisywanie…' : 'Zapisz reguły'}
                </button>
              </div>
            </form>
          ) : null}

          {rulesState === 'loading' ? (
            <StatePanel
              title="Wczytywanie wersji"
              text="Pobieram wersje reguł wybranej gry…"
            />
          ) : rulesState === 'error' ? (
            <StatePanel
              error
              onRetry={() =>
                selectedGameId && void loadRulesVersions(selectedGameId)
              }
              text={error}
              title="Nie udało się wczytać wersji"
            />
          ) : currentRulesVersion === null ? (
            <StatePanel
              onRetry={openCreate}
              text="Utwórz pierwszy draft, na przykład 3 × 5 z kosztem spinu 10."
              title="Ta gra nie ma jeszcze reguł"
            />
          ) : (
            <div className="rulesWorkspacePanel">
              <header className="rulesWorkspaceHeader">
                <div>
                  <p className="eyebrow">Bieżące reguły</p>
                  <div className="gameTitleLine">
                    <h2>Konfiguracja gry</h2>
                    <span
                      className={`gameStatus gameStatus-${currentRulesVersion.status}`}
                    >
                      {RULES_VERSION_STATUS_LABELS[currentRulesVersion.status]}
                    </span>
                  </div>
                  <p className="rulesMetadata">
                    {currentRulesVersion.rows} × {currentRulesVersion.columns}
                    <span>·</span>
                    spin {currentRulesVersion.spinCost} kredytów
                  </p>
                </div>
                <p className="rulesInternalVersion">
                  Wewnętrzna wersja {currentRulesVersion.version}
                </p>
              </header>

              <div className="rulesWorkspaceActions">
                <button
                  className="secondaryButton"
                  onClick={() => setManagedRulesVersion(currentRulesVersion)}
                  type="button"
                >
                  Wzorce
                </button>
                <button
                  className="secondaryButton"
                  onClick={() =>
                    setManagedPayoutRulesVersion(currentRulesVersion)
                  }
                  type="button"
                >
                  Payouty
                </button>
                {currentRulesVersion.status === 'draft' ? (
                  <>
                    <button
                      className="secondaryButton"
                      onClick={() => openEdit(currentRulesVersion)}
                      type="button"
                    >
                      Wymiary i koszt
                    </button>
                    <button
                      className="primaryButton"
                      onClick={() =>
                        setPublicationRulesVersion(currentRulesVersion)
                      }
                      type="button"
                    >
                      Publikuj reguły
                    </button>
                  </>
                ) : (
                  <button
                    className="primaryButton"
                    disabled={isCreatingDraft}
                    onClick={() => void beginPublishedEdit(currentRulesVersion)}
                    type="button"
                  >
                    {isCreatingDraft ? 'Przygotowywanie…' : 'Rozpocznij edycję'}
                  </button>
                )}
              </div>

              <p className="rulesWorkspaceNote">
                {currentRulesVersion.status === 'draft'
                  ? 'Zmiany dotyczą wyłącznie bieżącego draftu. Publikacja utworzy niezmienną wersję.'
                  : 'Ta konfiguracja jest niezmienna. Rozpoczęcie edycji utworzy pełną kopię roboczą.'}
              </p>
              {selectedGameId ? (
                <PayoutComputationPanel
                  api={api}
                  gameId={selectedGameId}
                  rulesVersion={currentRulesVersion}
                />
              ) : null}
            </div>
          )}
        </>
      )}
      {managedRulesVersion ? (
        <PaylineManagerModal
          api={api}
          onClose={() => setManagedRulesVersion(null)}
          rulesVersion={managedRulesVersion}
        />
      ) : null}
      {managedPayoutRulesVersion ? (
        <PayoutRulesManagerModal
          api={api}
          onClose={() => setManagedPayoutRulesVersion(null)}
          rulesVersion={managedPayoutRulesVersion}
        />
      ) : null}
      {publicationRulesVersion ? (
        <RulesPublicationModal
          api={api}
          onClose={() => setPublicationRulesVersion(null)}
          onPublished={onPublished}
          rulesVersion={publicationRulesVersion}
        />
      ) : null}
    </section>
  );
}

function StatePanel({
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
        <h2>{title}</h2>
        <p>{text}</p>
        {onRetry ? (
          <button className="secondaryButton" onClick={onRetry} type="button">
            {error ? 'Spróbuj ponownie' : 'Utwórz reguły'}
          </button>
        ) : null}
      </div>
    </div>
  );
}

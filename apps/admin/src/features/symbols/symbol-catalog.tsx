'use client';

import type {
  GameResponse,
  SymbolResponse,
  SymbolStatus,
} from '@game-predictor/admin-api-client';
import Image from 'next/image';
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
import {
  deleteSymbol,
  saveSymbol,
  type SymbolsClient,
} from '@/features/symbols/symbol-catalog-actions';
import {
  EMPTY_SYMBOL_DRAFT,
  selectGameId,
  type SymbolDraft,
  SYMBOL_STATUS_LABELS,
  symbolToDraft,
  upsertSymbol,
  validateSymbolDraft,
} from '@/features/symbols/symbol-catalog-state';

type LoadState = 'loading' | 'ready' | 'error';
type EditorState =
  | { readonly mode: 'closed' }
  | { readonly mode: 'create' }
  | { readonly mode: 'edit'; readonly symbol: SymbolResponse };
type Feedback = {
  readonly kind: 'error' | 'success';
  readonly text: string;
};

interface SymbolCatalogProps {
  readonly apiBaseUrl: string;
  readonly client?: SymbolsClient;
  readonly gameId?: string;
  readonly gamesRevision?: number;
}

export function SymbolCatalog({
  apiBaseUrl,
  client,
  gameId,
  gamesRevision = 0,
}: SymbolCatalogProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [gamesState, setGamesState] = useState<LoadState>('loading');
  const [gamesError, setGamesError] = useState('');
  const [uncontrolledGameId, setSelectedGameId] = useState<string | null>(null);
  const selectedGameId = gameId ?? uncontrolledGameId;
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [symbolsState, setSymbolsState] = useState<LoadState>('ready');
  const [symbolsError, setSymbolsError] = useState('');
  const [editor, setEditor] = useState<EditorState>({ mode: 'closed' });
  const [draft, setDraft] = useState<SymbolDraft>(EMPTY_SYMBOL_DRAFT);
  const [formError, setFormError] = useState('');
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deleteCandidateId, setDeleteCandidateId] = useState<string | null>(
    null,
  );
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const gamesRequestId = useRef(0);
  const symbolsRequestId = useRef(0);
  const mutationInProgress = useRef(false);

  const selectedGame = games.find((game) => game.id === selectedGameId) ?? null;

  const loadGames = useCallback(async () => {
    const requestId = ++gamesRequestId.current;
    setGamesState('loading');
    setGamesError('');

    try {
      const result = await api.listGames();
      if (requestId !== gamesRequestId.current) {
        return;
      }
      if (result.error !== undefined) {
        setGamesError(
          apiErrorMessage(result.error, 'Nie udało się pobrać listy gier.'),
        );
        setGamesState('error');
        return;
      }
      const loadedGames = result.data ?? [];
      setGames(loadedGames);
      setSelectedGameId((current) =>
        gameId === undefined ? selectGameId(loadedGames, current) : gameId,
      );
      setGamesState('ready');
    } catch {
      if (requestId === gamesRequestId.current) {
        setGamesError(
          'Nie można połączyć się z lokalnym Admin API. Sprawdź, czy API i PostgreSQL są uruchomione.',
        );
        setGamesState('error');
      }
    }
  }, [api, gameId]);

  const loadSymbols = useCallback(
    async (gameId: string) => {
      const requestId = ++symbolsRequestId.current;
      setSymbolsState('loading');
      setSymbolsError('');

      try {
        const result = await api.listSymbols(gameId);
        if (requestId !== symbolsRequestId.current) {
          return;
        }
        if (result.error !== undefined) {
          setSymbolsError(
            apiErrorMessage(
              result.error,
              'Nie udało się pobrać symboli tej gry.',
            ),
          );
          setSymbolsState('error');
          return;
        }
        setSymbols(result.data ?? []);
        setSymbolsState('ready');
      } catch {
        if (requestId === symbolsRequestId.current) {
          setSymbolsError(
            'Połączenie z lokalnym Admin API zostało przerwane podczas pobierania symboli.',
          );
          setSymbolsState('error');
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
          setSymbols([]);
          setSymbolsState('ready');
        }
      });
    } else {
      queueMicrotask(() => {
        if (!cancelled) {
          void loadSymbols(selectedGameId);
        }
      });
    }
    return () => {
      cancelled = true;
      symbolsRequestId.current += 1;
    };
  }, [loadSymbols, selectedGameId]);

  function chooseGame(gameId: string) {
    setSelectedGameId(gameId || null);
    setEditor({ mode: 'closed' });
    setFormError('');
    setFeedback(null);
    setDeleteCandidateId(null);
  }

  function openEditEditor(symbol: SymbolResponse) {
    setDraft(symbolToDraft(symbol));
    setFormError('');
    setFeedback(null);
    setEditor({ mode: 'edit', symbol });
  }

  function closeEditor() {
    if (!mutationInProgress.current) {
      setEditor({ mode: 'closed' });
      setFormError('');
    }
  }

  async function submitSymbol(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      mutationInProgress.current ||
      editor.mode === 'closed' ||
      selectedGameId === null
    ) {
      return;
    }

    const validation = validateSymbolDraft(draft);
    if (!validation.valid) {
      setFormError(validation.error);
      return;
    }

    mutationInProgress.current = true;
    setIsSubmitting(true);
    setFormError('');
    setFeedback(null);

    try {
      const result = await saveSymbol(
        api,
        selectedGameId,
        editor.mode === 'create'
          ? { mode: 'create' }
          : { mode: 'edit', symbolId: editor.symbol.id },
        validation.value,
      );
      if (!result.ok) {
        setFormError(result.error);
        return;
      }

      setSymbols((current) => upsertSymbol(current, result.symbol));
      setEditor({ mode: 'closed' });
      setFeedback({
        kind: 'success',
        text:
          editor.mode === 'create'
            ? `Utworzono symbol „${result.symbol.name}”.`
            : `Zapisano zmiany symbolu „${result.symbol.name}”.`,
      });
    } finally {
      mutationInProgress.current = false;
      setIsSubmitting(false);
    }
  }

  async function confirmDelete(symbol: SymbolResponse) {
    if (mutationInProgress.current || selectedGameId === null) {
      return;
    }
    mutationInProgress.current = true;
    setDeletingId(symbol.id);
    setFeedback(null);

    try {
      const result = await deleteSymbol(api, selectedGameId, symbol.id);
      if (!result.ok) {
        setFeedback({ kind: 'error', text: result.error });
        return;
      }
      setSymbols((current) => current.filter((item) => item.id !== symbol.id));
      setDeleteCandidateId(null);
      setFeedback({
        kind: 'success',
        text: `Usunięto symbol „${symbol.name}”.`,
      });
    } finally {
      mutationInProgress.current = false;
      setDeletingId(null);
    }
  }

  return (
    <section className="catalogSection" id="symbols">
      <header className="pageHeader symbolPageHeader">
        <div>
          <p className="eyebrow">M2.2 · Katalog symboli</p>
          <h1>Symbole gry</h1>
          <p className="lead">
            Ustal stabilne kody używane w danych mobilnych, kolejność, jokera i
            względną ścieżkę lokalnego obrazu referencyjnego.
          </p>
        </div>
      </header>

      {gamesState === 'loading' ? (
        <CatalogLoading text="Panel pobiera gry dostępne dla katalogu symboli." />
      ) : null}
      {gamesState === 'error' ? (
        <CatalogError
          message={gamesError}
          onRetry={() => void loadGames()}
          title="Nie udało się wczytać gier"
        />
      ) : null}
      {gamesState === 'ready' && games.length === 0 ? <NoGames /> : null}

      {gamesState === 'ready' && games.length > 0 ? (
        <>
          {gameId === undefined ? (
            <div className="gameSelectorPanel">
              <label htmlFor="symbol-game-selector">
                Gra dla katalogu symboli
              </label>
              <select
                id="symbol-game-selector"
                onChange={(event) => chooseGame(event.currentTarget.value)}
                value={selectedGameId ?? ''}
              >
                {games.map((game) => (
                  <option key={game.id} value={game.id}>
                    {game.name} · {game.code}
                    {game.status === 'archived' ? ' · zarchiwizowana' : ''}
                  </option>
                ))}
              </select>
              <p>
                {selectedGame
                  ? `Wybrano: ${selectedGame.name}. Kod gry pozostaje stabilny.`
                  : 'Wybierz grę, aby zarządzać jej symbolami.'}
              </p>
            </div>
          ) : null}

          {feedback ? (
            <p
              className={
                feedback.kind === 'error'
                  ? 'feedbackBanner feedbackBannerError'
                  : 'feedbackBanner'
              }
              role={feedback.kind === 'error' ? 'alert' : 'status'}
            >
              {feedback.text}
            </p>
          ) : null}

          {editor.mode !== 'closed' ? (
            <SymbolEditor
              draft={draft}
              error={formError}
              isSubmitting={isSubmitting}
              mode={editor.mode}
              onCancel={closeEditor}
              onChange={setDraft}
              onSubmit={submitSymbol}
            />
          ) : null}

          <div
            aria-busy={symbolsState === 'loading'}
            aria-live="polite"
            className="symbolCatalogBody"
          >
            {symbolsState === 'loading' ? (
              <CatalogLoading text="Panel pobiera symbole wybranej gry." />
            ) : null}
            {symbolsState === 'error' && selectedGameId ? (
              <CatalogError
                message={symbolsError}
                onRetry={() => void loadSymbols(selectedGameId)}
                title="Nie udało się wczytać symboli"
              />
            ) : null}
            {symbolsState === 'ready' && symbols.length === 0 ? (
              <SymbolsEmpty />
            ) : null}
            {symbolsState === 'ready' && symbols.length > 0 ? (
              <SymbolsList
                deleteCandidateId={deleteCandidateId}
                deletingId={deletingId}
                onDelete={setDeleteCandidateId}
                onDeleteCancel={() => setDeleteCandidateId(null)}
                onDeleteConfirm={(symbol) => void confirmDelete(symbol)}
                onEdit={openEditEditor}
                symbolImageAssetUrl={(symbol) =>
                  api.symbolImageAssetUrl(symbol.gameId, symbol.id)
                }
                symbols={symbols}
              />
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}

interface SymbolEditorProps {
  readonly draft: SymbolDraft;
  readonly error: string;
  readonly isSubmitting: boolean;
  readonly mode: 'create' | 'edit';
  readonly onCancel: () => void;
  readonly onChange: (draft: SymbolDraft) => void;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

function SymbolEditor({
  draft,
  error,
  isSubmitting,
  mode,
  onCancel,
  onChange,
  onSubmit,
}: SymbolEditorProps) {
  return (
    <section
      aria-labelledby="symbol-editor-title"
      className="editorPanel symbolEditorPanel"
      data-testid="symbol-editor"
    >
      <div className="editorHeader">
        <div>
          <p className="eyebrow">
            {mode === 'create' ? 'Nowy symbol' : 'Edycja symbolu'}
          </p>
          <h2 id="symbol-editor-title">
            {mode === 'create' ? 'Dodaj symbol do gry' : `Edytuj ${draft.code}`}
          </h2>
        </div>
        <button
          aria-label="Zamknij formularz symbolu"
          className="iconButton"
          disabled={isSubmitting}
          onClick={onCancel}
          type="button"
        >
          ×
        </button>
      </div>

      <form className="symbolForm" onSubmit={onSubmit}>
        {error ? (
          <p className="formError" role="alert">
            {error}
          </p>
        ) : null}

        <label>
          <span>Kod mobilny</span>
          <input
            disabled={mode === 'edit' || isSubmitting}
            inputMode="numeric"
            max={32767}
            min={1}
            name="mobileCode"
            onChange={(event) =>
              onChange({ ...draft, mobileCode: event.currentTarget.value })
            }
            placeholder="np. 12"
            required
            type="number"
            value={draft.mobileCode}
          />
          <small>
            Stabilna liczba `smallint`; po zapisie nie można jej zmienić.
          </small>
        </label>

        <label>
          <span>Kod stabilny</span>
          <input
            autoComplete="off"
            disabled={mode === 'edit' || isSubmitting}
            maxLength={64}
            name="code"
            onChange={(event) =>
              onChange({ ...draft, code: event.currentTarget.value })
            }
            placeholder="np. S12 lub WILD"
            required
            value={draft.code}
          />
          <small>Unikalny w ramach gry i nieedytowalny po utworzeniu.</small>
        </label>

        <label>
          <span>Nazwa</span>
          <input
            autoComplete="off"
            disabled={isSubmitting}
            maxLength={200}
            name="name"
            onChange={(event) =>
              onChange({ ...draft, name: event.currentTarget.value })
            }
            placeholder="Nazwa widoczna w panelu"
            required
            value={draft.name}
          />
          <small>Wymagany fallback dla starszych snapshotów i klientów.</small>
        </label>

        <label>
          <span>Nazwa polska</span>
          <input
            autoComplete="off"
            disabled={isSubmitting}
            maxLength={200}
            name="namePl"
            onChange={(event) =>
              onChange({ ...draft, namePl: event.currentTarget.value })
            }
            placeholder="Opcjonalna nazwa w aplikacji mobilnej"
            value={draft.namePl}
          />
        </label>

        <label>
          <span>Nazwa angielska</span>
          <input
            autoComplete="off"
            disabled={isSubmitting}
            maxLength={200}
            name="nameEn"
            onChange={(event) =>
              onChange({ ...draft, nameEn: event.currentTarget.value })
            }
            placeholder="Optional mobile application name"
            value={draft.nameEn}
          />
        </label>

        <label>
          <span>Kolejność</span>
          <input
            disabled={isSubmitting}
            inputMode="numeric"
            min={0}
            name="displayOrder"
            onChange={(event) =>
              onChange({ ...draft, displayOrder: event.currentTarget.value })
            }
            required
            type="number"
            value={draft.displayOrder}
          />
        </label>

        <label>
          <span>Status</span>
          <select
            disabled={isSubmitting}
            name="status"
            onChange={(event) =>
              onChange({
                ...draft,
                status: event.currentTarget.value as SymbolStatus,
              })
            }
            value={draft.status}
          >
            <option value="active">Aktywny</option>
            {mode === 'edit' && draft.status === 'archived' ? (
              <option value="archived">Zarchiwizowany</option>
            ) : null}
          </select>
          <small>
            Archiwizacja aktywnego symbolu wymaga potwierdzenia na liście.
          </small>
        </label>

        <label className="checkboxField">
          <input
            checked={draft.isWildcard}
            disabled={isSubmitting}
            name="isWildcard"
            onChange={(event) =>
              onChange({ ...draft, isWildcard: event.currentTarget.checked })
            }
            type="checkbox"
          />
          <span>
            Joker
            <small>Joker nie otrzymuje własnej reguły wypłaty.</small>
          </span>
        </label>

        <div className="formActions">
          <button
            className="secondaryButton"
            disabled={isSubmitting}
            onClick={onCancel}
            type="button"
          >
            Anuluj
          </button>
          <button
            aria-busy={isSubmitting}
            className="primaryButton"
            data-testid="symbol-submit"
            disabled={isSubmitting}
            type="submit"
          >
            {isSubmitting
              ? 'Zapisywanie…'
              : mode === 'create'
                ? 'Utwórz symbol'
                : 'Zapisz zmiany'}
          </button>
        </div>
      </form>
    </section>
  );
}

interface SymbolsListProps {
  readonly deleteCandidateId: string | null;
  readonly deletingId: string | null;
  readonly onDelete: (symbolId: string) => void;
  readonly onDeleteCancel: () => void;
  readonly onDeleteConfirm: (symbol: SymbolResponse) => void;
  readonly onEdit: (symbol: SymbolResponse) => void;
  readonly symbolImageAssetUrl: (symbol: SymbolResponse) => string;
  readonly symbols: readonly SymbolResponse[];
}

function SymbolsList({
  deleteCandidateId,
  deletingId,
  onDelete,
  onDeleteCancel,
  onDeleteConfirm,
  onEdit,
  symbolImageAssetUrl,
  symbols,
}: SymbolsListProps) {
  return (
    <div className="symbolsPanel">
      <div className="listHeader">
        <div>
          <p className="eyebrow">Symbole wybranej gry</p>
          <h2>
            {symbols.length} {symbols.length === 1 ? 'symbol' : 'symboli'}
          </h2>
        </div>
        <p>
          Kolejność pochodzi z Admin API: `displayOrder`, `mobileCode`, UUID.
        </p>
      </div>
      <div className="symbolsList">
        {symbols.map((symbol) => {
          const deletePending = deletingId === symbol.id;
          const confirmDelete = deleteCandidateId === symbol.id;
          return (
            <article
              className="symbolRow"
              data-testid={`symbol-row-${symbol.id}`}
              key={symbol.id}
            >
              <div className="symbolIdentity">
                <button
                  aria-label={`Zmień grafikę symbolu ${symbol.name}`}
                  className={
                    symbol.isWildcard
                      ? 'symbolImageButton symbolTileWildcard'
                      : 'symbolImageButton'
                  }
                  disabled
                  onClick={() => undefined}
                  title={
                    symbol.imagePath === null
                      ? 'Wybór zatwierdzonego cropa będzie dostępny po załadowaniu listy.'
                      : 'Wybór grafiki jest chwilowo niedostępny.'
                  }
                  type="button"
                >
                  <span aria-hidden="true" className="symbolImageFallback">
                    {symbol.isWildcard
                      ? 'W'
                      : String(symbol.mobileCode).padStart(2, '0')}
                  </span>
                  {symbol.imagePath ? (
                    <Image
                      alt=""
                      height={64}
                      onError={(event) => {
                        event.currentTarget.hidden = true;
                      }}
                      src={symbolImageAssetUrl(symbol)}
                      unoptimized
                      width={64}
                    />
                  ) : null}
                  <span aria-hidden="true" className="symbolImageEditMark">
                    ✎
                  </span>
                </button>
                <div>
                  <div className="gameTitleLine">
                    <h3>{symbol.name}</h3>
                    {symbol.isWildcard ? (
                      <span className="wildcardBadge">Joker</span>
                    ) : null}
                    <span className={`gameStatus gameStatus-${symbol.status}`}>
                      {SYMBOL_STATUS_LABELS[symbol.status]}
                    </span>
                  </div>
                  <div className="symbolMetadata">
                    <code>{symbol.code}</code>
                    <span>mobile {symbol.mobileCode}</span>
                    <span>kolejność {symbol.displayOrder}</span>
                  </div>
                  {symbol.namePl || symbol.nameEn ? (
                    <p className="imagePathValue">
                      PL: {symbol.namePl ?? '—'} · EN: {symbol.nameEn ?? '—'}
                    </p>
                  ) : null}
                  <p className="imagePathValue">
                    {symbol.imagePath ?? 'Brak obrazu referencyjnego'}
                  </p>
                </div>
              </div>

              {confirmDelete ? (
                <div className="archiveConfirmation" role="group">
                  <p>Usunąć symbol? Tej operacji nie można cofnąć.</p>
                  <button
                    className="textButton"
                    disabled={deletePending}
                    onClick={onDeleteCancel}
                    type="button"
                  >
                    Anuluj
                  </button>
                  <button
                    className="dangerButton"
                    data-testid={`symbol-delete-confirm-${symbol.id}`}
                    disabled={deletePending}
                    onClick={() => onDeleteConfirm(symbol)}
                    type="button"
                  >
                    {deletePending ? 'Usuwanie…' : 'Usuń'}
                  </button>
                </div>
              ) : (
                <div className="rowActions">
                  <button
                    className="secondaryButton"
                    data-testid={`symbol-edit-${symbol.id}`}
                    onClick={() => onEdit(symbol)}
                    type="button"
                  >
                    Edytuj
                  </button>
                  <button
                    className="textButton"
                    data-testid={`symbol-delete-${symbol.id}`}
                    onClick={() => onDelete(symbol.id)}
                    type="button"
                  >
                    Usuń
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}

function CatalogLoading({ text }: { readonly text: string }) {
  return (
    <div className="statePanel" data-testid="symbols-loading">
      <span className="loadingMark" aria-hidden="true" />
      <div>
        <h2>Wczytywanie katalogu</h2>
        <p>{text}</p>
      </div>
    </div>
  );
}

function CatalogError({
  message,
  onRetry,
  title,
}: {
  readonly message: string;
  readonly onRetry: () => void;
  readonly title: string;
}) {
  return (
    <div className="statePanel statePanelError" role="alert">
      <span className="stateIcon" aria-hidden="true">
        !
      </span>
      <div>
        <h2>{title}</h2>
        <p>{message}</p>
        <button
          className="secondaryButton"
          data-testid="symbols-retry"
          onClick={onRetry}
          type="button"
        >
          Spróbuj ponownie
        </button>
      </div>
    </div>
  );
}

function NoGames() {
  return (
    <div className="statePanel statePanelEmpty">
      <span className="stateIcon" aria-hidden="true">
        0
      </span>
      <div>
        <h2>Najpierw utwórz grę</h2>
        <p>
          Katalog symboli wymaga stabilnego rekordu gry. Utwórz go w sekcji
          powyżej, a lista odświeży się automatycznie.
        </p>
        <a className="secondaryLink" href="#games">
          Przejdź do gier
        </a>
      </div>
    </div>
  );
}

function SymbolsEmpty() {
  return (
    <div className="statePanel statePanelEmpty" data-testid="symbols-empty">
      <span className="stateIcon" aria-hidden="true">
        0
      </span>
      <div>
        <h2>Ta gra nie ma jeszcze symboli</h2>
        <p>
          Uruchom automatyczne wykrywanie powyżej. Symbole zostaną utworzone z
          rzeczywistych cropów importu.
        </p>
      </div>
    </div>
  );
}

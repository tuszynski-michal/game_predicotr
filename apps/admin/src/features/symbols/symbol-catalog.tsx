'use client';

import type {
  GameResponse,
  SymbolResponse,
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
import { SymbolImagePickerModal } from '@/features/symbols/symbol-image-picker-modal';
import {
  EMPTY_SYMBOL_DRAFT,
  selectGameId,
  type SymbolDraft,
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
  const [deleteError, setDeleteError] = useState('');
  const [imagePickerSymbolId, setImagePickerSymbolId] = useState<string | null>(
    null,
  );
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const gamesRequestId = useRef(0);
  const symbolsRequestId = useRef(0);
  const mutationInProgress = useRef(false);

  const selectedGame = games.find((game) => game.id === selectedGameId) ?? null;
  const deleteCandidate =
    symbols.find((symbol) => symbol.id === deleteCandidateId) ?? null;
  const imagePickerSymbol =
    symbols.find((symbol) => symbol.id === imagePickerSymbolId) ?? null;

  const loadGames = useCallback(async () => {
    const requestId = ++gamesRequestId.current;
    setGamesState('loading');
    setGamesError('');

    try {
      const result = await api.listGames();
      if (requestId !== gamesRequestId.current) return;
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
    async (currentGameId: string) => {
      const requestId = ++symbolsRequestId.current;
      setSymbolsState('loading');
      setSymbolsError('');

      try {
        const result = await api.listSymbols(currentGameId);
        if (requestId !== symbolsRequestId.current) return;
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
      if (!cancelled) void loadGames();
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
        if (!cancelled) void loadSymbols(selectedGameId);
      });
    }
    return () => {
      cancelled = true;
      symbolsRequestId.current += 1;
    };
  }, [loadSymbols, selectedGameId]);

  function closeEditor() {
    if (!mutationInProgress.current) {
      setEditor({ mode: 'closed' });
      setFormError('');
    }
  }

  function chooseGame(nextGameId: string) {
    setSelectedGameId(nextGameId || null);
    setEditor({ mode: 'closed' });
    setFormError('');
    setFeedback(null);
    setDeleteCandidateId(null);
    setDeleteError('');
    setImagePickerSymbolId(null);
  }

  function openCreateEditor() {
    setDraft(EMPTY_SYMBOL_DRAFT);
    setFormError('');
    setFeedback(null);
    setEditor({ mode: 'create' });
  }

  function openEditEditor(symbol: SymbolResponse) {
    setDraft(symbolToDraft(symbol));
    setFormError('');
    setFeedback(null);
    setEditor({ mode: 'edit', symbol });
  }

  function openDeleteDialog(symbolId: string) {
    setDeleteError('');
    setFeedback(null);
    setDeleteCandidateId(symbolId);
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
    if (mutationInProgress.current || selectedGameId === null) return;
    mutationInProgress.current = true;
    setDeletingId(symbol.id);
    setDeleteError('');
    setFeedback(null);
    try {
      const result = await deleteSymbol(api, selectedGameId, symbol.id);
      if (!result.ok) {
        setDeleteError(
          result.blockers.length === 0
            ? result.error
            : `${result.error} Zależności blokujące usunięcie: ${result.blockers.join(', ')}.`,
        );
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

  function requestImageSelection(symbol: SymbolResponse) {
    setFeedback(null);
    setImagePickerSymbolId(symbol.id);
  }

  return (
    <section className="catalogSection" id="symbols">
      <header className="pageHeader symbolPageHeader">
        <div>
          <p className="eyebrow">M2.2 · Katalog symboli</p>
          <h1>Symbole gry</h1>
          <p className="lead">
            Nadaj nazwy symbolom ręcznie. API nadaje niezmienny kod, numer
            mobilny i kolejność, a grafikę wybiera się później wyłącznie z
            zatwierdzonych plansz.
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
                  ? `Wybrano: ${selectedGame.name}.`
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

          {selectedGameId &&
          editor.mode === 'closed' &&
          symbolsState === 'ready' &&
          symbols.length > 0 ? (
            <div className="symbolCatalogToolbar">
              <button
                className="primaryButton"
                data-testid="symbol-add"
                onClick={openCreateEditor}
                type="button"
              >
                Dodaj symbol
              </button>
            </div>
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
              symbol={editor.mode === 'edit' ? editor.symbol : undefined}
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
              <SymbolsEmpty onCreate={openCreateEditor} />
            ) : null}
            {symbolsState === 'ready' && symbols.length > 0 ? (
              <SymbolsList
                onDelete={openDeleteDialog}
                onEdit={openEditEditor}
                onImageSelection={requestImageSelection}
                symbolImageAssetUrl={(symbol) =>
                  api.symbolImageAssetUrl(symbol.gameId, symbol.id)
                }
                symbols={symbols}
              />
            ) : null}
          </div>

          {deleteCandidate ? (
            <SymbolDeleteDialog
              error={deleteError}
              isDeleting={deletingId === deleteCandidate.id}
              onCancel={() => {
                setDeleteCandidateId(null);
                setDeleteError('');
              }}
              onConfirm={() => void confirmDelete(deleteCandidate)}
              symbol={deleteCandidate}
            />
          ) : null}

          {selectedGameId && imagePickerSymbol ? (
            <SymbolImagePickerModal
              api={api}
              gameId={selectedGameId}
              onClose={() => setImagePickerSymbolId(null)}
              onSelected={(savedSymbol) => {
                setSymbols((current) => upsertSymbol(current, savedSymbol));
                setImagePickerSymbolId(null);
                setFeedback({
                  kind: 'success',
                  text: `Zapisano zatwierdzoną grafikę dla „${savedSymbol.name}”.`,
                });
              }}
              symbol={imagePickerSymbol}
            />
          ) : null}
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
  readonly symbol?: SymbolResponse;
}

function SymbolEditor({
  draft,
  error,
  isSubmitting,
  mode,
  onCancel,
  onChange,
  onSubmit,
  symbol,
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
            {mode === 'create'
              ? 'Dodaj symbol do gry'
              : `Edytuj ${symbol?.name}`}
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

      <form className="symbolForm symbolManualForm" onSubmit={onSubmit}>
        {error ? (
          <p className="formError" role="alert">
            {error}
          </p>
        ) : null}

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

        {symbol ? <SymbolIdentityMetadata symbol={symbol} /> : null}

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

function SymbolIdentityMetadata({
  symbol,
}: {
  readonly symbol: SymbolResponse;
}) {
  return (
    <dl
      className="symbolIdentityMetadata"
      data-testid="symbol-identity-metadata"
    >
      <div>
        <dt>Kod</dt>
        <dd>
          <code>{symbol.code}</code>
        </dd>
      </div>
      <div>
        <dt>Numer mobilny</dt>
        <dd>{symbol.mobileCode}</dd>
      </div>
      <div>
        <dt>Kolejność</dt>
        <dd>{symbol.displayOrder}</dd>
      </div>
    </dl>
  );
}

interface SymbolsListProps {
  readonly onDelete: (symbolId: string) => void;
  readonly onEdit: (symbol: SymbolResponse) => void;
  readonly onImageSelection: (symbol: SymbolResponse) => void;
  readonly symbolImageAssetUrl: (symbol: SymbolResponse) => string;
  readonly symbols: readonly SymbolResponse[];
}

function SymbolsList({
  onDelete,
  onEdit,
  onImageSelection,
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
          Tożsamość i kolejność nadaje Admin API podczas utworzenia symbolu.
        </p>
      </div>
      <div className="symbolsList">
        {symbols.map((symbol) => (
          <article
            className="symbolRow"
            data-testid={`symbol-row-${symbol.id}`}
            key={symbol.id}
          >
            <div className="symbolIdentity">
              <button
                aria-label={`Wybierz grafikę symbolu ${symbol.name}`}
                className={
                  symbol.isWildcard
                    ? 'symbolImageButton symbolTileWildcard'
                    : 'symbolImageButton'
                }
                onClick={() => onImageSelection(symbol)}
                title="Wybierz zatwierdzony crop jako grafikę reprezentatywną"
                type="button"
              >
                <span aria-hidden="true" className="symbolImageFallback">
                  ?
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
                </div>
                <div className="symbolMetadata">
                  <code>{symbol.code}</code>
                  <span>mobile {symbol.mobileCode}</span>
                  <span>kolejność {symbol.displayOrder}</span>
                </div>
                <p className="imagePathValue">
                  {symbol.imagePath
                    ? 'Zatwierdzona grafika referencyjna'
                    : 'Brak zatwierdzonej grafiki referencyjnej'}
                </p>
              </div>
            </div>
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
          </article>
        ))}
      </div>
    </div>
  );
}

function SymbolDeleteDialog({
  error,
  isDeleting,
  onCancel,
  onConfirm,
  symbol,
}: {
  readonly error: string;
  readonly isDeleting: boolean;
  readonly onCancel: () => void;
  readonly onConfirm: () => void;
  readonly symbol: SymbolResponse;
}) {
  return (
    <dialog
      aria-labelledby="symbol-delete-title"
      aria-modal="true"
      className="paylineDialog"
      data-testid="symbol-delete-dialog"
      open
    >
      <div className="paylineDialogCard">
        <header className="paylineDialogHeader">
          <div>
            <p className="eyebrow">Usuwanie symbolu</p>
            <h2 id="symbol-delete-title">Usunąć „{symbol.name}”?</h2>
          </div>
        </header>
        <p>
          Operacja jest nieodwracalna. Symbol można usunąć tylko wtedy, gdy nie
          jest użyty przez reguły, plansze, predykcje ani modele.
        </p>
        {error ? (
          <p className="formError" role="alert">
            {error}
          </p>
        ) : null}
        <footer className="symbolDialogActions">
          <button
            className="secondaryButton"
            disabled={isDeleting}
            onClick={onCancel}
            type="button"
          >
            Anuluj
          </button>
          <button
            className="dangerButton"
            disabled={isDeleting}
            onClick={onConfirm}
            type="button"
          >
            {isDeleting ? 'Usuwanie…' : 'Usuń symbol'}
          </button>
        </footer>
      </div>
    </dialog>
  );
}

function CatalogLoading({ text }: { readonly text: string }) {
  return (
    <div className="statePanel" data-testid="symbols-loading">
      <span aria-hidden="true" className="loadingMark" />
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
      <span aria-hidden="true" className="stateIcon">
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
      <span aria-hidden="true" className="stateIcon">
        +
      </span>
      <div>
        <h2>Najpierw dodaj grę</h2>
        <p>Każdy katalog symboli należy do jednej gry.</p>
      </div>
    </div>
  );
}

function SymbolsEmpty({ onCreate }: { readonly onCreate: () => void }) {
  return (
    <div className="statePanel statePanelEmpty" data-testid="symbols-empty">
      <span aria-hidden="true" className="stateIcon">
        ?
      </span>
      <div>
        <h2>Brak symboli</h2>
        <p>
          Dodaj nazwy symboli ręcznie. Grafikę wybierzesz po zatwierdzeniu
          planszy, na której symbol występuje.
        </p>
        <button className="primaryButton" onClick={onCreate} type="button">
          Dodaj symbol
        </button>
      </div>
    </div>
  );
}

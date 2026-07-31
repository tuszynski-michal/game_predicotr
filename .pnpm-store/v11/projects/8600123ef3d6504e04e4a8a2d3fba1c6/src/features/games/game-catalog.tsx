'use client';

import type {
  GameResponse,
  GameStatus,
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
import {
  archiveGameIdentity,
  type GamesClient,
  restoreGameIdentity,
  saveGameIdentity,
} from '@/features/games/game-catalog-actions';
import {
  countGamesByStatus,
  EMPTY_GAME_DRAFT,
  filterGamesByStatus,
  GAME_STATUS_FILTER_LABELS,
  GAME_STATUS_FILTERS,
  GAME_STATUS_LABELS,
  type GameDraft,
  markGameArchived,
  upsertGame,
  validateGameDraft,
} from '@/features/games/game-catalog-state';

type LoadState = 'loading' | 'ready' | 'error';
type EditorState =
  | { readonly mode: 'closed' }
  | { readonly mode: 'create' }
  | { readonly mode: 'edit'; readonly game: GameResponse };

interface GameCatalogProps {
  readonly apiBaseUrl: string;
  readonly client?: GamesClient;
  readonly onGamesChanged?: () => void;
  readonly onGamesLoaded?: (games: readonly GameResponse[]) => void;
  readonly onSelectedGameIdChange?: (gameId: string | null) => void;
  readonly selectedGameId?: string | null;
}

export function GameCatalog({
  apiBaseUrl,
  client,
  onGamesChanged,
  onGamesLoaded,
  onSelectedGameIdChange,
  selectedGameId,
}: GameCatalogProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [statusFilter, setStatusFilter] = useState<GameStatus>('active');
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadError, setLoadError] = useState('');
  const [editor, setEditor] = useState<EditorState>({ mode: 'closed' });
  const [draft, setDraft] = useState<GameDraft>(EMPTY_GAME_DRAFT);
  const [formError, setFormError] = useState('');
  const [notice, setNotice] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [archiveCandidateId, setArchiveCandidateId] = useState<string | null>(
    null,
  );
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const loadRequestId = useRef(0);
  const mutationInProgress = useRef(false);
  const statusCounts = useMemo(() => countGamesByStatus(games), [games]);
  const selectedCatalogGame = games.find((game) => game.id === selectedGameId);
  const effectiveStatusFilter = selectedCatalogGame?.status ?? statusFilter;
  const visibleGames = useMemo(
    () => filterGamesByStatus(games, effectiveStatusFilter),
    [effectiveStatusFilter, games],
  );

  const loadGames = useCallback(async () => {
    const requestId = ++loadRequestId.current;
    setLoadState('loading');
    setLoadError('');

    try {
      const result = await api.listGames();
      if (requestId !== loadRequestId.current) {
        return;
      }
      if (result.error !== undefined) {
        setLoadError(
          apiErrorMessage(result.error, 'Nie udało się pobrać gier.'),
        );
        setLoadState('error');
        return;
      }
      const loadedGames = result.data ?? [];
      setGames(loadedGames);
      onGamesLoaded?.(loadedGames);
      setLoadState('ready');
    } catch {
      if (requestId === loadRequestId.current) {
        setLoadError(
          'Nie można połączyć się z lokalnym Admin API. Sprawdź, czy API i PostgreSQL są uruchomione.',
        );
        setLoadState('error');
      }
    }
  }, [api, onGamesLoaded]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) {
        void loadGames();
      }
    });
    return () => {
      cancelled = true;
      loadRequestId.current += 1;
    };
  }, [loadGames]);

  function openCreateEditor() {
    setDraft(EMPTY_GAME_DRAFT);
    setFormError('');
    setNotice('');
    setEditor({ mode: 'create' });
  }

  function openEditEditor(game: GameResponse) {
    setDraft({
      code: game.code,
      name: game.name,
      status: game.status,
    });
    setFormError('');
    setNotice('');
    setEditor({ mode: 'edit', game });
  }

  function closeEditor() {
    if (!mutationInProgress.current) {
      setEditor({ mode: 'closed' });
      setFormError('');
    }
  }

  async function submitGame(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutationInProgress.current || editor.mode === 'closed') {
      return;
    }

    const validation = validateGameDraft(draft);
    if (!validation.valid) {
      setFormError(validation.error);
      return;
    }
    const { code, name, status } = validation.value;

    mutationInProgress.current = true;
    setIsSubmitting(true);
    setFormError('');
    setNotice('');

    try {
      const result = await saveGameIdentity(
        api,
        editor.mode === 'create'
          ? { mode: 'create' }
          : { gameId: editor.game.id, mode: 'edit' },
        { code, name, status },
      );

      if (!result.ok) {
        setFormError(result.error);
        return;
      }

      const savedGame = result.game;
      const nextGames = upsertGame(games, savedGame);
      setGames(nextGames);
      setStatusFilter(savedGame.status);
      onGamesLoaded?.(nextGames);
      setEditor({ mode: 'closed' });
      onGamesChanged?.();
      onSelectedGameIdChange?.(
        savedGame.status === 'archived' ? null : savedGame.id,
      );
      setNotice(
        editor.mode === 'create'
          ? `Utworzono grę „${savedGame.name}”.`
          : `Zapisano zmiany gry „${savedGame.name}”.`,
      );
    } finally {
      mutationInProgress.current = false;
      setIsSubmitting(false);
    }
  }

  async function confirmArchive(game: GameResponse) {
    if (mutationInProgress.current) {
      return;
    }
    mutationInProgress.current = true;
    setArchivingId(game.id);
    setNotice('');

    try {
      const result = await archiveGameIdentity(api, game.id);
      if (!result.ok) {
        setNotice(result.error);
        return;
      }
      const nextGames = markGameArchived(games, game.id);
      setGames(nextGames);
      onGamesLoaded?.(nextGames);
      setArchiveCandidateId(null);
      onGamesChanged?.();
      if (selectedGameId === game.id) {
        onSelectedGameIdChange?.(null);
      }
      setNotice(
        `Zarchiwizowano grę „${game.name}”. Rekord pozostał w katalogu.`,
      );
    } finally {
      mutationInProgress.current = false;
      setArchivingId(null);
    }
  }

  async function restoreArchivedGame(game: GameResponse) {
    if (mutationInProgress.current || game.status !== 'archived') {
      return;
    }
    mutationInProgress.current = true;
    setRestoringId(game.id);
    setNotice('');

    try {
      const result = await restoreGameIdentity(api, game);
      if (!result.ok) {
        setNotice(result.error);
        return;
      }
      const nextGames = upsertGame(games, result.game);
      setGames(nextGames);
      setStatusFilter('draft');
      onGamesLoaded?.(nextGames);
      onGamesChanged?.();
      onSelectedGameIdChange?.(result.game.id);
      setNotice(
        `Przywrócono grę „${result.game.name}” jako szkic. Dane gry pozostały zachowane.`,
      );
    } finally {
      mutationInProgress.current = false;
      setRestoringId(null);
    }
  }

  function changeStatusFilter(nextFilter: GameStatus) {
    if (nextFilter === effectiveStatusFilter) {
      return;
    }
    const selectedGame = games.find((game) => game.id === selectedGameId);
    if (selectedGame && selectedGame.status !== nextFilter) {
      onSelectedGameIdChange?.(null);
    }
    setStatusFilter(nextFilter);
    setEditor({ mode: 'closed' });
    setArchiveCandidateId(null);
    setFormError('');
  }

  return (
    <div id="games">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">M2 · Konfiguracja administracyjna</p>
          <h1>Gry</h1>
          <p className="lead">
            Zarządzaj stabilną tożsamością gry. Wymiary planszy i koszt spinu
            zostaną przypisane później do wersji reguł.
          </p>
        </div>
        <button
          className="primaryButton"
          data-testid="game-create-open"
          onClick={openCreateEditor}
          type="button"
        >
          <span aria-hidden="true">+</span>
          Nowa gra
        </button>
      </header>

      {notice ? (
        <p className="feedbackBanner" role="status">
          {notice}
        </p>
      ) : null}

      {editor.mode !== 'closed' ? (
        <GameEditor
          draft={draft}
          error={formError}
          isSubmitting={isSubmitting}
          mode={editor.mode}
          onCancel={closeEditor}
          onChange={setDraft}
          onSubmit={submitGame}
        />
      ) : null}

      <section aria-busy={loadState === 'loading'} aria-live="polite">
        {loadState === 'loading' ? <GamesLoading /> : null}
        {loadState === 'error' ? (
          <GamesError message={loadError} onRetry={() => void loadGames()} />
        ) : null}
        {loadState === 'ready' && games.length === 0 ? (
          <GamesEmpty onCreate={openCreateEditor} />
        ) : null}
        {loadState === 'ready' && games.length > 0 ? (
          <div className="gamesPanel">
            <div
              aria-label="Filtr statusu gier"
              className="gameStatusFilters"
              role="group"
            >
              {GAME_STATUS_FILTERS.map((status) => (
                <button
                  aria-pressed={effectiveStatusFilter === status}
                  className={
                    effectiveStatusFilter === status
                      ? 'gameStatusFilter gameStatusFilterActive'
                      : 'gameStatusFilter'
                  }
                  data-testid={`game-filter-${status}`}
                  key={status}
                  onClick={() => changeStatusFilter(status)}
                  type="button"
                >
                  <span>{GAME_STATUS_FILTER_LABELS[status]}</span>
                  <strong>{statusCounts[status]}</strong>
                </button>
              ))}
            </div>
            <div className="listHeader">
              <div>
                <p className="eyebrow">
                  {GAME_STATUS_FILTER_LABELS[effectiveStatusFilter]}
                </p>
                <h2>
                  {visibleGames.length}{' '}
                  {visibleGames.length === 1 ? 'gra' : 'gry'}
                </h2>
              </div>
              <p>Łącznie w katalogu: {games.length}</p>
            </div>
            {visibleGames.length === 0 ? (
              <GamesFilteredEmpty status={effectiveStatusFilter} />
            ) : (
              <div className="gamesList">
                {visibleGames.map((game) => (
                  <GameRow
                    archivePending={archivingId === game.id}
                    confirmArchive={archiveCandidateId === game.id}
                    game={game}
                    key={game.id}
                    onArchive={() => setArchiveCandidateId(game.id)}
                    onArchiveCancel={() => setArchiveCandidateId(null)}
                    onArchiveConfirm={() => void confirmArchive(game)}
                    onEdit={() => openEditEditor(game)}
                    onRestore={() => void restoreArchivedGame(game)}
                    onSelect={() =>
                      game.status !== 'archived' &&
                      onSelectedGameIdChange?.(game.id)
                    }
                    restorePending={restoringId === game.id}
                    selectable={game.status !== 'archived'}
                    selected={
                      game.status !== 'archived' && selectedGameId === game.id
                    }
                  />
                ))}
              </div>
            )}
          </div>
        ) : null}
      </section>
    </div>
  );
}

interface GameEditorProps {
  readonly draft: GameDraft;
  readonly error: string;
  readonly isSubmitting: boolean;
  readonly mode: 'create' | 'edit';
  readonly onCancel: () => void;
  readonly onChange: (draft: GameDraft) => void;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

function GameEditor({
  draft,
  error,
  isSubmitting,
  mode,
  onCancel,
  onChange,
  onSubmit,
}: GameEditorProps) {
  return (
    <section
      aria-labelledby="game-editor-title"
      className="editorPanel"
      data-testid="game-editor"
    >
      <div className="editorHeader">
        <div>
          <p className="eyebrow">
            {mode === 'create' ? 'Nowy rekord' : 'Edycja rekordu'}
          </p>
          <h2 id="game-editor-title">
            {mode === 'create' ? 'Utwórz grę' : `Edytuj ${draft.code}`}
          </h2>
        </div>
        <button
          aria-label="Zamknij formularz"
          className="iconButton"
          disabled={isSubmitting}
          onClick={onCancel}
          type="button"
        >
          ×
        </button>
      </div>

      <form className="gameForm" onSubmit={onSubmit}>
        {error ? (
          <p className="formError" role="alert">
            {error}
          </p>
        ) : null}
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
            placeholder="np. blazing-hot"
            required
            value={draft.code}
          />
          <small>
            Litery, cyfry, myślnik lub podkreślenie. Po zapisaniu kod pozostaje
            niezmienny.
          </small>
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
        </label>

        <label>
          <span>Status</span>
          <select
            disabled={isSubmitting}
            name="status"
            onChange={(event) =>
              onChange({
                ...draft,
                status: event.currentTarget.value as GameStatus,
              })
            }
            value={draft.status}
          >
            <option value="draft">Szkic</option>
            <option value="active">Aktywna</option>
            {mode === 'edit' && draft.status === 'archived' ? (
              <option value="archived">Zarchiwizowana</option>
            ) : null}
          </select>
          <small>
            Archiwizacja aktywnego rekordu wymaga osobnego potwierdzenia na
            liście.
          </small>
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
            data-testid="game-submit"
            disabled={isSubmitting}
            type="submit"
          >
            {isSubmitting
              ? 'Zapisywanie…'
              : mode === 'create'
                ? 'Utwórz grę'
                : 'Zapisz zmiany'}
          </button>
        </div>
      </form>
    </section>
  );
}

interface GameRowProps {
  readonly archivePending: boolean;
  readonly confirmArchive: boolean;
  readonly game: GameResponse;
  readonly onArchive: () => void;
  readonly onArchiveCancel: () => void;
  readonly onArchiveConfirm: () => void;
  readonly onEdit: () => void;
  readonly onRestore: () => void;
  readonly onSelect: () => void;
  readonly restorePending: boolean;
  readonly selectable: boolean;
  readonly selected: boolean;
}

function GameRow({
  archivePending,
  confirmArchive,
  game,
  onArchive,
  onArchiveCancel,
  onArchiveConfirm,
  onEdit,
  onRestore,
  onSelect,
  restorePending,
  selectable,
  selected,
}: GameRowProps) {
  return (
    <article
      className={selected ? 'gameRow gameRowSelected' : 'gameRow'}
      data-testid={`game-row-${game.id}`}
    >
      <button
        aria-disabled={!selectable}
        aria-pressed={selected}
        className={
          selectable
            ? 'gameIdentity gameIdentityButton'
            : 'gameIdentity gameIdentityButton gameIdentityButtonDisabled'
        }
        onClick={onSelect}
        type="button"
      >
        <span className="gameMonogram" aria-hidden="true">
          {game.name.slice(0, 2).toUpperCase()}
        </span>
        <div>
          <div className="gameTitleLine">
            <h3>{game.name}</h3>
            <span className={`gameStatus gameStatus-${game.status}`}>
              {GAME_STATUS_LABELS[game.status]}
            </span>
          </div>
          <code>{game.code}</code>
        </div>
      </button>

      {confirmArchive ? (
        <div className="archiveConfirmation" role="group">
          <p>Archiwizować? Rekord pozostanie w katalogu.</p>
          <button
            className="textButton"
            disabled={archivePending}
            onClick={onArchiveCancel}
            type="button"
          >
            Anuluj
          </button>
          <button
            className="dangerButton"
            data-testid={`game-archive-confirm-${game.id}`}
            disabled={archivePending}
            onClick={onArchiveConfirm}
            type="button"
          >
            {archivePending ? 'Archiwizowanie…' : 'Potwierdź'}
          </button>
        </div>
      ) : (
        <div className="rowActions">
          <button
            className="secondaryButton"
            data-testid={`game-edit-${game.id}`}
            onClick={onEdit}
            type="button"
          >
            Edytuj
          </button>
          {game.status !== 'archived' ? (
            <button
              className="textButton"
              data-testid={`game-archive-${game.id}`}
              onClick={onArchive}
              type="button"
            >
              Archiwizuj
            </button>
          ) : (
            <button
              className="secondaryButton"
              data-testid={`game-restore-${game.id}`}
              disabled={restorePending}
              onClick={onRestore}
              type="button"
            >
              {restorePending ? 'Przywracanie…' : 'Przywróć jako szkic'}
            </button>
          )}
        </div>
      )}
    </article>
  );
}

function GamesLoading() {
  return (
    <div className="statePanel" data-testid="games-loading">
      <span className="loadingMark" aria-hidden="true" />
      <div>
        <h2>Wczytywanie katalogu</h2>
        <p>Panel pobiera gry z lokalnego Admin API.</p>
      </div>
    </div>
  );
}

function GamesError({
  message,
  onRetry,
}: {
  readonly message: string;
  readonly onRetry: () => void;
}) {
  return (
    <div className="statePanel statePanelError" role="alert">
      <span className="stateIcon" aria-hidden="true">
        !
      </span>
      <div>
        <h2>Nie udało się wczytać katalogu</h2>
        <p>{message}</p>
        <button
          className="secondaryButton"
          data-testid="games-retry"
          onClick={onRetry}
          type="button"
        >
          Spróbuj ponownie
        </button>
      </div>
    </div>
  );
}

function GamesEmpty({ onCreate }: { readonly onCreate: () => void }) {
  return (
    <div className="statePanel statePanelEmpty" data-testid="games-empty">
      <span className="stateIcon" aria-hidden="true">
        0
      </span>
      <div>
        <h2>Nie ma jeszcze żadnej gry</h2>
        <p>
          Utwórz pierwszy stabilny rekord, aby później dodać symbole i reguły.
        </p>
        <button className="secondaryButton" onClick={onCreate} type="button">
          Utwórz pierwszą grę
        </button>
      </div>
    </div>
  );
}

function GamesFilteredEmpty({ status }: { readonly status: GameStatus }) {
  return (
    <div className="filteredEmptyState" data-testid={`games-empty-${status}`}>
      <strong>Brak gier w tym widoku</strong>
      <p>
        Filtr „{GAME_STATUS_FILTER_LABELS[status]}” nie zawiera obecnie żadnych
        rekordów. Pozostałe gry nie zostały usunięte.
      </p>
    </div>
  );
}

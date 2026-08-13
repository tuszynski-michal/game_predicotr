'use client';

import type {
  GameResponse,
  JobResponse,
  OperationalImageReviewCountsResponse,
  OperationalImageReviewItemResponse,
  OperationalImageReviewPageResponse,
  OperationalImageReviewResolutionResponse,
  SymbolResponse,
  VerifiedCohortExportResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import {
  freezeVerifiedCohort,
  loadVerifiedCohortHistory,
  loadOperationalReviewGames,
  loadOperationalReviewJobs,
  loadOperationalReviewPage,
  loadOperationalReviewSymbols,
  resolveOperationalReview,
  type LoadOperationalReviewPageOptions,
  type OperationalReviewsClient,
} from '@/features/operational-reviews/operational-review-actions';
import { OperationalReviewGeometryEditor } from '@/features/operational-reviews/operational-review-geometry-editor';
import {
  buildOperationalReviewResolutionCommand,
  buildOperationalReviewSymbolShortcuts,
  formatOperationalConfidence,
  isOperationalReviewDraftChangedFromCurrent,
  isOperationalReviewTypingTarget,
  operationalReviewAssetUrl,
  operationalReviewDraftSymbols,
  operationalReviewJobLabel,
  operationalReviewKeyboardAction,
  operationalReviewNativeContextViewport,
  operationalReviewSequence,
  operationalReviewStatusLabel,
  updateOperationalReviewCounts,
} from '@/features/operational-reviews/operational-review-state';

type LoadState = 'error' | 'loading' | 'ready';

interface OperationalReviewWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: OperationalReviewsClient;
  readonly gameId: string;
  readonly importJobId: string;
}

interface PageNavigation {
  readonly afterCursor?: string;
  readonly beforeCursor?: string;
  readonly resumeAtFirstPending?: boolean;
  readonly sequenceNumber?: number;
}

const REVIEW_QUEUE_VIEW = 'all' as const;
const REVIEWER_RESTRICTED = true;

const EMPTY_COUNTS: OperationalImageReviewCountsResponse = {
  accepted: 0,
  completed: 0,
  corrected: 0,
  pending: 0,
  rejected: 0,
  total: 0,
};

export function OperationalReviewWorkspace({
  apiBaseUrl,
  client,
  gameId,
  importJobId,
}: OperationalReviewWorkspaceProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [selectedGameId, setSelectedGameId] = useState(gameId);
  const [gamesState, setGamesState] = useState<LoadState>('loading');
  const [gamesError, setGamesError] = useState('');
  const [jobs, setJobs] = useState<readonly JobResponse[]>([]);
  const [selectedJobId, setSelectedJobId] = useState(importJobId);
  const [jobsState, setJobsState] = useState<LoadState>('ready');
  const [jobsError, setJobsError] = useState('');
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [symbolsState, setSymbolsState] = useState<LoadState>('ready');
  const [symbolsError, setSymbolsError] = useState('');
  const [page, setPage] = useState<OperationalImageReviewPageResponse | null>(
    null,
  );
  const [pageState, setPageState] = useState<LoadState>('ready');
  const [pageError, setPageError] = useState('');
  const [cursorConflict, setCursorConflict] = useState(false);
  const [jumpValue, setJumpValue] = useState('');
  const [pageNotice, setPageNotice] = useState('');
  const [cohortExports, setCohortExports] = useState<
    readonly VerifiedCohortExportResponse[]
  >([]);
  const [cohortState, setCohortState] = useState<LoadState>('ready');
  const [cohortError, setCohortError] = useState('');
  const [freezeDialogOpen, setFreezeDialogOpen] = useState(false);
  const [freezingCohort, setFreezingCohort] = useState(false);
  const mounted = useRef(true);
  const gamesRequestId = useRef(0);
  const jobsRequestId = useRef(0);
  const symbolsRequestId = useRef(0);
  const pageRequestId = useRef(0);
  const cohortRequestId = useRef(0);

  const refreshGames = useCallback(async () => {
    const requestId = ++gamesRequestId.current;
    setGamesState('loading');
    setGamesError('');
    const result = await loadOperationalReviewGames(api);
    if (!mounted.current || requestId !== gamesRequestId.current) return;
    if (!result.ok) {
      setGamesState('error');
      setGamesError(result.error);
      return;
    }
    setGames(result.games.filter((game) => game.id === gameId));
    setSelectedGameId(gameId);
    setGamesState('ready');
  }, [api, gameId]);

  const refreshJobs = useCallback(async () => {
    if (selectedGameId === '') {
      setJobs([]);
      setSelectedJobId('');
      setJobsState('ready');
      return;
    }
    const requestId = ++jobsRequestId.current;
    setJobsState('loading');
    setJobsError('');
    const result = await loadOperationalReviewJobs(api, selectedGameId);
    if (!mounted.current || requestId !== jobsRequestId.current) return;
    if (!result.ok) {
      setJobsState('error');
      setJobsError(result.error);
      return;
    }
    setJobs(result.jobs.filter((job) => job.id === importJobId));
    setSelectedJobId(importJobId);
    setJobsState('ready');
  }, [api, importJobId, selectedGameId]);

  const refreshSymbols = useCallback(async () => {
    if (selectedGameId === '') {
      setSymbols([]);
      setSymbolsState('ready');
      return;
    }
    const requestId = ++symbolsRequestId.current;
    setSymbolsState('loading');
    setSymbolsError('');
    const result = await loadOperationalReviewSymbols(api, selectedGameId);
    if (!mounted.current || requestId !== symbolsRequestId.current) return;
    if (!result.ok) {
      setSymbolsState('error');
      setSymbolsError(result.error);
      return;
    }
    setSymbols(result.symbols);
    setSymbolsState('ready');
  }, [api, selectedGameId]);

  const refreshPage = useCallback(
    async (navigation: PageNavigation = {}) => {
      if (selectedGameId === '' || selectedJobId === '') {
        setPage(null);
        setPageState('ready');
        return;
      }
      const requestId = ++pageRequestId.current;
      setPageState('loading');
      setPageError('');
      setCursorConflict(false);
      const options: LoadOperationalReviewPageOptions = {
        gameId: selectedGameId,
        importJobId: selectedJobId,
        view: REVIEW_QUEUE_VIEW,
        ...navigation,
      };
      const result = await loadOperationalReviewPage(api, options);
      if (!mounted.current || requestId !== pageRequestId.current) return;
      if (!result.ok) {
        setPageState('error');
        setPageError(result.error);
        setCursorConflict(result.isCursorConflict);
        return;
      }
      setPage(result.page);
      setPageState('ready');
    },
    [api, selectedGameId, selectedJobId],
  );

  const refreshCohorts = useCallback(async () => {
    if (REVIEWER_RESTRICTED) {
      setCohortExports([]);
      setCohortState('ready');
      setCohortError('');
      return;
    }
    if (selectedGameId === '' || selectedJobId === '') {
      setCohortExports([]);
      setCohortState('ready');
      return;
    }
    const requestId = ++cohortRequestId.current;
    setCohortState('loading');
    setCohortError('');
    const result = await loadVerifiedCohortHistory(
      api,
      selectedGameId,
      selectedJobId,
    );
    if (!mounted.current || requestId !== cohortRequestId.current) return;
    if (!result.ok) {
      setCohortState('error');
      setCohortError(result.error);
      return;
    }
    setCohortExports(result.exports);
    setCohortState('ready');
  }, [api, selectedGameId, selectedJobId]);

  useEffect(() => {
    mounted.current = true;
    queueMicrotask(() => void refreshGames());
    return () => {
      mounted.current = false;
    };
  }, [refreshGames]);

  useEffect(() => {
    queueMicrotask(() => void refreshJobs());
  }, [refreshJobs]);

  useEffect(() => {
    queueMicrotask(() => void refreshSymbols());
  }, [refreshSymbols]);

  useEffect(() => {
    queueMicrotask(() => void refreshPage({ resumeAtFirstPending: true }));
  }, [refreshPage]);

  useEffect(() => {
    queueMicrotask(() => void refreshCohorts());
  }, [refreshCohorts]);

  const selectedGame =
    games.find((candidate) => candidate.id === selectedGameId) ?? null;
  const selectedJob =
    jobs.find((candidate) => candidate.id === selectedJobId) ?? null;
  const item = page?.items[0] ?? null;
  const counts = page?.counts ?? EMPTY_COUNTS;

  function jumpToSequence() {
    const sequenceNumber = Number(jumpValue);
    if (Number.isInteger(sequenceNumber) && sequenceNumber > 0) {
      void refreshPage({ sequenceNumber });
    }
  }

  function handleResolved(
    resolution: OperationalImageReviewResolutionResponse,
  ) {
    setPageNotice(
      resolution.created
        ? `Układ #${resolution.item.sequenceNumber ?? '—'} zapisano jako ${operationalReviewStatusLabel(resolution.item.status).toLocaleLowerCase('pl-PL')}.`
        : 'Ten sam zapis był już przyjęty — nie utworzono drugiej rewizji.',
    );
    if (page?.nextCursor !== null && page?.nextCursor !== undefined) {
      void refreshPage({ afterCursor: page.nextCursor });
      return;
    }
    setPage((current) => {
      if (current === null) return current;
      const previousStatus = current.items[0]?.status;
      return {
        ...current,
        counts: updateOperationalReviewCounts(
          current.counts,
          previousStatus,
          resolution.item.status,
        ),
        items: [resolution.item],
      };
    });
  }

  function handleGeometrySaved(updated: OperationalImageReviewItemResponse) {
    setPageNotice(
      `Zapisano siatkę jako rewizję ${updated.geometryRevision}. Plansza i cropy zostały odświeżone.`,
    );
    setPage((current) => {
      if (current === null) return current;
      const previousStatus = current.items[0]?.status;
      return {
        ...current,
        counts: updateOperationalReviewCounts(
          current.counts,
          previousStatus,
          updated.status,
        ),
        items: [updated],
      };
    });
  }

  async function handleFreezeCohort() {
    if (selectedGameId === '' || selectedJobId === '' || freezingCohort) {
      return;
    }
    setFreezingCohort(true);
    setCohortError('');
    const result = await freezeVerifiedCohort(
      api,
      selectedGameId,
      selectedJobId,
    );
    if (!mounted.current) return;
    setFreezingCohort(false);
    if (!result.ok) {
      setCohortError(result.error);
      setCohortState('error');
      return;
    }
    setFreezeDialogOpen(false);
    setPageNotice(
      result.freeze.created
        ? `Zamrożono kohortę v${result.freeze.export.version}: ${result.freeze.export.boardCount} plansz i ${result.freeze.export.sampleCount} próbek.`
        : `Kohorta v${result.freeze.export.version} już reprezentuje ten sam stan — nie utworzono duplikatu.`,
    );
    await refreshCohorts();
  }

  return (
    <section
      className="catalogSection operationalReviewSection"
      id="operational-reviews"
    >
      <header className="pageHeader operationalReviewPageHeader">
        <div>
          <p className="eyebrow">M6.5 · supervised verification</p>
          <h1>Weryfikacja plansz</h1>
          <p className="lead">
            Jedna plansza, pełny kontekst i szybki dostęp do kolejnego układu.
          </p>
        </div>
        <button
          className="secondaryButton"
          disabled={gamesState === 'loading' || jobsState === 'loading'}
          onClick={() => void refreshGames()}
          type="button"
        >
          Odśwież kontekst
        </button>
      </header>

      {gamesState === 'loading' ? (
        <OperationalReviewState
          text="Pobieram grę przypisaną do tej sesji."
          title="Wczytywanie gier"
        />
      ) : gamesState === 'error' ? (
        <OperationalReviewState
          action={() => void refreshGames()}
          error
          text={gamesError}
          title="Nie udało się pobrać gier"
        />
      ) : games.length === 0 ? (
        <OperationalReviewState
          text="Sesja nie wskazuje dostępnej gry. Sprawdź, czy gra nie została zarchiwizowana, albo utwórz nowy link."
          title="Brak dostępnej gry"
        />
      ) : (
        <>
          <OperationalReviewContextBar
            gameId={selectedGameId}
            games={games}
            jobId={selectedJobId}
            jobs={jobs}
            selectedJob={selectedJob}
          />
          {!REVIEWER_RESTRICTED && selectedJobId !== '' ? (
            <OperationalReviewCohortPanel
              counts={counts}
              error={cohortError}
              exports={cohortExports}
              loading={cohortState === 'loading'}
              onFreeze={() => setFreezeDialogOpen(true)}
              onReload={() => void refreshCohorts()}
            />
          ) : null}
          {jobsState === 'error' ? (
            <OperationalReviewState
              action={() => void refreshJobs()}
              error
              text={jobsError}
              title="Nie udało się pobrać importów zdjęć"
            />
          ) : jobsState === 'loading' ? (
            <OperationalReviewState
              text="Szukam importów zdjęć dla wybranej gry."
              title="Wczytywanie importów"
            />
          ) : jobs.length === 0 ? (
            <OperationalReviewState
              text="Wybrana gra nie ma jeszcze importu typu image_directory."
              title="Brak importów zdjęć"
            />
          ) : symbolsState === 'loading' ? (
            <OperationalReviewState
              text="Pobieram aktywny katalog i mapowanie skrótów."
              title="Wczytywanie symboli"
            />
          ) : symbolsState === 'error' ? (
            <OperationalReviewState
              action={() => void refreshSymbols()}
              error
              text={symbolsError}
              title="Nie udało się pobrać symboli"
            />
          ) : symbols.length === 0 ? (
            <OperationalReviewState
              error
              text="Wybrana gra nie ma aktywnych symboli. Zapis planszy jest zablokowany."
              title="Brak aktywnego katalogu symboli"
            />
          ) : pageState === 'loading' ? (
            <OperationalReviewState
              text="Pobieram jedną planszę i jej 15 komórek."
              title="Wczytywanie planszy"
            />
          ) : pageState === 'error' ? (
            <OperationalReviewState
              action={() => void refreshPage()}
              error
              text={
                cursorConflict
                  ? `${pageError} Kolejka zmieniła się — rozpocznij od aktualnej pozycji.`
                  : pageError
              }
              title={
                cursorConflict
                  ? 'Pozycja kolejki jest nieaktualna'
                  : 'Nie udało się pobrać planszy'
              }
            />
          ) : item === null ? (
            <OperationalReviewEmpty
              counts={counts}
              onReset={() => void refreshPage({ resumeAtFirstPending: true })}
            />
          ) : (
            <>
              {pageNotice ? (
                <p className="operationalReviewNotice" role="status">
                  {pageNotice}
                </p>
              ) : null}
              <OperationalReviewBoard
                api={api}
                apiBaseUrl={apiBaseUrl}
                counts={counts}
                game={selectedGame}
                importJobId={selectedJobId}
                item={item}
                jumpValue={jumpValue}
                key={`${item.id}:${item.geometryRevision}:${item.resolutionRevision}`}
                onJumpChange={setJumpValue}
                onJumpSubmit={jumpToSequence}
                onNext={() =>
                  void refreshPage({
                    afterCursor: page?.nextCursor ?? undefined,
                  })
                }
                onPrevious={() =>
                  void refreshPage({
                    beforeCursor: page?.previousCursor ?? undefined,
                  })
                }
                onGeometrySaved={handleGeometrySaved}
                onReload={() => {
                  const sequenceNumber = operationalReviewSequence(item);
                  void refreshPage(
                    sequenceNumber === null ? {} : { sequenceNumber },
                  );
                }}
                onResolved={handleResolved}
                symbols={symbols}
                hasNext={page?.nextCursor !== null}
                hasPrevious={page?.previousCursor !== null}
              />
            </>
          )}
        </>
      )}
      {!REVIEWER_RESTRICTED && freezeDialogOpen ? (
        <div
          aria-labelledby="operational-review-freeze-title"
          aria-modal="true"
          className="operationalReviewDialogBackdrop"
          role="dialog"
        >
          <div className="operationalReviewConfirmDialog">
            <p className="eyebrow">Niezmienny eksport</p>
            <h2 id="operational-review-freeze-title">
              Zamrozić bieżącą kohortę?
            </h2>
            <p>
              Eksport obejmie {counts.completed} kompletnych plansz i{' '}
              {counts.completed * 15} etykiet. Nie uruchomi treningu ani
              publikacji i nie zmieni decyzji człowieka.
            </p>
            <div className="buttonRow">
              <button
                className="secondaryButton"
                disabled={freezingCohort}
                onClick={() => setFreezeDialogOpen(false)}
                type="button"
              >
                Anuluj
              </button>
              <button
                className="primaryButton"
                disabled={freezingCohort || counts.completed === 0}
                onClick={() => void handleFreezeCohort()}
                type="button"
              >
                {freezingCohort ? 'Zamrażanie…' : 'Zamroź kohortę'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function OperationalReviewCohortPanel({
  counts,
  error,
  exports,
  loading,
  onFreeze,
  onReload,
}: {
  readonly counts: OperationalImageReviewCountsResponse;
  readonly error: string;
  readonly exports: readonly VerifiedCohortExportResponse[];
  readonly loading: boolean;
  readonly onFreeze: () => void;
  readonly onReload: () => void;
}) {
  const latest = exports[0] ?? null;
  return (
    <aside
      aria-label="Zweryfikowana kohorta"
      className="operationalReviewCohortPanel"
    >
      <div>
        <strong>{counts.completed} zweryfikowanych plansz</strong>
        <span>
          {counts.pending} oczekujących · {counts.rejected} odrzuconych
        </span>
      </div>
      <div className="operationalReviewCohortLatest">
        {loading ? (
          <span>Wczytywanie historii…</span>
        ) : error ? (
          <button className="linkButton" onClick={onReload} type="button">
            {error} Spróbuj ponownie
          </button>
        ) : latest ? (
          <span title={latest.payloadSha256}>
            Ostatnia: v{latest.version}, {latest.boardCount} plansz ·{' '}
            {new Intl.DateTimeFormat('pl-PL', {
              dateStyle: 'short',
              timeStyle: 'short',
            }).format(new Date(latest.createdAt))}
          </span>
        ) : (
          <span>Brak zamrożonej wersji</span>
        )}
      </div>
      <button
        className="secondaryButton"
        disabled={counts.completed === 0 || loading}
        onClick={onFreeze}
        type="button"
      >
        Zamroź kohortę
      </button>
    </aside>
  );
}

function OperationalReviewContextBar({
  gameId,
  games,
  jobId,
  jobs,
  selectedJob,
}: {
  readonly gameId: string;
  readonly games: readonly GameResponse[];
  readonly jobId: string;
  readonly jobs: readonly JobResponse[];
  readonly selectedJob: JobResponse | null;
}) {
  return (
    <div className="operationalReviewContext" aria-label="Kontekst weryfikacji">
      <label>
        Gra
        <select disabled value={gameId}>
          {games.map((game) => (
            <option key={game.id} value={game.id}>
              {game.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Import zdjęć
        <select disabled value={jobId}>
          {jobs.length === 0 ? (
            <option value="">Brak importów</option>
          ) : (
            jobs.map((job) => (
              <option key={job.id} value={job.id}>
                {operationalReviewJobLabel(job)}
              </option>
            ))
          )}
        </select>
      </label>
      <div className="operationalReviewContextStatus">
        <span>Stan importu</span>
        <strong>{selectedJob?.status ?? '—'}</strong>
        <small>
          {selectedJob
            ? `${selectedJob.progress.current} / ${selectedJob.progress.total ?? '?'}`
            : 'Wybierz import'}
        </small>
      </div>
    </div>
  );
}

function OperationalReviewBoard({
  api,
  apiBaseUrl,
  counts,
  game,
  hasNext,
  hasPrevious,
  importJobId,
  item,
  jumpValue,
  onJumpChange,
  onJumpSubmit,
  onNext,
  onPrevious,
  onGeometrySaved,
  onReload,
  onResolved,
  symbols,
}: {
  readonly api: OperationalReviewsClient;
  readonly apiBaseUrl: string;
  readonly counts: OperationalImageReviewCountsResponse;
  readonly game: GameResponse | null;
  readonly hasNext: boolean;
  readonly hasPrevious: boolean;
  readonly importJobId: string;
  readonly item: OperationalImageReviewItemResponse;
  readonly jumpValue: string;
  readonly onJumpChange: (value: string) => void;
  readonly onJumpSubmit: () => void;
  readonly onNext: () => void;
  readonly onPrevious: () => void;
  readonly onGeometrySaved: (item: OperationalImageReviewItemResponse) => void;
  readonly onReload: () => void;
  readonly onResolved: (
    resolution: OperationalImageReviewResolutionResponse,
  ) => void;
  readonly symbols: readonly SymbolResponse[];
}) {
  const context = { gameId: item.gameId, importJobId };
  const [selectedCellIndex, setSelectedCellIndex] = useState(0);
  const [draftSymbols, setDraftSymbols] = useState<readonly string[]>(() =>
    operationalReviewDraftSymbols(item),
  );
  const [sequenceDraft, setSequenceDraft] = useState(() =>
    String(operationalReviewSequence(item) ?? ''),
  );
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [revisionConflict, setRevisionConflict] = useState(false);
  const savingRef = useRef(false);
  const shortcuts = useMemo(
    () => buildOperationalReviewSymbolShortcuts(symbols),
    [symbols],
  );
  const symbolByCode = useMemo(
    () => new Map(symbols.map((symbol) => [symbol.code, symbol])),
    [symbols],
  );
  const selectedCell = item.cells[selectedCellIndex];
  const displaySequence = operationalReviewSequence(item);
  const sequenceNumber = Number(sequenceDraft);
  const sequenceIsValid =
    Number.isInteger(sequenceNumber) && sequenceNumber > 0;
  const allSymbolsAreActive =
    draftSymbols.length === 15 &&
    draftSymbols.every((symbolCode) => symbolByCode.has(symbolCode));
  const changedFromCurrent =
    sequenceIsValid &&
    isOperationalReviewDraftChangedFromCurrent(
      item,
      sequenceNumber,
      draftSymbols,
    );
  const draftMatchesCurrent =
    sequenceDraft.trim() === String(displaySequence ?? '') &&
    draftSymbols.length === item.cells.length &&
    item.cells.every(
      (cell, index) => cell.currentSymbolCode === draftSymbols[index],
    );
  const canResolve =
    sequenceIsValid &&
    allSymbolsAreActive &&
    (item.status === 'pending' || changedFromCurrent);
  const canAdvance =
    item.status !== 'pending' && draftMatchesCurrent && hasNext;
  const canUsePrimaryAction = (canResolve || canAdvance) && !isSaving;
  const selectedSuggestions = useMemo(() => {
    if (selectedCell === undefined) return [];
    const candidates = [
      {
        confidence: selectedCell.confidence,
        symbolCode: selectedCell.predictedSymbolCode,
      },
      ...selectedCell.alternatives,
    ];
    const seen = new Set<string>();
    return candidates
      .filter((candidate) => {
        if (
          seen.has(candidate.symbolCode) ||
          !symbolByCode.has(candidate.symbolCode)
        ) {
          return false;
        }
        seen.add(candidate.symbolCode);
        return true;
      })
      .slice(0, 4);
  }, [selectedCell, symbolByCode]);

  const changeSelectedSymbol = useCallback(
    (symbolCode: string) => {
      if (isSaving || !symbolByCode.has(symbolCode)) return;
      setDraftSymbols((current) =>
        current.map((value, index) =>
          index === selectedCellIndex ? symbolCode : value,
        ),
      );
      setSaveError('');
      setRevisionConflict(false);
    },
    [isSaving, selectedCellIndex, symbolByCode],
  );

  const submitResolution = useCallback(async () => {
    if (savingRef.current) return;
    if (canAdvance) {
      setSaveError('');
      setRevisionConflict(false);
      onNext();
      return;
    }
    if (!canResolve) {
      setSaveError(
        !sequenceIsValid
          ? 'Podaj dodatni, całkowity numer układu.'
          : !allSymbolsAreActive
            ? 'Każda komórka musi wskazywać aktywny symbol wybranej gry.'
            : 'Zmień numer lub symbol, zanim zapiszesz kolejną rewizję kompletnej planszy.',
      );
      return;
    }
    savingRef.current = true;
    setIsSaving(true);
    setSaveError('');
    setRevisionConflict(false);
    const command = buildOperationalReviewResolutionCommand(
      item,
      sequenceNumber,
      draftSymbols,
      globalThis.crypto.randomUUID(),
    );
    const result = await resolveOperationalReview(api, {
      command,
      gameId: item.gameId,
      importJobId,
      reviewItemId: item.id,
    });
    savingRef.current = false;
    setIsSaving(false);
    if (!result.ok) {
      setSaveError(result.error);
      setRevisionConflict(result.isRevisionConflict);
      return;
    }
    onResolved(result.resolution);
  }, [
    api,
    allSymbolsAreActive,
    canAdvance,
    canResolve,
    draftSymbols,
    importJobId,
    item,
    onNext,
    onResolved,
    sequenceIsValid,
    sequenceNumber,
    setIsSaving,
    setRevisionConflict,
    setSaveError,
  ]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const openDialog =
        document.querySelector<HTMLDialogElement>('dialog[open]');
      const action = operationalReviewKeyboardAction({
        hasPrevious,
        key: event.key,
        otherDialogOpen: openDialog !== null,
        repeat: event.repeat,
        saving: isSaving,
        shortcuts,
        typingTarget: isOperationalReviewTypingTarget(event.target),
      });
      if (action.type === 'none') return;
      event.preventDefault();
      if (action.type === 'submit') {
        void submitResolution();
      } else if (action.type === 'previous') {
        onPrevious();
      } else {
        changeSelectedSymbol(action.symbolCode);
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    changeSelectedSymbol,
    hasNext,
    hasPrevious,
    isSaving,
    onPrevious,
    shortcuts,
    submitResolution,
  ]);

  if (selectedCell === undefined) {
    return (
      <OperationalReviewState
        error
        text="Kontrakt planszy nie zawiera wymaganej komórki row-major."
        title="Niekompletna plansza"
      />
    );
  }

  return (
    <>
      <article className="operationalReviewStage">
        <header className="operationalReviewToolbar">
          <div className="operationalReviewIdentity">
            <p>
              {game?.name ?? 'Gra'} · źródło {item.sourceOrderIndex + 1} ·
              plansza {item.positionIndex + 1}
            </p>
            <h2>
              Układ{' '}
              {displaySequence === null ? 'bez numeru' : `#${displaySequence}`}
            </h2>
            <span>
              {operationalReviewStatusLabel(item.status)} · rewizja{' '}
              {item.resolutionRevision}
            </span>
          </div>
          <div className="operationalReviewViewTabs" aria-label="Widok kolejki">
            <span>Wszystkie plansze</span>
          </div>
          <div className="operationalReviewNavigation">
            <OperationalReviewGeometryEditor
              api={api}
              apiBaseUrl={apiBaseUrl}
              importJobId={importJobId}
              item={item}
              onSaved={onGeometrySaved}
            />
            <button
              aria-label="Poprzednia plansza"
              className="operationalReviewArrow"
              disabled={!hasPrevious}
              onClick={onPrevious}
              type="button"
            >
              ←
            </button>
            <button
              aria-label="Zatwierdź lub przejdź do następnej planszy"
              className="operationalReviewArrow"
              disabled={!canUsePrimaryAction}
              onClick={() => void submitResolution()}
              type="button"
            >
              →
            </button>
            <button
              className="primaryButton operationalReviewApprove"
              disabled={!canUsePrimaryAction}
              onClick={() => void submitResolution()}
              type="button"
            >
              {item.status === 'pending'
                ? 'Zatwierdź'
                : canAdvance
                  ? 'Dalej'
                  : 'Zapisz zmianę'}
            </button>
          </div>
        </header>

        <div className="operationalReviewSummary">
          <dl>
            <div>
              <dt>Do weryfikacji</dt>
              <dd>{counts.pending}</dd>
            </div>
            <div>
              <dt>Kompletne</dt>
              <dd>{counts.completed}</dd>
            </div>
            <div>
              <dt>Poprawione</dt>
              <dd>{counts.corrected}</dd>
            </div>
            <div>
              <dt>Odrzucone</dt>
              <dd>{counts.rejected}</dd>
            </div>
          </dl>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              onJumpSubmit();
            }}
          >
            <label htmlFor="operational-review-sequence">
              Przejdź do układu
            </label>
            <input
              id="operational-review-sequence"
              min="1"
              onChange={(event) => onJumpChange(event.target.value)}
              placeholder="np. 316"
              type="number"
              value={jumpValue}
            />
            <button
              className="textButton"
              disabled={!/^[1-9]\d*$/.test(jumpValue)}
              type="submit"
            >
              Pokaż
            </button>
          </form>
        </div>

        <div className="operationalReviewSelection" role="status">
          <span>Wybrana komórka {selectedCell.cellIndex + 1}</span>
          <strong>
            {symbolByCode.get(draftSymbols[selectedCellIndex] ?? '')?.name ??
              draftSymbols[selectedCellIndex]}
          </strong>
          <small>
            Pewność sugestii{' '}
            {formatOperationalConfidence(selectedCell.confidence)}
          </small>
          <label>
            Numer układu
            <input
              aria-invalid={!sequenceIsValid}
              disabled={isSaving}
              min="1"
              onChange={(event) => {
                setSequenceDraft(event.target.value);
                setSaveError('');
              }}
              type="number"
              value={sequenceDraft}
            />
          </label>
          {item.status !== 'pending' ? (
            <em>Edycja dozwolona — kolejny zapis utworzy nową rewizję.</em>
          ) : null}
        </div>

        <div
          aria-label={`Sugestie dla komórki ${selectedCell.cellIndex + 1}`}
          className="operationalReviewSuggestions"
        >
          <span>Najbardziej prawdopodobne</span>
          {selectedSuggestions.length === 0 ? (
            <small>Brak aktywnych sugestii dla tej komórki.</small>
          ) : (
            selectedSuggestions.map((suggestion) => {
              const symbol = symbolByCode.get(suggestion.symbolCode);
              return (
                <button
                  aria-label={`Ustaw ${symbol?.name ?? suggestion.symbolCode} w komórce ${selectedCell.cellIndex + 1}`}
                  aria-pressed={
                    draftSymbols[selectedCellIndex] === suggestion.symbolCode
                  }
                  disabled={isSaving}
                  key={suggestion.symbolCode}
                  onClick={() => changeSelectedSymbol(suggestion.symbolCode)}
                  type="button"
                >
                  <strong>{symbol?.name ?? suggestion.symbolCode}</strong>
                  <small>
                    {formatOperationalConfidence(suggestion.confidence)}
                  </small>
                </button>
              );
            })
          )}
        </div>

        {saveError ? (
          <div
            className={
              revisionConflict
                ? 'operationalReviewSaveError operationalReviewSaveConflict'
                : 'operationalReviewSaveError'
            }
            role="alert"
          >
            <p>{saveError}</p>
            {revisionConflict ? (
              <button className="textButton" onClick={onReload} type="button">
                Wczytaj aktualną rewizję
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="operationalReviewVisualComparison">
          <div className="operationalReviewSymbolsPanel">
            <section
              aria-label="Plansza pięć kolumn na trzy wiersze"
              className="operationalReviewGrid"
            >
              {item.cells.map((cell, index) => {
                const draftSymbolCode =
                  draftSymbols[index] ?? cell.currentSymbolCode;
                const changed = draftSymbolCode !== cell.currentSymbolCode;
                const selected = cell.cellIndex === selectedCellIndex;
                return (
                  <button
                    aria-label={`Wybierz komórkę ${cell.cellIndex + 1}, ${symbolByCode.get(draftSymbolCode)?.name ?? draftSymbolCode}`}
                    aria-current={selected ? 'true' : undefined}
                    className={[
                      'operationalReviewCell',
                      selected ? 'operationalReviewCellSelected' : '',
                      changed ? 'operationalReviewCellChanged' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    disabled={isSaving}
                    key={cell.cropSampleId}
                    onClick={() => setSelectedCellIndex(index)}
                    type="button"
                  >
                    <OperationalReviewImage
                      alt={`Komórka ${cell.cellIndex + 1}: ${draftSymbolCode}`}
                      src={operationalReviewAssetUrl(
                        apiBaseUrl,
                        context,
                        item.id,
                        'cell',
                        {
                          cellIndex: cell.cellIndex,
                          version: cell.cropChecksumSha256,
                        },
                      )}
                    />
                    <div>
                      <strong>
                        {symbolByCode.get(draftSymbolCode)?.name ??
                          draftSymbolCode}
                      </strong>
                      <small>
                        {formatOperationalConfidence(cell.confidence)}
                      </small>
                    </div>
                    <span>
                      R{cell.rowIndex + 1} · K{cell.columnIndex + 1}
                      {changed ? ' · zmieniono' : ''}
                    </span>
                  </button>
                );
              })}
            </section>

            <div
              aria-label="Legenda skrótów symboli"
              className="operationalReviewLegend"
            >
              <span>Skróty</span>
              {shortcuts.map(({ key, symbol }) => (
                <div key={symbol.id}>
                  {key === null ? <kbd>—</kbd> : <kbd>{key.toUpperCase()}</kbd>}
                  <span>{symbol.name}</span>
                </div>
              ))}
            </div>
          </div>

          <section className="operationalReviewBoardReference">
            {item.geometry.displayAssetKind === 'source_context' ? (
              <OperationalReviewImage
                alt={`Natywny wycinek planszy i numer układu ${displaySequence ?? 'bez numeru'}`}
                key={`${item.id}:${item.boardChecksumSha256}`}
                src={operationalReviewAssetUrl(
                  apiBaseUrl,
                  context,
                  item.id,
                  'board',
                  { version: item.boardChecksumSha256 },
                )}
              />
            ) : (
              <OperationalReviewNativeContext
                alt={`Oryginalna plansza i numer układu ${displaySequence ?? 'bez numeru'}`}
                item={item}
                key={item.id}
                src={operationalReviewAssetUrl(
                  apiBaseUrl,
                  context,
                  item.id,
                  'source',
                  { version: item.sourceChecksumSha256 },
                )}
              />
            )}
          </section>
        </div>
      </article>

      <p className="operationalReviewShortcutNote">
        Kliknij komórkę, użyj przypisanego klawisza do korekty, a następnie
        naciśnij Enter, aby od razu zapisać całą planszę.
      </p>
    </>
  );
}

function OperationalReviewImage({
  alt,
  src,
}: {
  readonly alt: string;
  readonly src: string;
}) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <div
        className="operationalReviewImageMissing"
        role="img"
        aria-label={alt}
      >
        <span aria-hidden="true">!</span>
        <p>Brak lokalnego obrazu. Metadane planszy pozostają dostępne.</p>
      </div>
    );
  }
  // Local checksum-bound review assets cannot use Next's remote image optimizer.
  // eslint-disable-next-line @next/next/no-img-element
  return <img alt={alt} onError={() => setFailed(true)} src={src} />;
}

function OperationalReviewNativeContext({
  alt,
  item,
  src,
}: {
  readonly alt: string;
  readonly item: OperationalImageReviewItemResponse;
  readonly src: string;
}) {
  const [failed, setFailed] = useState(false);
  const [naturalSize, setNaturalSize] = useState<{
    readonly height: number;
    readonly width: number;
  } | null>(null);
  if (failed) {
    return (
      <div
        className="operationalReviewImageMissing"
        role="img"
        aria-label={alt}
      >
        <span aria-hidden="true">!</span>
        <p>Brak oryginalnego obrazu. Metadane planszy pozostają dostępne.</p>
      </div>
    );
  }
  const viewport =
    naturalSize === null
      ? null
      : operationalReviewNativeContextViewport(
          item,
          naturalSize.width,
          naturalSize.height,
        );
  return (
    <div
      className="operationalReviewNativeContext"
      style={
        viewport === null
          ? undefined
          : { aspectRatio: `${viewport.width} / ${viewport.height}` }
      }
    >
      {/* Checksum-bound local assets intentionally bypass Next image optimization. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        alt={alt}
        onError={() => setFailed(true)}
        onLoad={(event) =>
          setNaturalSize({
            height: event.currentTarget.naturalHeight,
            width: event.currentTarget.naturalWidth,
          })
        }
        src={src}
        style={
          viewport === null || naturalSize === null
            ? undefined
            : {
                maxWidth: 'none',
                transform: `translate(-${(viewport.x / naturalSize.width) * 100}%, -${(viewport.y / naturalSize.height) * 100}%)`,
                transformOrigin: 'top left',
                width: `${(naturalSize.width / viewport.width) * 100}%`,
              }
        }
      />
    </div>
  );
}

function OperationalReviewEmpty({
  counts,
  onReset,
}: {
  readonly counts: OperationalImageReviewCountsResponse;
  readonly onReset: () => void;
}) {
  return (
    <div className="operationalReviewEmpty">
      <p className="eyebrow">Kolejka jest pusta</p>
      <h2>
        {counts.total > 0
          ? 'Nie znaleziono układu o podanym numerze'
          : 'Brak plansz do wyświetlenia'}
      </h2>
      <p>
        {counts.total > 0
          ? `Kolejka zawiera ${counts.total} układów. Wróć do pierwszej planszy oczekującej na zatwierdzenie.`
          : `Do weryfikacji: ${counts.pending}. Kompletne: ${counts.completed}. Odrzucone: ${counts.rejected}.`}
      </p>
      <button className="secondaryButton" onClick={onReset} type="button">
        Wróć do pierwszej niezatwierdzonej
      </button>
    </div>
  );
}

function OperationalReviewState({
  action,
  error = false,
  text,
  title,
}: {
  readonly action?: () => void;
  readonly error?: boolean;
  readonly text: string;
  readonly title: string;
}) {
  return (
    <div
      className={
        error
          ? 'operationalReviewState operationalReviewStateError'
          : 'operationalReviewState'
      }
      role={error ? 'alert' : 'status'}
    >
      <span aria-hidden="true">{error ? '!' : '…'}</span>
      <div>
        <h2>{title}</h2>
        <p>{text}</p>
      </div>
      {action ? (
        <button className="secondaryButton" onClick={action} type="button">
          Spróbuj ponownie
        </button>
      ) : null}
    </div>
  );
}

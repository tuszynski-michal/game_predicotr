'use client';

import type {
  GameResponse,
  JobResponse,
  LayoutImportIntegrityReportResponse,
  LayoutImportNormalizedRowPageResponse,
  LayoutImportNormalizedRowResponse,
  LayoutImportRowStatus,
  RulesVersionResponse,
  SymbolResponse,
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
import { formatJobTimestamp } from '@/features/jobs/job-state';

import {
  type ManualImportsClient,
  createLayoutImportJob,
  createLayoutImportValidation,
  loadLayoutImportReport,
  loadLayoutImportRows,
  publishLayoutImportDataset,
  rejectLayoutImportStaging,
} from './manual-import-actions';
import {
  canConfirmStagingRejection,
  completedLayoutFileImports,
  completedLayoutImportValidations,
  firstPreviewableRow,
  formatBoundedSample,
  layoutImportCheckLabel,
  layoutImportCheckStatusLabel,
  layoutImportSourcePath,
  layoutImportValidationIds,
  publishedRulesForGame,
  rowMajorCellLabel,
  validateImportSourcePath,
} from './manual-import-state';

const ROW_PAGE_SIZE = 25;
type LoadState = 'loading' | 'ready' | 'error';

interface ManualImportPanelProps {
  readonly apiBaseUrl: string;
  readonly client?: ManualImportsClient;
  readonly gameId?: string;
}

export function ManualImportPanel({
  apiBaseUrl,
  client,
  gameId,
}: ManualImportPanelProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [jobs, setJobs] = useState<readonly JobResponse[]>([]);
  const [rulesVersions, setRulesVersions] = useState<
    readonly RulesVersionResponse[]
  >([]);
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [uncontrolledGameId, setSelectedGameId] = useState<string | null>(null);
  const selectedGameId = gameId ?? uncontrolledGameId;
  const [sourcePath, setSourcePath] = useState('');
  const [selectedImportJobId, setSelectedImportJobId] = useState('');
  const [selectedRulesVersionId, setSelectedRulesVersionId] = useState('');
  const [selectedValidationJobId, setSelectedValidationJobId] = useState('');
  const [report, setReport] =
    useState<LayoutImportIntegrityReportResponse | null>(null);
  const [page, setPage] =
    useState<LayoutImportNormalizedRowPageResponse | null>(null);
  const [selectedRow, setSelectedRow] =
    useState<LayoutImportNormalizedRowResponse | null>(null);
  const [rowStatus, setRowStatus] = useState<LayoutImportRowStatus>('all');
  const [errorCode, setErrorCode] = useState('');
  const [afterLineNumber, setAfterLineNumber] = useState(0);
  const [cursorHistory, setCursorHistory] = useState<readonly number[]>([]);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [reportLoading, setReportLoading] = useState(false);
  const [rowsLoading, setRowsLoading] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [rejectionOpen, setRejectionOpen] = useState(false);
  const [rejectionTarget, setRejectionTarget] = useState('');
  const [publicationOpen, setPublicationOpen] = useState(false);
  const [publicationConfirmed, setPublicationConfirmed] = useState(false);
  const [rejectedValidationIds, setRejectedValidationIds] = useState<
    ReadonlySet<string>
  >(new Set());
  const requestId = useRef(0);
  const mutationInProgress = useRef(false);

  const validations = useMemo(
    () => completedLayoutImportValidations(jobs),
    [jobs],
  );
  const completedImports = useMemo(
    () => completedLayoutFileImports(jobs, selectedGameId),
    [jobs, selectedGameId],
  );
  const publishedRules = useMemo(
    () => publishedRulesForGame(rulesVersions),
    [rulesVersions],
  );
  const symbolByCode = useMemo(
    () => new Map(symbols.map((symbol) => [symbol.mobileCode, symbol])),
    [symbols],
  );

  const loadWorkspace = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setLoadState('loading');
    setError('');
    try {
      const [gamesResult, importsResult, validationsResult] = await Promise.all(
        [
          api.listGames(),
          api.listJobs({ jobType: 'import', limit: 200 }),
          api.listJobs({ jobType: 'validate', limit: 200 }),
        ],
      );
      if (currentRequest !== requestId.current) return;
      if (
        gamesResult.error !== undefined ||
        gamesResult.data === undefined ||
        importsResult.error !== undefined ||
        importsResult.data === undefined ||
        validationsResult.error !== undefined ||
        validationsResult.data === undefined
      ) {
        setError(
          apiErrorMessage(
            gamesResult.error ?? importsResult.error ?? validationsResult.error,
            'Nie udało się pobrać workspace ręcznego importu.',
          ),
        );
        setLoadState('error');
        return;
      }
      setGames(gamesResult.data);
      setJobs([...importsResult.data, ...validationsResult.data]);
      setSelectedGameId((current) =>
        gameId !== undefined
          ? gameId
          : gamesResult.data.some((game) => game.id === current)
            ? current
            : (gamesResult.data[0]?.id ?? null),
      );
      const completed = completedLayoutImportValidations(
        validationsResult.data,
      );
      setSelectedValidationJobId((current) =>
        completed.some((job) => job.id === current)
          ? current
          : (completed[0]?.id ?? ''),
      );
      setLoadState('ready');
    } catch {
      if (currentRequest === requestId.current) {
        setError('Brak połączenia z lokalnym Admin API.');
        setLoadState('error');
      }
    }
  }, [api, gameId]);

  const loadGameConfiguration = useCallback(
    async (gameId: string) => {
      const currentRequest = ++requestId.current;
      try {
        const [rulesResult, symbolsResult] = await Promise.all([
          api.listRulesVersions(gameId),
          api.listSymbols(gameId),
        ]);
        if (currentRequest !== requestId.current) return;
        if (
          rulesResult.error !== undefined ||
          rulesResult.data === undefined ||
          symbolsResult.error !== undefined ||
          symbolsResult.data === undefined
        ) {
          setError(
            apiErrorMessage(
              rulesResult.error ?? symbolsResult.error,
              'Nie udało się pobrać reguł i symboli gry.',
            ),
          );
          return;
        }
        const published = publishedRulesForGame(rulesResult.data);
        setRulesVersions(rulesResult.data);
        setSymbols(symbolsResult.data);
        setSelectedRulesVersionId((current) =>
          published.some((version) => version.id === current)
            ? current
            : (published[0]?.id ?? ''),
        );
        const imports = completedLayoutFileImports(jobs, gameId);
        setSelectedImportJobId((current) =>
          imports.some((job) => job.id === current)
            ? current
            : (imports[0]?.id ?? ''),
        );
      } catch {
        if (currentRequest === requestId.current) {
          setError('Brak połączenia z lokalnym Admin API.');
        }
      }
    },
    [api, jobs],
  );

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void loadWorkspace();
    });
    return () => {
      cancelled = true;
      requestId.current += 1;
    };
  }, [loadWorkspace]);

  useEffect(() => {
    let cancelled = false;
    if (selectedGameId !== null) {
      queueMicrotask(() => {
        if (!cancelled) void loadGameConfiguration(selectedGameId);
      });
    }
    return () => {
      cancelled = true;
      requestId.current += 1;
    };
  }, [loadGameConfiguration, selectedGameId]);

  async function submitImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutationInProgress.current || selectedGameId === null) return;
    const path = validateImportSourcePath(sourcePath);
    if (!path.valid) {
      setError(path.error);
      return;
    }
    mutationInProgress.current = true;
    setMutating(true);
    setError('');
    setFeedback('');
    const result = await createLayoutImportJob(api, selectedGameId, path.value);
    mutationInProgress.current = false;
    setMutating(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setJobs((current) => [result.job, ...current]);
    setSourcePath('');
    setFeedback(
      `Utworzono import ${result.job.id}. Uruchom worker i obserwuj sekcję Jobs.`,
    );
  }

  async function submitValidation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      mutationInProgress.current ||
      selectedGameId === null ||
      selectedImportJobId === '' ||
      selectedRulesVersionId === ''
    ) {
      return;
    }
    mutationInProgress.current = true;
    setMutating(true);
    setError('');
    setFeedback('');
    const result = await createLayoutImportValidation(
      api,
      selectedGameId,
      selectedImportJobId,
      selectedRulesVersionId,
    );
    mutationInProgress.current = false;
    setMutating(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setJobs((current) => [result.job, ...current]);
    setFeedback(
      `Utworzono walidację ${result.job.id}. Raport będzie dostępny po ukończeniu workera.`,
    );
  }

  async function fetchRows(
    validationJobId: string,
    cursor: number,
    status: LayoutImportRowStatus,
    selectedErrorCode: string,
  ) {
    setRowsLoading(true);
    setError('');
    const result = await loadLayoutImportRows(api, validationJobId, {
      afterLineNumber: cursor,
      ...(selectedErrorCode === '' ? {} : { errorCode: selectedErrorCode }),
      limit: ROW_PAGE_SIZE,
      status,
    });
    setRowsLoading(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setPage(result.page);
    setSelectedRow(firstPreviewableRow(result.page.items));
  }

  async function openReport() {
    if (selectedValidationJobId === '' || reportLoading) return;
    setReportLoading(true);
    setError('');
    setFeedback('');
    const result = await loadLayoutImportReport(api, selectedValidationJobId);
    setReportLoading(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setReport(result.report);
    setAfterLineNumber(0);
    setCursorHistory([]);
    setRowStatus('all');
    setErrorCode('');
    const validation = validations.find(
      (job) => job.id === selectedValidationJobId,
    );
    if (validation?.gameId) setSelectedGameId(validation.gameId);
    await fetchRows(selectedValidationJobId, 0, 'all', '');
  }

  async function applyFilters() {
    if (report === null || rowsLoading) return;
    const nextStatus = errorCode === '' ? rowStatus : 'invalid';
    setRowStatus(nextStatus);
    setAfterLineNumber(0);
    setCursorHistory([]);
    await fetchRows(report.validationJobId, 0, nextStatus, errorCode);
  }

  async function showNextPage() {
    if (report === null || page?.nextAfterLineNumber == null || rowsLoading) {
      return;
    }
    const nextCursor = page.nextAfterLineNumber;
    setCursorHistory((current) => [...current, afterLineNumber]);
    setAfterLineNumber(nextCursor);
    await fetchRows(report.validationJobId, nextCursor, rowStatus, errorCode);
  }

  async function showPreviousPage() {
    if (report === null || cursorHistory.length === 0 || rowsLoading) return;
    const previous = cursorHistory[cursorHistory.length - 1] ?? 0;
    setCursorHistory((current) => current.slice(0, -1));
    setAfterLineNumber(previous);
    await fetchRows(report.validationJobId, previous, rowStatus, errorCode);
  }

  async function confirmRejection() {
    if (
      report === null ||
      mutationInProgress.current ||
      !canConfirmStagingRejection(rejectionTarget, report)
    ) {
      return;
    }
    mutationInProgress.current = true;
    setMutating(true);
    setError('');
    const result = await rejectLayoutImportStaging(api, report.validationJobId);
    mutationInProgress.current = false;
    setMutating(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setRejectedValidationIds(
      (current) => new Set([...current, report.validationJobId]),
    );
    setRejectionOpen(false);
    setRejectionTarget('');
    setPage(null);
    setSelectedRow(null);
    setFeedback(
      `Odrzucono staging importu ${result.rejection.importJobId}: usunięto ${result.rejection.deletedRawRowCount} surowych i ${result.rejection.deletedNormalizedRowCount} znormalizowanych wierszy.`,
    );
    setReport(null);
  }

  async function confirmPublication() {
    if (
      report === null ||
      !report.readyForPublication ||
      !publicationConfirmed ||
      mutationInProgress.current
    ) {
      return;
    }
    mutationInProgress.current = true;
    setMutating(true);
    setError('');
    setFeedback('');
    const result = await publishLayoutImportDataset(
      api,
      report.validationJobId,
    );
    mutationInProgress.current = false;
    setMutating(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setPublicationOpen(false);
    setPublicationConfirmed(false);
    setFeedback(
      `Opublikowano niezmienny dataset v${result.dataset.version} z ${result.dataset.layoutCount.toLocaleString('pl-PL')} planszami. Source job: ${result.dataset.sourceJobId}.`,
    );
  }

  return (
    <section className="catalogSection manualImportSection" id="imports">
      <header className="pageHeader importPageHeader">
        <div>
          <p className="eyebrow">M4.3 · ręczny import danych</p>
          <h1>Import plansz</h1>
          <p className="lead">
            Lokalny CSV lub JSONL przechodzi przez worker, znormalizowany
            staging i dokładny raport integralności przed publikacją datasetu.
          </p>
        </div>
        <button
          className="secondaryButton"
          disabled={loadState === 'loading'}
          onClick={() => void loadWorkspace()}
          type="button"
        >
          Odśwież importy
        </button>
      </header>

      {feedback ? <p className="feedbackBanner">{feedback}</p> : null}
      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}

      {loadState === 'error' ? (
        <ImportState
          error
          onRetry={() => void loadWorkspace()}
          text={error}
          title="Nie udało się wczytać importów"
        />
      ) : loadState === 'loading' ? (
        <ImportState
          text="Pobieram gry oraz zadania importu i walidacji…"
          title="Wczytywanie"
        />
      ) : games.length === 0 ? (
        <ImportState
          text="Najpierw utwórz grę i opublikuj wersję reguł."
          title="Brak gier"
        />
      ) : (
        <>
          {gameId === undefined ? (
            <div className="gameSelectorPanel">
              <label htmlFor="import-game">Gra</label>
              <select
                id="import-game"
                onChange={(event) => {
                  setSelectedGameId(event.target.value || null);
                  setReport(null);
                  setPage(null);
                }}
                value={selectedGameId ?? ''}
              >
                {games.map((game) => (
                  <option key={game.id} value={game.id}>
                    {game.name} · {game.code}
                  </option>
                ))}
              </select>
              <p>
                Plik pozostaje na tym komputerze pod katalogiem skonfigurowanym
                jako <code>GAME_PREDICTOR_IMPORT_ROOT</code>.
              </p>
            </div>
          ) : null}

          <div className="importComposerGrid">
            <form
              className="editorPanel importComposer"
              onSubmit={submitImport}
            >
              <div className="editorHeader">
                <div>
                  <p className="eyebrow">Krok 1</p>
                  <h2>Utwórz import pliku</h2>
                </div>
              </div>
              <label>
                Względna ścieżka POSIX
                <input
                  disabled={mutating}
                  onChange={(event) => setSourcePath(event.target.value)}
                  placeholder="game-1/layouts.jsonl"
                  value={sourcePath}
                />
              </label>
              <p className="fieldHint">
                API akceptuje wyłącznie plik <code>.csv</code> albo{' '}
                <code>.jsonl</code> znajdujący się pod dozwolonym katalogiem.
              </p>
              <button
                className="primaryButton"
                disabled={mutating || selectedGameId === null}
                type="submit"
              >
                {mutating ? 'Zapisywanie…' : 'Utwórz job importu'}
              </button>
            </form>

            <form
              className="editorPanel importComposer"
              onSubmit={submitValidation}
            >
              <div className="editorHeader">
                <div>
                  <p className="eyebrow">Krok 2</p>
                  <h2>Waliduj ukończony import</h2>
                </div>
              </div>
              <label>
                Ukończony import
                <select
                  disabled={mutating || completedImports.length === 0}
                  onChange={(event) =>
                    setSelectedImportJobId(event.target.value)
                  }
                  value={selectedImportJobId}
                >
                  {completedImports.length === 0 ? (
                    <option value="">Brak ukończonych importów</option>
                  ) : null}
                  {completedImports.map((job) => (
                    <option key={job.id} value={job.id}>
                      {layoutImportSourcePath(job)} · {shortId(job.id)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Opublikowana wersja reguł
                <select
                  disabled={mutating || publishedRules.length === 0}
                  onChange={(event) =>
                    setSelectedRulesVersionId(event.target.value)
                  }
                  value={selectedRulesVersionId}
                >
                  {publishedRules.length === 0 ? (
                    <option value="">Brak opublikowanych reguł</option>
                  ) : null}
                  {publishedRules.map((version) => (
                    <option key={version.id} value={version.id}>
                      v{version.version} · {version.rows} × {version.columns}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="primaryButton"
                disabled={
                  mutating ||
                  selectedImportJobId === '' ||
                  selectedRulesVersionId === ''
                }
                type="submit"
              >
                {mutating ? 'Zapisywanie…' : 'Utwórz job walidacji'}
              </button>
            </form>
          </div>

          <section
            className="importReportPanel"
            aria-labelledby="import-report"
          >
            <div className="listHeader importReportSelector">
              <div>
                <p className="eyebrow">Krok 3</p>
                <h2 id="import-report">Raport integralności</h2>
                <p>
                  Dostępne są wyłącznie ukończone walidacje typu import plansz.
                </p>
              </div>
              <div className="importReportControls">
                <label>
                  Walidacja
                  <select
                    disabled={validations.length === 0 || reportLoading}
                    onChange={(event) =>
                      setSelectedValidationJobId(event.target.value)
                    }
                    value={selectedValidationJobId}
                  >
                    {validations.length === 0 ? (
                      <option value="">Brak ukończonych walidacji</option>
                    ) : null}
                    {validations.map((job) => {
                      const ids = layoutImportValidationIds(job);
                      return (
                        <option key={job.id} value={job.id}>
                          {shortId(job.id)} · import {shortId(ids?.importJobId)}
                          {' · '}
                          {formatJobTimestamp(job.finishedAt)}
                          {rejectedValidationIds.has(job.id)
                            ? ' · staging odrzucony'
                            : ''}
                        </option>
                      );
                    })}
                  </select>
                </label>
                <button
                  className="primaryButton"
                  disabled={selectedValidationJobId === '' || reportLoading}
                  onClick={() => void openReport()}
                  type="button"
                >
                  {reportLoading ? 'Pobieranie raportu…' : 'Otwórz raport'}
                </button>
              </div>
            </div>

            {validations.length === 0 ? (
              <ImportState
                text="Utwórz walidację i uruchom worker. Raport pojawi się po statusie completed."
                title="Brak raportów"
              />
            ) : reportLoading ? (
              <ImportState
                text="Liczniki obejmują cały staging; próbki pozostają ograniczone."
                title="Wczytywanie"
              />
            ) : report ? (
              <ImportReport
                errorCode={errorCode}
                onApplyFilters={() => void applyFilters()}
                onErrorCodeChange={setErrorCode}
                onOpenRejection={() => {
                  setRejectionTarget('');
                  setRejectionOpen(true);
                }}
                onOpenPublication={() => {
                  setPublicationConfirmed(false);
                  setPublicationOpen(true);
                }}
                onRowStatusChange={setRowStatus}
                onSelectRow={setSelectedRow}
                onShowNext={() => void showNextPage()}
                onShowPrevious={() => void showPreviousPage()}
                page={page}
                report={report}
                rowStatus={rowStatus}
                rowsLoading={rowsLoading}
                busy={mutating}
                selectedRow={selectedRow}
                symbolByCode={symbolByCode}
                canShowPrevious={cursorHistory.length > 0}
              />
            ) : (
              <ImportState
                text="Wybierz ukończoną walidację i otwórz jej raport."
                title="Wybierz raport"
              />
            )}
          </section>
        </>
      )}

      {rejectionOpen && report ? (
        <RejectionDialog
          busy={mutating}
          canConfirm={canConfirmStagingRejection(rejectionTarget, report)}
          onCancel={() => {
            setRejectionOpen(false);
            setRejectionTarget('');
          }}
          onConfirm={() => void confirmRejection()}
          onTargetChange={setRejectionTarget}
          report={report}
          target={rejectionTarget}
        />
      ) : null}
      {publicationOpen && report ? (
        <PublicationDialog
          busy={mutating}
          confirmed={publicationConfirmed}
          onCancel={() => {
            setPublicationOpen(false);
            setPublicationConfirmed(false);
          }}
          onConfirm={() => void confirmPublication()}
          onConfirmedChange={setPublicationConfirmed}
          report={report}
        />
      ) : null}
    </section>
  );
}

function ImportReport({
  busy,
  canShowPrevious,
  errorCode,
  onApplyFilters,
  onErrorCodeChange,
  onOpenRejection,
  onOpenPublication,
  onRowStatusChange,
  onSelectRow,
  onShowNext,
  onShowPrevious,
  page,
  report,
  rowStatus,
  rowsLoading,
  selectedRow,
  symbolByCode,
}: {
  readonly busy: boolean;
  readonly canShowPrevious: boolean;
  readonly errorCode: string;
  readonly onApplyFilters: () => void;
  readonly onErrorCodeChange: (value: string) => void;
  readonly onOpenRejection: () => void;
  readonly onOpenPublication: () => void;
  readonly onRowStatusChange: (value: LayoutImportRowStatus) => void;
  readonly onSelectRow: (row: LayoutImportNormalizedRowResponse) => void;
  readonly onShowNext: () => void;
  readonly onShowPrevious: () => void;
  readonly page: LayoutImportNormalizedRowPageResponse | null;
  readonly report: LayoutImportIntegrityReportResponse;
  readonly rowStatus: LayoutImportRowStatus;
  readonly rowsLoading: boolean;
  readonly selectedRow: LayoutImportNormalizedRowResponse | null;
  readonly symbolByCode: ReadonlyMap<number, SymbolResponse>;
}) {
  return (
    <div className="importReportBody">
      <div
        className={
          report.readyForPublication
            ? 'importReadiness importReadinessReady'
            : 'importReadiness importReadinessBlocked'
        }
      >
        <div>
          <strong>
            {report.readyForPublication
              ? 'Raport nie zawiera blokad'
              : 'Publikacja jest zablokowana'}
          </strong>
          <p>
            Duplikaty sygnatur są dozwolone. Luki, błędne wiersze i duplikaty
            numerów muszą zostać usunięte w pliku źródłowym i zaimportowane
            ponownie.
          </p>
        </div>
        <div className="formActions">
          {report.readyForPublication ? (
            <button
              className="primaryButton"
              disabled={busy}
              onClick={onOpenPublication}
              type="button"
            >
              Opublikuj dataset
            </button>
          ) : null}
          <button
            className="dangerButton"
            disabled={busy}
            onClick={onOpenRejection}
            type="button"
          >
            Odrzuć staging
          </button>
        </div>
      </div>

      <dl className="importStats">
        <Stat label="Oczekiwane" value={report.expectedRowCount ?? 'brak'} />
        <Stat label="Rzeczywiste" value={report.actualRowCount} />
        <Stat label="Poprawne" value={report.validRowCount} />
        <Stat label="Błędne" value={report.invalidRowCount} />
        <Stat label="Luki" value={report.missingSequenceCount} />
        <Stat
          label="Duplikaty numeru"
          value={report.duplicateSequenceGroupCount}
        />
        <Stat
          label="Duplikaty sygnatur"
          value={report.duplicateSignatureGroupCount}
        />
        <Stat
          label="Zakres sekwencji"
          value={
            report.minSequenceNumber === null
              ? 'brak'
              : `${report.minSequenceNumber}–${report.maxSequenceNumber}`
          }
        />
      </dl>

      <div className="importChecks">
        {report.checks.map((check) => (
          <article
            className={`importCheck importCheck-${check.status}`}
            key={check.code}
          >
            <div>
              <strong>{layoutImportCheckLabel(check.code)}</strong>
              <span>{layoutImportCheckStatusLabel(check.status)}</span>
            </div>
            <p>{check.message}</p>
            {check.sequenceNumbers.length > 0 ? (
              <p>
                Numery:{' '}
                {formatBoundedSample(check.sequenceNumbers, check.truncated)}
              </p>
            ) : null}
            {check.lineNumbers.length > 0 ? (
              <p>
                Linie: {formatBoundedSample(check.lineNumbers, check.truncated)}
              </p>
            ) : null}
          </article>
        ))}
      </div>

      {report.duplicateSequences.length > 0 ||
      report.duplicateSignatures.length > 0 ? (
        <div className="importDiagnostics">
          <DiagnosticGroups report={report} />
        </div>
      ) : null}

      <section className="importRowsPanel">
        <header>
          <div>
            <p className="eyebrow">Wiersze stagingu</p>
            <h3>Podgląd po fizycznym line_number</h3>
          </div>
          <div className="importRowFilters">
            <label>
              Status
              <select
                onChange={(event) =>
                  onRowStatusChange(event.target.value as LayoutImportRowStatus)
                }
                value={rowStatus}
              >
                <option value="all">Wszystkie</option>
                <option value="valid">Poprawne</option>
                <option value="invalid">Błędne</option>
              </select>
            </label>
            <label>
              Kod błędu
              <select
                onChange={(event) => onErrorCodeChange(event.target.value)}
                value={errorCode}
              >
                <option value="">Wszystkie kody</option>
                {report.errorCodeCounts.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.code} ({item.count})
                  </option>
                ))}
              </select>
            </label>
            <button
              className="secondaryButton"
              disabled={rowsLoading}
              onClick={onApplyFilters}
              type="button"
            >
              Zastosuj filtry
            </button>
          </div>
        </header>

        {rowsLoading ? (
          <ImportState
            text="Pobieram maksymalnie 25 kolejnych wierszy…"
            title="Wczytywanie"
          />
        ) : page && page.items.length > 0 ? (
          <>
            <div className="importRowsWorkspace">
              <div className="importRowsTableWrap">
                <table className="importRowsTable">
                  <thead>
                    <tr>
                      <th>Linia</th>
                      <th>Sequence</th>
                      <th>Status</th>
                      <th>Kod / sygnatura</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((row) => (
                      <tr key={row.lineNumber}>
                        <td>{row.lineNumber}</td>
                        <td>{row.sequenceNumber ?? '—'}</td>
                        <td>
                          <span
                            className={
                              row.errorCode === null
                                ? 'importRowStatus importRowStatusValid'
                                : 'importRowStatus importRowStatusInvalid'
                            }
                          >
                            {row.errorCode === null ? 'Poprawny' : 'Błąd'}
                          </span>
                        </td>
                        <td>
                          {row.errorCode ? (
                            <>
                              <strong>{row.errorCode}</strong>
                              <small>{row.errorMessage}</small>
                            </>
                          ) : (
                            <button
                              className="textButton"
                              onClick={() => onSelectRow(row)}
                              type="button"
                            >
                              {shortSignature(row.signature)}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {selectedRow?.cells ? (
                <ImportLayoutBoard
                  columns={report.columns}
                  row={selectedRow}
                  symbolByCode={symbolByCode}
                />
              ) : (
                <div className="importBoardPlaceholder">
                  <strong>Brak poprawnej planszy na stronie</strong>
                  <p>
                    Błędny wiersz zachowuje bezpieczny opis, ale nie jest
                    traktowany jako poprawna plansza.
                  </p>
                </div>
              )}
            </div>
            <footer className="importRowsFooter">
              <p>
                Strona keyset · {page.items.length} wierszy · row-major{' '}
                {report.rows} × {report.columns}
              </p>
              <div className="rowActions">
                <button
                  className="textButton"
                  disabled={!canShowPrevious || rowsLoading}
                  onClick={onShowPrevious}
                  type="button"
                >
                  Poprzednia
                </button>
                <button
                  className="secondaryButton"
                  disabled={page.nextAfterLineNumber === null || rowsLoading}
                  onClick={onShowNext}
                  type="button"
                >
                  Następna
                </button>
              </div>
            </footer>
          </>
        ) : (
          <ImportState
            text="Dla wybranych filtrów nie ma żadnych wierszy."
            title="Brak wyników"
          />
        )}
      </section>
    </div>
  );
}

function DiagnosticGroups({
  report,
}: {
  readonly report: LayoutImportIntegrityReportResponse;
}) {
  return (
    <>
      {report.duplicateSequences.length > 0 ? (
        <section>
          <h3>Duplikaty sequence_number — blokada</h3>
          {report.duplicateSequences.map((group) => (
            <p key={group.sequenceNumber}>
              <strong>#{group.sequenceNumber}</strong> · {group.occurrenceCount}{' '}
              wystąpienia · linie{' '}
              {formatBoundedSample(group.lineNumbers, group.truncated)}
            </p>
          ))}
          {report.duplicateSequencesTruncated ? (
            <small>
              Lista grup została obcięta; licznik powyżej jest dokładny.
            </small>
          ) : null}
        </section>
      ) : null}
      {report.duplicateSignatures.length > 0 ? (
        <section>
          <h3>Duplikaty sygnatur — dozwolone ostrzeżenie</h3>
          {report.duplicateSignatures.map((group) => (
            <p key={group.signature}>
              <code>{shortSignature(group.signature)}</code> · sekwencje{' '}
              {formatBoundedSample(
                group.sequenceNumbers,
                group.sequenceNumbersTruncated,
              )}{' '}
              · linie{' '}
              {formatBoundedSample(
                group.lineNumbers,
                group.lineNumbersTruncated,
              )}
            </p>
          ))}
          {report.duplicateSignaturesTruncated ? (
            <small>
              Lista grup została obcięta; licznik powyżej jest dokładny.
            </small>
          ) : null}
        </section>
      ) : null}
    </>
  );
}

function ImportLayoutBoard({
  columns,
  row,
  symbolByCode,
}: {
  readonly columns: number;
  readonly row: LayoutImportNormalizedRowResponse;
  readonly symbolByCode: ReadonlyMap<number, SymbolResponse>;
}) {
  return (
    <section
      aria-label={`Plansza z linii ${row.lineNumber}`}
      className="importLayoutBoard"
    >
      <header>
        <p className="eyebrow">Linia {row.lineNumber}</p>
        <h3>Plansza row-major</h3>
      </header>
      <div
        className="datasetLayoutGrid"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {row.cells?.map((mobileCode, index) => {
          const symbol = symbolByCode.get(mobileCode);
          return (
            <div
              aria-label={rowMajorCellLabel(index, columns)}
              className="datasetLayoutCell"
              key={`${index}-${mobileCode}`}
            >
              <strong>{symbol?.code ?? mobileCode}</strong>
              <span>{symbol?.name ?? `Kod ${mobileCode}`}</span>
            </div>
          );
        })}
      </div>
      <p className="datasetSignature">
        Sekwencja: <strong>{row.sequenceNumber}</strong>
        <br />
        Sygnatura: <code>{row.signature}</code>
      </p>
    </section>
  );
}

function RejectionDialog({
  busy,
  canConfirm,
  onCancel,
  onConfirm,
  onTargetChange,
  report,
  target,
}: {
  readonly busy: boolean;
  readonly canConfirm: boolean;
  readonly onCancel: () => void;
  readonly onConfirm: () => void;
  readonly onTargetChange: (value: string) => void;
  readonly report: LayoutImportIntegrityReportResponse;
  readonly target: string;
}) {
  return (
    <dialog
      aria-labelledby="reject-import-title"
      aria-modal="true"
      className="paylineDialog"
      open
    >
      <div className="paylineDialogCard importRejectionDialog">
        <header className="paylineDialogHeader">
          <div>
            <p className="eyebrow">Operacja destrukcyjna</p>
            <h2 id="reject-import-title">Odrzuć nieopublikowany staging</h2>
          </div>
        </header>
        <p>
          Usunięte zostaną surowe i wszystkie znormalizowane wiersze importu.
          Joby pozostaną w historii jako audyt. Operacja zostanie zablokowana,
          jeśli staging jest używany przez dataset.
        </p>
        <dl className="rejectionTargetDetails">
          <div>
            <dt>Validation job</dt>
            <dd>
              <code>{report.validationJobId}</code>
            </dd>
          </div>
          <div>
            <dt>Import job — cel</dt>
            <dd>
              <code>{report.importJobId}</code>
            </dd>
          </div>
        </dl>
        <label>
          Wpisz pełny identyfikator import joba, aby potwierdzić cel
          <input
            autoComplete="off"
            disabled={busy}
            onChange={(event) => onTargetChange(event.target.value)}
            value={target}
          />
        </label>
        <footer className="formActions">
          <button
            className="textButton"
            disabled={busy}
            onClick={onCancel}
            type="button"
          >
            Anuluj
          </button>
          <button
            className="dangerButton"
            disabled={!canConfirm || busy}
            onClick={onConfirm}
            type="button"
          >
            {busy ? 'Usuwanie stagingu…' : 'Potwierdź odrzucenie stagingu'}
          </button>
        </footer>
      </div>
    </dialog>
  );
}

function PublicationDialog({
  busy,
  confirmed,
  onCancel,
  onConfirm,
  onConfirmedChange,
  report,
}: {
  readonly busy: boolean;
  readonly confirmed: boolean;
  readonly onCancel: () => void;
  readonly onConfirm: () => void;
  readonly onConfirmedChange: (value: boolean) => void;
  readonly report: LayoutImportIntegrityReportResponse;
}) {
  return (
    <dialog
      aria-labelledby="publish-import-title"
      aria-modal="true"
      className="paylineDialog"
      open
    >
      <div className="paylineDialogCard importRejectionDialog">
        <header className="paylineDialogHeader">
          <div>
            <p className="eyebrow">Publikacja niezmiennej wersji</p>
            <h2 id="publish-import-title">Opublikuj dataset z importu</h2>
          </div>
        </header>
        <p>
          API ponownie sprawdzi pełny raport pod blokadą transakcyjną. Dataset
          oraz wszystkie plansze powstaną atomowo i będą dostępne dla pipeline’u
          payoutów oraz wydań.
        </p>
        <dl className="rejectionTargetDetails">
          <div>
            <dt>Validation job</dt>
            <dd>
              <code>{report.validationJobId}</code>
            </dd>
          </div>
          <div>
            <dt>Liczba plansz</dt>
            <dd>{report.validRowCount.toLocaleString('pl-PL')}</dd>
          </div>
        </dl>
        <label className="confirmationCheck">
          <input
            checked={confirmed}
            disabled={busy}
            onChange={(event) => onConfirmedChange(event.target.checked)}
            type="checkbox"
          />
          Rozumiem, że opublikowany dataset będzie niezmienny.
        </label>
        <footer className="formActions">
          <button
            className="textButton"
            disabled={busy}
            onClick={onCancel}
            type="button"
          >
            Anuluj
          </button>
          <button
            className="primaryButton"
            disabled={!confirmed || busy}
            onClick={onConfirm}
            type="button"
          >
            {busy ? 'Publikowanie…' : 'Potwierdź publikację'}
          </button>
        </footer>
      </div>
    </dialog>
  );
}

function Stat({
  label,
  value,
}: {
  readonly label: string;
  readonly value: number | string;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {typeof value === 'number' ? value.toLocaleString('pl-PL') : value}
      </dd>
    </div>
  );
}

function ImportState({
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
      <span className={title === 'Wczytywanie' ? 'loadingMark' : 'stateIcon'}>
        {title === 'Wczytywanie' ? '' : error ? '!' : '0'}
      </span>
      <div>
        <h2>{title}</h2>
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

function shortId(value: string | undefined): string {
  if (!value) return 'brak';
  return value.length > 12 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

function shortSignature(value: string | null): string {
  if (!value) return 'brak sygnatury';
  return value.length > 24 ? `${value.slice(0, 24)}…` : value;
}

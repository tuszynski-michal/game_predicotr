'use client';

import type {
  DatasetValidationReportResponse,
  DatasetVersionResponse,
  GameResponse,
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
import {
  type DatasetsClient,
  archiveDataset,
  generateMockDataset,
  getDatasetValidationReport,
} from '@/features/datasets/dataset-actions';
import {
  DEFAULT_DATASET_SEED,
  publishedRulesVersions,
  upsertDatasetVersion,
  validateDatasetSeed,
} from '@/features/datasets/dataset-state';
import { selectRulesGameId } from '@/features/rules/rules-version-state';
import { DatasetValidationReport } from '@/features/datasets/dataset-validation-report';
import { DatasetPreviewModal } from '@/features/datasets/dataset-preview-modal';
import { DatasetPublicationModal } from '@/features/datasets/dataset-publication-modal';

type LoadState = 'loading' | 'ready' | 'error';

interface DatasetCatalogProps {
  readonly apiBaseUrl: string;
  readonly client?: DatasetsClient;
  readonly gameId?: string;
  readonly gamesRevision?: number;
}

export function DatasetCatalog({
  apiBaseUrl,
  client,
  gameId,
  gamesRevision = 0,
}: DatasetCatalogProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [uncontrolledGameId, setSelectedGameId] = useState<string | null>(null);
  const selectedGameId = gameId ?? uncontrolledGameId;
  const [rulesVersions, setRulesVersions] = useState<
    readonly RulesVersionResponse[]
  >([]);
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [datasets, setDatasets] = useState<readonly DatasetVersionResponse[]>(
    [],
  );
  const [selectedRulesVersionId, setSelectedRulesVersionId] = useState('');
  const [seed, setSeed] = useState(DEFAULT_DATASET_SEED);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [validatingDatasetId, setValidatingDatasetId] = useState<string | null>(
    null,
  );
  const [validationReports, setValidationReports] = useState<
    Readonly<Record<string, DatasetValidationReportResponse>>
  >({});
  const [validationError, setValidationError] = useState<{
    readonly datasetId: string;
    readonly message: string;
  } | null>(null);
  const [previewDataset, setPreviewDataset] =
    useState<DatasetVersionResponse | null>(null);
  const [publicationDataset, setPublicationDataset] =
    useState<DatasetVersionResponse | null>(null);
  const [archiveCandidateId, setArchiveCandidateId] = useState<string | null>(
    null,
  );
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const requestId = useRef(0);
  const validationRequestId = useRef(0);
  const mutationInProgress = useRef(false);
  const validationInProgress = useRef<string | null>(null);

  const loadGames = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setLoadState('loading');
    setError('');
    try {
      const result = await api.listGames();
      if (currentRequest !== requestId.current) return;
      if (result.error !== undefined || result.data === undefined) {
        setError(apiErrorMessage(result.error, 'Nie udało się pobrać gier.'));
        setLoadState('error');
        return;
      }
      setGames(result.data);
      setSelectedGameId((current) =>
        gameId === undefined ? selectRulesGameId(result.data, current) : gameId,
      );
      setLoadState('ready');
    } catch {
      if (currentRequest === requestId.current) {
        setError('Brak połączenia z lokalnym Admin API.');
        setLoadState('error');
      }
    }
  }, [api, gameId]);

  const loadDatasetWorkspace = useCallback(
    async (gameId: string) => {
      const currentRequest = ++requestId.current;
      validationRequestId.current += 1;
      validationInProgress.current = null;
      setValidatingDatasetId(null);
      setLoadState('loading');
      setError('');
      try {
        const [rulesResult, datasetsResult, symbolsResult] = await Promise.all([
          api.listRulesVersions(gameId),
          api.listDatasetVersions(gameId),
          api.listSymbols(gameId),
        ]);
        if (currentRequest !== requestId.current) return;
        if (
          rulesResult.error !== undefined ||
          rulesResult.data === undefined ||
          datasetsResult.error !== undefined ||
          datasetsResult.data === undefined ||
          symbolsResult.error !== undefined ||
          symbolsResult.data === undefined
        ) {
          setError(
            apiErrorMessage(
              rulesResult.error ?? datasetsResult.error ?? symbolsResult.error,
              'Nie udało się pobrać workspace datasetów.',
            ),
          );
          setLoadState('error');
          return;
        }
        const published = publishedRulesVersions(rulesResult.data);
        setRulesVersions(published);
        setSelectedRulesVersionId((current) =>
          published.some((version) => version.id === current)
            ? current
            : (published[0]?.id ?? ''),
        );
        setDatasets(datasetsResult.data);
        setSymbols(symbolsResult.data);
        setValidationReports({});
        setValidationError(null);
        setLoadState('ready');
      } catch {
        if (currentRequest === requestId.current) {
          setError('Brak połączenia z lokalnym Admin API.');
          setLoadState('error');
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
      requestId.current += 1;
    };
  }, [gamesRevision, loadGames]);

  useEffect(() => {
    let cancelled = false;
    if (selectedGameId !== null) {
      queueMicrotask(() => {
        if (!cancelled) {
          void loadDatasetWorkspace(selectedGameId);
        }
      });
    }
    return () => {
      cancelled = true;
      requestId.current += 1;
    };
  }, [loadDatasetWorkspace, selectedGameId]);

  async function onGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      mutationInProgress.current ||
      selectedGameId === null ||
      selectedRulesVersionId === ''
    ) {
      return;
    }
    const validation = validateDatasetSeed(seed);
    if (!validation.valid) {
      setError(validation.error);
      return;
    }
    mutationInProgress.current = true;
    setIsGenerating(true);
    setError('');
    setFeedback('');
    const result = await generateMockDataset(
      api,
      selectedGameId,
      selectedRulesVersionId,
      validation.value,
    );
    mutationInProgress.current = false;
    setIsGenerating(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setDatasets((current) => upsertDatasetVersion(current, result.dataset));
    setFeedback(
      `Utworzono staging datasetu v${result.dataset.version} z 1000 plansz.`,
    );
  }

  async function onValidate(datasetId: string) {
    if (validationInProgress.current !== null) return;
    const currentRequest = ++validationRequestId.current;
    validationInProgress.current = datasetId;
    setValidatingDatasetId(datasetId);
    setValidationError(null);
    const result = await getDatasetValidationReport(api, datasetId);
    if (currentRequest !== validationRequestId.current) return;
    validationInProgress.current = null;
    setValidatingDatasetId(null);
    if (!result.ok) {
      setValidationError({ datasetId, message: result.error });
      return;
    }
    setValidationReports((current) => ({
      ...current,
      [datasetId]: result.report,
    }));
  }

  function onPublished(dataset: DatasetVersionResponse) {
    setDatasets((current) => upsertDatasetVersion(current, dataset));
    setPublicationDataset(null);
    setFeedback(`Opublikowano niezmienny dataset v${dataset.version}.`);
  }

  async function confirmArchive(dataset: DatasetVersionResponse) {
    if (mutationInProgress.current || dataset.status !== 'published') return;
    mutationInProgress.current = true;
    setArchivingId(dataset.id);
    setError('');
    setFeedback('');
    const result = await archiveDataset(api, dataset);
    mutationInProgress.current = false;
    setArchivingId(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setDatasets((current) => upsertDatasetVersion(current, result.dataset));
    setArchiveCandidateId(null);
    setFeedback(`Zarchiwizowano dataset v${dataset.version}.`);
  }

  const selectedGame = games.find((game) => game.id === selectedGameId) ?? null;

  return (
    <section className="catalogSection" id="datasets">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">M2.4 · kanoniczny staging</p>
          <h1>Datasety</h1>
          <p className="lead">
            Generator tworzy deterministyczny staging 1000 plansz. Raport
            oddziela blokady integralności od dozwolonych duplikatów treści.
          </p>
        </div>
      </header>

      {feedback ? <p className="feedbackBanner">{feedback}</p> : null}
      {error && loadState !== 'error' ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}

      {loadState === 'error' ? (
        <DatasetState
          error
          onRetry={() =>
            void (selectedGameId
              ? loadDatasetWorkspace(selectedGameId)
              : loadGames())
          }
          text={error}
          title="Nie udało się wczytać datasetów"
        />
      ) : games.length === 0 && loadState === 'ready' ? (
        <DatasetState
          text="Najpierw utwórz grę i opublikuj jej wersję reguł."
          title="Brak gry"
        />
      ) : (
        <>
          {gameId === undefined ? (
            <div className="gameSelectorPanel">
              <label htmlFor="dataset-game">Gra</label>
              <select
                id="dataset-game"
                onChange={(event) => {
                  setSelectedGameId(event.target.value || null);
                  setFeedback('');
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
                {selectedGame
                  ? `Przygotowujesz dane gry „${selectedGame.name}”.`
                  : 'Wybierz grę.'}
              </p>
            </div>
          ) : null}

          {loadState === 'loading' ? (
            <DatasetState
              text="Pobieram wersje reguł i datasety…"
              title="Wczytywanie"
            />
          ) : rulesVersions.length === 0 ? (
            <DatasetState
              text="Generator wymaga opublikowanej wersji reguł z co najmniej dwoma aktywnymi symbolami."
              title="Brak opublikowanych reguł"
            />
          ) : (
            <form className="editorPanel rulesForm" onSubmit={onGenerate}>
              <div className="editorHeader">
                <div>
                  <p className="eyebrow">Generator mock-v1</p>
                  <h2>Nowy staging 1000 plansz</h2>
                </div>
              </div>
              <label>
                Opublikowana wersja reguł
                <select
                  disabled={isGenerating}
                  onChange={(event) =>
                    setSelectedRulesVersionId(event.target.value)
                  }
                  value={selectedRulesVersionId}
                >
                  {rulesVersions.map((version) => (
                    <option key={version.id} value={version.id}>
                      v{version.version} · {version.rows} × {version.columns}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Seed
                <input
                  disabled={isGenerating}
                  inputMode="numeric"
                  min="0"
                  onChange={(event) => setSeed(event.target.value)}
                  type="number"
                  value={seed}
                />
              </label>
              <div className="formActions">
                <button
                  className="primaryButton"
                  disabled={isGenerating}
                  type="submit"
                >
                  {isGenerating
                    ? 'Generowanie 1000 plansz…'
                    : 'Generuj staging'}
                </button>
              </div>
            </form>
          )}

          {loadState === 'ready' && datasets.length === 0 ? (
            <DatasetState
              text="Utwórz pierwszy deterministyczny mock dla wybranej gry."
              title="Brak datasetów"
            />
          ) : datasets.length > 0 ? (
            <div className="rulesPanel">
              <div className="listHeader">
                <h2>Historia datasetów</h2>
                <p>
                  Opublikowane wersje są niezmienne; archiwizacja zachowuje
                  plansze i czas publikacji.
                </p>
              </div>
              {datasets.map((dataset) => (
                <article className="datasetHistoryRow" key={dataset.id}>
                  <div className="datasetHistoryHeader">
                    <div>
                      <div className="gameTitleLine">
                        <h3>Dataset v{dataset.version}</h3>
                        <span
                          className={`gameStatus gameStatus-${dataset.status}`}
                        >
                          {dataset.status}
                        </span>
                      </div>
                      <p className="rulesMetadata">
                        {dataset.rows} × {dataset.columns}
                        <span>·</span>
                        {dataset.layoutCount} plansz
                        <span>·</span>
                        seed {dataset.generationSeed}
                        <span>·</span>
                        {dataset.generatorVersion}
                      </p>
                    </div>
                    <div className="rowActions">
                      <button
                        className="secondaryButton"
                        onClick={() => setPreviewDataset(dataset)}
                        type="button"
                      >
                        Podgląd
                      </button>
                      <button
                        className="secondaryButton"
                        disabled={validatingDatasetId !== null}
                        onClick={() => void onValidate(dataset.id)}
                        type="button"
                      >
                        {validatingDatasetId === dataset.id
                          ? 'Sprawdzanie…'
                          : validationReports[dataset.id]
                            ? 'Sprawdź ponownie'
                            : 'Sprawdź integralność'}
                      </button>
                      {dataset.status === 'staging' ? (
                        <button
                          className="primaryButton"
                          onClick={() => setPublicationDataset(dataset)}
                          type="button"
                        >
                          Publikuj
                        </button>
                      ) : dataset.status === 'published' &&
                        archiveCandidateId === dataset.id ? (
                        <>
                          <button
                            className="textButton"
                            disabled={archivingId === dataset.id}
                            onClick={() => setArchiveCandidateId(null)}
                            type="button"
                          >
                            Anuluj
                          </button>
                          <button
                            className="dangerButton"
                            disabled={archivingId === dataset.id}
                            onClick={() => void confirmArchive(dataset)}
                            type="button"
                          >
                            {archivingId === dataset.id
                              ? 'Archiwizowanie…'
                              : 'Potwierdź archiwizację'}
                          </button>
                        </>
                      ) : dataset.status === 'published' ? (
                        <button
                          className="textButton"
                          onClick={() => setArchiveCandidateId(dataset.id)}
                          type="button"
                        >
                          Archiwizuj
                        </button>
                      ) : (
                        <span className="immutableLabel">Tylko do odczytu</span>
                      )}
                    </div>
                  </div>
                  {validationError?.datasetId === dataset.id ? (
                    <p
                      className="feedbackBanner feedbackBannerError"
                      role="alert"
                    >
                      {validationError.message}
                    </p>
                  ) : null}
                  {validationReports[dataset.id] ? (
                    <DatasetValidationReport
                      report={validationReports[dataset.id]}
                    />
                  ) : (
                    <p className="datasetDiagnosticNote">
                      Raport nie został jeszcze uruchomiony.
                    </p>
                  )}
                </article>
              ))}
            </div>
          ) : null}
        </>
      )}
      {previewDataset ? (
        <DatasetPreviewModal
          api={api}
          dataset={previewDataset}
          onClose={() => setPreviewDataset(null)}
          symbols={symbols}
        />
      ) : null}
      {publicationDataset ? (
        <DatasetPublicationModal
          api={api}
          dataset={publicationDataset}
          onClose={() => setPublicationDataset(null)}
          onPublished={onPublished}
        />
      ) : null}
    </section>
  );
}

function DatasetState({
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

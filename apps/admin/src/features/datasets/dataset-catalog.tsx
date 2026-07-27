'use client';

import type {
  DatasetVersionResponse,
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
import {
  type DatasetsClient,
  generateMockDataset,
} from '@/features/datasets/dataset-actions';
import {
  DEFAULT_DATASET_SEED,
  publishedRulesVersions,
  upsertDatasetVersion,
  validateDatasetSeed,
} from '@/features/datasets/dataset-state';
import { selectRulesGameId } from '@/features/rules/rules-version-state';

type LoadState = 'loading' | 'ready' | 'error';

interface DatasetCatalogProps {
  readonly apiBaseUrl: string;
  readonly client?: DatasetsClient;
  readonly gamesRevision?: number;
}

export function DatasetCatalog({
  apiBaseUrl,
  client,
  gamesRevision = 0,
}: DatasetCatalogProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);
  const [rulesVersions, setRulesVersions] = useState<
    readonly RulesVersionResponse[]
  >([]);
  const [datasets, setDatasets] = useState<readonly DatasetVersionResponse[]>(
    [],
  );
  const [selectedRulesVersionId, setSelectedRulesVersionId] = useState('');
  const [seed, setSeed] = useState(DEFAULT_DATASET_SEED);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const requestId = useRef(0);
  const mutationInProgress = useRef(false);

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
      setSelectedGameId((current) => selectRulesGameId(result.data, current));
      setLoadState('ready');
    } catch {
      if (currentRequest === requestId.current) {
        setError('Brak połączenia z lokalnym Admin API.');
        setLoadState('error');
      }
    }
  }, [api]);

  const loadDatasetWorkspace = useCallback(
    async (gameId: string) => {
      const currentRequest = ++requestId.current;
      setLoadState('loading');
      setError('');
      try {
        const [rulesResult, datasetsResult] = await Promise.all([
          api.listRulesVersions(gameId),
          api.listDatasetVersions(gameId),
        ]);
        if (currentRequest !== requestId.current) return;
        if (
          rulesResult.error !== undefined ||
          rulesResult.data === undefined ||
          datasetsResult.error !== undefined ||
          datasetsResult.data === undefined
        ) {
          setError(
            apiErrorMessage(
              rulesResult.error ?? datasetsResult.error,
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
      `Utworzono staging datasetu v${result.dataset.version} z 1000 layoutów.`,
    );
  }

  const selectedGame = games.find((game) => game.id === selectedGameId) ?? null;

  return (
    <section className="catalogSection" id="datasets">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">M2.4 · kanoniczny staging</p>
          <h1>Datasety</h1>
          <p className="lead">
            Generator tworzy deterministyczny staging 1000 layoutów. Raporty,
            podgląd i publikacja pojawią się w kolejnych zadaniach.
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
                  <h2>Nowy staging 1000 layoutów</h2>
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
                    ? 'Generowanie 1000 layoutów…'
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
                  Na tym etapie wszystkie wygenerowane wersje są stagingowe.
                </p>
              </div>
              {datasets.map((dataset) => (
                <article className="rulesRow" key={dataset.id}>
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
                      {dataset.layoutCount} layoutów
                      <span>·</span>
                      seed {dataset.generationSeed}
                      <span>·</span>
                      {dataset.generatorVersion}
                    </p>
                  </div>
                  <span className="immutableLabel">Raport w TASK-0026</span>
                </article>
              ))}
            </div>
          ) : null}
        </>
      )}
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

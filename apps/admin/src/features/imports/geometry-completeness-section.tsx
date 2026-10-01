'use client';

import type {
  ImageGeometryCompletenessResponse,
  ImageGeometryLowQualityBoardsResponse,
  IncompleteGeometryImageResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useRef, useState } from 'react';

import type { ImageFolderImportClient } from './image-folder-import-actions';
import {
  DEFAULT_LOW_QUALITY_MAX_CONFIDENCE,
  DEFAULT_LOW_QUALITY_MIN_CELLS,
  INCOMPLETE_IMAGE_STATES,
  LISTED_IMAGE_STATES,
  errorCodeOf,
  formatPercent,
  geometryImageStateLabel,
  geometryImportErrorLabel,
  geometryPositionLabel,
  geometryPositionTone,
  geometryScopeImportId,
  geometrySectionState,
  geometrySourceStatusLabel,
  lowQualityErrorMessage,
  parseLowQualityThresholds,
  quadCentre,
  quadSvgPoints,
  type GeometryImportOption,
  type ListedImageStateName,
} from './geometry-completeness-state';

const PAGE_LIMIT = 25;
const LOW_QUALITY_LIMIT = 50;
const POLL_INTERVAL_MS = 15_000;

type Scope = 'game' | 'import';
type StateFilter = 'all' | ListedImageStateName;
type PreviewStatus = 'idle' | 'loading' | 'ready' | 'error';

interface GeometryCompletenessSectionProps {
  readonly api: ImageFolderImportClient;
  readonly gameId: string;
  readonly imports: readonly GeometryImportOption[];
  /** Polling of the counters runs only while an import is being processed. */
  readonly importActive: boolean;
  readonly refreshToken: number;
}

export function GeometryCompletenessSection({
  api,
  gameId,
  imports,
  importActive,
  refreshToken,
}: GeometryCompletenessSectionProps) {
  const [scope, setScope] = useState<Scope>('game');
  const [importId, setImportId] = useState('');
  const [stateFilter, setStateFilter] = useState<StateFilter>('all');
  const [gameReport, setGameReport] =
    useState<ImageGeometryCompletenessResponse | null>(null);
  const [importReport, setImportReport] =
    useState<ImageGeometryCompletenessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [images, setImages] = useState<
    readonly IncompleteGeometryImageResponse[]
  >([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const reportRequestRef = useRef(0);
  const listRequestRef = useRef(0);

  const selectedImportId = geometryScopeImportId(scope, importId, imports);

  const loadReports = useCallback(
    async (options?: { readonly silent?: boolean }) => {
      const requestId = ++reportRequestRef.current;
      if (!options?.silent) setLoading(true);
      try {
        const [game, selected] = await Promise.all([
          api.getImageGeometryCompleteness({ gameId }),
          selectedImportId === undefined
            ? Promise.resolve(null)
            : api.getImageGeometryCompleteness({
                gameId,
                importJobId: selectedImportId,
              }),
        ]);
        if (requestId !== reportRequestRef.current) return;
        if (
          game.error ||
          !game.data ||
          (selected !== null && (selected.error || !selected.data))
        ) {
          setError('Nie udało się pobrać kompletności geometrii zdjęć.');
          return;
        }
        setGameReport(game.data);
        setImportReport(selected?.data ?? null);
        setError(null);
      } catch {
        if (requestId !== reportRequestRef.current) return;
        setError('Nie udało się pobrać kompletności geometrii zdjęć.');
      } finally {
        if (requestId === reportRequestRef.current) setLoading(false);
      }
    },
    [api, gameId, selectedImportId],
  );

  const loadImages = useCallback(
    async (afterCursor: string | null) => {
      const requestId = ++listRequestRef.current;
      setListLoading(true);
      try {
        const result = await api.listIncompleteGeometryImages({
          afterCursor: afterCursor ?? undefined,
          gameId,
          imageState: stateFilter === 'all' ? undefined : stateFilter,
          importJobId: selectedImportId,
          limit: PAGE_LIMIT,
        });
        if (requestId !== listRequestRef.current) return;
        if (result.error || !result.data) {
          setListError('Nie udało się pobrać listy zdjęć niekompletnych.');
          return;
        }
        const page = result.data;
        setImages((current) =>
          afterCursor === null ? page.images : [...current, ...page.images],
        );
        setNextCursor(page.nextCursor);
        setListError(null);
      } catch {
        if (requestId !== listRequestRef.current) return;
        setListError('Nie udało się pobrać listy zdjęć niekompletnych.');
      } finally {
        if (requestId === listRequestRef.current) setListLoading(false);
      }
    },
    [api, gameId, selectedImportId, stateFilter],
  );

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void loadReports();
    });
    return () => {
      cancelled = true;
    };
  }, [loadReports, refreshToken]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void loadImages(null);
    });
    return () => {
      cancelled = true;
    };
  }, [loadImages, refreshToken]);

  // Only the counters are polled, and only while an import runs; the list is
  // refreshed by the token, the filters and the refresh button.
  useEffect(() => {
    if (!importActive) return;
    const interval = window.setInterval(() => {
      void loadReports({ silent: true });
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [importActive, loadReports]);

  function refresh() {
    void loadReports();
    void loadImages(null);
  }

  const activeReport = importReport ?? gameReport;
  const state = geometrySectionState({
    error,
    hasStaleData: gameReport !== null,
    incompleteImages: activeReport?.images.incomplete ?? 0,
    loading,
    totalImages: activeReport?.images.total ?? 0,
  });
  const processingWithoutGeometry = (activeReport?.sourceStatuses ?? []).filter(
    (entry) =>
      entry.sourceStatus === 'processing' &&
      entry.imageState !== 'complete' &&
      entry.imageState !== 'superseded',
  );
  const supersededImages = activeReport?.images.superseded ?? 0;
  const supersededPositions =
    activeReport?.positions.find((position) => position.state === 'superseded')
      ?.count ?? 0;
  const listVisible =
    activeReport !== null &&
    (activeReport.images.incomplete > 0 || supersededImages > 0);
  const processingCount = processingWithoutGeometry.reduce(
    (sum, entry) => sum + entry.count,
    0,
  );

  return (
    <section
      aria-busy={state === 'loading'}
      aria-labelledby="geometry-completeness-title"
      className="importCompletenessCard"
    >
      <header className="importCompletenessHeader">
        <div>
          <p className="eyebrow">Kompletność siatek zdjęć</p>
          <h3 id="geometry-completeness-title">
            {gameReport
              ? `${gameReport.images.incomplete.toLocaleString('pl-PL')} niekompletnych zdjęć z ${gameReport.images.total.toLocaleString('pl-PL')}`
              : 'Kompletność siatek zdjęć'}
          </h3>
          <p>
            Zdjęcie jest kompletne, gdy każda oczekiwana plansza ma siatkę
            zatwierdzoną przez człowieka albo zaakceptowaną przez silnik bez
            zastrzeżeń. Plansze odrzucone nie są dowodem poprawnej siatki, a
            zdjęcia zastąpione nowszym importem nie są brakami. Widok tylko do
            odczytu; siatki poprawiasz w kolejce siatek.
          </p>
        </div>
        <button
          className="secondaryButton"
          disabled={loading || listLoading}
          onClick={refresh}
          type="button"
        >
          ↻ Odśwież
        </button>
      </header>

      {state === 'loading' && gameReport === null ? (
        <p className="importEmptyState">Ładowanie kompletności siatek…</p>
      ) : null}

      {state === 'error' ? (
        <>
          <p className="feedbackBanner feedbackBannerError" role="alert">
            {error}
          </p>
          <button
            className="secondaryButton"
            onClick={() => void loadReports()}
            type="button"
          >
            Spróbuj ponownie
          </button>
        </>
      ) : null}

      {gameReport !== null && state !== 'error' ? (
        <>
          {error !== null ? (
            <p className="feedbackBanner feedbackBannerError" role="alert">
              Dane mogą być nieaktualne: {error}
            </p>
          ) : null}

          <div className="importSourceControls geometryScopeControls">
            <div
              aria-label="Zakres kompletności"
              className="operationalReviewViewTabs"
              role="group"
            >
              <button
                aria-pressed={scope === 'game'}
                onClick={() => setScope('game')}
                type="button"
              >
                Cała gra
              </button>
              <button
                aria-pressed={scope === 'import'}
                disabled={imports.length === 0}
                onClick={() => {
                  setScope('import');
                  if (importId === '' && imports[0] !== undefined) {
                    setImportId(imports[0].id);
                  }
                }}
                type="button"
              >
                Wybrany import
              </button>
            </div>
            {scope === 'import' ? (
              <label>
                <span>Import</span>
                <select
                  aria-label="Import do sprawdzenia"
                  onChange={(event) => setImportId(event.currentTarget.value)}
                  value={importId}
                >
                  {imports.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>

          <dl className="importMetrics geometryMetrics">
            <div className="importMetric">
              <dt>Zdjęcia w grze</dt>
              <dd>{gameReport.images.total.toLocaleString('pl-PL')}</dd>
            </div>
            <div className="importMetric">
              <dt>Niekompletne w grze</dt>
              <dd>{gameReport.images.incomplete.toLocaleString('pl-PL')}</dd>
            </div>
            {importReport !== null ? (
              <div className="importMetric">
                <dt>Niekompletne w imporcie</dt>
                <dd>
                  {importReport.images.incomplete.toLocaleString('pl-PL')} z{' '}
                  {importReport.images.total.toLocaleString('pl-PL')}
                </dd>
              </div>
            ) : null}
            <div className="importMetric">
              <dt>Zastąpione nowszym importem</dt>
              <dd>
                {(activeReport?.images.superseded ?? 0).toLocaleString('pl-PL')}
              </dd>
            </div>
          </dl>

          {activeReport !== null && activeReport.images.incomplete > 0 ? (
            <p className="importSubsectionHeader">
              {INCOMPLETE_IMAGE_STATES.map((name) => ({
                count: imageStateCount(activeReport, name),
                name,
              }))
                .filter((entry) => entry.count > 0)
                .map(
                  (entry) =>
                    `${geometryImageStateLabel(entry.name)} ${entry.count.toLocaleString('pl-PL')}`,
                )
                .join(' · ')}
              {processingCount > 0
                ? ` · w tym ${processingCount.toLocaleString('pl-PL')} zdjęć w przetwarzaniu`
                : ''}
            </p>
          ) : null}
          {activeReport !== null &&
          activeReport.positions.some(
            (position) =>
              position.state !== 'ok' &&
              position.state !== 'superseded' &&
              position.count > 0,
          ) ? (
            <p className="importSubsectionHeader">
              Plansze bez poprawnej siatki:{' '}
              {activeReport.positions
                .filter(
                  (position) =>
                    position.state !== 'ok' &&
                    position.state !== 'superseded' &&
                    position.count > 0,
                )
                .map(
                  (position) =>
                    `${geometryPositionLabel(position.state, position.reasonCode)} ${position.count.toLocaleString('pl-PL')}`,
                )
                .join(' · ')}
            </p>
          ) : null}
          {supersededImages > 0 || supersededPositions > 0 ? (
            <p className="importSubsectionHeader">
              Zastąpione nowszym importem, więc nie są brakami:{' '}
              {supersededImages.toLocaleString('pl-PL')} zdjęć,{' '}
              {supersededPositions.toLocaleString('pl-PL')} pozycji. Lista
              domyślna ich nie zawiera; filtr „
              {geometryImageStateLabel('superseded')}” je pokazuje.
            </p>
          ) : null}

          {state === 'no-images' ? (
            <p className="importEmptyState">
              Brak zdjęć źródłowych w wybranym zakresie.
            </p>
          ) : null}
          {state === 'all-complete' ? (
            <p className="importEmptyState">
              {supersededImages > 0
                ? 'Wszystkie pozostałe zdjęcia mają komplet poprawnych siatek.'
                : 'Wszystkie zdjęcia mają komplet poprawnych siatek.'}
            </p>
          ) : null}

          {listVisible ? (
            <>
              <div
                aria-label="Filtr stanu zdjęcia"
                className="operationalReviewViewTabs geometryFilterTabs"
                role="group"
              >
                <button
                  aria-pressed={stateFilter === 'all'}
                  onClick={() => setStateFilter('all')}
                  type="button"
                >
                  Wszystkie
                </button>
                {LISTED_IMAGE_STATES.map((name) => (
                  <button
                    aria-pressed={stateFilter === name}
                    key={name}
                    onClick={() => setStateFilter(name)}
                    type="button"
                  >
                    {geometryImageStateLabel(name)}
                  </button>
                ))}
              </div>

              {listError !== null ? (
                <p className="feedbackBanner feedbackBannerError" role="alert">
                  {listError}
                </p>
              ) : null}
              {listLoading && images.length === 0 ? (
                <p className="importEmptyState">Ładowanie listy zdjęć…</p>
              ) : null}
              {!listLoading && listError === null && images.length === 0 ? (
                <p className="importEmptyState">
                  Brak zdjęć w wybranym stanie.
                </p>
              ) : null}

              <ul className="importCompactList geometryImageList">
                {images.map((image) => (
                  <GeometryImageItem
                    api={api}
                    gameId={gameId}
                    image={image}
                    key={image.sourceImageId}
                  />
                ))}
              </ul>
              {nextCursor !== null ? (
                <button
                  className="secondaryButton"
                  disabled={listLoading}
                  onClick={() => void loadImages(nextCursor)}
                  type="button"
                >
                  {listLoading ? 'Ładowanie…' : 'Pokaż więcej zdjęć →'}
                </button>
              ) : null}
            </>
          ) : null}

          <LowQualityBlock
            api={api}
            gameId={gameId}
            importJobId={selectedImportId}
          />
        </>
      ) : null}
    </section>
  );
}

function imageStateCount(
  report: ImageGeometryCompletenessResponse,
  state: ListedImageStateName,
): number {
  switch (state) {
    case 'incomplete_missing':
      return report.images.incompleteMissing;
    case 'incomplete_partial':
      return report.images.incompletePartial;
    case 'incomplete_uncertain':
      return report.images.incompleteUncertain;
    case 'import_failed':
      return report.images.importFailed;
    case 'no_source_geometry':
      return report.images.noSourceGeometry;
    case 'superseded':
      return report.images.superseded;
  }
}

interface GeometryImageItemProps {
  readonly api: ImageFolderImportClient;
  readonly gameId: string;
  readonly image: IncompleteGeometryImageResponse;
}

function GeometryImageItem({ api, gameId, image }: GeometryImageItemProps) {
  const [status, setStatus] = useState<PreviewStatus>('idle');
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const photoUrlRef = useRef<string | null>(null);
  const width = image.orientedWidth;
  const height = image.orientedHeight;
  const canDraw =
    width !== null && height !== null && image.positions.length > 0;

  useEffect(
    () => () => {
      if (photoUrlRef.current !== null) {
        URL.revokeObjectURL(photoUrlRef.current);
        photoUrlRef.current = null;
      }
    },
    [],
  );

  async function showPhoto() {
    setStatus('loading');
    try {
      const asset = await api.getImageGeometryCompletenessSourceAsset(
        gameId,
        image.sourceImageId,
      );
      if (asset.error !== undefined || !(asset.data instanceof Blob)) {
        setStatus('error');
        return;
      }
      if (photoUrlRef.current !== null)
        URL.revokeObjectURL(photoUrlRef.current);
      const url = URL.createObjectURL(asset.data);
      photoUrlRef.current = url;
      setPhotoUrl(url);
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  }

  const fontSize = width === null ? 12 : Math.max(12, Math.round(width / 45));
  const strokeWidth = width === null ? 2 : Math.max(2, Math.round(width / 400));

  return (
    <li className="geometryImageItem">
      <strong>
        {image.relativePath}
        <span className={`geometryStateBadge geometryTone-${imageTone(image)}`}>
          {geometryImageStateLabel(image.imageState)}
        </span>
      </strong>
      <span>
        Status zdjęcia: {geometrySourceStatusLabel(image.sourceStatus)}
        {image.sequenceRangeStart !== null && image.sequenceRangeEnd !== null
          ? ` · numery ${image.sequenceRangeStart.toLocaleString('pl-PL')}–${image.sequenceRangeEnd.toLocaleString('pl-PL')}`
          : ' · brak geometrii źródła, oczekiwana liczba plansz nieznana'}
        {image.expectedBoardCount !== null
          ? ` · oczekiwane plansze: ${image.expectedBoardCount}`
          : ''}
      </span>
      {image.importErrorCode !== null ? (
        <span className="geometryTone-danger">
          Błąd importu pliku: {geometryImportErrorLabel(image.importErrorCode)}
        </span>
      ) : null}

      {canDraw ? (
        <svg
          aria-label={`Zdjęcie ${image.relativePath} z naniesionymi siatkami plansz`}
          className="geometryPreview"
          role="img"
          viewBox={`0 0 ${width} ${height}`}
        >
          <rect fill="rgba(255,255,255,0.04)" height={height} width={width} />
          {photoUrl !== null ? (
            <image
              height={height}
              href={photoUrl}
              preserveAspectRatio="none"
              width={width}
            />
          ) : null}
          {image.positions.map((position) => {
            const points = quadSvgPoints(position.quad);
            if (points === null || !position.quad) return null;
            const centre = quadCentre(position.quad);
            const tone = geometryPositionTone(position.state);
            return (
              <g
                className={`geometryQuad geometryTone-${tone}`}
                key={position.positionIndex}
              >
                <polygon
                  fill="none"
                  points={points}
                  strokeDasharray={tone === 'danger' ? '12 8' : undefined}
                  strokeWidth={strokeWidth}
                />
                <text
                  fontSize={fontSize}
                  textAnchor="middle"
                  x={centre.x}
                  y={centre.y}
                >
                  {position.positionIndex + 1}
                </text>
              </g>
            );
          })}
        </svg>
      ) : null}

      {!canDraw && photoUrl !== null ? (
        // eslint-disable-next-line @next/next/no-img-element -- a blob URL of the checksum-bound source image
        <img
          alt={`Zdjęcie ${image.relativePath}`}
          className="geometryPreview"
          src={photoUrl}
        />
      ) : null}

      {photoUrl === null ? (
        <button
          aria-busy={status === 'loading'}
          className="secondaryButton"
          disabled={status === 'loading'}
          onClick={() => void showPhoto()}
          type="button"
        >
          {status === 'loading' ? 'Pobieranie…' : 'Pokaż zdjęcie pod siatkami'}
        </button>
      ) : null}
      {status === 'error' ? (
        <small className="geometryTone-danger">
          Zdjęcie źródłowe jest niedostępne.
        </small>
      ) : null}

      {image.positions.length > 0 ? (
        <ul className="geometryPositionList">
          {image.positions.map((position) => {
            const tone = geometryPositionTone(position.state);
            return (
              <li
                className={`geometryPositionChip geometryTone-${tone}`}
                key={position.positionIndex}
              >
                <span>
                  {position.positionIndex + 1}. #
                  {position.sequenceNumber.toLocaleString('pl-PL')}
                </span>
                <span>
                  {geometryPositionLabel(position.state, position.reasonCode)}
                  {position.quad === null || position.quad === undefined
                    ? ' · bez siatki'
                    : ''}
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </li>
  );
}

function imageTone(image: IncompleteGeometryImageResponse): string {
  if (image.imageState === 'superseded') return 'muted';
  return image.imageState === 'incomplete_uncertain' ||
    image.imageState === 'incomplete_partial'
    ? 'warning'
    : 'danger';
}

interface LowQualityBlockProps {
  readonly api: ImageFolderImportClient;
  readonly gameId: string;
  readonly importJobId: string | undefined;
}

function LowQualityBlock({ api, gameId, importJobId }: LowQualityBlockProps) {
  const [maxConfidence, setMaxConfidence] = useState(
    String(DEFAULT_LOW_QUALITY_MAX_CONFIDENCE * 100),
  );
  const [minCells, setMinCells] = useState(
    String(DEFAULT_LOW_QUALITY_MIN_CELLS),
  );
  const [validationError, setValidationError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [report, setReport] =
    useState<ImageGeometryLowQualityBoardsResponse | null>(null);
  const requestRef = useRef(0);

  // A result belongs to the scope it was computed for.
  useEffect(() => {
    requestRef.current += 1;
    queueMicrotask(() => {
      setReport(null);
      setError(null);
      setLoading(false);
    });
  }, [gameId, importJobId]);

  async function run() {
    const thresholds = parseLowQualityThresholds(maxConfidence, minCells);
    if (!thresholds.ok) {
      setValidationError(thresholds.error);
      return;
    }
    setValidationError(null);
    const requestId = ++requestRef.current;
    setLoading(true);
    try {
      const result = await api.getImageGeometryLowQualityBoards({
        gameId,
        importJobId,
        limit: LOW_QUALITY_LIMIT,
        maxConfidence: thresholds.maxConfidence,
        minCells: thresholds.minCells,
      });
      if (requestId !== requestRef.current) return;
      if (result.error || !result.data) {
        setReport(null);
        setError(lowQualityErrorMessage(errorCodeOf(result.error)));
        return;
      }
      setReport(result.data);
      setError(null);
    } catch {
      if (requestId !== requestRef.current) return;
      setReport(null);
      setError(lowQualityErrorMessage(null));
    } finally {
      if (requestId === requestRef.current) setLoading(false);
    }
  }

  return (
    <div className="geometryLowQuality">
      <div className="importSubsectionHeader">
        <p>
          <strong>Plansze z niską jakością symboli</strong>
        </p>
        <p>
          Osobne sprawdzenie, uruchamiane ręcznie: plansze, na których co
          najmniej zadaną liczbę pól bez decyzji człowieka model rozpoznał z
          pewnością nie większą niż próg. Może wskazywać błędną siatkę.{' '}
          {importJobId === undefined
            ? 'Obejmuje całą grę i może potrwać kilka sekund.'
            : 'Obejmuje wybrany import.'}
        </p>
      </div>
      <div className="importSourceControls geometryLowQualityControls">
        <label>
          <span>Próg pewności (%)</span>
          <input
            inputMode="decimal"
            onChange={(event) => setMaxConfidence(event.currentTarget.value)}
            type="text"
            value={maxConfidence}
          />
        </label>
        <label>
          <span>Min. liczba pól</span>
          <input
            inputMode="numeric"
            onChange={(event) => setMinCells(event.currentTarget.value)}
            type="text"
            value={minCells}
          />
        </label>
        <button
          aria-busy={loading}
          className="secondaryButton"
          disabled={loading}
          onClick={() => void run()}
          type="button"
        >
          {loading ? 'Sprawdzanie…' : 'Sprawdź jakość symboli'}
        </button>
      </div>
      {validationError !== null ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {validationError}
        </p>
      ) : null}
      {error !== null ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {report !== null ? (
        <>
          <p className="importSubsectionHeader">
            {report.totalBoards.toLocaleString('pl-PL')} plansz z co najmniej{' '}
            {report.minCells} polami o pewności ≤{' '}
            {formatPercent(report.maxConfidence)}
            {report.totalBoards > report.boards.length
              ? ` · pokazano ${report.boards.length}`
              : ''}
          </p>
          {report.boards.length === 0 ? (
            <p className="importEmptyState">
              Żadna plansza nie spełnia tych progów.
            </p>
          ) : (
            <div className="importRowsTableWrap">
              <table className="importRowsTable">
                <thead>
                  <tr>
                    <th>Numer</th>
                    <th>Pola</th>
                    <th>Najniższa pewność</th>
                    <th>Zdjęcie</th>
                  </tr>
                </thead>
                <tbody>
                  {report.boards.map((board) => (
                    <tr key={board.recognizedBoardId}>
                      <td>
                        {board.sequenceNumber === null
                          ? '—'
                          : board.sequenceNumber.toLocaleString('pl-PL')}
                      </td>
                      <td>{board.lowCellCount}</td>
                      <td>{formatPercent(board.minConfidence)}</td>
                      <td>
                        <small>
                          {board.relativePath} · plansza{' '}
                          {board.positionIndex + 1}
                        </small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

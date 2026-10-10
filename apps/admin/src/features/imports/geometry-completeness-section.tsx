'use client';

import type {
  ImageGeometryCompletenessResponse,
  ImageGeometryLowQualityBoardsResponse,
  IncompleteGeometryImageResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  buildPreparedLocalReviewUrl,
  closePreparedLocalReviewerWindow,
  navigatePreparedLocalReviewerWindow,
  prepareLocalReviewerWindow,
} from '../reviewer-access/reviewer-local-window';
import { startLocalReviewerProcess } from '../reviewer-access/reviewer-local-start';
import type { ImageFolderImportClient } from './image-folder-import-actions';
import {
  DEFAULT_LOW_QUALITY_MAX_CONFIDENCE,
  DEFAULT_LOW_QUALITY_MIN_CELLS,
  GEOMETRY_QUEUE_FILTERS,
  INCOMPLETE_IMAGE_STATES,
  LISTED_IMAGE_STATES,
  MAX_GEOMETRY_EXCEPTION_REASON_LENGTH,
  canSetGeometryException,
  canWithdrawGeometryException,
  errorCodeOf,
  formatPercent,
  formatSequenceNumbers,
  geometryCompletenessStatusLabel,
  geometryExceptionErrorMessage,
  geometryGateReasonLabel,
  geometryImageStateLabel,
  geometryImportErrorLabel,
  geometryPositionLabel,
  geometryPositionTone,
  geometryQueueFilterLabel,
  geometryQueueFilterStatus,
  geometryScopeImportId,
  geometrySectionState,
  geometrySourceStatusLabel,
  lowQualityErrorMessage,
  parseLowQualityThresholds,
  quadCentre,
  quadSvgPoints,
  validateGeometryExceptionReason,
  type GeometryImportOption,
  type GeometryQueueFilter,
  type ListedImageStateName,
} from './geometry-completeness-state';

const PAGE_LIMIT = 25;
const LOW_QUALITY_LIMIT = 50;
const POLL_INTERVAL_MS = 15_000;

export type GeometryCompletenessClient = Pick<
  ImageFolderImportClient,
  | 'getImageGeometryCompleteness'
  | 'listIncompleteGeometryImages'
  | 'getImageGeometryCompletenessSourceAsset'
  | 'getImageGeometryLowQualityBoards'
  | 'setSourceImageGeometryException'
  | 'withdrawSourceImageGeometryException'
  | 'startLocalReviewer'
>;

type Scope = 'game' | 'import';
// The queue tabs read the persisted gate status (TASK-0807); the state tabs
// classify the images on the fly (TASK-0806/0808).
type StateFilter = 'all' | ListedImageStateName | GeometryQueueFilter;
type PreviewStatus = 'idle' | 'loading' | 'ready' | 'error';

interface GeometryCompletenessSectionProps {
  readonly api: GeometryCompletenessClient;
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
  const [stateFilter, setStateFilter] = useState<StateFilter>('queue');
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
        const queueFilter = isQueueFilter(stateFilter) ? stateFilter : null;
        const result = await api.listIncompleteGeometryImages({
          afterCursor: afterCursor ?? undefined,
          completenessStatus:
            queueFilter === null
              ? undefined
              : geometryQueueFilterStatus(queueFilter),
          gameId,
          imageState:
            stateFilter === 'all' || isQueueFilter(stateFilter)
              ? undefined
              : stateFilter,
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
  const gate = activeReport?.gate ?? null;
  // D-539 (TASK-0950): only the report of one import carries it.
  const sequenceOwnership = importReport?.sequenceOwnership ?? null;
  const listVisible =
    activeReport !== null &&
    (activeReport.images.incomplete > 0 ||
      supersededImages > 0 ||
      (gate !== null && gate.geometryIncomplete + gate.geometryException > 0));
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
          <p className="eyebrow">Diagnostyka siatek zdjęć</p>
          <h3 id="geometry-completeness-title">
            {gameReport
              ? `${gameReport.images.incomplete.toLocaleString('pl-PL')} niekompletnych zdjęć z ${gameReport.images.total.toLocaleString('pl-PL')}`
              : 'Zdjęcia wymagające sprawdzenia siatek'}
          </h3>
          <p>
            Tutaj sprawdzisz zdjęcia z brakującą, częściową albo niepewną
            siatką. Wybierz zdjęcie i otwórz je do korekty w Reviewerze. W V3
            poprawne pełne siatki są cięte automatycznie, niezależnie od
            problemów pozostałych plansz na zdjęciu. Raport całego zdjęcia nie
            oznacza, że wszystkie jego symbole są niedostępne.
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

          {gate !== null ? (
            <>
              <dl className="importMetrics geometryMetrics">
                <div className="importMetric">
                  <dt>Kolejka siatek (wstrzymane)</dt>
                  <dd>{gate.geometryIncomplete.toLocaleString('pl-PL')}</dd>
                </div>
                <div className="importMetric">
                  <dt>Wyjątki operatora</dt>
                  <dd>{gate.geometryException.toLocaleString('pl-PL')}</dd>
                </div>
                <div className="importMetric">
                  <dt>Plansze wstrzymane przed cięciem</dt>
                  <dd>{gate.withheldBoards.toLocaleString('pl-PL')}</dd>
                </div>
                <div className="importMetric">
                  <dt>Nieocenione przez bramkę</dt>
                  <dd>{gate.notEvaluated.toLocaleString('pl-PL')}</dd>
                </div>
              </dl>
              {gate.withheldBoards > 0 ? (
                <p className="importSubsectionHeader">
                  Powód wstrzymania:{' '}
                  {geometryGateReasonLabel(gate.withheldReasonCode)}.
                </p>
              ) : null}
              {gate.notEvaluated > 0 ? (
                <p className="importSubsectionHeader">
                  {gate.notEvaluated.toLocaleString('pl-PL')} zdjęć nie ma
                  jeszcze stanu bramki (sprzed backfillu); działają jak przed
                  wdrożeniem bramki.
                </p>
              ) : null}
            </>
          ) : null}

          {sequenceOwnership !== null ? (
            <>
              <dl
                aria-label="Sekwencje importu"
                className="importMetrics geometryMetrics"
              >
                <div className="importMetric">
                  <dt>Zastąpione sekwencje</dt>
                  <dd>
                    {sequenceOwnership.replacedCount.toLocaleString('pl-PL')}
                  </dd>
                </div>
                <div className="importMetric">
                  <dt>Pominięte — sekwencja ma właściciela</dt>
                  <dd>
                    {sequenceOwnership.skippedCount.toLocaleString('pl-PL')}
                  </dd>
                </div>
              </dl>
              {sequenceOwnership.replacedCount > 0 ? (
                <p className="importSubsectionHeader">
                  Zastąpione sekwencje (odrzucona plansza innego zdjęcia):{' '}
                  {formatSequenceNumbers(
                    sequenceOwnership.replacedSequenceNumbers,
                    sequenceOwnership.replacedCount,
                  )}
                </p>
              ) : null}
              {sequenceOwnership.skippedCount > 0 ? (
                <p className="importSubsectionHeader">
                  Pominięte, bo sekwencja ma właściciela w innym zdjęciu (aby ją
                  zastąpić, najpierw odrzuć tamtą planszę):{' '}
                  {formatSequenceNumbers(
                    sequenceOwnership.skippedSequenceNumbers,
                    sequenceOwnership.skippedCount,
                  )}
                </p>
              ) : null}
            </>
          ) : null}

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
                {GEOMETRY_QUEUE_FILTERS.map((filter) => (
                  <button
                    aria-pressed={stateFilter === filter}
                    key={filter}
                    onClick={() => setStateFilter(filter)}
                    type="button"
                  >
                    {geometryQueueFilterLabel(filter)}
                  </button>
                ))}
                <button
                  aria-pressed={stateFilter === 'all'}
                  onClick={() => setStateFilter('all')}
                  type="button"
                >
                  Wszystkie niekompletne
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
                    onChanged={refresh}
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

function isQueueFilter(filter: StateFilter): filter is GeometryQueueFilter {
  return (GEOMETRY_QUEUE_FILTERS as readonly string[]).includes(filter);
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
  readonly api: GeometryCompletenessClient;
  readonly gameId: string;
  readonly image: IncompleteGeometryImageResponse;
  /** Refreshes the counters and the queue after a gate decision. */
  readonly onChanged: () => void;
}

function GeometryImageItem({
  api,
  gameId,
  image,
  onChanged,
}: GeometryImageItemProps) {
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
      <GeometryGateControls
        api={api}
        gameId={gameId}
        image={image}
        onChanged={onChanged}
      />

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

interface GeometryGateControlsProps {
  readonly api: GeometryCompletenessClient;
  readonly gameId: string;
  readonly image: IncompleteGeometryImageResponse;
  readonly onChanged: () => void;
}

/** Persisted gate status, the operator exception and the grid correction link. */
function GeometryGateControls({
  api,
  gameId,
  image,
  onChanged,
}: GeometryGateControlsProps) {
  const [reason, setReason] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lock = useRef(false);
  const status = image.completenessStatus;

  async function setException() {
    const validated = validateGeometryExceptionReason(reason);
    if (!validated.ok) {
      setError(validated.error);
      return;
    }
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await api.setSourceImageGeometryException(
        gameId,
        image.sourceImageId,
        validated.reason,
      );
      if (result.error !== undefined || !result.data) {
        setError(geometryExceptionErrorMessage(errorCodeOf(result.error)));
        return;
      }
      setFormOpen(false);
      setReason('');
      onChanged();
    } catch {
      setError(geometryExceptionErrorMessage(null));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  async function withdrawException() {
    if (lock.current) return;
    if (
      !window.confirm(
        'Wycofać wyjątek? Zdjęcie wróci do kolejki siatek; komórki pozostaną bez zmian.',
      )
    ) {
      return;
    }
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await api.withdrawSourceImageGeometryException(
        gameId,
        image.sourceImageId,
      );
      if (result.error !== undefined || !result.data) {
        setError(geometryExceptionErrorMessage(errorCodeOf(result.error)));
        return;
      }
      onChanged();
    } catch {
      setError(geometryExceptionErrorMessage(null));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  async function correctGrids() {
    if (lock.current) return;
    const input = { gameId, importJobId: image.importJobId };
    const base = buildPreparedLocalReviewUrl(window.location.href, input);
    if (!base) {
      setError('Korekta siatek jest dostępna tylko w lokalnym Adminie.');
      return;
    }
    const popup = prepareLocalReviewerWindow(
      window.location.href,
      input,
      (url, target) => window.open(url, target),
    );
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await startLocalReviewerProcess(api);
      if (!result.ok) {
        closePreparedLocalReviewerWindow(popup);
        setError(result.error);
        return;
      }
      if (!popup || !navigatePreparedLocalReviewerWindow(popup, base)) {
        setError(
          'Przeglądarka zablokowała otwarcie Reviewera. Zezwól na nowe okno i spróbuj ponownie.',
        );
      }
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="geometryGateControls">
      <span>
        Bramka: {geometryCompletenessStatusLabel(status)}
        {image.gateReasonCode !== null
          ? ` · ${geometryGateReasonLabel(image.gateReasonCode)}`
          : ''}
      </span>
      {status === 'geometry_exception' ? (
        <span>
          Wyjątek: {image.exceptionReason}
          {image.exceptionBy !== null ? ` · ${image.exceptionBy}` : ''}
          {image.exceptionAt !== null
            ? ` · ${new Date(image.exceptionAt).toLocaleString('pl-PL')}`
            : ''}
        </span>
      ) : null}
      <div className="importSourceControls">
        {status === 'geometry_incomplete' ? (
          <button
            className="secondaryButton"
            disabled={busy}
            onClick={() => void correctGrids()}
            type="button"
          >
            Popraw siatki w Reviewerze
          </button>
        ) : null}
        {canSetGeometryException(status) && !formOpen ? (
          <button
            className="secondaryButton"
            disabled={busy}
            onClick={() => setFormOpen(true)}
            type="button"
          >
            Dopuść wyjątkiem…
          </button>
        ) : null}
        {canWithdrawGeometryException(status) ? (
          <button
            className="secondaryButton"
            disabled={busy}
            onClick={() => void withdrawException()}
            type="button"
          >
            {busy ? 'Zapisywanie…' : 'Wycofaj wyjątek'}
          </button>
        ) : null}
      </div>
      {formOpen ? (
        <div className="importSourceControls">
          <label>
            <span>Powód wyjątku (np. plansza poza kadrem)</span>
            <input
              maxLength={MAX_GEOMETRY_EXCEPTION_REASON_LENGTH}
              onChange={(event) => setReason(event.currentTarget.value)}
              type="text"
              value={reason}
            />
          </label>
          <button
            aria-busy={busy}
            className="secondaryButton"
            disabled={busy}
            onClick={() => void setException()}
            type="button"
          >
            {busy ? 'Zapisywanie…' : 'Dopuść zdjęcie do cięcia'}
          </button>
          <button
            className="secondaryButton"
            disabled={busy}
            onClick={() => {
              setFormOpen(false);
              setError(null);
            }}
            type="button"
          >
            Anuluj
          </button>
        </div>
      ) : null}
      {error !== null ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

interface LowQualityBlockProps {
  readonly api: GeometryCompletenessClient;
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

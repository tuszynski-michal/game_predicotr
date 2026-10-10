'use client';

import type {
  ImageGeometryCompletenessResponse,
  ImageGeometryLowQualityBoardsResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useRef, useState } from 'react';

import type { ImageFolderImportClient } from './image-folder-import-actions';
import {
  DEFAULT_LOW_QUALITY_MAX_CONFIDENCE,
  DEFAULT_LOW_QUALITY_MIN_CELLS,
  INCOMPLETE_IMAGE_STATES,
  errorCodeOf,
  formatPercent,
  formatSequenceNumbers,
  geometryGapCounts,
  geometryGateReasonLabel,
  geometryImageStateLabel,
  geometryPositionLabel,
  geometryScopeImportId,
  geometrySectionState,
  lowQualityErrorMessage,
  parseLowQualityThresholds,
  type GeometryImportOption,
  type IncompleteImageStateName,
} from './geometry-completeness-state';

const LOW_QUALITY_LIMIT = 50;
const POLL_INTERVAL_MS = 15_000;

export type GeometryCompletenessClient = Pick<
  ImageFolderImportClient,
  'getImageGeometryCompleteness' | 'getImageGeometryLowQualityBoards'
>;

type Scope = 'game' | 'import';

interface GeometryCompletenessSectionProps {
  readonly api: GeometryCompletenessClient;
  readonly gameId: string;
  readonly imports: readonly GeometryImportOption[];
  /** Polling of the counters runs only while an import is being processed. */
  readonly importActive: boolean;
  readonly refreshToken: number;
  /** Opens the local Reviewer on the game's photo gaps (owned by the launcher). */
  readonly onOpenReviewer: () => void;
  readonly openReviewerDisabled?: boolean;
}

export function GeometryCompletenessSection({
  api,
  gameId,
  imports,
  importActive,
  onOpenReviewer,
  openReviewerDisabled = false,
  refreshToken,
}: GeometryCompletenessSectionProps) {
  const [scope, setScope] = useState<Scope>('game');
  const [importId, setImportId] = useState('');
  const [gameReport, setGameReport] =
    useState<ImageGeometryCompletenessResponse | null>(null);
  const [importReport, setImportReport] =
    useState<ImageGeometryCompletenessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const reportRequestRef = useRef(0);

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

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void loadReports();
    });
    return () => {
      cancelled = true;
    };
  }, [loadReports, refreshToken]);

  // Only the counters are polled, and only while an import runs.
  useEffect(() => {
    if (!importActive) return;
    const interval = window.setInterval(() => {
      void loadReports({ silent: true });
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [importActive, loadReports]);

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
  // D-543 (TASK-0971): only the report of one import carries it.
  const sequenceOwnership = importReport?.sequenceOwnership ?? null;
  const processingCount = processingWithoutGeometry.reduce(
    (sum, entry) => sum + entry.count,
    0,
  );
  const gaps =
    gameReport === null ? null : geometryGapCounts(gameReport.images);

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
            {gaps !== null
              ? `${gaps.realGaps.toLocaleString('pl-PL')} zdjęć z realnymi brakami · ${gaps.unconfirmed.toLocaleString('pl-PL')} z niepotwierdzoną siatką`
              : 'Zdjęcia wymagające sprawdzenia siatek'}
          </h3>
          <p>
            Realne braki to zdjęcia, którym brakuje plansz, mają planszę
            częściową, nieudany import albo nie mają geometrii źródła.
            „Niepotwierdzona” oznacza automatyczną siatkę bez ręcznego
            zatwierdzenia i nie jest błędem cięcia. W V3 poprawne pełne siatki
            są cięte automatycznie, niezależnie od problemów pozostałych plansz
            na zdjęciu. Braki poprawia się w Reviewerze.
          </p>
        </div>
        <div className="importSourceControls">
          <button
            className="secondaryButton"
            disabled={openReviewerDisabled}
            onClick={onOpenReviewer}
            type="button"
          >
            Otwórz braki w Reviewerze
          </button>
          <button
            className="secondaryButton"
            disabled={loading}
            onClick={() => void loadReports()}
            type="button"
          >
            ↻ Odśwież
          </button>
        </div>
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
              {supersededPositions.toLocaleString('pl-PL')} pozycji.
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
  state: IncompleteImageStateName,
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
  }
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

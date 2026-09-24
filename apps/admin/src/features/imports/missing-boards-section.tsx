'use client';

import type {
  BoardImportCoverageResponse,
  BoardImportCoverageView,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useRef, useState } from 'react';

import type { ImageFolderImportClient } from './image-folder-import-actions';
import {
  formatSegmentRange,
  missingReasonLabel,
  parseSequenceRangeQuery,
  summaryState,
} from './missing-boards-state';

const PAGE_LIMIT = 100;
const POLL_INTERVAL_MS = 15_000;

interface CommittedRange {
  readonly from: number;
  readonly to: number;
}

interface MissingBoardsSectionProps {
  readonly api: ImageFolderImportClient;
  readonly gameId: string;
  readonly refreshToken: number;
}

export function MissingBoardsSection({
  api,
  gameId,
  refreshToken,
}: MissingBoardsSectionProps) {
  const [view, setView] = useState<BoardImportCoverageView>('missing');
  const [rangeInput, setRangeInput] = useState('');
  const [rangeError, setRangeError] = useState<string | null>(null);
  const [committedRange, setCommittedRange] = useState<CommittedRange | null>(
    null,
  );
  const [afterSequenceNumber, setAfterSequenceNumber] = useState<number | null>(
    null,
  );
  const [report, setReport] = useState<BoardImportCoverageResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const load = useCallback(
    async (options?: { readonly silent?: boolean }) => {
      const requestId = ++requestIdRef.current;
      if (!options?.silent) setLoading(true);
      try {
        const result = await api.getBoardImportCoverage({
          afterSequenceNumber: afterSequenceNumber ?? undefined,
          from: committedRange?.from,
          gameId,
          limit: PAGE_LIMIT,
          to: committedRange?.to,
          view,
        });
        if (requestId !== requestIdRef.current) return;
        if (result.error || !result.data) {
          setError('Nie udało się pobrać pokrycia importu plansz.');
          return;
        }
        setReport(result.data);
        setError(null);
      } catch {
        if (requestId !== requestIdRef.current) return;
        setError('Nie udało się pobrać pokrycia importu plansz.');
      } finally {
        if (requestId === requestIdRef.current) setLoading(false);
      }
    },
    [afterSequenceNumber, api, committedRange, gameId, view],
  );

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void load();
    });
    return () => {
      cancelled = true;
    };
  }, [load, refreshToken]);

  useEffect(() => {
    if (report === null || report.notices.activeImportJobCount <= 0) return;
    const interval = window.setInterval(() => {
      void load({ silent: true });
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [load, report]);

  function handleViewChange(nextView: BoardImportCoverageView) {
    if (nextView === view) return;
    setView(nextView);
    setAfterSequenceNumber(null);
  }

  function handleSearch() {
    const expected = report?.expectedLayoutCount ?? Number.MAX_SAFE_INTEGER;
    const result = parseSequenceRangeQuery(rangeInput, expected);
    if (!result.ok) {
      setRangeError(result.error);
      return;
    }
    setRangeError(null);
    setCommittedRange(result.range);
    setAfterSequenceNumber(null);
  }

  const state = summaryState({
    countsAdded: report?.counts.added ?? 0,
    countsMissing: report?.counts.missing ?? 0,
    error,
    expectedLayoutCount: report?.expectedLayoutCount ?? null,
    hasStaleData: report !== null,
    loading,
    missingByReason: report?.missingByReason ?? {},
    segmentCount: report?.segments.length ?? 0,
  });

  return (
    <section
      aria-labelledby="missing-boards-title"
      aria-busy={state === 'loading'}
      className="importCompletenessCard"
    >
      <header className="importCompletenessHeader">
        <div>
          <p className="eyebrow">Brakujące plansze</p>
          <h3 id="missing-boards-title">
            {report
              ? `${report.counts.added.toLocaleString('pl-PL')} / ${report.expectedLayoutCount.toLocaleString('pl-PL')}`
              : 'Brakujące plansze'}
          </h3>
          <p>
            Plansze bez ukończonego importu (pocięte na symbole i zapisane).
            Zatwierdzenie symboli nie jest wymagane.
          </p>
        </div>
        <button
          className="secondaryButton"
          disabled={loading}
          onClick={() => void load()}
          type="button"
        >
          ↻ Odśwież
        </button>
      </header>

      {state === 'loading' && report === null ? (
        <p className="importEmptyState">Ładowanie pokrycia importu…</p>
      ) : null}

      {state === 'error' ? (
        <>
          <p className="feedbackBanner feedbackBannerError" role="alert">
            {error}
          </p>
          <button
            className="secondaryButton"
            onClick={() => void load()}
            type="button"
          >
            Spróbuj ponownie
          </button>
        </>
      ) : null}

      {state === 'unknown-target' ? (
        <p className="importEmptyState">
          Nie znamy oczekiwanej liczby plansz — ustaw cel kompletności w
          Katalogu gier.
        </p>
      ) : null}

      {report !== null && state !== 'error' && state !== 'unknown-target' ? (
        <>
          {error !== null ? (
            <p className="feedbackBanner feedbackBannerError" role="alert">
              Dane mogą być nieaktualne: {error}
            </p>
          ) : null}

          <dl className="importMetrics">
            <div className="importMetric">
              <dt>Oczekiwane</dt>
              <dd>{report.expectedLayoutCount.toLocaleString('pl-PL')}</dd>
            </div>
            <div className="importMetric">
              <dt>Dodane</dt>
              <dd>{report.counts.added.toLocaleString('pl-PL')}</dd>
            </div>
            <div className="importMetric">
              <dt>Brakujące</dt>
              <dd>{report.counts.missing.toLocaleString('pl-PL')}</dd>
            </div>
          </dl>
          <p className="importSubsectionHeader">
            w tym zatwierdzone: {report.counts.approved.toLocaleString('pl-PL')}
            {report.counts.outOfRange > 0
              ? ` · poza zakresem: ${report.counts.outOfRange.toLocaleString('pl-PL')}`
              : ''}{' '}
            · cel z ustawień gry (Katalog gier)
          </p>

          {Object.entries(report.missingByReason).some(
            ([, count]) => count > 0,
          ) ? (
            <p className="importSubsectionHeader">
              Powody:{' '}
              {Object.entries(report.missingByReason)
                .filter(([, count]) => count > 0)
                .map(
                  ([reason, count]) =>
                    `${missingReasonLabel(reason)} ${count.toLocaleString('pl-PL')}`,
                )
                .join(' · ')}
            </p>
          ) : null}

          {report.notices.unnumberedCutBoardCount > 0 ||
          report.notices.failedSourcesWithoutRangeCount > 0 ||
          report.notices.activeImportJobCount > 0 ||
          report.notices.activeSourcesWithoutRangeCount > 0 ? (
            <p className="feedbackBanner">
              {[
                report.notices.unnumberedCutBoardCount > 0
                  ? `${report.notices.unnumberedCutBoardCount.toLocaleString('pl-PL')} pociętych plansz bez ustalonego numeru`
                  : null,
                report.notices.failedSourcesWithoutRangeCount > 0
                  ? `${report.notices.failedSourcesWithoutRangeCount.toLocaleString('pl-PL')} zdjęć z błędem bez znanego zakresu numerów`
                  : null,
                report.notices.activeImportJobCount > 0
                  ? `${report.notices.activeImportJobCount.toLocaleString('pl-PL')} aktywnych jobów importu`
                  : null,
                report.notices.activeSourcesWithoutRangeCount > 0
                  ? `${report.notices.activeSourcesWithoutRangeCount.toLocaleString('pl-PL')} aktywnych zdjęć bez znanego zakresu numerów`
                  : null,
              ]
                .filter((line) => line !== null)
                .join(' · ')}
              . Część brakujących numerów może już istnieć jako plansza bez
              ustalonego numeru — sprawdź Zatwierdzanie.
            </p>
          ) : null}

          <div
            aria-label="Widok pokrycia"
            className="operationalReviewViewTabs"
            role="group"
          >
            <button
              aria-pressed={view === 'missing'}
              onClick={() => handleViewChange('missing')}
              type="button"
            >
              Brakujące
            </button>
            <button
              aria-pressed={view === 'added'}
              onClick={() => handleViewChange('added')}
              type="button"
            >
              Dodane
            </button>
          </div>

          <div className="importSourceControls">
            <label>
              <span>Numer lub zakres</span>
              <input
                aria-label="Numer lub zakres sekwencji"
                onChange={(event) => setRangeInput(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') handleSearch();
                }}
                placeholder="np. 1200-1500"
                type="text"
                value={rangeInput}
              />
            </label>
            <button
              className="secondaryButton"
              onClick={handleSearch}
              type="button"
            >
              Szukaj
            </button>
          </div>
          {rangeError ? (
            <p className="feedbackBanner feedbackBannerError" role="alert">
              {rangeError}
            </p>
          ) : null}
          {report.range !== null && report.rangeCounts !== null ? (
            <p className="importSubsectionHeader">
              W zakresie{' '}
              {formatSegmentRange(report.range.from, report.range.to)}: dodane{' '}
              {report.rangeCounts.added.toLocaleString('pl-PL')} · brakujące{' '}
              {report.rangeCounts.missing.toLocaleString('pl-PL')}
            </p>
          ) : null}

          {state === 'empty' ? (
            <p className="importEmptyState">
              Nie dodano jeszcze żadnej planszy.
            </p>
          ) : null}
          {state === 'all-added' ? (
            <p className="importEmptyState">
              Wszystkie oczekiwane plansze są dodane.
            </p>
          ) : null}
          {state === 'no-results' ? (
            <p className="importEmptyState">
              Brak {report.view === 'missing' ? 'brakujących' : 'dodanych'}{' '}
              plansz w wybranym zakresie.
            </p>
          ) : null}

          {report.segments.length > 0 ? (
            <div className="importRowsTableWrap">
              <table className="importRowsTable">
                <thead>
                  <tr>
                    <th>Zakres</th>
                    <th>Liczba</th>
                    <th>Stan</th>
                  </tr>
                </thead>
                <tbody>
                  {report.segments.map((segment) => (
                    <tr key={`${segment.start}-${segment.end}`}>
                      <td>{formatSegmentRange(segment.start, segment.end)}</td>
                      <td>{segment.count.toLocaleString('pl-PL')}</td>
                      <td>
                        {report.view === 'added'
                          ? 'Dodana'
                          : missingReasonLabel(segment.state)}
                        {segment.geometryReasonCode
                          ? ` · ${segment.geometryReasonCode}`
                          : ''}
                        {segment.errorCode ? ` · ${segment.errorCode}` : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {report.nextAfterSequenceNumber !== null ? (
            <button
              className="secondaryButton"
              onClick={() =>
                setAfterSequenceNumber(report.nextAfterSequenceNumber)
              }
              type="button"
            >
              Następna strona →
            </button>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

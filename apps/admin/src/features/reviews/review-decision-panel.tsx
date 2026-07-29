'use client';

import type {
  ReviewBatchResponse,
  ReviewFeedbackExportResponse,
  ReviewItemResponse,
  ReviewResolutionAction,
  ReviewResolutionResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useState } from 'react';

import {
  type ReviewsClient,
  createReviewFeedbackExport,
  loadReviewFeedbackExports,
  loadReviewResolutions,
  submitReviewResolution,
} from './review-actions';
import { reviewStatusLabel } from './review-state';

const DEFAULT_ACTOR = 'local-admin';

export function ReviewDecisionPanel({
  api,
  item,
  onResolved,
  symbols,
}: {
  readonly api: ReviewsClient;
  readonly item: ReviewItemResponse;
  readonly onResolved: (item: ReviewItemResponse) => void;
  readonly symbols: readonly SymbolResponse[];
}) {
  const [labels, setLabels] = useState<readonly string[]>(() =>
    initialLabels(item),
  );
  const [geometryAccepted, setGeometryAccepted] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [resolvedBy, setResolvedBy] = useState(DEFAULT_ACTOR);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [history, setHistory] = useState<readonly ReviewResolutionResponse[]>(
    [],
  );

  useEffect(() => {
    queueMicrotask(
      () => void refreshHistory(api, item.id, setHistory, setError),
    );
  }, [api, item]);

  const predictionLabels = useMemo(
    () => item.snapshot.cells.map((cell) => cell.predictedSymbolCode),
    [item],
  );
  const changedCount = labels.reduce(
    (count, label, index) => count + Number(label !== predictionLabels[index]),
    0,
  );
  const actorValid = resolvedBy.trim().length > 0;

  async function resolve(action: ReviewResolutionAction) {
    setBusy(true);
    setError('');
    setMessage('');
    const result = await submitReviewResolution(api, item.id, {
      action,
      expectedRevision: item.resolutionRevision,
      geometryAccepted: action === 'rejected' ? false : geometryAccepted,
      idempotencyKey: crypto.randomUUID(),
      labels:
        action === 'rejected'
          ? []
          : item.snapshot.cells.map((cell) => ({
              cellIndex: cell.cellIndex,
              sampleId: cell.sampleId,
              symbolCode: labels[cell.cellIndex] ?? cell.predictedSymbolCode,
            })),
      rejectionReason:
        action === 'rejected' ? rejectionReason.trim() : undefined,
      resolvedBy: resolvedBy.trim(),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    onResolved(result.item);
    setMessage(
      result.created
        ? `Zapisano rewizję ${result.resolution.revision}.`
        : `Ta sama akcja była już zapisana jako rewizja ${result.resolution.revision}.`,
    );
    await refreshHistory(api, item.id, setHistory, setError);
  }

  return (
    <section
      className="reviewDecisionPanel"
      aria-labelledby="review-decision-title"
    >
      <header>
        <div>
          <p className="eyebrow">Decyzja całej planszy</p>
          <h3 id="review-decision-title">Etykiety i audyt</h3>
        </div>
        <span className="statusPill">{reviewStatusLabel(item.status)}</span>
      </header>

      <div className="reviewDecisionMeta">
        <label>
          Administrator
          <input
            maxLength={200}
            onChange={(event) => setResolvedBy(event.target.value)}
            value={resolvedBy}
          />
        </label>
        <label className="reviewGeometryConfirmation">
          <input
            checked={geometryAccepted}
            onChange={(event) => setGeometryAccepted(event.target.checked)}
            type="checkbox"
          />
          Potwierdzam poprawną geometrię i komplet 15 cropów
        </label>
      </div>

      <div className="reviewLabelEditor" aria-label="Korekta 15 symboli">
        {item.snapshot.cells.map((cell) => (
          <label key={cell.sampleId}>
            R{cell.rowIndex + 1} C{cell.columnIndex + 1}
            <select
              aria-label={`Symbol R${cell.rowIndex + 1} C${
                cell.columnIndex + 1
              }`}
              disabled={busy}
              onChange={(event) =>
                setLabels((current) =>
                  current.map((value, index) =>
                    index === cell.cellIndex ? event.target.value : value,
                  ),
                )
              }
              value={labels[cell.cellIndex] ?? cell.predictedSymbolCode}
            >
              {symbols.map((symbol) => (
                <option key={symbol.id} value={symbol.code}>
                  {symbol.name} ({symbol.code})
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <p className="reviewCorrectionSummary">
        Zmienione symbole: <strong>{changedCount}</strong> z 15
      </p>

      <label>
        Powód odrzucenia
        <textarea
          maxLength={500}
          onChange={(event) => setRejectionReason(event.target.value)}
          placeholder="Wymagany tylko przy odrzuceniu planszy"
          value={rejectionReason}
        />
      </label>

      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {message ? (
        <p className="feedbackBanner feedbackBannerSuccess" role="status">
          {message}
        </p>
      ) : null}

      <div className="rowActions reviewDecisionActions">
        <button
          className="primaryButton"
          disabled={
            busy || !actorValid || !geometryAccepted || changedCount !== 0
          }
          onClick={() => void resolve('accepted')}
          type="button"
        >
          Zatwierdź predykcje
        </button>
        <button
          className="secondaryButton"
          disabled={
            busy || !actorValid || !geometryAccepted || changedCount === 0
          }
          onClick={() => void resolve('corrected')}
          type="button"
        >
          Zapisz korektę
        </button>
        <button
          className="dangerButton"
          disabled={busy || !actorValid || rejectionReason.trim().length === 0}
          onClick={() => void resolve('rejected')}
          type="button"
        >
          Odrzuć planszę
        </button>
      </div>

      <ReviewHistory history={history} />
    </section>
  );
}

export function ReviewFeedbackExportsPanel({
  api,
  batch,
}: {
  readonly api: ReviewsClient;
  readonly batch: ReviewBatchResponse;
}) {
  const [exports, setExports] = useState<
    readonly ReviewFeedbackExportResponse[]
  >([]);
  const [createdBy, setCreatedBy] = useState(DEFAULT_ACTOR);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    queueMicrotask(
      () => void refreshExports(api, batch.id, setExports, setError),
    );
  }, [api, batch.id]);

  async function createExport() {
    setBusy(true);
    setError('');
    setMessage('');
    const result = await createReviewFeedbackExport(
      api,
      batch.id,
      createdBy.trim(),
    );
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setMessage(
      result.created
        ? `Utworzono feedback v${result.feedbackExport.version}.`
        : `Stan jest już zamrożony jako feedback v${result.feedbackExport.version}.`,
    );
    await refreshExports(api, batch.id, setExports, setError);
  }

  return (
    <section
      className="reviewExportsPanel"
      aria-labelledby="review-export-title"
    >
      <div>
        <p className="eyebrow">Niezmienny dataset</p>
        <h2 id="review-export-title">Eksport oznaczonego feedbacku</h2>
        <p>
          Eksport jest dostępny dopiero po rozwiązaniu wszystkich plansz.
          Odrzucone elementy nie trafiają do próbek.
        </p>
      </div>
      <label>
        Autor eksportu
        <input
          maxLength={200}
          onChange={(event) => setCreatedBy(event.target.value)}
          value={createdBy}
        />
      </label>
      <button
        className="secondaryButton"
        disabled={busy || createdBy.trim().length === 0}
        onClick={() => void createExport()}
        type="button"
      >
        {busy ? 'Tworzenie…' : 'Utwórz nową wersję feedbacku'}
      </button>
      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {message ? (
        <p className="feedbackBanner feedbackBannerSuccess" role="status">
          {message}
        </p>
      ) : null}
      <ol className="reviewExportList">
        {exports.map((feedbackExport) => (
          <li key={feedbackExport.id}>
            <strong>v{feedbackExport.version}</strong>
            <span>{feedbackExport.sampleCount} próbek</span>
            <span>{feedbackExport.rejectedItemCount} odrzuconych plansz</span>
            <code>{feedbackExport.payloadSha256.slice(0, 12)}…</code>
          </li>
        ))}
      </ol>
    </section>
  );
}

function ReviewHistory({
  history,
}: {
  readonly history: readonly ReviewResolutionResponse[];
}) {
  return (
    <section className="reviewHistory" aria-labelledby="review-history-title">
      <h4 id="review-history-title">Historia decyzji</h4>
      {history.length === 0 ? (
        <p>Brak zapisanych decyzji.</p>
      ) : (
        <ol>
          {history.map((entry) => (
            <li key={entry.id}>
              <strong>Rewizja {entry.revision}</strong>
              <span>{reviewStatusLabel(entry.action)}</span>
              <span>{entry.resolvedBy}</span>
              <time dateTime={entry.createdAt}>
                {new Date(entry.createdAt).toLocaleString('pl-PL')}
              </time>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function initialLabels(item: ReviewItemResponse): readonly string[] {
  const resolvedCells = item.resolvedValue?.cells;
  if (Array.isArray(resolvedCells) && resolvedCells.length === 15) {
    const labels = resolvedCells.map((cell) =>
      typeof cell === 'object' &&
      cell !== null &&
      'symbolCode' in cell &&
      typeof cell.symbolCode === 'string'
        ? cell.symbolCode
        : '',
    );
    if (labels.every((label) => label !== '')) return labels;
  }
  return item.snapshot.cells.map((cell) => cell.predictedSymbolCode);
}

async function refreshHistory(
  api: ReviewsClient,
  itemId: string,
  setHistory: (history: readonly ReviewResolutionResponse[]) => void,
  setError: (error: string) => void,
) {
  const result = await loadReviewResolutions(api, itemId);
  if (result.ok) setHistory(result.resolutions);
  else setError(result.error);
}

async function refreshExports(
  api: ReviewsClient,
  batchId: string,
  setExports: (exports: readonly ReviewFeedbackExportResponse[]) => void,
  setError: (error: string) => void,
) {
  const result = await loadReviewFeedbackExports(api, batchId);
  if (result.ok) setExports(result.feedbackExports);
  else setError(result.error);
}

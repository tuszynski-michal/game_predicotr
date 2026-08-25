'use client';

import type {
  DatasetValidationReportResponse,
  DatasetVersionResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  type DatasetsClient,
  getDatasetValidationReport,
  publishDataset,
} from './dataset-actions';
import { DatasetValidationReport } from './dataset-validation-report';

interface DatasetPublicationModalProps {
  readonly api: DatasetsClient;
  readonly dataset: DatasetVersionResponse;
  readonly onClose: () => void;
  readonly onPublished: (dataset: DatasetVersionResponse) => void;
}

export function DatasetPublicationModal({
  api,
  dataset,
  onClose,
  onPublished,
}: DatasetPublicationModalProps) {
  const [report, setReport] = useState<DatasetValidationReportResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [confirmed, setConfirmed] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState('');
  const requestId = useRef(0);
  const mutationInProgress = useRef(false);

  const loadReport = useCallback(
    async (clearError = true) => {
      const currentRequest = ++requestId.current;
      setLoading(true);
      setConfirmed(false);
      if (clearError) setError('');
      const result = await getDatasetValidationReport(api, dataset.id);
      if (currentRequest !== requestId.current) return;
      setLoading(false);
      if (!result.ok) {
        setError(result.error);
        setReport(null);
        return;
      }
      setReport(result.report);
    },
    [api, dataset.id],
  );

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void loadReport();
    });
    return () => {
      cancelled = true;
      requestId.current += 1;
    };
  }, [loadReport]);

  async function confirmPublication() {
    if (
      mutationInProgress.current ||
      !confirmed ||
      report?.readyForPublication !== true
    ) {
      return;
    }
    mutationInProgress.current = true;
    setPublishing(true);
    setError('');
    const result = await publishDataset(api, dataset.id);
    mutationInProgress.current = false;
    setPublishing(false);
    if (!result.ok) {
      setError(result.error);
      await loadReport(false);
      return;
    }
    onPublished(result.dataset);
  }

  return (
    <dialog
      aria-labelledby="dataset-publication-title"
      aria-modal="true"
      className="paylineDialog"
      open
    >
      <div className="paylineDialogCard publicationDialogCard">
        <header className="paylineDialogHeader">
          <div>
            <p className="eyebrow">
              Dataset v{dataset.version} · {dataset.layoutCount} plansz
            </p>
            <h2 id="dataset-publication-title">Publikacja datasetu</h2>
          </div>
          <button
            aria-label="Zamknij modal publikacji datasetu"
            className="iconButton"
            disabled={publishing}
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>

        {loading ? (
          <div className="modalState">
            <span className="loadingMark" />
            <div>
              <h3>Sprawdzanie integralności</h3>
              <p>Weryfikuję cały bounded dataset przed potwierdzeniem…</p>
            </div>
          </div>
        ) : report ? (
          <div className="publicationSummary">
            <DatasetValidationReport report={report} />
            {error ? (
              <p className="feedbackBanner feedbackBannerError" role="alert">
                {error}
              </p>
            ) : null}
            {report.readyForPublication ? (
              <label className="publicationConfirmation">
                <input
                  checked={confirmed}
                  disabled={publishing}
                  onChange={(event) => setConfirmed(event.target.checked)}
                  type="checkbox"
                />
                Rozumiem, że opublikowany dataset będzie niezmienny.
              </label>
            ) : (
              <p className="datasetDiagnosticNote">
                Usuń wszystkie blokady. Ostrzeżenia o duplikatach są dozwolone.
              </p>
            )}
            <div className="formActions">
              <button
                className="textButton"
                disabled={publishing}
                onClick={onClose}
                type="button"
              >
                Anuluj
              </button>
              {report.readyForPublication ? (
                <button
                  className="primaryButton"
                  disabled={!confirmed || publishing}
                  onClick={() => void confirmPublication()}
                  type="button"
                >
                  {publishing ? 'Publikowanie…' : 'Opublikuj dataset'}
                </button>
              ) : (
                <button
                  className="secondaryButton"
                  onClick={() => void loadReport()}
                  type="button"
                >
                  Sprawdź ponownie
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="modalState">
            <span className="stateIcon">!</span>
            <div>
              <h3>Nie udało się sprawdzić datasetu</h3>
              <p role="alert">{error}</p>
              <button
                className="secondaryButton"
                onClick={() => void loadReport()}
                type="button"
              >
                Spróbuj ponownie
              </button>
            </div>
          </div>
        )}
      </div>
    </dialog>
  );
}

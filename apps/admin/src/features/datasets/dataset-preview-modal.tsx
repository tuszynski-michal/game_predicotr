'use client';

import type {
  DatasetLayoutPageResponse,
  DatasetLayoutResponse,
  DatasetVersionResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { type DatasetsClient, listDatasetLayouts } from './dataset-actions';

const PREVIEW_PAGE_SIZE = 12;

interface DatasetPreviewModalProps {
  readonly api: DatasetsClient;
  readonly dataset: DatasetVersionResponse;
  readonly onClose: () => void;
  readonly symbols: readonly SymbolResponse[];
}

export function DatasetPreviewModal({
  api,
  dataset,
  onClose,
  symbols,
}: DatasetPreviewModalProps) {
  const [afterSequenceNumber, setAfterSequenceNumber] = useState(0);
  const [cursorHistory, setCursorHistory] = useState<readonly number[]>([]);
  const [page, setPage] = useState<DatasetLayoutPageResponse | null>(null);
  const [selectedSequence, setSelectedSequence] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const requestId = useRef(0);
  const symbolByMobileCode = useMemo(
    () => new Map(symbols.map((symbol) => [symbol.mobileCode, symbol])),
    [symbols],
  );

  const loadPage = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setError('');
    const result = await listDatasetLayouts(
      api,
      dataset.id,
      afterSequenceNumber,
      PREVIEW_PAGE_SIZE,
    );
    if (currentRequest !== requestId.current) return;
    setLoading(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setPage(result.page);
    setSelectedSequence(result.page.items[0]?.sequenceNumber ?? null);
  }, [afterSequenceNumber, api, dataset.id]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void loadPage();
    });
    return () => {
      cancelled = true;
      requestId.current += 1;
    };
  }, [loadPage]);

  const selectedLayout =
    page?.items.find((item) => item.sequenceNumber === selectedSequence) ??
    null;

  function showNextPage() {
    if (page?.nextAfterSequenceNumber == null || loading) return;
    setCursorHistory((current) => [...current, afterSequenceNumber]);
    setAfterSequenceNumber(page.nextAfterSequenceNumber);
  }

  function showPreviousPage() {
    if (cursorHistory.length === 0 || loading) return;
    const previous = cursorHistory[cursorHistory.length - 1] ?? 0;
    setCursorHistory((current) => current.slice(0, -1));
    setAfterSequenceNumber(previous);
  }

  return (
    <dialog
      aria-labelledby="dataset-preview-title"
      aria-modal="true"
      className="paylineDialog"
      open
    >
      <div className="paylineDialogCard datasetPreviewDialogCard">
        <header className="paylineDialogHeader">
          <div>
            <p className="eyebrow">
              Dataset v{dataset.version} · {dataset.rows} × {dataset.columns}
            </p>
            <h2 id="dataset-preview-title">Podgląd plansz</h2>
          </div>
          <button
            aria-label="Zamknij podgląd plansz"
            className="iconButton"
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
              <h3>Wczytywanie strony</h3>
              <p>Pobieram plansze w kolejności sekwencji…</p>
            </div>
          </div>
        ) : error ? (
          <div className="modalState">
            <span className="stateIcon">!</span>
            <div>
              <h3>Nie udało się pobrać plansz</h3>
              <p role="alert">{error}</p>
              <button
                className="secondaryButton"
                onClick={() => void loadPage()}
                type="button"
              >
                Spróbuj ponownie
              </button>
            </div>
          </div>
        ) : page && page.items.length > 0 ? (
          <>
            <div className="datasetPreviewWorkspace">
              <ol
                aria-label="Plansze na bieżącej stronie"
                className="datasetPreviewList"
              >
                {page.items.map((layout) => (
                  <li key={layout.sequenceNumber}>
                    <button
                      aria-pressed={layout.sequenceNumber === selectedSequence}
                      className={
                        layout.sequenceNumber === selectedSequence
                          ? 'datasetPreviewItem datasetPreviewItemSelected'
                          : 'datasetPreviewItem'
                      }
                      onClick={() => setSelectedSequence(layout.sequenceNumber)}
                      type="button"
                    >
                      <strong>#{layout.sequenceNumber}</strong>
                      <span>{shortSignature(layout.signature)}</span>
                    </button>
                  </li>
                ))}
              </ol>
              {selectedLayout ? (
                <LayoutBoard
                  columns={page.columns}
                  layout={selectedLayout}
                  symbolByMobileCode={symbolByMobileCode}
                />
              ) : null}
            </div>
            <footer className="datasetPreviewFooter">
              <p>
                Strona {cursorHistory.length + 1} · kolejność po{' '}
                <code>sequence_number</code>
              </p>
              <div className="rowActions">
                <button
                  className="textButton"
                  disabled={cursorHistory.length === 0}
                  onClick={showPreviousPage}
                  type="button"
                >
                  Poprzednia
                </button>
                <button
                  className="secondaryButton"
                  disabled={page.nextAfterSequenceNumber === null}
                  onClick={showNextPage}
                  type="button"
                >
                  Następna
                </button>
              </div>
            </footer>
          </>
        ) : (
          <div className="modalState">
            <span className="stateIcon">0</span>
            <div>
              <h3>Brak plansz</h3>
              <p>Ta strona nie zawiera żadnej planszy.</p>
            </div>
          </div>
        )}
      </div>
    </dialog>
  );
}

function LayoutBoard({
  columns,
  layout,
  symbolByMobileCode,
}: {
  readonly columns: number;
  readonly layout: DatasetLayoutResponse;
  readonly symbolByMobileCode: ReadonlyMap<number, SymbolResponse>;
}) {
  return (
    <section
      aria-label={`Plansza ${layout.sequenceNumber}`}
      className="datasetLayoutBoardPanel"
    >
      <header>
        <p className="eyebrow">Plansza #{layout.sequenceNumber}</p>
        <h3>Plansza row-major</h3>
      </header>
      <div
        className="datasetLayoutGrid"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {layout.cells.map((mobileCode, index) => {
          const symbol = symbolByMobileCode.get(mobileCode);
          return (
            <div className="datasetLayoutCell" key={`${index}-${mobileCode}`}>
              <strong>{symbol?.code ?? mobileCode}</strong>
              <span>{symbol?.name ?? `Kod ${mobileCode}`}</span>
            </div>
          );
        })}
      </div>
      <p className="datasetSignature">
        Sygnatura: <code>{layout.signature}</code>
      </p>
    </section>
  );
}

function shortSignature(signature: string): string {
  return signature.length > 18 ? `${signature.slice(0, 18)}…` : signature;
}

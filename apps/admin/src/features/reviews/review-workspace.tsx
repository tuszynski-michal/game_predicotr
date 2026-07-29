'use client';

import type {
  ReviewBatchResponse,
  ReviewCellSnapshot,
  ReviewItemResponse,
  ReviewItemStatus,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import {
  type ReviewsClient,
  loadReviewBatches,
  loadReviewItem,
  loadReviewItems,
  loadReviewSymbols,
} from '@/features/reviews/review-actions';
import {
  ReviewDecisionPanel,
  ReviewFeedbackExportsPanel,
} from '@/features/reviews/review-decision-panel';
import {
  REVIEW_STATUS_OPTIONS,
  adjacentReviewItemId,
  formatReviewConfidence,
  reviewAssetUrl,
  reviewCell,
  reviewStatusLabel,
} from '@/features/reviews/review-state';

type LoadState = 'error' | 'loading' | 'ready';

interface ReviewWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: ReviewsClient;
}

export function ReviewWorkspace({ apiBaseUrl, client }: ReviewWorkspaceProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [batches, setBatches] = useState<readonly ReviewBatchResponse[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState('');
  const [batchState, setBatchState] = useState<LoadState>('loading');
  const [batchError, setBatchError] = useState('');
  const [items, setItems] = useState<readonly ReviewItemResponse[]>([]);
  const [selectedItemId, setSelectedItemId] = useState('');
  const [selectedItem, setSelectedItem] = useState<ReviewItemResponse | null>(
    null,
  );
  const [selectedCellIndex, setSelectedCellIndex] = useState(0);
  const [statusFilter, setStatusFilter] = useState<ReviewItemStatus | ''>('');
  const [queueState, setQueueState] = useState<LoadState>('ready');
  const [queueError, setQueueError] = useState('');
  const [detailError, setDetailError] = useState('');
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [symbolsError, setSymbolsError] = useState('');
  const mounted = useRef(true);
  const batchRequestId = useRef(0);
  const queueRequestId = useRef(0);
  const detailRequestId = useRef(0);

  const refreshBatches = useCallback(async () => {
    const requestId = ++batchRequestId.current;
    setBatchState('loading');
    setBatchError('');
    const result = await loadReviewBatches(api);
    if (!mounted.current || requestId !== batchRequestId.current) return;
    if (!result.ok) {
      setBatchState('error');
      setBatchError(result.error);
      return;
    }
    setBatches(result.batches);
    setSelectedBatchId((current) =>
      result.batches.some((batch) => batch.id === current)
        ? current
        : (result.batches[0]?.id ?? ''),
    );
    setBatchState('ready');
  }, [api]);

  const refreshQueue = useCallback(async () => {
    if (selectedBatchId === '') {
      setItems([]);
      setSelectedItemId('');
      setSelectedItem(null);
      setQueueState('ready');
      return;
    }
    const requestId = ++queueRequestId.current;
    setQueueState('loading');
    setQueueError('');
    setDetailError('');
    const result = await loadReviewItems(
      api,
      selectedBatchId,
      statusFilter === '' ? undefined : statusFilter,
    );
    if (!mounted.current || requestId !== queueRequestId.current) return;
    if (!result.ok) {
      setQueueState('error');
      setQueueError(result.error);
      return;
    }
    setItems(result.items);
    setSelectedItemId((current) =>
      result.items.some((item) => item.id === current)
        ? current
        : (result.items[0]?.id ?? ''),
    );
    setSelectedItem((current) =>
      result.items.some((item) => item.id === current?.id) ? current : null,
    );
    setSelectedCellIndex(0);
    setQueueState('ready');
  }, [api, selectedBatchId, statusFilter]);

  useEffect(() => {
    mounted.current = true;
    queueMicrotask(() => void refreshBatches());
    return () => {
      mounted.current = false;
    };
  }, [refreshBatches]);

  useEffect(() => {
    queueMicrotask(() => void refreshQueue());
  }, [refreshQueue]);

  useEffect(() => {
    if (selectedItemId === '') {
      return;
    }
    const requestId = ++detailRequestId.current;
    queueMicrotask(async () => {
      setDetailError('');
      const result = await loadReviewItem(api, selectedItemId);
      if (!mounted.current || requestId !== detailRequestId.current) return;
      if (!result.ok) {
        setDetailError(result.error);
        setSelectedItem(
          items.find((item) => item.id === selectedItemId) ?? null,
        );
        return;
      }
      setSelectedItem(result.item);
      setSelectedCellIndex(0);
    });
  }, [api, items, selectedItemId]);

  useEffect(() => {
    const batch = batches.find((candidate) => candidate.id === selectedBatchId);
    if (!batch) {
      return;
    }
    queueMicrotask(async () => {
      setSymbols([]);
      setSymbolsError('');
      const result = await loadReviewSymbols(api, batch.gameId);
      if (!mounted.current) return;
      if (!result.ok) {
        setSymbols([]);
        setSymbolsError(result.error);
        return;
      }
      setSymbols(result.symbols);
    });
  }, [api, batches, selectedBatchId]);

  const selectedBatch =
    batches.find((batch) => batch.id === selectedBatchId) ?? null;
  const currentItemIndex = items.findIndex(
    (item) => item.id === selectedItemId,
  );
  const selectedCell =
    selectedItem === null ? null : reviewCell(selectedItem, selectedCellIndex);

  function selectItem(itemId: string) {
    setSelectedItemId(itemId);
    setSelectedCellIndex(0);
  }

  function move(direction: -1 | 1) {
    if (selectedItemId === '') return;
    const adjacent = adjacentReviewItemId(items, selectedItemId, direction);
    if (adjacent !== null) selectItem(adjacent);
  }

  function handleResolved(item: ReviewItemResponse) {
    setSelectedItem(item);
    setItems((current) =>
      current.map((candidate) => (candidate.id === item.id ? item : candidate)),
    );
    if (statusFilter !== '' && item.status !== statusFilter) {
      void refreshQueue();
    }
  }

  return (
    <section className="catalogSection reviewSection" id="reviews">
      <header className="pageHeader reviewPageHeader">
        <div>
          <p className="eyebrow">M6.3 · active learning</p>
          <h1>Manual review</h1>
          <p className="lead">
            Odtwarzaj kontekst plansz, poprawiaj etykiety i zachowuj każdą
            decyzję jako audytowaną rewizję.
          </p>
        </div>
        <button
          className="secondaryButton"
          disabled={batchState === 'loading' || queueState === 'loading'}
          onClick={() => void refreshBatches()}
          type="button"
        >
          Odśwież
        </button>
      </header>

      <p className="reviewReadOnlyBanner" role="status">
        Predykcja i confidence pozostają sugestią. Dopiero jawna decyzja
        administratora tworzy etykiety do kolejnej wersji datasetu.
      </p>

      {batchState === 'loading' ? (
        <ReviewState
          text="Pobieram niezmienne batche active-learning…"
          title="Wczytywanie batchy"
        />
      ) : batchState === 'error' ? (
        <ReviewState
          action={() => void refreshBatches()}
          error
          text={batchError}
          title="Nie udało się pobrać batchy"
        />
      ) : batches.length === 0 ? (
        <ReviewState
          text="Najpierw zaimportuj raport selekcji TASK-0063 przez Admin API."
          title="Brak batchy manual review"
        />
      ) : (
        <>
          <ReviewControls
            batches={batches}
            selectedBatchId={selectedBatchId}
            selectedBatch={selectedBatch}
            statusFilter={statusFilter}
            onBatchChange={setSelectedBatchId}
            onStatusChange={setStatusFilter}
          />
          {selectedBatch ? (
            <ReviewFeedbackExportsPanel
              api={api}
              batch={selectedBatch}
              key={selectedBatch.id}
            />
          ) : null}

          {queueState === 'loading' ? (
            <ReviewState
              text="Pobieram plansze w kolejności selection rank…"
              title="Wczytywanie kolejki"
            />
          ) : queueState === 'error' ? (
            <ReviewState
              action={() => void refreshQueue()}
              error
              text={queueError}
              title="Nie udało się pobrać kolejki"
            />
          ) : items.length === 0 ? (
            <ReviewState
              text={
                statusFilter === ''
                  ? 'Wybrany batch nie zawiera plansz.'
                  : 'Żadna plansza nie ma wybranego statusu.'
              }
              title="Pusta kolejka"
            />
          ) : selectedItem && selectedCell ? (
            <div className="reviewWorkspace">
              <ReviewQueue
                currentItemId={selectedItemId}
                items={items}
                onSelect={selectItem}
              />
              <div className="reviewInspection">
                {detailError ? (
                  <p
                    className="feedbackBanner feedbackBannerError"
                    role="alert"
                  >
                    {detailError} Pokazuję snapshot z listy.
                  </p>
                ) : null}
                <ReviewItemHeader
                  batch={selectedBatch}
                  currentIndex={currentItemIndex}
                  item={selectedItem}
                  itemCount={items.length}
                  onNext={() => move(1)}
                  onPrevious={() => move(-1)}
                />
                <ReviewImages apiBaseUrl={apiBaseUrl} item={selectedItem} />
                <ReviewGrid
                  apiBaseUrl={apiBaseUrl}
                  item={selectedItem}
                  onSelectCell={setSelectedCellIndex}
                  selectedCellIndex={selectedCellIndex}
                />
                <ReviewCellDetails
                  apiBaseUrl={apiBaseUrl}
                  cell={selectedCell}
                  item={selectedItem}
                />
                {symbolsError ? (
                  <p
                    className="feedbackBanner feedbackBannerError"
                    role="alert"
                  >
                    {symbolsError}
                  </p>
                ) : symbols.length > 0 ? (
                  <ReviewDecisionPanel
                    api={api}
                    item={selectedItem}
                    key={selectedItem.id}
                    onResolved={handleResolved}
                    symbols={symbols}
                  />
                ) : (
                  <ReviewState
                    text="Pobieram aktywny katalog symboli…"
                    title="Przygotowanie edytora decyzji"
                  />
                )}
              </div>
            </div>
          ) : (
            <ReviewState
              text="Szczegóły wybranej planszy nie są jeszcze dostępne."
              title="Wczytywanie szczegółów"
            />
          )}
        </>
      )}
    </section>
  );
}

function ReviewControls({
  batches,
  onBatchChange,
  onStatusChange,
  selectedBatch,
  selectedBatchId,
  statusFilter,
}: {
  readonly batches: readonly ReviewBatchResponse[];
  readonly onBatchChange: (value: string) => void;
  readonly onStatusChange: (value: ReviewItemStatus | '') => void;
  readonly selectedBatch: ReviewBatchResponse | null;
  readonly selectedBatchId: string;
  readonly statusFilter: ReviewItemStatus | '';
}) {
  return (
    <div className="reviewControls" aria-label="Wybór batcha i statusu">
      <label>
        Batch review
        <select
          onChange={(event) => onBatchChange(event.target.value)}
          value={selectedBatchId}
        >
          {batches.map((batch) => (
            <option key={batch.id} value={batch.id}>
              {batch.modelVersion} · {batch.itemCount} plansz
            </option>
          ))}
        </select>
      </label>
      <label>
        Status
        <select
          onChange={(event) =>
            onStatusChange(event.target.value as ReviewItemStatus | '')
          }
          value={statusFilter}
        >
          <option value="">Wszystkie statusy</option>
          {REVIEW_STATUS_OPTIONS.map((status) => (
            <option key={status} value={status}>
              {reviewStatusLabel(status)}
            </option>
          ))}
        </select>
      </label>
      <dl>
        <div>
          <dt>Model</dt>
          <dd>{selectedBatch?.modelVersion ?? '—'}</dd>
        </div>
        <div>
          <dt>Temperatura</dt>
          <dd>{selectedBatch?.temperature.toFixed(4) ?? '—'}</dd>
        </div>
      </dl>
    </div>
  );
}

function ReviewQueue({
  currentItemId,
  items,
  onSelect,
}: {
  readonly currentItemId: string;
  readonly items: readonly ReviewItemResponse[];
  readonly onSelect: (itemId: string) => void;
}) {
  return (
    <aside className="reviewQueue" aria-label="Kolejka plansz manual review">
      <header>
        <p className="eyebrow">Kolejka</p>
        <h2>{items.length} plansz</h2>
      </header>
      <ol>
        {items.map((item) => (
          <li key={item.id}>
            <button
              aria-pressed={item.id === currentItemId}
              className={
                item.id === currentItemId
                  ? 'reviewQueueItem reviewQueueItemSelected'
                  : 'reviewQueueItem'
              }
              onClick={() => onSelect(item.id)}
              type="button"
            >
              <span>Rank {item.snapshot.selectionRank}</span>
              <strong>Sequence #{item.snapshot.sequenceNumber}</strong>
              <small>{reviewStatusLabel(item.status)}</small>
            </button>
          </li>
        ))}
      </ol>
    </aside>
  );
}

function ReviewItemHeader({
  batch,
  currentIndex,
  item,
  itemCount,
  onNext,
  onPrevious,
}: {
  readonly batch: ReviewBatchResponse | null;
  readonly currentIndex: number;
  readonly item: ReviewItemResponse;
  readonly itemCount: number;
  readonly onNext: () => void;
  readonly onPrevious: () => void;
}) {
  return (
    <header className="reviewItemHeader">
      <div>
        <p className="eyebrow">
          Pozycja {currentIndex + 1} z {itemCount} · rank{' '}
          {item.snapshot.selectionRank}
        </p>
        <h2>Sequence #{item.snapshot.sequenceNumber}</h2>
        <p>
          {item.snapshot.sourceImageId} · {item.snapshot.sourceGroup}
        </p>
      </div>
      <div className="rowActions">
        <button
          className="textButton"
          disabled={currentIndex <= 0}
          onClick={onPrevious}
          type="button"
        >
          Poprzednia
        </button>
        <button
          className="secondaryButton"
          disabled={currentIndex >= itemCount - 1}
          onClick={onNext}
          type="button"
        >
          Następna
        </button>
      </div>
      <dl className="reviewProvenance">
        <div>
          <dt>Status</dt>
          <dd>{reviewStatusLabel(item.status)}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd>{batch?.modelVersion ?? '—'}</dd>
        </div>
        <div>
          <dt>Uncertainty</dt>
          <dd>{formatReviewConfidence(item.snapshot.uncertaintyScore)}</dd>
        </div>
        <div>
          <dt>Selection score</dt>
          <dd>{formatReviewConfidence(item.snapshot.selectionScore)}</dd>
        </div>
      </dl>
    </header>
  );
}

function ReviewImages({
  apiBaseUrl,
  item,
}: {
  readonly apiBaseUrl: string;
  readonly item: ReviewItemResponse;
}) {
  return (
    <div className="reviewImageComparison">
      <ReviewImage
        alt={`Oryginalne zdjęcie ${item.snapshot.sourceImageId}`}
        label="Oryginalne zdjęcie"
        src={reviewAssetUrl(apiBaseUrl, item.id, 'source')}
      />
      <ReviewImage
        alt={`Kanoniczna plansza sequence ${item.snapshot.sequenceNumber}`}
        label="Wyprostowana plansza 5 × 3"
        src={reviewAssetUrl(apiBaseUrl, item.id, 'board')}
      />
    </div>
  );
}

function ReviewGrid({
  apiBaseUrl,
  item,
  onSelectCell,
  selectedCellIndex,
}: {
  readonly apiBaseUrl: string;
  readonly item: ReviewItemResponse;
  readonly onSelectCell: (cellIndex: number) => void;
  readonly selectedCellIndex: number;
}) {
  return (
    <section className="reviewGridPanel" aria-labelledby="review-grid-title">
      <header>
        <div>
          <p className="eyebrow">15 komórek · row-major</p>
          <h3 id="review-grid-title">Wybierz kafelek do inspekcji</h3>
        </div>
        <p>Wiersze i kolumny są numerowane od 1 w interfejsie.</p>
      </header>
      <div className="reviewCellGrid">
        {item.snapshot.cells.map((cell) => (
          <button
            aria-label={`Wiersz ${cell.rowIndex + 1}, kolumna ${
              cell.columnIndex + 1
            }, ${cell.predictedSymbolCode}, confidence ${formatReviewConfidence(
              cell.confidence,
            )}`}
            aria-pressed={cell.cellIndex === selectedCellIndex}
            className={
              cell.cellIndex === selectedCellIndex
                ? 'reviewCell reviewCellSelected'
                : 'reviewCell'
            }
            key={cell.sampleId}
            onClick={() => onSelectCell(cell.cellIndex)}
            type="button"
          >
            <ReviewCellImage
              alt=""
              src={reviewAssetUrl(apiBaseUrl, item.id, 'cell', cell.cellIndex)}
            />
            <span>
              R{cell.rowIndex + 1} · C{cell.columnIndex + 1}
            </span>
            <strong>{cell.predictedSymbolCode}</strong>
            <small>{formatReviewConfidence(cell.confidence)}</small>
          </button>
        ))}
      </div>
    </section>
  );
}

function ReviewCellDetails({
  apiBaseUrl,
  cell,
  item,
}: {
  readonly apiBaseUrl: string;
  readonly cell: ReviewCellSnapshot;
  readonly item: ReviewItemResponse;
}) {
  return (
    <section className="reviewCellDetails" aria-labelledby="review-cell-title">
      <ReviewImage
        alt={`Crop komórki ${cell.rowIndex + 1}, ${cell.columnIndex + 1}`}
        label={`Wybrany crop · R${cell.rowIndex + 1} C${cell.columnIndex + 1}`}
        src={reviewAssetUrl(apiBaseUrl, item.id, 'cell', cell.cellIndex)}
      />
      <div>
        <p className="eyebrow">Sugestia modelu</p>
        <h3 id="review-cell-title">{cell.predictedSymbolCode}</h3>
        <p className="reviewPrimaryConfidence">
          Confidence: <strong>{formatReviewConfidence(cell.confidence)}</strong>{' '}
          · entropy {formatReviewConfidence(cell.entropy)}
        </p>
        <h4>Alternatywy</h4>
        <ol className="reviewAlternatives">
          {cell.alternatives.map((alternative, index) => (
            <li key={alternative.symbolCode}>
              <span>#{index + 1}</span>
              <strong>{alternative.symbolCode}</strong>
              <small>{formatReviewConfidence(alternative.confidence)}</small>
            </li>
          ))}
        </ol>
        <p className="reviewDecisionNotice">
          Sugestia modelu nie jest zapisywana bez jawnej decyzji poniżej.
        </p>
      </div>
    </section>
  );
}

function ReviewImage({
  alt,
  label,
  src,
}: {
  readonly alt: string;
  readonly label: string;
  readonly src: string;
}) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const failed = failedSrc === src;

  return (
    <figure className="reviewImage">
      <figcaption>{label}</figcaption>
      {failed ? (
        <div className="reviewImagePlaceholder">
          <span aria-hidden="true">!</span>
          <p>
            Obraz lokalny jest niedostępny. Dane planszy pozostają widoczne.
          </p>
        </div>
      ) : (
        // The source is a loopback-only, item-scoped API endpoint.
        // eslint-disable-next-line @next/next/no-img-element
        <img alt={alt} onError={() => setFailedSrc(src)} src={src} />
      )}
    </figure>
  );
}

function ReviewCellImage({
  alt,
  src,
}: {
  readonly alt: string;
  readonly src: string;
}) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const failed = failedSrc === src;

  return failed ? (
    <span className="reviewCellImagePlaceholder" aria-hidden="true">
      brak
    </span>
  ) : (
    // The source is a loopback-only, item-scoped API endpoint.
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} onError={() => setFailedSrc(src)} src={src} />
  );
}

function ReviewState({
  action,
  error = false,
  text,
  title,
}: {
  readonly action?: () => void;
  readonly error?: boolean;
  readonly text: string;
  readonly title: string;
}) {
  return (
    <div className="emptyState reviewState">
      <span className="stateIcon" aria-hidden="true">
        {error ? '!' : '·'}
      </span>
      <div>
        <h2>{title}</h2>
        <p role={error ? 'alert' : undefined}>{text}</p>
        {action ? (
          <button className="secondaryButton" onClick={action} type="button">
            Spróbuj ponownie
          </button>
        ) : null}
      </div>
    </div>
  );
}

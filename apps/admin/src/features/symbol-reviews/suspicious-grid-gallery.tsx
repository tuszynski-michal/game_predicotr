'use client';

import type { ImageGridReviewItemResponse } from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';

import type { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import { applySingleSymbolReviewDecision } from './symbol-review-mutation-actions';
import styles from './suspicious-grid-gallery.module.css';

export type SuspiciousGridGalleryClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  | 'applySymbolCellReviewDecision'
  | 'imageGridReviewSourceAssetUrl'
  | 'listImageGridReviews'
>;

type Candidate = ImageGridReviewItemResponse;
type Suspicion = NonNullable<Candidate['cutSuspicion']>;
type Cell = Suspicion['cells'][number];
type RouteResult = { kind: 'applied' | 'stale' | 'failed'; message: string };

const VISIBLE_BATCH = 24;
const WRITE_BATCH = 4;

const REASON_LABELS = {
  opposite_edges: 'Różne długości przeciwległych krawędzi',
  board_aspect: 'Nietypowa szerokość lub wysokość planszy',
  line_spacing: 'Nierówne odstępy między liniami',
} satisfies Record<Suspicion['reason'], string>;

function defaultCell(suspicion: Suspicion): Cell | undefined {
  const preferred = suspicion.cells.filter((cell) =>
    suspicion.preferredCellIndices.includes(cell.cellIndex),
  );
  const pool = preferred.length === 0 ? suspicion.cells : preferred;
  return pool.find((cell) => cell.pending) ?? pool[0];
}

export function SuspiciousGridGallery({
  api,
  gameId,
  importJobId,
  onClose,
  onRouted,
}: {
  readonly api: SuspiciousGridGalleryClient;
  readonly gameId: string;
  readonly importJobId: string | null;
  readonly onClose: () => void;
  readonly onRouted: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const sending = useRef(false);
  const [running, setRunning] = useState(true);
  // Undefined requests the first page. Null confirms the end of the scan.
  const [cursor, setCursor] = useState<string | null>();
  const [scanError, setScanError] = useState(false);
  const [scanned, setScanned] = useState(0);
  const [candidates, setCandidates] = useState<readonly Candidate[]>([]);
  const [visible, setVisible] = useState(VISIBLE_BATCH);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [chosen, setChosen] = useState<ReadonlyMap<string, Cell>>(new Map());
  const [results, setResults] = useState<ReadonlyMap<string, RouteResult>>(
    new Map(),
  );
  const [isSending, setIsSending] = useState(false);
  const [summary, setSummary] = useState('');
  const [showGrid, setShowGrid] = useState(true);

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  useEffect(() => {
    if (!running || cursor === null) return;
    const controller = new AbortController();

    async function scanPage() {
      try {
        const { data } = await api.listImageGridReviews({
          gameId,
          view: 'suspicious',
          importJobId: importJobId ?? undefined,
          afterCursor: cursor ?? undefined,
          counts: 'none',
          limit: 500,
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        if (
          data === undefined ||
          data.scannedCount === undefined ||
          data.scannedCount === null ||
          data.nextCursor === cursor
        ) {
          throw new Error('Nieprawidłowa odpowiedź skanu siatek.');
        }
        setCandidates((previous) => [...previous, ...data.items]);
        setScanned((previous) => previous + (data.scannedCount ?? 0));
        setCursor(data.nextCursor);
      } catch {
        if (controller.signal.aborted) return;
        setScanError(true);
        setRunning(false);
      }
    }

    void scanPage();
    return () => controller.abort();
  }, [api, cursor, gameId, importJobId, running]);

  const ranked = useMemo(
    () =>
      [...candidates].sort(
        (a, b) =>
          (b.cutSuspicion?.score ?? 0) - (a.cutSuspicion?.score ?? 0) ||
          a.sequenceNumber - b.sequenceNumber,
      ),
    [candidates],
  );

  function rescan() {
    setCursor(undefined);
    setScanned(0);
    setScanError(false);
    setCandidates([]);
    setResults(new Map());
    setSelected(new Set());
    setChosen(new Map());
    setVisible(VISIBLE_BATCH);
    setSummary('');
    setRunning(true);
  }

  async function routeSelection() {
    if (sending.current || selected.size === 0) return;
    sending.current = true;
    setIsSending(true);
    setSummary('');
    const snapshot = candidates.flatMap((item) => {
      const suspicion = item.cutSuspicion;
      if (!selected.has(item.slotId) || !suspicion) return [];
      const cell = chosen.get(item.slotId) ?? defaultCell(suspicion);
      return cell === undefined ? [] : [{ item, cell }];
    });

    const updated = new Map<string, RouteResult>();
    for (let start = 0; start < snapshot.length; start += WRITE_BATCH) {
      const batch = snapshot.slice(start, start + WRITE_BATCH);
      await Promise.all(
        batch.map(async ({ item, cell }) => {
          const outcome = await applySingleSymbolReviewDecision(
            api,
            gameId,
            'mark_grid_issue',
            cell.target,
            null,
          );
          const result: RouteResult = outcome.ok
            ? { kind: 'applied', message: 'W kolejce korekty' }
            : outcome.conflict
              ? { kind: 'stale', message: 'Nieaktualna plansza lub pole' }
              : { kind: 'failed', message: outcome.error };
          updated.set(item.slotId, result);
        }),
      );
    }
    setResults((previous) => new Map([...previous, ...updated]));
    setSelected(
      new Set(
        [...updated]
          .filter(([, result]) => result.kind === 'failed')
          .map(([id]) => id),
      ),
    );

    const outcomes = [...updated.values()];
    const applied = outcomes.filter(
      (result) => result.kind === 'applied',
    ).length;
    const stale = outcomes.filter((result) => result.kind === 'stale').length;
    const failed = outcomes.length - applied - stale;
    setSummary(
      `Skierowano do korekty: ${applied}. Nieaktualne: ${stale}. Brak potwierdzenia: ${failed}.`,
    );
    setIsSending(false);
    sending.current = false;
    if (applied > 0) onRouted();
  }

  return (
    <dialog
      aria-label="Podejrzane siatki Mumii A2"
      className={styles.gallery}
      onCancel={(event) => {
        event.preventDefault();
        if (!sending.current) onClose();
      }}
      ref={dialog}
    >
      <header className={styles.heading}>
        <div>
          <h2>Podejrzane siatki</h2>
          <p>
            {importJobId === null ? 'Wszystkie katalogi' : 'Wybrany katalog'}
          </p>
        </div>
        <button disabled={isSending} onClick={onClose} type="button">
          Zamknij
        </button>
      </header>
      <div className={styles.actions}>
        <label>
          <input
            checked={showGrid}
            onChange={(event) => setShowGrid(event.target.checked)}
            type="checkbox"
          />
          Pokaż siatkę
        </label>
        {cursor !== null ? (
          <button
            onClick={() => {
              setScanError(false);
              setRunning(!running);
            }}
            type="button"
          >
            {running ? 'Wstrzymaj skan' : 'Wznów skan'}
          </button>
        ) : null}
        <button
          disabled={isSending || (running && cursor === undefined)}
          onClick={rescan}
          type="button"
        >
          Skanuj ponownie
        </button>
        <button
          disabled={selected.size === 0 || isSending}
          onClick={() => void routeSelection()}
          type="button"
        >
          {isSending
            ? 'Przekazywanie…'
            : `Skieruj do korekty (${selected.size})`}
        </button>
      </div>

      <p className={styles.status} role="status">
        {scanError
          ? 'Nie udało się pobrać kolejnej partii. Możesz wznowić skan.'
          : cursor === null
            ? 'Skan zakończony.'
            : running
              ? 'Skanowanie…'
              : 'Skan wstrzymany.'}
        {' Sprawdzono '}
        {scanned.toLocaleString('pl-PL')}
        {', wskazano '}
        {candidates.length.toLocaleString('pl-PL')}.
      </p>
      {summary && (
        <p className={styles.status} role="status">
          {summary}
        </p>
      )}
      {cursor === null && ranked.length === 0 && (
        <p className={styles.status}>
          Brak podejrzanych siatek w tym zakresie.
        </p>
      )}

      <div className={styles.cards}>
        {ranked.slice(0, visible).map((item) => {
          const suspicion = item.cutSuspicion;
          if (!suspicion || item.reviewItemId === null || !item.latticeNodes)
            return null;
          const currentCell = chosen.get(item.slotId) ?? defaultCell(suspicion);
          const result = results.get(item.slotId);
          const locked =
            isSending || result?.kind === 'applied' || result?.kind === 'stale';
          return (
            <article className={styles.card} key={item.slotId}>
              <label className={styles.cardTitle}>
                <input
                  checked={selected.has(item.slotId)}
                  disabled={locked || currentCell === undefined}
                  onChange={(event) => {
                    const nextChecked = event.target.checked;
                    setSelected((previous) => {
                      const next = new Set(previous);
                      if (nextChecked) next.add(item.slotId);
                      else next.delete(item.slotId);
                      return next;
                    });
                  }}
                  type="checkbox"
                />
                Plansza #{item.sequenceNumber}
              </label>
              <GridCutPreview
                item={item}
                nodes={item.latticeNodes}
                showGrid={showGrid}
                suspicion={suspicion}
                url={api.imageGridReviewSourceAssetUrl(
                  item.reviewItemId,
                  gameId,
                  item.sourceChecksumSha256,
                )}
              />
              <p className={styles.reason}>{REASON_LABELS[suspicion.reason]}</p>
              {currentCell ? (
                <label className={styles.cell}>
                  Pole do zgłoszenia
                  <select
                    disabled={locked}
                    onChange={(event) => {
                      const index = Number(event.target.value);
                      const cell = suspicion.cells.find(
                        (value) => value.cellIndex === index,
                      );
                      if (cell)
                        setChosen((prev) =>
                          new Map(prev).set(item.slotId, cell),
                        );
                    }}
                    value={currentCell.cellIndex}
                  >
                    {suspicion.cells.map((cell) => (
                      <option key={cell.cellIndex} value={cell.cellIndex}>
                        {Math.floor(cell.cellIndex / 5) + 1}. rząd,{' '}
                        {(cell.cellIndex % 5) + 1}. kolumna
                        {!cell.pending && ' · zatwierdzone'}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <p className={styles.reason}>
                  Brak dostępnego pola do zgłoszenia.
                </p>
              )}
              {result && <p className={styles.reason}>{result.message}</p>}
            </article>
          );
        })}
      </div>
      {ranked.length > visible && (
        <button
          className={styles.more}
          onClick={() => setVisible((count) => count + VISIBLE_BATCH)}
          type="button"
        >
          Pokaż kolejne
        </button>
      )}
    </dialog>
  );
}

function GridCutPreview({
  item,
  nodes,
  showGrid,
  suspicion,
  url,
}: {
  readonly item: Candidate;
  readonly nodes: NonNullable<Candidate['latticeNodes']>;
  readonly showGrid: boolean;
  readonly suspicion: Suspicion;
  readonly url: string;
}) {
  const [missing, setMissing] = useState(false);
  const xs = nodes.map((p) => p.x);
  const ys = nodes.map((p) => p.y);
  const pad =
    0.18 *
    Math.min(
      Math.max(...xs) - Math.min(...xs),
      Math.max(...ys) - Math.min(...ys),
    );
  const left = Math.max(0, Math.min(...xs) - pad);
  const top = Math.max(0, Math.min(...ys) - pad);
  const width = Math.min(item.sourceWidth, Math.max(...xs) + pad) - left;
  const height = Math.min(item.sourceHeight, Math.max(...ys) + pad) - top;
  if (missing || width <= 0 || height <= 0) {
    return <p className={styles.reason}>Podgląd zdjęcia jest niedostępny.</p>;
  }
  const edge = suspicion.nodeIndices?.map((index) => nodes[index]);
  const rowLines = Array.from({ length: 4 }, (_, row) =>
    nodes.slice(6 * row, 6 * row + 6),
  );
  const columnLines = Array.from({ length: 6 }, (_, column) =>
    rowLines.map((row) => row[column]!),
  );
  return (
    <div className={styles.preview} style={{ aspectRatio: width / height }}>
      {/* eslint-disable-next-line @next/next/no-img-element -- checksum-bound local source */}
      <img
        alt={`Fragment zdjęcia planszy ${item.sequenceNumber}`}
        loading="lazy"
        onError={() => setMissing(true)}
        src={url}
        style={{
          left: `${(-left * 100) / width}%`,
          top: `${(-top * 100) / height}%`,
          width: `${(item.sourceWidth * 100) / width}%`,
          height: `${(item.sourceHeight * 100) / height}%`,
        }}
      />
      {showGrid && (
        <svg aria-hidden="true" viewBox={`${left} ${top} ${width} ${height}`}>
          {[...rowLines, ...columnLines].map((line, index) => (
            <polyline
              key={index}
              points={line.map((point) => `${point.x},${point.y}`).join(' ')}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {edge?.[0] && edge[1] && (
            <line
              vectorEffect="non-scaling-stroke"
              x1={edge[0].x}
              x2={edge[1].x}
              y1={edge[0].y}
              y2={edge[1].y}
            />
          )}
        </svg>
      )}
    </div>
  );
}

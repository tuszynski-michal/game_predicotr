'use client';
/* eslint-disable @next/next/no-img-element -- registered local image */
import { useCallback, useEffect, useRef, useState } from 'react';
import { PhotoReviewPanel } from './photo-review-panel';
import {
  assetUrl,
  previewGeometry,
  writeAnnotation,
  type AnnotationRequest,
  type GeometryResult,
  type GeometryAnnotation,
  type Point,
  type Source,
} from '../../../../packages/vision-lab-api-client/src/index';
import {
  activeIntervals,
  interpolateCorners,
} from '../lib/annotation-geometry';
import {
  captureHandlePointer,
  fitViewport,
  fullViewport,
  sourcePoint,
  type Viewport,
} from '../lib/editor-viewport';
import { LatestPreview } from '../lib/latest-preview';
import { useAnnotations } from './annotation-context';
import { useToast } from '../../../../packages/ui/src/toasts';
import {
  approvalSummary,
  boardStatus,
  nextApprovedPosition,
  positionIndices,
  sourceAnnotations,
  statusLabel,
} from '../lib/annotation-status';

export function GeometryEditor({
  source,
  proposal,
  columns: initialColumns,
  onProtectionChange,
  onColumnsChange,
}: {
  source: Source;
  proposal: GeometryResult | null;
  columns: 3 | 5;
  onProtectionChange: (dirty: boolean, pending: boolean) => void;
  onColumnsChange: (columns: 3 | 5) => void;
}) {
  const { state, accept, refresh } = useAnnotations();
  const notify = useToast();
  const [columns, setColumns] = useState<3 | 5>(initialColumns);
  const [dirty, setDirty] = useState(false);
  const [reviewProtection, setReviewProtection] = useState({
    dirty: false,
    pending: false,
  });
  const onReviewProtection = useCallback(
    (dirty: boolean, pending: boolean) =>
      setReviewProtection({ dirty, pending }),
    [],
  );
  const submitting = useRef(false);
  const initialized = useRef(false);
  const [loadedRevision, setLoadedRevision] = useState<number | null>(null);
  const [size, setSize] = useState({ width: 1, height: 1 });
  const [viewport, setViewport] = useState<Viewport>({
    x: 0,
    y: 0,
    width: 1,
    height: 1,
  });
  const [preview, setPreview] = useState<GeometryResult | null>(null);
  const previewOrder = useRef(new LatestPreview());
  const photoRef = useRef<HTMLDivElement>(null);
  const [displayWidth, setDisplayWidth] = useState(800);
  const latestNodes = useRef<Point[]>([]);
  const dragViewport = useRef<Viewport | null>(null);
  const [board, setBoard] = useState(0);
  const [corners, setCorners] = useState<Point[]>([]);
  const [nodes, setNodes] = useState<Point[]>([]);
  const [mode, setMode] = useState<'corners' | 'nodes'>('corners');
  const [presence, setPresence] =
    useState<GeometryAnnotation['presence']>('present');
  const [busy, setBusy] = useState(false);
  const drag = useRef<number | null>(null);
  const activity = useRef<number[]>([]);
  const last = useRef<number | null>(null);
  const [pending, setPending] = useState<AnnotationRequest | null>(null);
  const pendingTarget = useRef<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const corrections = useRef(0);
  const geometryLocked = busy || pending !== null;
  const locked = geometryLocked || reviewProtection.pending;
  const rows = sourceAnnotations(state, source.id);
  useEffect(() => {
    onProtectionChange(dirty || reviewProtection.dirty, locked);
  }, [dirty, reviewProtection.dirty, locked, onProtectionChange]);
  useEffect(() => {
    const prevent = (event: BeforeUnloadEvent) => {
      if (dirty || reviewProtection.dirty || locked) event.preventDefault();
    };
    window.addEventListener('beforeunload', prevent);
    return () => window.removeEventListener('beforeunload', prevent);
  }, [dirty, reviewProtection.dirty, locked]);
  useEffect(() => {
    const order = previewOrder.current;
    const element = photoRef.current;
    const observer = new ResizeObserver(() => {
      if (element) setDisplayWidth(element.getBoundingClientRect().width);
    });
    if (element) observer.observe(element);
    return () => {
      observer.disconnect();
      order.invalidate();
    };
  }, []);
  function clearPreview() {
    previewOrder.current.invalidate();
    setPreview(null);
  }
  function refreshPreview(
    next: Point[],
    nextPresence = presence,
    nextBoard = board,
    nextColumns = columns,
  ) {
    clearPreview();
    if (nextPresence !== 'present' || next.length !== 4 * (nextColumns + 1))
      return;
    void previewOrder.current.run(
      () =>
        previewGeometry(source.id, nextColumns, {
          position_index: nextBoard,
          status: 'complete',
          nodes: next,
        }),
      (value) => {
        setPreview(value);
        if (value.status !== 'detected')
          notify({
            kind: 'warning',
            message: `Nieprawidłowa siatka: ${value.reasons.join(', ')}`,
            operation: 'preview',
          });
      },
      () =>
        notify({
          kind: 'error',
          message: 'Nie można pobrać cropów. Ponów podgląd.',
          operation: 'preview',
        }),
    );
  }
  function updateNodes(next: Point[]) {
    latestNodes.current = next;
    setNodes(next);
  }
  function finishDrag() {
    if (drag.current === null) return;
    corrections.current += 1;
    drag.current = null;
    dragViewport.current = null;
    setViewport(fitViewport(latestNodes.current, size));
    refreshPreview(latestNodes.current);
  }
  function trackActivity() {
    if (locked) return;
    const now = performance.now();
    if (last.current !== null)
      activity.current.push(Math.round(now - last.current));
    last.current = now;
    setElapsed(activeIntervals(activity.current));
  }
  function mark() {
    trackActivity();
    setDirty(true);
  }
  function load(
    saved = true,
    nextBoard = board,
    nextState = state,
    proposeMissing = true,
  ) {
    const stored = nextState?.annotations[`${source.id}:${nextBoard}`];
    setLoadedRevision(stored?.revision ?? null);
    const nextColumns = saved && stored ? stored.topology.columns : columns;
    if (stored && saved && nextColumns !== columns)
      notify({
        kind: 'info',
        message: `Wczytano zapisaną topologię ${nextColumns} × 3 pozycji ${nextBoard + 1}, bez konwersji węzłów.`,
      });
    setColumns(nextColumns);
    onColumnsChange(nextColumns);
    setBoard(nextBoard);
    drag.current = null;
    dragViewport.current = null;
    clearPreview();
    const suggested =
      proposal?.topology.columns === nextColumns
        ? proposal.boards.find((b) => b.position_index === nextBoard)?.nodes
        : undefined;
    if (saved && stored) {
      setCorners(stored.corners);
      updateNodes(stored.nodes);
      setPresence(stored.presence);
      refreshPreview(stored.nodes, stored.presence, nextBoard, nextColumns);
      setDirty(false);
    } else if (proposeMissing) {
      const c: Point[] = suggested?.length
        ? [
            suggested[0],
            suggested[nextColumns],
            suggested.at(-1)!,
            suggested[suggested.length - nextColumns - 1],
          ]
        : [
            { x: size.width * 0.15, y: size.height * 0.15 },
            { x: size.width * 0.85, y: size.height * 0.15 },
            { x: size.width * 0.85, y: size.height * 0.85 },
            { x: size.width * 0.15, y: size.height * 0.85 },
          ].map((p) => ({ ...p, provenance: 'baseline_proposal' }));
      setCorners(c);
      const next = interpolateCorners(c, nextColumns);
      updateNodes(next);
      setPresence('present');
      refreshPreview(next, 'present', nextBoard, nextColumns);
      setDirty(true);
    } else {
      setCorners([]);
      updateNodes([]);
      setPresence('present');
      setDirty(false);
    }
    activity.current = [];
    setViewport(fullViewport(size));
    last.current = performance.now();
    setPending(null);
    pendingTarget.current = null;
    setElapsed(0);
    corrections.current = 0;
  }
  function canLeave() {
    return (
      !locked &&
      (!dirty || window.confirm('Odrzucić niezapisane zmiany tej planszy?'))
    );
  }
  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled && !initialized.current && state && size.width > 1) {
        initialized.current = true;
        load(true, 0, state, false);
      }
    });
    return () => {
      cancelled = true;
    };
    // Initial load only: subsequent shared revisions must not overwrite local edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, size]);
  function selectBoard(index: number) {
    if (canLeave()) load(true, index, state, false);
  }
  async function save(action: AnnotationRequest['action'], retry = false) {
    if (!state || submitting.current || reviewProtection.pending) return;
    if (pending && !retry) return;
    if (
      !pending &&
      (state.annotations[`${source.id}:${board}`]?.revision ?? null) !==
        loadedRevision
    ) {
      notify({
        kind: 'warning',
        message:
          'Zapis tej planszy zmienił się. Odśwież i sprawdź aktualny zapis przed nową decyzją.',
      });
      return;
    }
    if (!pending) trackActivity();
    submitting.current = true;
    setBusy(true);
    const body: AnnotationRequest = pending ?? {
      request_id: crypto.randomUUID(),
      expected_revision: state.revision,
      actor: 'operator',
      annotation: {
        source_id: source.id,
        board_index: board,
        topology: { columns, rows: 3 },
        presence,
        corners: presence === 'present' ? corners : [],
        nodes:
          presence === 'present'
            ? action === 'approve_full'
              ? nodes.map((p) => ({ ...p, provenance: 'human' as const }))
              : nodes
            : [],
      },
      action,
      reviewed_all_nodes: action === 'approve_full',
      activity_intervals_ms: [...activity.current],
      correction_count: corrections.current,
    };
    if (!pending)
      pendingTarget.current = state.photo_reviews?.[source.id]?.issues?.[
        String(body.annotation.board_index)
      ]
        ? body.annotation.board_index
        : nextApprovedPosition(body);
    setPending(body);
    try {
      const next = await writeAnnotation(body);
      accept(next);
      setPending(null);
      activity.current = [];
      corrections.current = 0;
      last.current = null;
      setDirty(false);
      const target = pendingTarget.current ?? body.annotation.board_index;
      if (target !== body.annotation.board_index) load(true, target, next);
      else load(true, body.annotation.board_index, next, false);
      notify({
        kind: 'success',
        message: `Zapisano pozycję ${body.annotation.board_index + 1}, rewizja ${next.revision}. ${body.action === 'draft' ? 'Szkic bez zatwierdzenia.' : body.action === 'approve_full' ? 'Pełna siatka zatwierdzona.' : 'Lokalizacja zatwierdzona.'} ${body.annotation.board_index === 8 ? approvalSummary(sourceAnnotations(next, source.id)) : ''}`,
      });
    } catch {
      notify({
        kind: 'error',
        message:
          'Zapis niepotwierdzony. Ponów identyczne żądanie; przy konflikcie rewizji odśwież stan i sprawdź zmiany.',
      });
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <section className="annotation-editor" onKeyDown={trackActivity}>
      <PhotoReviewPanel
        source={source}
        geometryDirty={dirty}
        geometryLocked={geometryLocked}
        geometryStale={
          (state?.annotations[`${source.id}:${board}`]?.revision ?? null) !==
          loadedRevision
        }
        onProtectionChange={onReviewProtection}
        onSelect={selectBoard}
      />
      <h3>Ręczna anotacja geometrii</h3>
      <p>
        Lokalizacja zatwierdza narożniki. Interpolowane węzły pozostają
        propozycją. Pełne zatwierdzenie wymaga oceny wszystkich{' '}
        {4 * (columns + 1)} węzłów i granic komórek.
      </p>
      <p>
        Pozycja {board + 1} ·{' '}
        {dirty
          ? 'Niezapisane zmiany / propozycja'
          : !nodes.length && presence === 'present'
            ? 'Brak wczytanej siatki'
            : statusLabel[
                boardStatus(state?.annotations[`${source.id}:${board}`])
              ]}{' '}
        · {columns} × 3
      </p>
      <nav aria-label="Pozycje plansz">
        {positionIndices(rows).map((index) => (
          <button
            key={index}
            disabled={locked || !state}
            aria-pressed={board === index}
            className={board === index ? 'selected' : ''}
            onClick={() => selectBoard(index)}
          >
            {index + 1} ·{' '}
            {
              statusLabel[
                boardStatus(state?.annotations[`${source.id}:${index}`])
              ]
            }
          </button>
        ))}
      </nav>
      <details open>
        <summary>Przegląd zapisanych plansz na całym zdjęciu</summary>
        <p>
          Pomarańczowy obrys i „!”: Do poprawy. „↻”: Do ponownego sprawdzenia.
          „◀”: wybrana pozycja i jej cropy poniżej.
        </p>
        <div
          className="saved-overview"
          style={{ aspectRatio: `${size.width} / ${size.height}` }}
        >
          <svg
            viewBox={`0 0 ${size.width} ${size.height}`}
            aria-label="Zapisane plansze"
          >
            <image
              href={assetUrl(source.asset_id)}
              width={size.width}
              height={size.height}
            />
            {rows
              .filter((row) => row.corners.length === 4)
              .map((row) => (
                <g
                  key={row.board_index}
                  role="button"
                  tabIndex={locked ? -1 : 0}
                  aria-label={`Wczytaj zapisaną pozycję ${row.board_index + 1}: ${statusLabel[boardStatus(row)]}`}
                  onClick={() => selectBoard(row.board_index)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      selectBoard(row.board_index);
                    }
                  }}
                >
                  <polygon
                    points={row.corners
                      .map((point) => `${point.x},${point.y}`)
                      .join(' ')}
                    fill="#74dcba22"
                    stroke={
                      state?.photo_reviews?.[source.id]?.issues?.[
                        String(row.board_index)
                      ]?.status === 'needs_correction'
                        ? '#f5a142'
                        : boardStatus(row) === 'full'
                          ? '#74dcba'
                          : '#ffce54'
                    }
                    strokeWidth={size.width / 300}
                  />
                  {Array.from({ length: 4 }, (_, gridRow) => (
                    <polyline
                      key={`row-${gridRow}`}
                      points={row.nodes
                        .slice(
                          gridRow * (row.topology.columns + 1),
                          (gridRow + 1) * (row.topology.columns + 1),
                        )
                        .map((point) => `${point.x},${point.y}`)
                        .join(' ')}
                      fill="none"
                      stroke="#fff9"
                      strokeWidth={size.width / 700}
                    />
                  ))}
                  {Array.from(
                    { length: row.topology.columns + 1 },
                    (_, col) => (
                      <polyline
                        key={`col-${col}`}
                        points={row.nodes
                          .filter(
                            (_, i) => i % (row.topology.columns + 1) === col,
                          )
                          .map((point) => `${point.x},${point.y}`)
                          .join(' ')}
                        fill="none"
                        stroke="#fff9"
                        strokeWidth={size.width / 700}
                      />
                    ),
                  )}
                  <text
                    x={row.corners[0].x}
                    y={row.corners[0].y + size.width / 35}
                    fontSize={size.width / 35}
                    fill="white"
                    stroke="#101827"
                    strokeWidth={size.width / 700}
                    paintOrder="stroke"
                  >
                    {row.board_index + 1}
                    {state?.photo_reviews?.[source.id]?.issues?.[
                      String(row.board_index)
                    ]?.status === 'needs_correction'
                      ? ' !'
                      : state?.photo_reviews?.[source.id]?.issues?.[
                            String(row.board_index)
                          ]?.status === 'needs_review'
                        ? ' ↻'
                        : ''}
                    {board === row.board_index ? ' ◀' : ''}
                  </text>
                </g>
              ))}
          </svg>
        </div>
      </details>
      <fieldset disabled={locked} aria-label="Edycja geometrii">
        <label>
          Topologia planszy{' '}
          <select
            value={columns}
            onChange={(event) => {
              if (!canLeave()) return;
              const value = Number(event.target.value) as 3 | 5;
              setColumns(value);
              onColumnsChange(value);
              setCorners([]);
              updateNodes([]);
              clearPreview();
              setPresence('present');
              setDirty(false);
              setViewport(fullViewport(size));
              drag.current = null;
              dragViewport.current = null;
            }}
          >
            <option value={5}>5 kolumn × 3 wiersze</option>
            <option value={3}>3 kolumny × 3 wiersze</option>
          </select>
        </label>
        <label>
          Pozycja planszy (od 1){' '}
          <input
            type="number"
            min={1}
            max={101}
            value={board + 1}
            disabled={busy}
            onChange={(e) => {
              const index = Number(e.target.value) - 1;
              if (Number.isInteger(index) && index >= 0 && index <= 100)
                selectBoard(index);
            }}
          />
        </label>
        <div className="action-group">
          <button
            disabled={busy || !state}
            onClick={() => {
              if (canLeave()) load(true, board, state, false);
            }}
          >
            Wczytaj dokładny zapis
          </button>
          <button
            disabled={busy || !state || size.width <= 1}
            onClick={() => {
              if (canLeave()) load(false);
            }}
          >
            Nowa propozycja z narożników
          </button>
        </div>
        <p>
          Wczytanie odtwarza zapisane węzły. Nowa propozycja wymaga osobnego
          zapisu i nie jest zatwierdzona.
        </p>
        <label>
          Obecność{' '}
          <select
            value={presence}
            disabled={busy}
            onChange={(e) => {
              mark();
              setPresence(e.target.value as GeometryAnnotation['presence']);
              refreshPreview(
                nodes,
                e.target.value as GeometryAnnotation['presence'],
              );
            }}
          >
            <option value="present">Obecna</option>
            <option value="absent">Nieobecna</option>
            <option value="occluded">Zasłonięta</option>
            <option value="unreadable">Nieczytelna</option>
          </select>
        </label>
        <label>
          Edytuj{' '}
          <select
            value={mode}
            disabled={busy}
            onChange={(e) => setMode(e.target.value as 'corners' | 'nodes')}
          >
            <option value="corners">Cztery narożniki</option>
            <option value="nodes">Wszystkie węzły</option>
          </select>
        </label>
        <div className="editor-workspace">
          <div>
            <button
              type="button"
              onClick={() => setViewport(fullViewport(size))}
            >
              Pokaż całe zdjęcie
            </button>
            <div
              className="editor-photo"
              ref={photoRef}
              style={{ aspectRatio: `${viewport.width} / ${viewport.height}` }}
            >
              <img
                className="editor-source-loader"
                src={assetUrl(source.asset_id)}
                alt="Zdjęcie do ręcznej anotacji"
                onLoad={(e) => {
                  const nextSize = {
                    width: e.currentTarget.naturalWidth,
                    height: e.currentTarget.naturalHeight,
                  };
                  setSize(nextSize);
                  setViewport(fullViewport(nextSize));
                }}
              />
              <svg
                viewBox={`${viewport.x} ${viewport.y} ${viewport.width} ${viewport.height}`}
                preserveAspectRatio="none"
                onDragStart={(e) => e.preventDefault()}
                style={{ touchAction: 'none', pointerEvents: 'auto' }}
                onPointerMove={(e) => {
                  if (drag.current === null || locked) return;
                  const rect = e.currentTarget.getBoundingClientRect();
                  const point = sourcePoint(
                    e.clientX,
                    e.clientY,
                    rect,
                    dragViewport.current ?? viewport,
                    size,
                  );
                  mark();
                  if (mode === 'corners') {
                    const next = corners.map((p, i) =>
                      i === drag.current ? point : p,
                    );
                    setCorners(next);
                    updateNodes(interpolateCorners(next, columns));
                  } else {
                    const next = nodes.map((p, i) =>
                      i === drag.current ? point : p,
                    );
                    updateNodes(next);
                    setCorners([
                      next[0],
                      next[columns],
                      next.at(-1)!,
                      next[next.length - columns - 1],
                    ]);
                  }
                }}
                onPointerUp={finishDrag}
                onPointerCancel={finishDrag}
                onLostPointerCapture={finishDrag}
              >
                <title>Przeciągnij numerowane uchwyty</title>
                <image
                  href={assetUrl(source.asset_id)}
                  x={0}
                  y={0}
                  width={size.width}
                  height={size.height}
                />
                {presence === 'present' && (
                  <>
                    {Array.from({ length: 4 }, (_, row) => (
                      <polyline
                        key={row}
                        points={nodes
                          .slice(row * (columns + 1), (row + 1) * (columns + 1))
                          .map((p) => `${p.x},${p.y}`)
                          .join(' ')}
                        fill="none"
                        stroke="#ffce54"
                        strokeWidth={(1.5 * viewport.width) / displayWidth}
                      />
                    ))}
                    {Array.from({ length: columns + 1 }, (_, col) => (
                      <polyline
                        key={`c${col}`}
                        points={nodes
                          .filter((_, i) => i % (columns + 1) === col)
                          .map((p) => `${p.x},${p.y}`)
                          .join(' ')}
                        fill="none"
                        stroke="#ffce54"
                        strokeWidth={(1.5 * viewport.width) / displayWidth}
                      />
                    ))}
                    {(mode === 'corners' ? corners : nodes).map((p, i) => (
                      <g
                        key={i}
                        onPointerDown={(e) => {
                          if (locked) return;
                          captureHandlePointer(e);
                          drag.current = i;
                          dragViewport.current = viewport;
                          clearPreview();
                          mark();
                        }}
                      >
                        <circle
                          cx={p.x}
                          cy={p.y}
                          r={(22 * viewport.width) / displayWidth}
                          fill="transparent"
                        />
                        <circle
                          cx={p.x}
                          cy={p.y}
                          r={(9 * viewport.width) / displayWidth}
                          fill="#263a4e"
                          stroke="white"
                          strokeWidth={viewport.width / displayWidth}
                        />
                        <text
                          x={p.x}
                          y={p.y}
                          fill="white"
                          textAnchor="middle"
                          dominantBaseline="central"
                          fontSize={(11 * viewport.width) / displayWidth}
                        >
                          {i + 1}
                        </text>
                      </g>
                    ))}
                  </>
                )}
              </svg>
            </div>
          </div>
          <aside className="editor-preview" aria-label="Cropy bieżącej siatki">
            <h4>Podgląd symboli</h4>
            <p>
              Cropy bieżącej siatki, bez zapisu. Odświeżają się po puszczeniu
              uchwytu.
            </p>
            <div
              className="editor-crops"
              style={{
                gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
              }}
            >
              {preview?.boards
                .flatMap((b) => b.cells)
                .map((cell) => (
                  <figure key={cell.index}>
                    {cell.asset_id ? (
                      <img
                        src={assetUrl(cell.asset_id)}
                        alt={`Komórka ${cell.index + 1}`}
                      />
                    ) : (
                      <span>Poza zdjęciem</span>
                    )}
                    <figcaption>{cell.index + 1}</figcaption>
                  </figure>
                ))}
            </div>
            <button
              type="button"
              disabled={!nodes.length || presence !== 'present'}
              onClick={() => refreshPreview(nodes)}
            >
              Ponów podgląd
            </button>
          </aside>
        </div>
        <p>
          Aktywny czas tego odcinka: {(elapsed / 1000).toFixed(1)} s. Przerwy
          ponad 30 s są wyłączone. Zmiana geometrii unieważnia poprzednie
          zatwierdzenie i podział.
        </p>
        <div className="action-group">
          <button
            disabled={
              busy || !state || (presence === 'present' && corners.length !== 4)
            }
            onClick={() => save('draft')}
          >
            Zapisz szkic
          </button>
          <button
            disabled={
              busy || !state || (presence === 'present' && corners.length !== 4)
            }
            onClick={() => save('approve_location')}
          >
            Zatwierdź tylko lokalizację
          </button>
          <button
            disabled={
              busy ||
              !state ||
              presence !== 'present' ||
              nodes.length !== 4 * (columns + 1)
            }
            onClick={() => save('approve_full')}
          >
            Zatwierdź pełną siatkę
          </button>
        </div>
        <p>
          Szkic zachowuje pracę bez zatwierdzenia. Lokalizacja potwierdza
          obecność i narożniki. Klikając pełne zatwierdzenie, potwierdzasz
          wszystkie węzły oraz granice komórek. Zapis pozycji oznaczonej do
          poprawy lub ponownego sprawdzenia pozostawia bieżącą pozycję. W
          pozostałych zatwierdzenie pozycji 1–8 otwiera kolejną; po pozycji9
          pozostajesz na zdjęciu.
        </p>
      </fieldset>
      {pending && (
        <button disabled={busy} onClick={() => save(pending.action, true)}>
          Ponów identyczne żądanie: {pending.action}
        </button>
      )}
      <button
        disabled={busy || reviewProtection.pending}
        onClick={() => {
          if (submitting.current || reviewProtection.pending) return;
          if (
            (dirty || pending) &&
            !window.confirm(
              'Odczytać aktualny zapis i zastąpić lokalną edycję? Niepotwierdzone żądanie nie będzie ponawiane automatycznie.',
            )
          )
            return;
          submitting.current = true;
          setBusy(true);
          refresh()
            .then((next) => {
              setPending(null);
              load(true, board, next, false);
              notify({
                kind: 'info',
                message:
                  'Odświeżono i wczytano zapis. Sprawdź go przed nową decyzją.',
              });
            })
            .catch(() =>
              notify({ kind: 'error', message: 'Odczyt nie powiódł się.' }),
            )
            .finally(() => {
              submitting.current = false;
              setBusy(false);
            });
        }}
      >
        Odśwież po konflikcie
      </button>
    </section>
  );
}

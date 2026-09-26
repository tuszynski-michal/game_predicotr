'use client';
/* eslint-disable @next/next/no-img-element -- registered local image */
import { useEffect, useRef, useState } from 'react';
import {
  assetUrl,
  previewGeometry,
  readAnnotations,
  writeAnnotation,
  type AnnotationRequest,
  type AnnotationState,
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

export function GeometryEditor({
  source,
  proposal,
  columns,
}: {
  source: Source;
  proposal: GeometryResult | null;
  columns: 3 | 5;
}) {
  const [state, setState] = useState<AnnotationState | null>(null);
  const [size, setSize] = useState({ width: 1, height: 1 });
  const [viewport, setViewport] = useState<Viewport>({
    x: 0,
    y: 0,
    width: 1,
    height: 1,
  });
  const [preview, setPreview] = useState<GeometryResult | null>(null);
  const [previewMessage, setPreviewMessage] = useState(
    'Wczytaj siatkę, aby zobaczyć cropy.',
  );
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
  const [actor, setActor] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Wczytywanie anotacji…');
  const drag = useRef<number | null>(null);
  const activity = useRef<number[]>([]);
  const last = useRef<number | null>(null);
  const [pending, setPending] = useState<AnnotationRequest | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const corrections = useRef(0);
  const locked = busy || pending !== null;
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
    setPreviewMessage('Podgląd wymaga bieżącej kompletnej siatki.');
  }
  function refreshPreview(next: Point[], nextPresence = presence) {
    clearPreview();
    if (nextPresence !== 'present' || next.length !== 4 * (columns + 1)) return;
    setPreviewMessage('Odświeżanie cropów…');
    void previewOrder.current.run(
      () =>
        previewGeometry(source.id, columns, {
          position_index: board,
          status: 'complete',
          nodes: next,
        }),
      (value) => {
        setPreview(value);
        setPreviewMessage(
          value.status === 'detected'
            ? 'Cropy bieżącej siatki — bez zapisu.'
            : `Nieprawidłowa siatka: ${value.reasons.join(', ')}`,
        );
      },
      () => setPreviewMessage('Nie można pobrać cropów. Ponów podgląd.'),
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
  useEffect(() => {
    let cancelled = false;
    readAnnotations()
      .then((value) => {
        if (!cancelled) {
          setState(value);
          setMessage('');
        }
      })
      .catch(() => {
        if (!cancelled)
          setMessage(
            'Nie można wczytać anotacji. Wymagana konfiguracja VISION_LAB_ANNOTATIONS.',
          );
      });
    return () => {
      cancelled = true;
    };
  }, []);
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
    setReviewed(false);
  }
  function load(saved = true) {
    const stored = state?.annotations[`${source.id}:${board}`];
    const suggested =
      proposal?.topology.columns === columns
        ? proposal.boards.find((b) => b.position_index === board)?.nodes
        : undefined;
    if (saved && stored) {
      if (stored.topology.columns !== columns) {
        setMessage(
          'Zapisana plansza ma inną topologię. Ustaw właściwą topologię przed wczytaniem.',
        );
        return;
      }
      setCorners(stored.corners);
      updateNodes(stored.nodes);
      setPresence(stored.presence);
      refreshPreview(stored.nodes, stored.presence);
    } else {
      const c: Point[] = suggested?.length
        ? [
            suggested[0],
            suggested[columns],
            suggested.at(-1)!,
            suggested[suggested.length - columns - 1],
          ]
        : [
            { x: size.width * 0.15, y: size.height * 0.15 },
            { x: size.width * 0.85, y: size.height * 0.15 },
            { x: size.width * 0.85, y: size.height * 0.85 },
            { x: size.width * 0.15, y: size.height * 0.85 },
          ].map((p) => ({ ...p, provenance: 'baseline_proposal' }));
      setCorners(c);
      const next = interpolateCorners(c, columns);
      updateNodes(next);
      setPresence('present');
      refreshPreview(next, 'present');
    }
    activity.current = [];
    setViewport(fullViewport(size));
    last.current = performance.now();
    setPending(null);
    setElapsed(0);
    corrections.current = 0;
    setReviewed(false);
    setMessage('Wczytano do edycji. Każdy zapis wymaga osobnej decyzji.');
  }
  async function save(action: AnnotationRequest['action'], retry = false) {
    if (!state || busy) return;
    if (pending && !retry) return;
    if (!pending) trackActivity();
    setBusy(true);
    const body: AnnotationRequest = pending ?? {
      request_id: crypto.randomUUID(),
      expected_revision: state.revision,
      actor,
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
      reviewed_all_nodes: reviewed,
      activity_intervals_ms: [...activity.current],
      correction_count: corrections.current,
    };
    setPending(body);
    try {
      const next = await writeAnnotation(body);
      setState(next);
      setPending(null);
      activity.current = [];
      corrections.current = 0;
      last.current = null;
      setMessage(
        `Zapisano rewizję ${next.revision}. ${action === 'approve_full' ? 'Pełna siatka zatwierdzona.' : 'Brak zatwierdzenia pełnej siatki.'}`,
      );
    } catch {
      setMessage(
        'Zapis niepotwierdzony. Ponów identyczne żądanie; przy konflikcie rewizji odśwież stan i sprawdź zmiany.',
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="annotation-editor" onKeyDown={trackActivity}>
      <h3>Ręczna anotacja geometrii</h3>
      <p>
        Lokalizacja zatwierdza narożniki. Interpolowane węzły pozostają
        propozycją. Pełne zatwierdzenie wymaga oceny wszystkich{' '}
        {4 * (columns + 1)} węzłów i granic komórek.
      </p>
      <fieldset disabled={locked}>
        <label>
          Osoba podejmująca decyzję{' '}
          <input
            value={actor}
            disabled={busy}
            onChange={(e) => setActor(e.target.value)}
          />
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
              setBoard(Number(e.target.value) - 1);
              setCorners([]);
              updateNodes([]);
              clearPreview();
              setViewport(fullViewport(size));
              setReviewed(false);
              setPending(null);
            }}
          />
        </label>
        <button disabled={busy || !state} onClick={() => load(true)}>
          Wczytaj zapis / propozycję
        </button>
        <button disabled={busy || !state} onClick={() => load(false)}>
          Nowa propozycja z narożników
        </button>
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
                          setPreviewMessage(
                            'Podgląd odświeży się po puszczeniu uchwytu.',
                          );
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
            <p role="status">{previewMessage}</p>
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
        <label>
          <input
            type="checkbox"
            checked={reviewed}
            disabled={
              busy ||
              nodes.length !== 4 * (columns + 1) ||
              presence !== 'present'
            }
            onChange={(e) => setReviewed(e.target.checked)}
          />{' '}
          Sprawdziłem każdy węzeł i wszystkie granice komórek; zatwierdzam pełną
          referencję.
        </label>
        <p>
          Aktywny czas tego odcinka: {(elapsed / 1000).toFixed(1)} s. Przerwy
          ponad 30 s są wyłączone. Zmiana geometrii unieważnia poprzednie
          zatwierdzenie i podział.
        </p>
        <button
          disabled={busy || !state || !actor.trim()}
          onClick={() => save('draft')}
        >
          Zapisz szkic
        </button>
        <button
          disabled={busy || !state || !actor.trim()}
          onClick={() => save('approve_location')}
        >
          Zatwierdź tylko lokalizację
        </button>
        <button
          disabled={busy || !state || !actor.trim() || !reviewed}
          onClick={() => save('approve_full')}
        >
          Zatwierdź pełną siatkę
        </button>
      </fieldset>
      {pending && (
        <button disabled={busy} onClick={() => save(pending.action, true)}>
          Ponów identyczne żądanie: {pending.action}
        </button>
      )}
      <button
        disabled={busy}
        onClick={() =>
          readAnnotations()
            .then((next) => {
              setState(next);
              setPending(null);
              setMessage('Odświeżono stan. Wczytaj zapis przed nową decyzją.');
            })
            .catch(() => setMessage('Odczyt nie powiódł się.'))
        }
      >
        Odśwież po konflikcie
      </button>
      <p role="status">{message}</p>
    </section>
  );
}

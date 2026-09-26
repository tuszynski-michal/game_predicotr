'use client';
/* eslint-disable @next/next/no-img-element -- registered local image */
import { useEffect, useRef, useState } from 'react';
import {
  assetUrl,
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
      setNodes(stored.nodes);
      setPresence(stored.presence);
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
      setNodes(interpolateCorners(c, columns));
      setPresence('present');
    }
    activity.current = [];
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
              setNodes([]);
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
        <div className="photo editor-photo">
          <img
            src={assetUrl(source.asset_id)}
            alt="Zdjęcie do ręcznej anotacji"
            onLoad={(e) =>
              setSize({
                width: e.currentTarget.naturalWidth,
                height: e.currentTarget.naturalHeight,
              })
            }
          />
          <svg
            viewBox={`0 0 ${size.width} ${size.height}`}
            style={{ touchAction: 'none', pointerEvents: 'auto' }}
            onPointerMove={(e) => {
              if (drag.current === null || locked) return;
              const rect = e.currentTarget.getBoundingClientRect();
              const point: Point = {
                x: Math.max(
                  0,
                  Math.min(
                    size.width - 1,
                    ((e.clientX - rect.left) / rect.width) * size.width,
                  ),
                ),
                y: Math.max(
                  0,
                  Math.min(
                    size.height - 1,
                    ((e.clientY - rect.top) / rect.height) * size.height,
                  ),
                ),
                provenance: 'human',
              };
              mark();
              if (mode === 'corners') {
                const next = corners.map((p, i) =>
                  i === drag.current ? point : p,
                );
                setCorners(next);
                setNodes(interpolateCorners(next, columns));
              } else {
                const next = nodes.map((p, i) =>
                  i === drag.current ? point : p,
                );
                setNodes(next);
                setCorners([
                  next[0],
                  next[columns],
                  next.at(-1)!,
                  next[next.length - columns - 1],
                ]);
              }
            }}
            onPointerUp={() => {
              if (drag.current !== null) corrections.current += 1;
              drag.current = null;
            }}
            onPointerCancel={() => {
              drag.current = null;
            }}
          >
            <title>Przeciągnij numerowane uchwyty</title>
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
                    strokeWidth={size.width / 500}
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
                    strokeWidth={size.width / 500}
                  />
                ))}
                {(mode === 'corners' ? corners : nodes).map((p, i) => (
                  <g
                    key={i}
                    onPointerDown={(e) => {
                      if (locked) return;
                      drag.current = i;
                      e.currentTarget.ownerSVGElement?.setPointerCapture(
                        e.pointerId,
                      );
                      mark();
                    }}
                  >
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={size.width / 45}
                      fill="#263a4e"
                      stroke="white"
                      strokeWidth={size.width / 600}
                    />
                    <text
                      x={p.x}
                      y={p.y}
                      fill="white"
                      textAnchor="middle"
                      dominantBaseline="central"
                      fontSize={size.width / 45}
                    >
                      {i + 1}
                    </text>
                  </g>
                ))}
              </>
            )}
          </svg>
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

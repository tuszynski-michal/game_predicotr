'use client';

import { useRef, useState } from 'react';
import type { ContentReferenceResponse } from '@game-predictor/admin-api-client';
import {
  contentStateLabels,
  convexContentQuad,
  emptyContentCells,
  manualContentLattice,
  validContentCells,
  type ContentCells,
  type ContentCell,
  type ContentNodes,
  type ContentPoint,
} from './grid-content-state';

/** Pure annotation surface: no API, storage, model suggestions or geometry writes. */
export function GridContentCanvas({
  sourceUrl,
  width,
  height,
  measureGeometry = false,
  initialCells,
  ordinaryPreview,
  disabled = false,
  onChange,
}: {
  readonly sourceUrl: string;
  readonly width: number;
  readonly height: number;
  readonly measureGeometry?: boolean;
  readonly initialCells?: ContentCells;
  readonly ordinaryPreview?: ContentReferenceResponse['ordinaryPreview'];
  readonly disabled?: boolean;
  readonly onChange: (
    cells: ContentCells,
    nodes: ContentNodes | null,
    ready: boolean,
  ) => void;
}) {
  const [cells, setCells] = useState<ContentCells>(() =>
    structuredClone(initialCells ?? emptyContentCells()),
  );
  const [nodes, setNodes] = useState<ContentNodes | null>(null);
  const [corners, setCorners] = useState<ContentPoint[]>([]);
  const [draft, setDraft] = useState<ContentPoint[]>([]);
  const [cellIndex, setCellIndex] = useState(0);
  const [nodeIndex, setNodeIndex] = useState(0);
  const [quadIndex, setQuadIndex] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [showGrid, setShowGrid] = useState(true);
  const [showOutlines, setShowOutlines] = useState(true);
  const contentHidden = !measureGeometry && !showOutlines;
  const [showCrops, setShowCrops] = useState(false);
  const [panning, setPanning] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);
  const panStart = useRef<{
    x: number;
    y: number;
    left: number;
    top: number;
  } | null>(null);
  const [tool, setTool] = useState<'geometry' | 'content'>(
    measureGeometry ? 'geometry' : 'content',
  );
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [drag, setDrag] = useState<{
    kind: 'node' | 'quad';
    index: number;
  } | null>(null);
  const ready = (
    c: ContentCells,
    n: ContentNodes | null,
    imageReady = loaded,
  ) => imageReady && validContentCells(c) && (!measureGeometry || n !== null);
  function publish(c: ContentCells, n = nodes) {
    setCells(c);
    setNodes(n);
    onChange(c, n, ready(c, n));
  }
  function updateCell(cell: ContentCell) {
    const next = [...cells] as ContentCells;
    next[cellIndex] = cell;
    publish(next);
  }
  function point(event: React.PointerEvent<SVGSVGElement>): ContentPoint {
    const rect = event.currentTarget.getBoundingClientRect();
    return [
      Math.max(
        0,
        Math.min(width, ((event.clientX - rect.left) * width) / rect.width),
      ),
      Math.max(
        0,
        Math.min(height, ((event.clientY - rect.top) * height) / rect.height),
      ),
    ];
  }
  function place(p: ContentPoint) {
    if (disabled || !loaded || panning) return;
    if (tool === 'content' && !showOutlines) {
      setError('Włącz obrysy grafik, aby je zmieniać.');
      return;
    }
    setError('');
    if (tool === 'geometry') {
      if (nodes !== null) {
        const n = [...nodes] as ContentNodes;
        n[nodeIndex] = p;
        publish(cells, n);
        return;
      }
      const next = [...corners, p];
      if (next.length === 4) {
        try {
          publish(cells, manualContentLattice(next));
          setCorners([]);
        } catch (failure) {
          setError(String(failure));
          setCorners([]);
        }
      } else setCorners(next);
    } else {
      const next = [...draft, p];
      if (next.length === 4) {
        if (!convexContentQuad(next))
          setError(
            'Obwiednia musi być wypukła. Zaznacz rogi kolejno wokół grafiki.',
          );
        else
          updateCell({
            ...cells[cellIndex],
            quad: next as NonNullable<ContentCell['quad']>,
          });
        setDraft([]);
      } else setDraft(next);
    }
  }
  const selected = cells[cellIndex];
  // Saved ordinary geometry is a read-only overlay, never the editable blind nodes.
  const displayedNodes = measureGeometry ? nodes : ordinaryPreview?.nodes;
  const selectedCrop = ordinaryPreview?.productionCells.find(
    (c) => c.cellIndex === cellIndex,
  );
  const cropPoints = selectedCrop?.quad;
  const cropBounds = cropPoints
    ? (() => {
        const xs = cropPoints.map((p) => p[0]),
          ys = cropPoints.map((p) => p[1]);
        const left = Math.min(...xs),
          top = Math.min(...ys),
          w = Math.max(...xs) - left,
          h = Math.max(...ys) - top;
        return `${left - w * 0.25} ${top - h * 0.25} ${w * 1.5} ${h * 1.5}`;
      })()
    : undefined;
  return (
    <section className="gridContentCanvas" aria-label="Edytor zawartości pól">
      <p>
        {measureGeometry
          ? 'Zaznacz pełną widoczną grafikę bez tła pola. „10” to jeden symbol. Obwiednie i siatka są niezależne.'
          : 'Obrys obejmuje pełną grafikę razem z ozdobnym obramowaniem, bez tła i sąsiedniego symbolu. Pola siatki mają wspólne granice, a obrysy J i 10 mogą mieć różne rozmiary. „10” to jeden symbol.'}
      </p>
      <div className="gridContentActions">
        {!measureGeometry && ordinaryPreview ? (
          <>
            <label>
              <input
                type="checkbox"
                checked={showGrid}
                onChange={(e) => setShowGrid(e.target.checked)}
              />{' '}
              Siatka pól
            </label>
            <label>
              <input
                type="checkbox"
                checked={showOutlines}
                onChange={(e) => setShowOutlines(e.target.checked)}
              />{' '}
              Obrysy grafik
            </label>
            <label>
              <input
                type="checkbox"
                checked={showCrops}
                onChange={(e) => setShowCrops(e.target.checked)}
              />{' '}
              Rzeczywiste wycinki
            </label>
            <p>
              Siatka pól: wspólne granice z 24 zapisanych punktów. Obrysy
              grafik: aktualne etykiety i Twoje zmiany. Rzeczywiste wycinki:
              kreskowany zakres produkcji z przypiętego renderu, nie większy
              kadr do oznaczania.
            </p>
            {ordinaryPreview.state === 'protected' ? (
              <p role="status">
                Podgląd siatki i wycinków ukryty dla tego zdjęcia lub roli
                kontrolnej.
              </p>
            ) : null}
          </>
        ) : null}
        <label>
          Powiększenie podglądu{' '}
          <select
            aria-label="Powiększenie podglądu"
            value={zoom}
            disabled={disabled}
            onChange={(event) => setZoom(Number(event.target.value))}
          >
            {[1, 2, 4, 8, 16].map((value) => (
              <option key={value} value={value}>
                {value}×
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondaryButton"
          type="button"
          disabled={disabled}
          aria-pressed={panning}
          onClick={() => {
            setPanning((value) => !value);
            setDrag(null);
            panStart.current = null;
          }}
        >
          {panning ? 'Wróć do zaznaczania' : 'Przesuwaj podgląd'}
        </button>
        <span>
          Powiększenie i przesuwanie nie zmieniają punktów ani wycinków.
        </span>
      </div>
      {measureGeometry ? (
        <div className="gridContentActions">
          <button
            className={
              tool === 'geometry' ? 'primaryButton' : 'secondaryButton'
            }
            type="button"
            disabled={disabled}
            aria-pressed={tool === 'geometry'}
            onClick={() => {
              setTool('geometry');
              setDraft([]);
            }}
          >
            Edytuj 24 punkty geometrii
          </button>
          <button
            className={tool === 'content' ? 'primaryButton' : 'secondaryButton'}
            type="button"
            disabled={disabled}
            aria-pressed={tool === 'content'}
            onClick={() => {
              setTool('content');
              setCorners([]);
            }}
          >
            Edytuj zawartość 15 pól
          </button>
        </div>
      ) : null}
      {tool === 'content' ? (
        <div className="gridContentActions">
          <label>
            Pole{' '}
            <select
              aria-label="Pole zawartości"
              disabled={disabled}
              value={cellIndex}
              onChange={(e) => {
                setCellIndex(Number(e.target.value));
                setDraft([]);
              }}
            >
              {cells.map((_, i) => (
                <option key={i} value={i}>
                  Rząd {Math.floor(i / 5) + 1}, kolumna {(i % 5) + 1}
                </option>
              ))}
            </select>
          </label>
          <label>
            Widoczność{' '}
            <select
              aria-label="Widoczność pola"
              disabled={disabled}
              value={selected.state}
              onChange={(e) =>
                updateCell({
                  ...selected,
                  state: e.target.value as ContentCell['state'],
                })
              }
            >
              {Object.entries(contentStateLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="secondaryButton"
            disabled={disabled || contentHidden}
            onClick={() => {
              if (contentHidden) return;
              updateCell({ state: selected.state });
              setDraft([]);
            }}
          >
            Usuń obwiednię wybranego pola
          </button>
        </div>
      ) : null}
      {tool === 'geometry' ? (
        <p>
          {nodes
            ? 'Wybierz węzeł, przeciągnij go lub popraw jego współrzędne.'
            : `Zaznacz kolejno: lewy górny, prawy górny, prawy dolny i lewy dolny róg planszy. Zaznaczono ${corners.length}/4. Następnie sprawdź wszystkie 24 węzły.`}
        </p>
      ) : (
        <p>
          Zaznacz cztery rogi obwiedni kolejno wokół grafiki ({draft.length}/4).
          Dla zasłoniętej lub uciętej grafiki oznacz tylko faktycznie widoczny
          fragment.
        </p>
      )}
      <div ref={viewportRef} className="gridContentViewport">
        <div
          className="gridContentImage"
          style={{
            aspectRatio: `${width} / ${height}`,
            width: `${zoom * 100}%`,
          }}
        >
          {/* A plain source image; only annotations made in this surface are overlaid. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={sourceUrl}
            alt="Źródło do etykietowania"
            onLoad={(event) => {
              if (
                event.currentTarget.naturalWidth !== width ||
                event.currentTarget.naturalHeight !== height
              ) {
                setError(
                  'Wymiary obrazu nie zgadzają się z przypiętym źródłem.',
                );
                setLoaded(false);
                onChange(cells, nodes, false);
                return;
              }
              setLoaded(true);
              setError('');
              onChange(cells, nodes, ready(cells, nodes, true));
            }}
            onError={() => {
              setLoaded(false);
              setError('Nie udało się odczytać źródła.');
              onChange(cells, nodes, false);
            }}
          />
          <svg
            viewBox={`0 0 ${width} ${height}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={
              measureGeometry
                ? 'Ręczne punkty i obwiednie'
                : 'Zapisana siatka i obwiednie'
            }
            style={{ touchAction: 'none' }}
            onPointerDown={(event) => {
              if (event.button !== 0 || disabled || !loaded) return;
              if (panning && viewportRef.current) {
                panStart.current = {
                  x: event.clientX,
                  y: event.clientY,
                  left: viewportRef.current.scrollLeft,
                  top: viewportRef.current.scrollTop,
                };
                event.currentTarget.setPointerCapture?.(event.pointerId);
                return;
              }
              if (drag) return;
              place(point(event));
            }}
            onPointerMove={(event) => {
              if (panning && panStart.current && viewportRef.current) {
                viewportRef.current.scrollLeft =
                  panStart.current.left - (event.clientX - panStart.current.x);
                viewportRef.current.scrollTop =
                  panStart.current.top - (event.clientY - panStart.current.y);
                return;
              }
              if (
                !drag ||
                disabled ||
                !loaded ||
                (drag.kind === 'quad' && !showOutlines)
              )
                return;
              const p = point(event);
              if (drag.kind === 'node' && nodes) {
                const n = [...nodes] as ContentNodes;
                n[drag.index] = p;
                publish(cells, n);
              } else if (selected.quad) {
                const q = [...selected.quad] as NonNullable<
                  ContentCell['quad']
                >;
                q[drag.index] = p;
                if (convexContentQuad(q)) updateCell({ ...selected, quad: q });
              }
            }}
            onPointerUp={() => {
              setDrag(null);
              panStart.current = null;
            }}
            onPointerCancel={() => {
              setDrag(null);
              panStart.current = null;
            }}
          >
            {displayedNodes && showGrid
              ? Array.from({ length: 4 }, (_, row) => (
                  <polyline
                    key={`r${row}`}
                    points={displayedNodes
                      .slice(row * 6, row * 6 + 6)
                      .map((p) => p.join(','))
                      .join(' ')}
                    className="gridContentLattice"
                  />
                ))
              : null}
            {displayedNodes && showGrid
              ? Array.from({ length: 6 }, (_, col) => (
                  <polyline
                    key={`c${col}`}
                    points={[0, 1, 2, 3]
                      .map((r) => displayedNodes[r * 6 + col].join(','))
                      .join(' ')}
                    className="gridContentLattice"
                  />
                ))
              : null}
            {!measureGeometry && showCrops
              ? ordinaryPreview?.productionCells.map((cell) => (
                  <polygon
                    key={`crop${cell.cellIndex}`}
                    data-cell-index={cell.cellIndex}
                    points={cell.quad.map((p) => p.join(',')).join(' ')}
                    className="gridContentProductionCrop"
                  />
                ))
              : null}
            {showOutlines
              ? cells.map((cell, i) =>
                  cell.quad ? (
                    <polygon
                      key={i}
                      data-content-state={cell.state}
                      points={cell.quad.map((p) => p.join(',')).join(' ')}
                      className={
                        i === cellIndex
                          ? 'gridContentQuad selected'
                          : 'gridContentQuad'
                      }
                    >
                      <title>{`Pole ${i + 1}: ${contentStateLabels[cell.state]}. ${cell.state === 'visible' ? 'Obwiednia pełnej grafiki.' : 'Obwiednia widocznego fragmentu; nie potwierdza pełnego symbolu.'}`}</title>
                    </polygon>
                  ) : null,
                )
              : null}
            {[...corners, ...draft].map((p, i) => (
              <circle
                key={`d${i}`}
                cx={p[0]}
                cy={p[1]}
                r={Math.max(width / 150, 2)}
                className="gridContentHandle"
              />
            ))}
            {tool === 'geometry' && nodes
              ? nodes.map((p, i) => (
                  <circle
                    key={`n${i}`}
                    cx={p[0]}
                    cy={p[1]}
                    r={Math.max(width / 100, 3)}
                    className="gridContentHandle"
                    onPointerDown={(event) => {
                      if (panning) return;
                      event.stopPropagation();
                      if (disabled) return;
                      setNodeIndex(i);
                      setDrag({ kind: 'node', index: i });
                      event.currentTarget.setPointerCapture?.(event.pointerId);
                    }}
                  />
                ))
              : null}
            {tool === 'content' && showOutlines && selected.quad
              ? selected.quad.map((p, i) => (
                  <circle
                    key={`q${i}`}
                    cx={p[0]}
                    cy={p[1]}
                    r={Math.max(width / 100, 3)}
                    className="gridContentHandle"
                    onPointerDown={(event) => {
                      if (panning) return;
                      event.stopPropagation();
                      if (disabled) return;
                      setDrag({ kind: 'quad', index: i });
                      event.currentTarget.setPointerCapture?.(event.pointerId);
                    }}
                  />
                ))
              : null}
          </svg>
        </div>
      </div>
      {!loaded ? <p role="status">Oczekiwanie na obraz źródłowy…</p> : null}
      {!measureGeometry && ordinaryPreview && showCrops ? (
        <figure>
          <figcaption>
            Powiększone pole {cellIndex + 1}: otoczenie pomaga ocenić grafikę.
            Kreskowany obrys ogranicza rzeczywisty wycinek produkcyjny; kadr
            podglądu jest większy.
          </figcaption>
          {cropBounds && selectedCrop ? (
            <svg
              viewBox={cropBounds}
              role="img"
              aria-label={`Otoczenie i zakres produkcyjnego wycinka pola ${cellIndex + 1}`}
              style={{ width: '100%', maxWidth: 480 }}
            >
              <image href={sourceUrl} width={width} height={height} />
              <polygon
                points={selectedCrop.quad.map((p) => p.join(',')).join(' ')}
                className="gridContentProductionCrop"
              />
              {showOutlines && selected.quad ? (
                <polygon
                  points={selected.quad.map((p) => p.join(',')).join(' ')}
                  className="gridContentQuad"
                />
              ) : null}
            </svg>
          ) : (
            <p>
              Brak przypiętego produkcyjnego wycinka tego pola. Nie zastępujemy
              go całym polem.
            </p>
          )}
        </figure>
      ) : null}
      {tool === 'geometry' && nodes ? (
        <div className="gridContentActions">
          <label>
            Węzeł{' '}
            <select
              aria-label="Węzeł geometrii"
              value={nodeIndex}
              disabled={disabled}
              onChange={(e) => setNodeIndex(Number(e.target.value))}
            >
              {nodes.map((_, i) => (
                <option key={i} value={i}>
                  {i + 1}
                </option>
              ))}
            </select>
          </label>
          {([0, 1] as const).map((axis) => (
            <label key={axis}>
              {axis === 0 ? 'X' : 'Y'}{' '}
              <input
                aria-label={`Węzeł ${axis === 0 ? 'X' : 'Y'}`}
                type="number"
                step="any"
                min={0}
                max={axis === 0 ? width : height}
                disabled={disabled}
                value={nodes[nodeIndex][axis]}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (
                    !Number.isFinite(v) ||
                    v < 0 ||
                    v > (axis === 0 ? width : height)
                  )
                    return;
                  const n = structuredClone(nodes);
                  n[nodeIndex][axis] = v;
                  publish(cells, n);
                }}
              />
            </label>
          ))}
          <button
            className="secondaryButton"
            type="button"
            disabled={disabled}
            onClick={() => {
              setCorners([]);
              publish(cells, null);
            }}
          >
            Wyznacz geometrię od początku
          </button>
        </div>
      ) : null}
      {tool === 'content' && selected.quad ? (
        <div className="gridContentActions">
          <label>
            Róg obwiedni{' '}
            <select
              aria-label="Róg obwiedni"
              value={quadIndex}
              disabled={disabled || contentHidden}
              onChange={(e) => setQuadIndex(Number(e.target.value))}
            >
              {[0, 1, 2, 3].map((i) => (
                <option key={i} value={i}>
                  {i + 1}
                </option>
              ))}
            </select>
          </label>
          {([0, 1] as const).map((axis) => (
            <label key={axis}>
              {axis === 0 ? 'X' : 'Y'}{' '}
              <input
                aria-label={`Obwiednia ${axis === 0 ? 'X' : 'Y'}`}
                type="number"
                step="any"
                min={0}
                max={axis === 0 ? width : height}
                disabled={disabled || contentHidden}
                value={selected.quad![quadIndex][axis]}
                onChange={(e) => {
                  if (contentHidden) return;
                  const v = Number(e.target.value);
                  if (
                    !Number.isFinite(v) ||
                    v < 0 ||
                    v > (axis === 0 ? width : height)
                  )
                    return;
                  const q = structuredClone(selected.quad!);
                  q[quadIndex][axis] = v;
                  if (convexContentQuad(q))
                    updateCell({ ...selected, quad: q });
                }}
              />
            </label>
          ))}
        </div>
      ) : null}
      {tool === 'content' ? (
        <button
          className="secondaryButton"
          type="button"
          disabled={disabled || cellIndex === 14}
          onClick={() => {
            setCellIndex((v) => Math.min(14, v + 1));
            setDraft([]);
          }}
        >
          Następne pole
        </button>
      ) : null}
      <p>
        Obwiednie: {cells.filter((c) => c.quad).length}/15. Widoczne w całości:{' '}
        {cells.filter((c) => c.state === 'visible').length}/15. Nieznane:{' '}
        {cells.filter((c) => c.state === 'unknown').length}/15.
      </p>
      {!validContentCells(cells) ? (
        <p role="alert">
          Każde pole „Widoczny w całości” wymaga pełnej wypukłej obwiedni.
        </p>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}

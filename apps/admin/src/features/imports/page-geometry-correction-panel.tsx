'use client';

/* Geometry previews are checksum-bound local assets and must bypass Next image optimization. */
/* eslint-disable @next/next/no-img-element */

import type {
  AdminApiClient,
  BrowserPageGeometryOverrideCreate,
  BrowserPageGeometryReviewSourceResponse,
} from '@game-predictor/admin-api-client';
import { fitManualImageToViewport } from '@game-predictor/manual-image-selection-core';
import {
  type PointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { resolveAdminApiBaseUrl } from '@/config/admin-api';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';

import {
  appendPageGeometryCorner,
  applyPageGeometryMeshOverrides,
  completePageGeometryCorners,
  createPageGeometryMesh,
  isPageGeometryMeshBoundaryPoint,
  PAGE_MESH_POINT_COUNT,
  pageGeometryPointFromRenderedCanvas,
  pageGeometryQuadsFromMesh,
  type PageGeometryCorners,
  type PageGeometryPoint,
  type PageGeometryQuad,
} from './page-geometry-mesh';

type GeometryCorrectionClient = Pick<
  AdminApiClient,
  'createBrowserPageGeometryOverride' | 'listBrowserPageGeometryReviewSources'
>;

type Point = PageGeometryPoint;
type Quad = PageGeometryQuad;
type PageCorners = PageGeometryCorners;
type CorrectionMode = 'curve' | 'page' | number;

interface PageGeometryCorrectionPanelProps {
  readonly api: GeometryCorrectionClient;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly onSubmitSaved: () => Promise<void>;
  readonly preflightJobId: string;
  readonly uploadId: string;
}

const HANDLE_RADIUS = 14;
const MIN_GEOMETRY_ZOOM = 1;
const MAX_GEOMETRY_ZOOM = 30;
const GEOMETRY_ZOOM_STEP = 0.25;

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, Math.round(value)));
}

function initialCorners(width: number, height: number): PageCorners {
  const horizontal = Math.max(2, Math.round(width * 0.08));
  const vertical = Math.max(2, Math.round(height * 0.08));
  return [
    { x: horizontal, y: vertical },
    { x: width - horizontal, y: vertical },
    { x: width - horizontal, y: height - vertical },
    { x: horizontal, y: height - vertical },
  ];
}

function existingSourceQuads(
  source: BrowserPageGeometryReviewSourceResponse,
): readonly Quad[] {
  const raw = source.existingFinalQuads;
  if (
    raw === null ||
    raw === undefined ||
    raw.length !== 9 ||
    raw.some((quad) => quad.length !== 4)
  ) {
    return [];
  }
  return raw.map((quad) => [quad[0]!, quad[1]!, quad[2]!, quad[3]!] as Quad);
}

function outerCornersFromQuads(quads: readonly Quad[]): PageCorners | null {
  if (quads.length !== 9) return null;
  return [quads[0]![0], quads[2]![1], quads[8]![2], quads[6]![3]];
}

function sourceAssetUrl(
  apiBaseUrl: string,
  uploadId: string,
  sourceChecksumSha256: string,
  gameId: string,
) {
  const base = resolveAdminApiBaseUrl(apiBaseUrl);
  const encodedUpload = encodeURIComponent(uploadId);
  const encodedChecksum = encodeURIComponent(sourceChecksumSha256);
  const encodedGame = encodeURIComponent(gameId);
  return `${base}/api/v1/admin/image-imports/browser-selections/${encodedUpload}/page-geometry-sources/${encodedChecksum}/asset?game_id=${encodedGame}`;
}

function pointText(point: Point) {
  return `${Math.round(point.x)},${Math.round(point.y)}`;
}

export function PageGeometryCorrectionPanel({
  api,
  apiBaseUrl,
  gameId,
  onSubmitSaved,
  preflightJobId,
  uploadId,
}: PageGeometryCorrectionPanelProps) {
  const [sources, setSources] = useState<
    readonly BrowserPageGeometryReviewSourceResponse[]
  >([]);
  const [sourceIndex, setSourceIndex] = useState(0);
  const [imageSize, setImageSize] = useState<{
    height: number;
    width: number;
  } | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [viewportSize, setViewportSize] = useState<{
    height: number;
    width: number;
  } | null>(null);
  const [zoom, setZoom] = useState(MIN_GEOMETRY_ZOOM);
  const [pageCorners, setPageCorners] = useState<PageCorners | null>(null);
  const [initialPageCorners, setInitialPageCorners] =
    useState<PageCorners | null>(null);
  const [initialBoardOverrides, setInitialBoardOverrides] = useState<
    ReadonlyMap<number, Quad>
  >(new Map());
  const [cornerPlacement, setCornerPlacement] = useState<
    readonly Point[] | null
  >(null);
  const [meshOverrides, setMeshOverrides] = useState<
    ReadonlyMap<number, Point>
  >(new Map());
  const [boardOverrides, setBoardOverrides] = useState<
    ReadonlyMap<number, Quad>
  >(new Map());
  const [correctionMode, setCorrectionMode] = useState<CorrectionMode>('page');
  const [dragging, setDragging] = useState<
    | {
        readonly kind: 'board';
        readonly pointIndex: number;
        readonly boardIndex: number;
      }
    | { readonly kind: 'mesh'; readonly pointIndex: number }
    | { readonly kind: 'page'; readonly pointIndex: number }
    | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [savedCount, setSavedCount] = useState(0);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await api.listBrowserPageGeometryReviewSources(
        uploadId,
        preflightJobId,
        gameId,
      );
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się pobrać stron wymagających korekty geometrii.',
          ),
        );
        return;
      }
      setSavedCount(
        result.data.sources.filter((item) => item.savedSincePreflight).length,
      );
      setSources(
        result.data.sources.filter((item) => !item.savedSincePreflight),
      );
      setSourceIndex(0);
    } catch {
      setError('Nie udało się połączyć z lokalnym API korekty geometrii.');
    } finally {
      setLoading(false);
    }
  }, [api, gameId, preflightJobId, uploadId]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void refresh();
    });
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  const source = sources[sourceIndex] ?? null;

  useEffect(() => {
    const viewport = viewportRef.current;
    if (viewport === null) return;
    const updateSize = () =>
      setViewportSize({
        height: viewport.clientHeight,
        width: viewport.clientWidth,
      });
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [source?.sourceChecksumSha256]);

  const mesh = useMemo(() => {
    if (pageCorners === null) return [];
    return applyPageGeometryMeshOverrides(
      createPageGeometryMesh(pageCorners),
      meshOverrides,
    );
  }, [meshOverrides, pageCorners]);
  const quads = useMemo(() => {
    const generated = pageGeometryQuadsFromMesh(mesh);
    return generated.map((quad, index) => boardOverrides.get(index) ?? quad);
  }, [boardOverrides, mesh]);
  const zoomedCanvasSize = fitManualImageToViewport(
    imageSize,
    viewportSize,
    zoom,
  );

  const imageUrl =
    source === null
      ? null
      : sourceAssetUrl(
          apiBaseUrl,
          uploadId,
          source.sourceChecksumSha256,
          gameId,
        );

  function resetGeometry(
    width: number,
    height: number,
    existingQuads: readonly Quad[],
  ) {
    const corners =
      outerCornersFromQuads(existingQuads) ?? initialCorners(width, height);
    const overrides = new Map(
      existingQuads.map((quad, index) => [index, quad] as const),
    );
    setImageSize({ height, width });
    setInitialPageCorners(corners);
    setInitialBoardOverrides(overrides);
    setPageCorners(corners);
    setCornerPlacement(null);
    setMeshOverrides(new Map());
    setBoardOverrides(overrides);
    setCorrectionMode('page');
    setDragging(null);
  }

  function resetCurrentGeometry() {
    if (initialPageCorners === null) return;
    setPageCorners(initialPageCorners);
    setCornerPlacement(null);
    setMeshOverrides(new Map());
    setBoardOverrides(initialBoardOverrides);
    setCorrectionMode('page');
    setDragging(null);
    setFeedback('Przywrócono geometrię widoczną przy otwarciu zdjęcia.');
  }

  function beginCornerPlacement() {
    setCorrectionMode('page');
    setCornerPlacement([]);
    setDragging(null);
    setFeedback(
      'Wskaż kolejno: lewy górny, prawy górny, prawy dolny i lewy dolny punkt.',
    );
  }

  function placeNextCorner(event: PointerEvent<SVGSVGElement>) {
    if (cornerPlacement === null || imageSize === null) return;
    const point = relativePoint(event);
    if (point === null) return;
    const bounded = {
      x: clamp(point.x, 0, imageSize.width - 1),
      y: clamp(point.y, 0, imageSize.height - 1),
    };
    const next = appendPageGeometryCorner(cornerPlacement, bounded);
    const complete = completePageGeometryCorners(next);
    if (complete === null) {
      setCornerPlacement(next);
      if (next.length === 4) {
        setFeedback(
          'Punkty nie tworzą poprawnego obrysu LT → PT → PD → LD. Cofnij błędny punkt i wskaż go ponownie.',
        );
      }
      return;
    }
    setPageCorners(complete);
    setCornerPlacement(null);
    setMeshOverrides(new Map());
    setBoardOverrides(new Map());
    setFeedback(
      'Cztery narożniki ustawione. Możesz je przeciągnąć albo dopasować krzywiznę.',
    );
  }

  function undoCornerPlacement() {
    setCornerPlacement((current) =>
      current === null ? current : current.slice(0, -1),
    );
  }

  function updatePoint(next: Point) {
    if (dragging === null || imageSize === null || pageCorners === null) return;
    const point = {
      x: clamp(next.x, 0, imageSize.width - 1),
      y: clamp(next.y, 0, imageSize.height - 1),
    };
    if (dragging.kind === 'page') {
      setPageCorners((current) => {
        if (current === null) return current;
        const nextCorners: PageCorners = [
          dragging.pointIndex === 0 ? point : current[0],
          dragging.pointIndex === 1 ? point : current[1],
          dragging.pointIndex === 2 ? point : current[2],
          dragging.pointIndex === 3 ? point : current[3],
        ];
        return nextCorners;
      });
      setMeshOverrides(new Map());
      setBoardOverrides(new Map());
      return;
    }
    if (dragging.kind === 'mesh') {
      setMeshOverrides((current) => {
        const nextOverrides = new Map(current);
        nextOverrides.set(dragging.pointIndex, point);
        return nextOverrides;
      });
      setBoardOverrides(new Map());
      return;
    }
    setBoardOverrides((current) => {
      const currentQuad =
        current.get(dragging.boardIndex) ?? quads[dragging.boardIndex];
      if (currentQuad === undefined) return current;
      const nextOverrides = new Map(current);
      const nextQuad: Quad = [
        dragging.pointIndex === 0 ? point : currentQuad[0],
        dragging.pointIndex === 1 ? point : currentQuad[1],
        dragging.pointIndex === 2 ? point : currentQuad[2],
        dragging.pointIndex === 3 ? point : currentQuad[3],
      ];
      nextOverrides.set(dragging.boardIndex, nextQuad);
      return nextOverrides;
    });
  }

  function relativePoint(event: PointerEvent<SVGSVGElement>): Point | null {
    if (imageSize === null) return null;
    const rect = event.currentTarget.getBoundingClientRect();
    return pageGeometryPointFromRenderedCanvas({
      clientX: event.clientX,
      clientY: event.clientY,
      imageHeight: imageSize.height,
      imageWidth: imageSize.width,
      renderedHeight: rect.height,
      renderedLeft: rect.left,
      renderedTop: rect.top,
      renderedWidth: rect.width,
    });
  }

  function beginDrag(
    event: PointerEvent<SVGCircleElement>,
    value: NonNullable<typeof dragging>,
  ) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.ownerSVGElement?.setPointerCapture(event.pointerId);
    setDragging(value);
  }

  async function save() {
    if (source === null || imageSize === null || quads.length !== 9 || saving)
      return;
    setSaving(true);
    setError('');
    setFeedback('Zapisuję korektę całej strony…');
    try {
      const finalQuads = quads.map((quad) =>
        quad.map((point) => ({
          x: Math.round(point.x),
          y: Math.round(point.y),
        })),
      ) as BrowserPageGeometryOverrideCreate['finalQuads'];
      const result = await api.createBrowserPageGeometryOverride(uploadId, {
        actor: 'local-owner',
        finalQuads,
        gameId,
        imageHeight: imageSize.height,
        imageWidth: imageSize.width,
        sourceChecksumSha256: source.sourceChecksumSha256,
      });
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się zapisać korekty geometrii.',
          ),
        );
        return;
      }
      setFeedback(
        'Korekta została zapisana lokalnie w partii. Preflight nie został jeszcze uruchomiony.',
      );
      setSavedCount((current) => current + 1);
      setSources((current) =>
        current.filter(
          (item) => item.sourceChecksumSha256 !== source.sourceChecksumSha256,
        ),
      );
      setSourceIndex((current) =>
        Math.min(current, Math.max(0, sources.length - 2)),
      );
    } catch {
      setError('Nie udało się zapisać korekty geometrii strony.');
    } finally {
      setSaving(false);
    }
  }

  async function submitSaved() {
    if (submitting || saving || savedCount === 0) return;
    setSubmitting(true);
    setError('');
    setFeedback('Tworzę jeden preflight dla całej zapisanej partii…');
    try {
      await onSubmitSaved();
    } catch {
      setError('Nie udało się wysłać zapisanych geometrii do weryfikacji.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section
      className="pageGeometryCorrection"
      aria-label="Korekta geometrii strony"
    >
      <div className="pageGeometryCorrectionHeader">
        <div>
          <h3>Korekta geometrii strony</h3>
          <p>
            Żadna z tych stron nie zostanie pocięta ani przekazana do symboli,
            dopóki kompletna siatka 3×3 nie zostanie potwierdzona.
          </p>
        </div>
        <div className="pageGeometryCorrectionHeaderActions">
          <button
            className="secondaryButton"
            disabled={loading || saving || submitting}
            onClick={() => void refresh()}
            type="button"
          >
            Odśwież listę
          </button>
          <button
            className="primaryButton"
            disabled={savedCount === 0 || saving || submitting}
            onClick={() => void submitSaved()}
            type="button"
          >
            {submitting
              ? 'Wysyłanie partii…'
              : `Wyślij zapisane do weryfikacji (${savedCount})`}
          </button>
        </div>
      </div>
      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {feedback ? (
        <p className="feedbackBanner" role="status">
          {feedback}
        </p>
      ) : null}
      {loading ? (
        <p className="curatedImportStatus">Ładowanie stron do korekty…</p>
      ) : null}
      {!loading && sources.length === 0 ? (
        <p className="curatedImportStatus">
          Nie ma już stron oczekujących na korektę geometrii.
        </p>
      ) : null}
      {source !== null ? (
        <div className="pageGeometryCorrectionGrid">
          <div className="pageGeometryControls">
            <p className="curatedImportStatus">
              Strona {sourceIndex + 1}/{sources.length} ·{' '}
              {source.sourceRelativePath}
              {source.sequenceRangeStart !== null &&
              source.sequenceRangeEnd !== null
                ? ` · plansze ${source.sequenceRangeStart}–${source.sequenceRangeEnd}`
                : ''}
              {source.reviewReason === 'manual_override'
                ? ` · zapisana korekta r${source.existingOverrideRevision ?? '?'}`
                : ' · wymaga korekty'}
            </p>
            <label>
              Zakres korekty
              <select
                disabled={saving}
                onChange={(event) => {
                  const value = event.target.value;
                  if (value === 'curve') {
                    setBoardOverrides(new Map());
                  }
                  setCorrectionMode(
                    value === 'page' || value === 'curve'
                      ? value
                      : Number(value),
                  );
                }}
                value={String(correctionMode)}
              >
                <option value="page">Cała strona — 4 główne uchwyty</option>
                <option value="curve">
                  Krzywizna i odstępy — 36 punktów krawędzi
                </option>
                {Array.from({ length: 9 }, (_, index) => (
                  <option key={index} value={index}>
                    Plansza {index + 1} — korekta wyjątkowa
                  </option>
                ))}
              </select>
            </label>
            <p className="geometryInstructions">
              {cornerPlacement !== null
                ? `Kliknij punkt ${cornerPlacement.length + 1} z 4: ${['lewy górny', 'prawy górny', 'prawy dolny', 'lewy dolny'][cornerPlacement.length]}.`
                : correctionMode === 'page'
                  ? 'Najpierw ustaw cztery żółte uchwyty na zewnętrznych narożnikach. Ta operacja zeruje korektę krzywizny.'
                  : correctionMode === 'curve'
                    ? 'Przesuń punkty krawędzi każdej czerwonej ramki. Osobne linie zachowują odstępy między planszami i pozwalają odwzorować łuk góry, środka i dołu.'
                    : 'W razie wyjątku doprecyzuj tylko tę jedną planszę. Pozostałe zachowają elastyczną geometrię całej strony.'}
            </p>
            <div className="pageGeometryNavigation">
              <button
                className="secondaryButton"
                disabled={saving || sourceIndex === 0}
                onClick={() =>
                  setSourceIndex((current) => Math.max(0, current - 1))
                }
                type="button"
              >
                Poprzednia
              </button>
              <button
                className="secondaryButton"
                disabled={saving || sourceIndex >= sources.length - 1}
                onClick={() =>
                  setSourceIndex((current) =>
                    Math.min(sources.length - 1, current + 1),
                  )
                }
                type="button"
              >
                Następna
              </button>
              <button
                className="primaryButton"
                disabled={
                  saving ||
                  submitting ||
                  imageSize === null ||
                  cornerPlacement !== null
                }
                onClick={() => void save()}
                type="button"
              >
                {saving ? 'Zapisywanie…' : 'Zapisz i przejdź dalej'}
              </button>
              <button
                className="secondaryButton"
                disabled={saving || submitting || imageSize === null}
                onClick={beginCornerPlacement}
                type="button"
              >
                Wyznacz 4 narożniki
              </button>
              {cornerPlacement !== null && cornerPlacement.length > 0 ? (
                <button
                  className="secondaryButton"
                  disabled={saving || submitting}
                  onClick={undoCornerPlacement}
                  type="button"
                >
                  Cofnij punkt
                </button>
              ) : null}
              <button
                className="secondaryButton"
                disabled={saving || submitting || initialPageCorners === null}
                onClick={resetCurrentGeometry}
                type="button"
              >
                Reset
              </button>
            </div>
            <div
              className="pageGeometryZoom"
              aria-label="Powiększenie zdjęcia geometrii"
            >
              <button
                aria-label="Pomniejsz zdjęcie geometrii"
                className="secondaryButton"
                disabled={saving || submitting || zoom <= MIN_GEOMETRY_ZOOM}
                onClick={() =>
                  setZoom((current) =>
                    Math.max(MIN_GEOMETRY_ZOOM, current - GEOMETRY_ZOOM_STEP),
                  )
                }
                type="button"
              >
                −
              </button>
              <button
                className="secondaryButton pageGeometryZoomValue"
                disabled={saving || submitting || zoom === MIN_GEOMETRY_ZOOM}
                onClick={() => setZoom(MIN_GEOMETRY_ZOOM)}
                title="Przywróć dopasowanie do okna"
                type="button"
              >
                {Math.round(zoom * 100)}%
              </button>
              <button
                aria-label="Powiększ zdjęcie geometrii"
                className="secondaryButton"
                disabled={saving || submitting || zoom >= MAX_GEOMETRY_ZOOM}
                onClick={() =>
                  setZoom((current) =>
                    Math.min(MAX_GEOMETRY_ZOOM, current + GEOMETRY_ZOOM_STEP),
                  )
                }
                type="button"
              >
                +
              </button>
              <span>Przewijaj powiększony obraz w obu osiach.</span>
            </div>
          </div>
          <div className="pageGeometryViewport" ref={viewportRef}>
            <div
              className="pageGeometryCanvas"
              key={source.sourceChecksumSha256}
              style={
                zoomedCanvasSize === null
                  ? undefined
                  : {
                      height: `${zoomedCanvasSize.height}px`,
                      width: `${zoomedCanvasSize.width}px`,
                    }
              }
            >
              {imageUrl !== null ? (
                <img
                  alt={`Źródło do korekty: ${source.sourceRelativePath}`}
                  onLoad={(event) =>
                    resetGeometry(
                      event.currentTarget.naturalWidth,
                      event.currentTarget.naturalHeight,
                      existingSourceQuads(source),
                    )
                  }
                  src={imageUrl}
                />
              ) : null}
              {imageSize !== null && pageCorners !== null ? (
                <svg
                  aria-label="Nakładka geometrii strony"
                  onPointerDown={placeNextCorner}
                  onPointerMove={(event) => {
                    const point = relativePoint(event);
                    if (point !== null) updatePoint(point);
                  }}
                  onPointerUp={() => setDragging(null)}
                  viewBox={`0 0 ${imageSize.width} ${imageSize.height}`}
                >
                  {quads.map((quad, index) => (
                    <polygon
                      className={
                        correctionMode === index
                          ? 'pageGeometryBoard pageGeometryBoardSelected'
                          : 'pageGeometryBoard'
                      }
                      key={index}
                      points={quad.map(pointText).join(' ')}
                    />
                  ))}
                  {cornerPlacement !== null ? (
                    <>
                      {cornerPlacement.length > 1 ? (
                        <polyline
                          className="pageGeometryPlacementLine"
                          points={cornerPlacement.map(pointText).join(' ')}
                        />
                      ) : null}
                      {cornerPlacement.map((point, index) => (
                        <g key={index}>
                          <circle
                            className="pageGeometryHandle pageGeometryPlacementHandle"
                            cx={point.x}
                            cy={point.y}
                            r={HANDLE_RADIUS}
                          />
                          <text
                            className="pageGeometryPlacementLabel"
                            x={point.x + HANDLE_RADIUS + 4}
                            y={point.y - HANDLE_RADIUS - 4}
                          >
                            {['LT', 'PT', 'PD', 'LD'][index]}
                          </text>
                        </g>
                      ))}
                    </>
                  ) : null}
                  {correctionMode === 'page'
                    ? pageCorners.map((point, index) => (
                        <circle
                          className="pageGeometryHandle"
                          cx={point.x}
                          cy={point.y}
                          key={index}
                          onPointerDown={(event) =>
                            beginDrag(event, {
                              kind: 'page',
                              pointIndex: index,
                            })
                          }
                          r={HANDLE_RADIUS}
                        />
                      ))
                    : correctionMode === 'curve'
                      ? mesh.map((point, index) => (
                          <circle
                            className={
                              isPageGeometryMeshBoundaryPoint(index)
                                ? 'pageGeometryHandle pageGeometryMeshBoundaryHandle'
                                : 'pageGeometryHandle pageGeometryMeshInnerHandle'
                            }
                            cx={point.x}
                            cy={point.y}
                            key={index}
                            onPointerDown={(event) =>
                              beginDrag(event, {
                                kind: 'mesh',
                                pointIndex: index,
                              })
                            }
                            r={HANDLE_RADIUS}
                          />
                        ))
                      : (quads[correctionMode] ?? []).map((point, index) => (
                          <circle
                            className="pageGeometryHandle pageGeometryBoardHandle"
                            cx={point.x}
                            cy={point.y}
                            key={index}
                            onPointerDown={(event) =>
                              beginDrag(event, {
                                boardIndex: correctionMode,
                                kind: 'board',
                                pointIndex: index,
                              })
                            }
                            r={HANDLE_RADIUS}
                          />
                        ))}
                </svg>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

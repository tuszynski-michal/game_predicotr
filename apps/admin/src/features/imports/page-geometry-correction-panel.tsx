'use client';

import type {
  AdminApiClient,
  BrowserPageGeometryOverrideCreate,
  BrowserPageGeometryReviewSourceResponse,
} from '@game-predictor/admin-api-client';
import {
  type PointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { resolveAdminApiBaseUrl } from '@/config/admin-api';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';

type GeometryCorrectionClient = Pick<
  AdminApiClient,
  | 'createBrowserPageGeometryOverride'
  | 'listBrowserPageGeometryReviewSources'
>;

type Point = { readonly x: number; readonly y: number };
type Quad = readonly [Point, Point, Point, Point];
type PageCorners = readonly [Point, Point, Point, Point];

interface PageGeometryCorrectionPanelProps {
  readonly api: GeometryCorrectionClient;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly onSaved: () => Promise<void>;
  readonly preflightJobId: string;
  readonly uploadId: string;
}

const HANDLE_RADIUS = 14;

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, Math.round(value)));
}

function lerp(left: Point, right: Point, ratio: number): Point {
  return {
    x: left.x + (right.x - left.x) * ratio,
    y: left.y + (right.y - left.y) * ratio,
  };
}

function bilinear(corners: PageCorners, u: number, v: number): Point {
  const upper = lerp(corners[0], corners[1], u);
  const lower = lerp(corners[3], corners[2], u);
  return lerp(upper, lower, v);
}

function gridFromPage(corners: PageCorners): readonly Quad[] {
  return Array.from({ length: 9 }, (_, index) => {
    const row = Math.floor(index / 3);
    const column = index % 3;
    const left = column / 3;
    const right = (column + 1) / 3;
    const top = row / 3;
    const bottom = (row + 1) / 3;
    return [
      bilinear(corners, left, top),
      bilinear(corners, right, top),
      bilinear(corners, right, bottom),
      bilinear(corners, left, bottom),
    ] as const;
  });
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
  onSaved,
  preflightJobId,
  uploadId,
}: PageGeometryCorrectionPanelProps) {
  const [sources, setSources] = useState<
    readonly BrowserPageGeometryReviewSourceResponse[]
  >([]);
  const [sourceIndex, setSourceIndex] = useState(0);
  const [imageSize, setImageSize] = useState<{ height: number; width: number } | null>(null);
  const [pageCorners, setPageCorners] = useState<PageCorners | null>(null);
  const [boardOverrides, setBoardOverrides] = useState<ReadonlyMap<number, Quad>>(new Map());
  const [selectedBoard, setSelectedBoard] = useState<number | null>(null);
  const [dragging, setDragging] = useState<
    | { readonly kind: 'board'; readonly pointIndex: number; readonly boardIndex: number }
    | { readonly kind: 'page'; readonly pointIndex: number }
    | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
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
      setSources(result.data.sources);
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
  const quads = useMemo(() => {
    if (pageCorners === null) return [];
    const generated = gridFromPage(pageCorners);
    return generated.map((quad, index) => boardOverrides.get(index) ?? quad);
  }, [boardOverrides, pageCorners]);

  const imageUrl =
    source === null
      ? null
      : sourceAssetUrl(apiBaseUrl, uploadId, source.sourceChecksumSha256, gameId);

  function resetGeometry(width: number, height: number) {
    setImageSize({ height, width });
    setPageCorners(initialCorners(width, height));
    setBoardOverrides(new Map());
    setSelectedBoard(null);
    setDragging(null);
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
      setBoardOverrides(new Map());
      return;
    }
    setBoardOverrides((current) => {
      const currentQuad = current.get(dragging.boardIndex) ?? quads[dragging.boardIndex];
      if (currentQuad === undefined) return current;
      const nextOverrides = new Map(current);
      const nextQuad: Quad = [
        dragging.pointIndex === 0 ? point : currentQuad[0],
        dragging.pointIndex === 1 ? point : currentQuad[1],
        dragging.pointIndex === 2 ? point : currentQuad[2],
        dragging.pointIndex === 3 ? point : currentQuad[3],
      ];
      nextOverrides.set(
        dragging.boardIndex,
        nextQuad,
      );
      return nextOverrides;
    });
  }

  function relativePoint(event: PointerEvent<SVGSVGElement>): Point | null {
    if (imageSize === null) return null;
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;
    return {
      x: ((event.clientX - rect.left) * imageSize.width) / rect.width,
      y: ((event.clientY - rect.top) * imageSize.height) / rect.height,
    };
  }

  function beginDrag(
    event: PointerEvent<SVGCircleElement>,
    value: NonNullable<typeof dragging>,
  ) {
    event.preventDefault();
    event.currentTarget.ownerSVGElement?.setPointerCapture(event.pointerId);
    setDragging(value);
  }

  async function save() {
    if (source === null || imageSize === null || quads.length !== 9 || saving) return;
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
          apiErrorMessage(result.error, 'Nie udało się zapisać korekty geometrii.'),
        );
        return;
      }
      setFeedback(
        'Korekta została zapisana. Tworzę nowy preflight tylko dla nierozwiązanych stron.',
      );
      await onSaved();
    } catch {
      setError('Nie udało się zapisać korekty geometrii strony.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="pageGeometryCorrection" aria-label="Korekta geometrii strony">
      <div className="pageGeometryCorrectionHeader">
        <div>
          <h3>Korekta geometrii strony</h3>
          <p>
            Żadna z tych stron nie zostanie pocięta ani przekazana do symboli, dopóki
            kompletna siatka 3×3 nie zostanie potwierdzona.
          </p>
        </div>
        <button className="secondaryButton" disabled={loading || saving} onClick={() => void refresh()} type="button">
          Odśwież listę
        </button>
      </div>
      {error ? <p className="feedbackBanner feedbackBannerError" role="alert">{error}</p> : null}
      {feedback ? <p className="feedbackBanner" role="status">{feedback}</p> : null}
      {loading ? <p className="curatedImportStatus">Ładowanie stron do korekty…</p> : null}
      {!loading && sources.length === 0 ? (
        <p className="curatedImportStatus">Nie ma już stron oczekujących na korektę geometrii.</p>
      ) : null}
      {source !== null ? (
        <div className="pageGeometryCorrectionGrid">
          <div className="pageGeometryControls">
            <p className="curatedImportStatus">
              Strona {sourceIndex + 1}/{sources.length} · {source.sourceRelativePath}
              {source.sequenceRangeStart !== null && source.sequenceRangeEnd !== null
                ? ` · layouty ${source.sequenceRangeStart}–${source.sequenceRangeEnd}`
                : ''}
            </p>
            <label>
              Zakres korekty
              <select
                disabled={saving}
                onChange={(event) =>
                  setSelectedBoard(
                    event.target.value === 'page' ? null : Number(event.target.value),
                  )
                }
                value={selectedBoard === null ? 'page' : String(selectedBoard)}
              >
                <option value="page">Cała strona — 4 główne uchwyty</option>
                {Array.from({ length: 9 }, (_, index) => (
                  <option key={index} value={index}>
                    Plansza {index + 1} — korekta wyjątkowa
                  </option>
                ))}
              </select>
            </label>
            <p className="geometryInstructions">
              {selectedBoard === null
                ? 'Przeciągnij cztery żółte uchwyty na zewnętrzne narożniki siatki. Zmiana zachowuje układ wszystkich dziewięciu plansz.'
                : 'W razie wyjątku doprecyzuj tylko tę jedną planszę. Pozostałe zachowają geometrię całej strony.'}
            </p>
            <div className="pageGeometryNavigation">
              <button
                className="secondaryButton"
                disabled={saving || sourceIndex === 0}
                onClick={() => setSourceIndex((current) => Math.max(0, current - 1))}
                type="button"
              >
                Poprzednia
              </button>
              <button
                className="secondaryButton"
                disabled={saving || sourceIndex >= sources.length - 1}
                onClick={() => setSourceIndex((current) => Math.min(sources.length - 1, current + 1))}
                type="button"
              >
                Następna
              </button>
              <button className="primaryButton" disabled={saving || imageSize === null} onClick={() => void save()} type="button">
                {saving ? 'Zapisywanie…' : 'Zapisz geometrię strony'}
              </button>
            </div>
          </div>
          <div className="pageGeometryCanvas" key={source.sourceChecksumSha256}>
            {imageUrl !== null ? (
              <img
                alt={`Źródło do korekty: ${source.sourceRelativePath}`}
                onLoad={(event) => resetGeometry(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight)}
                src={imageUrl}
              />
            ) : null}
            {imageSize !== null && pageCorners !== null ? (
              <svg
                aria-label="Nakładka geometrii strony"
                onPointerMove={(event) => {
                  const point = relativePoint(event);
                  if (point !== null) updatePoint(point);
                }}
                onPointerUp={() => setDragging(null)}
                viewBox={`0 0 ${imageSize.width} ${imageSize.height}`}
              >
                {quads.map((quad, index) => (
                  <polygon
                    className={selectedBoard === index ? 'pageGeometryBoard pageGeometryBoardSelected' : 'pageGeometryBoard'}
                    key={index}
                    points={quad.map(pointText).join(' ')}
                  />
                ))}
                {selectedBoard === null
                  ? pageCorners.map((point, index) => (
                      <circle
                        className="pageGeometryHandle"
                        cx={point.x}
                        cy={point.y}
                        key={index}
                        onPointerDown={(event) => beginDrag(event, { kind: 'page', pointIndex: index })}
                        r={HANDLE_RADIUS}
                      />
                    ))
                  : (quads[selectedBoard] ?? []).map((point, index) => (
                      <circle
                        className="pageGeometryHandle pageGeometryBoardHandle"
                        cx={point.x}
                        cy={point.y}
                        key={index}
                        onPointerDown={(event) =>
                          beginDrag(event, {
                            boardIndex: selectedBoard,
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
      ) : null}
    </section>
  );
}

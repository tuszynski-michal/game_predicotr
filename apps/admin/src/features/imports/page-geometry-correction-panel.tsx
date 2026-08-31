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
  appendPageGeometryBoardCorner,
  appendPageGeometryCorner,
  applyPageGeometryMeshOverrides,
  completePageGeometryBoardQuads,
  completePageGeometryCorners,
  createPageGeometryMesh,
  isPageGeometryMeshBoundaryPoint,
  PAGE_BOARD_CORNER_COUNT,
  PAGE_BOARD_COUNT,
  pageGeometryPointFromRenderedCanvas,
  pageGeometryMeshFromQuads,
  pageGeometryQuadsFromCornerPlacement,
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
const CORNER_LABELS = ['LT', 'PT', 'PD', 'LD'] as const;
const CORNER_NAMES = [
  'lewy górny',
  'prawy górny',
  'prawy dolny',
  'lewy dolny',
] as const;

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
  const [boardCornerPlacement, setBoardCornerPlacement] = useState<
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
  const deferredSourceCount = sources.filter(
    (item) => item.reviewReason === 'review_required',
  ).length;
  const registeredUpdateSourceCount = sources.length - deferredSourceCount;

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
  const placedBoardQuads = useMemo(
    () =>
      boardCornerPlacement === null
        ? []
        : pageGeometryQuadsFromCornerPlacement(boardCornerPlacement),
    [boardCornerPlacement],
  );
  const activeBoardPlacementIndex = Math.min(
    placedBoardQuads.length,
    PAGE_BOARD_COUNT - 1,
  );
  const activeBoardPlacementPoints =
    boardCornerPlacement === null
      ? []
      : boardCornerPlacement.slice(
          activeBoardPlacementIndex * PAGE_BOARD_CORNER_COUNT,
        );
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
    setBoardCornerPlacement(null);
    setMeshOverrides(new Map());
    setBoardOverrides(overrides);
    setCorrectionMode('page');
    setDragging(null);
  }

  function resetCurrentGeometry() {
    if (initialPageCorners === null) return;
    setPageCorners(initialPageCorners);
    setCornerPlacement(null);
    setBoardCornerPlacement(null);
    setMeshOverrides(new Map());
    setBoardOverrides(initialBoardOverrides);
    setCorrectionMode('page');
    setDragging(null);
    setFeedback('Przywrócono geometrię widoczną przy otwarciu zdjęcia.');
  }

  function beginCornerPlacement() {
    setCorrectionMode('page');
    setCornerPlacement([]);
    setBoardCornerPlacement(null);
    setDragging(null);
    setFeedback(
      'Wskaż kolejno: lewy górny, prawy górny, prawy dolny i lewy dolny punkt.',
    );
  }

  function beginBoardCornerPlacement() {
    setCorrectionMode(0);
    setCornerPlacement(null);
    setBoardCornerPlacement([]);
    setDragging(null);
    setFeedback(
      'Plansza 1 z 9 (rząd 1, kolumna 1). Wskaż kolejno: lewy górny, prawy górny, prawy dolny i lewy dolny punkt.',
    );
  }

  function showAllBoardCorners(currentQuads: readonly Quad[]) {
    const independentMesh = pageGeometryMeshFromQuads(currentQuads);
    if (independentMesh === null) return false;
    setMeshOverrides(
      new Map(independentMesh.map((point, index) => [index, point] as const)),
    );
    setBoardOverrides(new Map());
    setCorrectionMode('curve');
    return true;
  }

  function placeNextCorner(event: PointerEvent<SVGSVGElement>) {
    if (
      (cornerPlacement === null && boardCornerPlacement === null) ||
      imageSize === null
    ) {
      return;
    }
    const point = relativePoint(event);
    if (point === null) return;
    const bounded = {
      x: clamp(point.x, 0, imageSize.width - 1),
      y: clamp(point.y, 0, imageSize.height - 1),
    };
    if (boardCornerPlacement !== null) {
      const next = appendPageGeometryBoardCorner(boardCornerPlacement, bounded);
      const nextQuads = pageGeometryQuadsFromCornerPlacement(next);
      const expectedCompletedPoints =
        nextQuads.length * PAGE_BOARD_CORNER_COUNT;
      setBoardCornerPlacement(next);
      if (
        next.length % PAGE_BOARD_CORNER_COUNT === 0 &&
        next.length !== expectedCompletedPoints
      ) {
        setFeedback(
          `Plansza ${nextQuads.length + 1} nie tworzy poprawnego obrysu albo nie leży po właściwej stronie poprzedniej planszy. Cofnij błędny punkt i wskaż go ponownie.`,
        );
        return;
      }
      const completeQuads = completePageGeometryBoardQuads(next);
      if (completeQuads !== null) {
        const outerCorners = outerCornersFromQuads(completeQuads);
        if (outerCorners === null) return;
        setPageCorners(outerCorners);
        showAllBoardCorners(completeQuads);
        setBoardCornerPlacement(null);
        setFeedback(
          'Ustawiono osobno wszystkie 9 plansz w kolejności 1–3, 4–6, 7–9. Włączono wszystkie 36 narożników, które możesz teraz doprecyzować przed zapisem.',
        );
        return;
      }
      const boardIndex = nextQuads.length;
      const cornerIndex = next.length - expectedCompletedPoints;
      setFeedback(
        cornerIndex === 0
          ? `Plansza ${boardIndex + 1} z 9 (rząd ${Math.floor(boardIndex / 3) + 1}, kolumna ${(boardIndex % 3) + 1}). Wskaż lewy górny punkt.`
          : `Plansza ${boardIndex + 1} z 9: wskaż ${CORNER_NAMES[cornerIndex]}.`,
      );
      return;
    }
    if (cornerPlacement === null) return;
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
    if (boardCornerPlacement !== null) {
      setBoardCornerPlacement((current) =>
        current === null ? current : current.slice(0, -1),
      );
      return;
    }
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
        source.reviewReason === 'manual_override'
          ? 'Zapisano aktualizację już zarejestrowanej geometrii. Licznik poprawnych zdjęć nie wzrośnie, ponieważ to źródło było w nim wcześniej.'
          : 'Zapisano geometrię odroczonego zdjęcia. Po wysłaniu partii i ukończeniu preflightu przejdzie ono do zarejestrowanych.',
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
            Liczniki dotyczą zdjęć źródłowych, nie pojedynczych plansz. Jedno
            zdjęcie zawiera dziewięć plansz; zostaną one utworzone dopiero w
            imporcie po zakończeniu preflightu geometrii.
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
              Pozostałe zdjęcia: odroczone {deferredSourceCount} · aktualizacje
              wcześniej zarejestrowanej geometrii {registeredUpdateSourceCount}
            </p>
            <p className="curatedImportStatus">
              Strona {sourceIndex + 1}/{sources.length} ·{' '}
              {source.sourceRelativePath}
              {source.sequenceRangeStart !== null &&
              source.sequenceRangeEnd !== null
                ? ` · plansze ${source.sequenceRangeStart}–${source.sequenceRangeEnd}`
                : ''}
              {source.reviewReason === 'manual_override'
                ? ` · aktualizacja już zarejestrowanej geometrii r${source.existingOverrideRevision ?? '?'}`
                : ' · odroczone zdjęcie — wymaga geometrii'}
            </p>
            <p className="geometryInstructions">
              {source.reviewReason === 'manual_override'
                ? 'To zdjęcie jest już uwzględnione w liczniku zarejestrowanych. Zapis zmieni jego obrys, ale nie zwiększy tego licznika.'
                : 'Po zapisaniu i wykonaniu preflightu to zdjęcie przejdzie z odroczonych do zarejestrowanych.'}
            </p>
            <label>
              Zakres korekty
              <select
                disabled={
                  saving ||
                  submitting ||
                  cornerPlacement !== null ||
                  boardCornerPlacement !== null
                }
                onChange={(event) => {
                  const value = event.target.value;
                  if (value === 'curve') {
                    showAllBoardCorners(quads);
                    return;
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
                <option value="curve">Wszystkie plansze — 36 narożników</option>
                {Array.from({ length: 9 }, (_, index) => (
                  <option key={index} value={index}>
                    Plansza {index + 1} — korekta wyjątkowa
                  </option>
                ))}
              </select>
            </label>
            <p className="geometryInstructions">
              {boardCornerPlacement !== null
                ? activeBoardPlacementPoints.length >= PAGE_BOARD_CORNER_COUNT
                  ? `Plansza ${activeBoardPlacementIndex + 1} z 9 nie tworzy poprawnego obrysu albo nie zachowuje kolejności od lewej do prawej. Cofnij błędny punkt.`
                  : `Plansza ${activeBoardPlacementIndex + 1} z 9 · rząd ${Math.floor(activeBoardPlacementIndex / 3) + 1}, kolumna ${(activeBoardPlacementIndex % 3) + 1} · kliknij punkt ${activeBoardPlacementPoints.length + 1} z 4: ${CORNER_NAMES[activeBoardPlacementPoints.length]}.`
                : cornerPlacement !== null
                  ? `Kliknij punkt ${cornerPlacement.length + 1} z 4: ${CORNER_NAMES[cornerPlacement.length]}.`
                  : correctionMode === 'page'
                    ? 'Najpierw ustaw cztery żółte uchwyty na zewnętrznych narożnikach. Ta operacja zeruje korektę krzywizny.'
                    : correctionMode === 'curve'
                      ? 'Przesuń dowolny z 36 niezależnych narożników dziewięciu plansz. Każda plansza zachowuje własny obrys, odstępy i krzywiznę.'
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
                  cornerPlacement !== null ||
                  boardCornerPlacement !== null
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
              <button
                className="secondaryButton"
                disabled={saving || submitting || imageSize === null}
                onClick={beginBoardCornerPlacement}
                type="button"
              >
                Wyznacz 9 plansz osobno
              </button>
              {(cornerPlacement !== null && cornerPlacement.length > 0) ||
              (boardCornerPlacement !== null &&
                boardCornerPlacement.length > 0) ? (
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
                  {boardCornerPlacement !== null
                    ? placedBoardQuads.map((quad, index) => (
                        <polygon
                          className="pageGeometryBoardPlacement"
                          key={`placed-board-${index}`}
                          points={quad.map(pointText).join(' ')}
                        />
                      ))
                    : null}
                  {boardCornerPlacement !== null ? (
                    <>
                      {activeBoardPlacementPoints.length > 1 ? (
                        <polyline
                          className="pageGeometryPlacementLine"
                          points={activeBoardPlacementPoints
                            .map(pointText)
                            .join(' ')}
                        />
                      ) : null}
                      {activeBoardPlacementPoints.map((point, index) => (
                        <g key={`board-corner-${index}`}>
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
                            {CORNER_LABELS[index]}
                          </text>
                        </g>
                      ))}
                    </>
                  ) : null}
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
                            {CORNER_LABELS[index]}
                          </text>
                        </g>
                      ))}
                    </>
                  ) : null}
                  {cornerPlacement === null && boardCornerPlacement === null
                    ? correctionMode === 'page'
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
                          ))
                    : null}
                </svg>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

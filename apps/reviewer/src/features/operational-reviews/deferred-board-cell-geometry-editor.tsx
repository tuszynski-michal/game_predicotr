'use client';

import type {
  BoardCellGeometryCorrectionContextResponse,
  OperationalImageReviewGeometryPoint,
} from '@game-predictor/admin-api-client';
import {
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  type DeferredBoardCellGeometryClient,
  loadDeferredBoardCellGeometryContext,
  previewDeferredBoardCellGeometry,
  resolveDeferredBoardCellGeometry,
} from './deferred-board-cell-geometry-actions';
import {
  deferredBoardCellGeometryCommandKey,
  deferredBoardCellGeometryCorners,
  deferredBoardCellGeometryIdempotency,
  deferredBoardCellGeometryPreviewCommand,
  deferredBoardCellGeometryReasonLabel,
  deferredBoardCellGeometryResolutionCommand,
  deferredBoardCellGeometrySourceUrl,
  type DeferredBoardCellGeometryIdempotency,
} from './deferred-board-cell-geometry-state';
import {
  operationalReviewGeometryEdgeHandles,
  operationalReviewGeometryViewport,
  operationalReviewPointInCanvas,
  operationalReviewPointInGeometryViewport,
  operationalReviewPointInLattice,
  operationalReviewPointInSourceImage,
  type OperationalReviewGeometryCorners,
  type OperationalReviewGeometryViewport,
} from './operational-review-state';

type LoadState = 'error' | 'loading' | 'ready';

export function DeferredBoardCellGeometryEditor({
  api,
  apiBaseUrl,
  itemId,
  onConflict,
  onMaterialized,
  scope,
}: {
  readonly api: DeferredBoardCellGeometryClient;
  readonly apiBaseUrl: string;
  readonly itemId: string;
  readonly onConflict: (message: string) => Promise<void>;
  readonly onMaterialized: (reviewItemId: string | null) => Promise<void>;
  readonly scope: { readonly gameId: string; readonly importJobId: string };
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sourceImageRef = useRef<HTMLImageElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const dragIndexRef = useRef<number | null>(null);
  const currentCommandKeyRef = useRef('');
  const idempotencyRef = useRef<DeferredBoardCellGeometryIdempotency | null>(
    null,
  );
  const [context, setContext] =
    useState<BoardCellGeometryCorrectionContextResponse | null>(null);
  const [contextState, setContextState] = useState<LoadState>('loading');
  const [corners, setCorners] =
    useState<OperationalReviewGeometryCorners | null>(null);
  const [viewport, setViewport] =
    useState<OperationalReviewGeometryViewport | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewKey, setPreviewKey] = useState('');
  const [loadingSource, setLoadingSource] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const commandKey =
    context === null || corners === null
      ? ''
      : deferredBoardCellGeometryCommandKey(context, corners);
  const previewIsCurrent = previewUrl !== null && previewKey === commandKey;

  useEffect(() => {
    currentCommandKeyRef.current = commandKey;
  }, [commandKey]);

  const clearPreview = useCallback(() => {
    if (previewUrlRef.current !== null) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
    setPreviewUrl(null);
    setPreviewKey('');
  }, []);

  const replaceCorners = useCallback(
    (next: OperationalReviewGeometryCorners) => {
      clearPreview();
      idempotencyRef.current = null;
      setCorners(next);
    },
    [clearPreview],
  );

  useEffect(() => {
    let active = true;
    async function load() {
      setContextState('loading');
      setError('');
      clearPreview();
      idempotencyRef.current = null;
      const result = await loadDeferredBoardCellGeometryContext(
        api,
        scope,
        itemId,
      );
      if (!active) return;
      if (!result.ok) {
        if (result.isConflict) {
          await onConflict(result.error);
          return;
        }
        setContextState('error');
        setError(result.error);
        return;
      }
      setLoadingSource(true);
      setContext(result.context);
      setCorners(deferredBoardCellGeometryCorners(result.context));
      setContextState('ready');
    }
    void load();
    return () => {
      active = false;
    };
  }, [api, clearPreview, itemId, onConflict, scope]);

  const sourceUrl = useMemo(
    () =>
      context === null
        ? null
        : deferredBoardCellGeometrySourceUrl(apiBaseUrl, context.item),
    [apiBaseUrl, context],
  );

  useEffect(() => {
    if (context === null || sourceUrl === null) return;
    const image = new window.Image();
    image.crossOrigin = 'anonymous';
    image.decoding = 'async';
    image.onload = () => {
      sourceImageRef.current = image;
      const boardCorners = context.boardQuad.map(
        copyPoint,
      ) as OperationalReviewGeometryCorners;
      setViewport(
        operationalReviewGeometryViewport(
          boardCorners,
          context.sourceWidth,
          context.sourceHeight,
          0.35,
        ),
      );
      setLoadingSource(false);
    };
    image.onerror = () => {
      sourceImageRef.current = null;
      setLoadingSource(false);
      setError('Nie udało się wczytać checksum-bound obrazu źródłowego.');
    };
    image.src = sourceUrl;
    return () => {
      image.onload = null;
      image.onerror = null;
    };
  }, [context, sourceUrl]);

  useEffect(
    () => () => {
      if (previewUrlRef.current !== null) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
    },
    [],
  );

  const drawSource = useCallback(() => {
    const canvas = canvasRef.current;
    const image = sourceImageRef.current;
    if (
      canvas === null ||
      image === null ||
      corners === null ||
      viewport === null
    )
      return;
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const context2d = canvas.getContext('2d');
    if (context2d === null) return;
    context2d.clearRect(0, 0, canvas.width, canvas.height);
    context2d.drawImage(
      image,
      viewport.x,
      viewport.y,
      viewport.width,
      viewport.height,
      0,
      0,
      viewport.width,
      viewport.height,
    );
    context2d.lineWidth = Math.max(2, canvas.width / 500);
    context2d.strokeStyle = '#f4d35e';
    for (let column = 0; column <= 5; column += 1) {
      drawLine(
        context2d,
        operationalReviewPointInGeometryViewport(
          operationalReviewPointInLattice(corners, column / 5, 0),
          viewport,
        ),
        operationalReviewPointInGeometryViewport(
          operationalReviewPointInLattice(corners, column / 5, 1),
          viewport,
        ),
      );
    }
    for (let row = 0; row <= 3; row += 1) {
      drawLine(
        context2d,
        operationalReviewPointInGeometryViewport(
          operationalReviewPointInLattice(corners, 0, row / 3),
          viewport,
        ),
        operationalReviewPointInGeometryViewport(
          operationalReviewPointInLattice(corners, 1, row / 3),
          viewport,
        ),
      );
    }
    operationalReviewGeometryEdgeHandles(corners)
      .map((point) => operationalReviewPointInGeometryViewport(point, viewport))
      .forEach((point) => {
        const radius = Math.max(5, canvas.width / 180);
        context2d.beginPath();
        context2d.fillStyle = '#8ea0b8';
        context2d.strokeStyle = '#253b56';
        context2d.rect(
          point.x - radius,
          point.y - radius,
          radius * 2,
          radius * 2,
        );
        context2d.fill();
        context2d.stroke();
      });
    corners
      .map((point) => operationalReviewPointInGeometryViewport(point, viewport))
      .forEach((point, index) => {
        context2d.beginPath();
        context2d.fillStyle = '#fffaf0';
        context2d.strokeStyle = '#b42318';
        context2d.arc(
          point.x,
          point.y,
          Math.max(7, canvas.width / 140),
          0,
          Math.PI * 2,
        );
        context2d.fill();
        context2d.stroke();
        context2d.fillStyle = '#7a271a';
        context2d.font = `bold ${Math.max(12, canvas.width / 65)}px sans-serif`;
        context2d.fillText(String(index + 1), point.x + 10, point.y - 10);
      });
  }, [corners, viewport]);

  useEffect(() => {
    drawSource();
  }, [drawSource]);

  async function refreshPreview() {
    if (context === null || corners === null || loadingPreview || saving)
      return;
    const requestedKey = commandKey;
    setLoadingPreview(true);
    setError('');
    const result = await previewDeferredBoardCellGeometry(
      api,
      scope,
      itemId,
      deferredBoardCellGeometryPreviewCommand(context, corners),
    );
    setLoadingPreview(false);
    if (!result.ok) {
      setError(result.error);
      if (result.isConflict) await onConflict(result.error);
      return;
    }
    if (requestedKey !== currentCommandKeyRef.current) return;
    clearPreview();
    const url = URL.createObjectURL(result.blob);
    previewUrlRef.current = url;
    setPreviewUrl(url);
    setPreviewKey(requestedKey);
  }

  async function saveGeometry() {
    if (
      context === null ||
      corners === null ||
      !previewIsCurrent ||
      saving ||
      loadingPreview
    )
      return;
    const idempotency = deferredBoardCellGeometryIdempotency(
      idempotencyRef.current,
      commandKey,
      () => globalThis.crypto.randomUUID(),
    );
    idempotencyRef.current = idempotency;
    setSaving(true);
    setError('');
    const result = await resolveDeferredBoardCellGeometry(
      api,
      scope,
      itemId,
      deferredBoardCellGeometryResolutionCommand(
        context,
        corners,
        idempotency.idempotencyKey,
      ),
    );
    setSaving(false);
    if (!result.ok) {
      setError(result.error);
      if (result.isConflict) await onConflict(result.error);
      return;
    }
    idempotencyRef.current = null;
    clearPreview();
    await onMaterialized(result.resolution.reviewItemId);
  }

  function updateDraggedCorner(event: ReactPointerEvent<HTMLCanvasElement>) {
    const index = dragIndexRef.current;
    const canvas = canvasRef.current;
    if (
      index === null ||
      canvas === null ||
      context === null ||
      corners === null ||
      viewport === null
    )
      return;
    const rect = canvas.getBoundingClientRect();
    const pointer = operationalReviewPointInCanvas(
      { x: event.clientX, y: event.clientY },
      rect,
      canvas.width,
      canvas.height,
    );
    const point = operationalReviewPointInSourceImage(
      pointer.point,
      viewport,
      context.sourceWidth,
      context.sourceHeight,
    );
    const next = [...corners] as OperationalReviewGeometryCorners;
    next[index] = point;
    replaceCorners(next);
  }

  function startDragging(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (corners === null || viewport === null) return;
    event.preventDefault();
    const canvas = event.currentTarget;
    const rect = canvas.getBoundingClientRect();
    const pointer = operationalReviewPointInCanvas(
      { x: event.clientX, y: event.clientY },
      rect,
      canvas.width,
      canvas.height,
    );
    const threshold = 44 / pointer.scale;
    const candidate = corners
      .map((point) => operationalReviewPointInGeometryViewport(point, viewport))
      .map((point, index) => ({
        distance: Math.hypot(
          point.x - pointer.point.x,
          point.y - pointer.point.y,
        ),
        index,
      }))
      .sort((left, right) => left.distance - right.distance)[0];
    if (candidate === undefined || candidate.distance > threshold) return;
    dragIndexRef.current = candidate.index;
    canvas.setPointerCapture(event.pointerId);
    updateDraggedCorner(event);
  }

  function finishDragging(event: ReactPointerEvent<HTMLCanvasElement>) {
    updateDraggedCorner(event);
    dragIndexRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  if (contextState === 'loading') {
    return (
      <DeferredGeometryState text="Pobieram kontekst i oryginalne zdjęcie." />
    );
  }
  if (contextState === 'error' || context === null) {
    return <DeferredGeometryState error text={error} />;
  }

  return (
    <div className="deferredGeometryEditor">
      <div className="deferredGeometryMetadata">
        <div>
          <span>Numer planszy</span>
          <strong>{context.item.sequenceNumber.toLocaleString('pl-PL')}</strong>
        </div>
        <div>
          <span>Pozycja na stronie</span>
          <strong>{context.item.positionIndex + 1} / 9</strong>
        </div>
        <div>
          <span>Powód odroczenia</span>
          <strong>
            {deferredBoardCellGeometryReasonLabel(context.item.reasonCode)}
          </strong>
        </div>
        <div>
          <span>Plik</span>
          <strong title={context.item.sourceRelativePath}>
            {context.item.sourceRelativePath}
          </strong>
        </div>
      </div>

      <div className="operationalReviewGeometryBody deferredGeometryBody">
        <section>
          <div className="deferredGeometrySectionHeader">
            <div>
              <h3>Oryginał i edytowalna siatka</h3>
              <p>
                Przeciągnij tylko cztery numerowane narożniki. Szare punkty są
                wyliczane automatycznie.
              </p>
            </div>
            <button
              className="textButton"
              disabled={saving}
              onClick={() =>
                replaceCorners(deferredBoardCellGeometryCorners(context))
              }
              type="button"
            >
              Przywróć sugestię
            </button>
          </div>
          {loadingSource ? <p>Wczytywanie obrazu…</p> : null}
          <canvas
            aria-label="Odroczona plansza z edytowalną siatką 5 na 3"
            className="operationalReviewGeometryCanvas deferredGeometryCanvas"
            onLostPointerCapture={() => {
              dragIndexRef.current = null;
            }}
            onPointerCancel={() => {
              dragIndexRef.current = null;
            }}
            onPointerDown={startDragging}
            onPointerMove={updateDraggedCorner}
            onPointerUp={finishDragging}
            ref={canvasRef}
            style={{
              aspectRatio:
                viewport === null
                  ? undefined
                  : `${viewport.width} / ${viewport.height}`,
            }}
          />
        </section>

        <section className="operationalReviewGeometryPreview">
          <div>
            <div>
              <h3>15 finalnych cropów source-direct</h3>
              <p>Podgląd niczego nie zapisuje.</p>
            </div>
            <button
              className="secondaryButton"
              disabled={
                corners === null || loadingPreview || saving || loadingSource
              }
              onClick={() => void refreshPreview()}
              type="button"
            >
              {loadingPreview ? 'Generowanie…' : 'Aktualizuj podgląd'}
            </button>
          </div>
          {previewUrl === null ? (
            <p className="operationalReviewGeometryPlaceholder">
              Ustaw narożniki i wygeneruj aktualny podgląd przed zapisem.
            </p>
          ) : (
            <>
              {/* Checksum-bound Blob URL zwrócony przez lokalny backend. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img alt="Kontaktowy podgląd 15 cropów" src={previewUrl} />
              <div
                aria-label="Podgląd 15 cropów odroczonej planszy"
                className="operationalReviewGeometryCrops"
              >
                {Array.from({ length: 15 }, (_, index) => {
                  const row = Math.floor(index / 5);
                  const column = index % 5;
                  return (
                    <div
                      aria-label={`Crop ${index + 1}`}
                      key={index}
                      role="img"
                      style={{
                        backgroundImage: `url("${previewUrl}")`,
                        backgroundPosition: `${column * 25}% ${row * 50}%`,
                        backgroundSize: '500% 300%',
                      }}
                    />
                  );
                })}
              </div>
            </>
          )}
        </section>
      </div>

      {error ? (
        <p className="operationalReviewSaveError" role="alert">
          {error}
        </p>
      ) : null}

      <div className="deferredGeometrySaveBar">
        <span>
          Zapis utworzy zwykłą planszę oczekującą na zatwierdzenie symboli. Nie
          zatwierdzi jej automatycznie.
        </span>
        <button
          className="primaryButton"
          disabled={!previewIsCurrent || saving || loadingPreview}
          onClick={() => void saveGeometry()}
          type="button"
        >
          {saving ? 'Zapisywanie…' : 'Zapisz geometrię i dalej'}
        </button>
      </div>
    </div>
  );
}

function DeferredGeometryState({
  error = false,
  text,
}: {
  readonly error?: boolean;
  readonly text: string;
}) {
  return (
    <div className={error ? 'emptyState errorState' : 'emptyState'}>
      <h3>{error ? 'Nie udało się wczytać korekty' : 'Wczytywanie korekty'}</h3>
      <p>{text}</p>
    </div>
  );
}

function copyPoint(
  point: OperationalImageReviewGeometryPoint,
): OperationalImageReviewGeometryPoint {
  return { x: point.x, y: point.y };
}

function drawLine(
  context: CanvasRenderingContext2D,
  start: OperationalImageReviewGeometryPoint,
  end: OperationalImageReviewGeometryPoint,
) {
  context.beginPath();
  context.moveTo(start.x, start.y);
  context.lineTo(end.x, end.y);
  context.stroke();
}

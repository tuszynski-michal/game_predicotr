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
  automaticUnavailableGridCells,
  completeManualGridFlags,
  manualGridUnavailable,
  type ManualGridFlags,
} from '@game-predictor/manual-image-selection-core/manual-grid-qualification';

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
  operationalReviewTranslatedGeometryViewport,
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
  const panViewportRef = useRef<{
    readonly point: OperationalImageReviewGeometryPoint;
    readonly viewport: OperationalReviewGeometryViewport;
  } | null>(null);
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
  const [viewportPanningEnabled, setViewportPanningEnabled] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewKey, setPreviewKey] = useState('');
  const [loadingSource, setLoadingSource] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [flags, setFlags] = useState<ManualGridFlags>(completeManualGridFlags);
  const allowOutsideSource = flags.partial;
  const commandKey = useMemo(() => {
    if (context === null || corners === null) return '';
    try {
      return deferredBoardCellGeometryCommandKey(context, corners, flags);
    } catch {
      // Invalid qualification (e.g. "Niepełna plansza" without any field
      // marked as missing) never matches a preview; save() surfaces it.
      return '';
    }
  }, [context, corners, flags]);
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
      if (context !== null) {
        setViewport(
          operationalReviewGeometryViewport(
            next,
            context.sourceWidth,
            context.sourceHeight,
            0.35,
            allowOutsideSource,
          ),
        );
      }
    },
    [allowOutsideSource, clearPreview, context],
  );

  const updateFlags = useCallback(
    (next: ManualGridFlags) => {
      clearPreview();
      idempotencyRef.current = null;
      setError('');
      setFlags(next);
      if (context !== null && corners !== null) {
        setViewport(
          operationalReviewGeometryViewport(
            corners,
            context.sourceWidth,
            context.sourceHeight,
            0.35,
            next.partial,
          ),
        );
      }
    },
    [clearPreview, context, corners],
  );

  useEffect(() => {
    let active = true;
    async function load() {
      setContextState('loading');
      setError('');
      clearPreview();
      idempotencyRef.current = null;
      setFlags(completeManualGridFlags);
      setViewportPanningEnabled(false);
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
      const initialCorners = deferredBoardCellGeometryCorners(result.context);
      setCorners(initialCorners);
      setViewport(
        operationalReviewGeometryViewport(
          initialCorners,
          result.context.sourceWidth,
          result.context.sourceHeight,
          0.35,
        ),
      );
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

  const centerViewport = useCallback(() => {
    if (context === null || corners === null) return;
    setViewport(
      operationalReviewGeometryViewport(
        corners,
        context.sourceWidth,
        context.sourceHeight,
        0.35,
        allowOutsideSource,
      ),
    );
  }, [allowOutsideSource, context, corners]);

  useEffect(() => {
    if (context === null || sourceUrl === null) return;
    const image = new window.Image();
    image.crossOrigin = 'anonymous';
    image.decoding = 'async';
    image.onload = () => {
      sourceImageRef.current = image;
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
    if (allowOutsideSource) {
      // The viewport may extend past the real photo when the board is
      // extrapolated beyond its frame; fill the gap before drawing the
      // overlapping part of the real image on top of it.
      context2d.fillStyle = '#555';
      context2d.fillRect(0, 0, canvas.width, canvas.height);
    }
    const sourceLeft = Math.max(0, viewport.x);
    const sourceTop = Math.max(0, viewport.y);
    const sourceRight = Math.min(
      image.naturalWidth,
      viewport.x + viewport.width,
    );
    const sourceBottom = Math.min(
      image.naturalHeight,
      viewport.y + viewport.height,
    );
    const overlapWidth = sourceRight - sourceLeft;
    const overlapHeight = sourceBottom - sourceTop;
    if (overlapWidth > 0 && overlapHeight > 0) {
      context2d.drawImage(
        image,
        sourceLeft,
        sourceTop,
        overlapWidth,
        overlapHeight,
        sourceLeft - viewport.x,
        sourceTop - viewport.y,
        overlapWidth,
        overlapHeight,
      );
    }
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
  }, [corners, viewport, allowOutsideSource]);

  useEffect(() => {
    drawSource();
  }, [drawSource]);

  async function refreshPreview() {
    if (context === null || corners === null || loadingPreview || saving)
      return;
    let command;
    try {
      command = deferredBoardCellGeometryPreviewCommand(
        context,
        corners,
        flags,
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Sprawdź oznaczenia niedostępnych pól.',
      );
      return;
    }
    const requestedKey = commandKey;
    setLoadingPreview(true);
    setError('');
    const result = await previewDeferredBoardCellGeometry(
      api,
      scope,
      itemId,
      command,
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
        flags,
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

  function updateCanvasGesture(event: ReactPointerEvent<HTMLCanvasElement>) {
    const index = dragIndexRef.current;
    const canvas = canvasRef.current;
    if (canvas === null || context === null || viewport === null) return;
    const rect = canvas.getBoundingClientRect();
    const pointer = operationalReviewPointInCanvas(
      { x: event.clientX, y: event.clientY },
      rect,
      canvas.width,
      canvas.height,
    );
    if (index === null) {
      const pan = panViewportRef.current;
      if (pan === null) return;
      setViewport(
        operationalReviewTranslatedGeometryViewport(
          pan.viewport,
          {
            x: pan.point.x - pointer.point.x,
            y: pan.point.y - pointer.point.y,
          },
          context.sourceWidth,
          context.sourceHeight,
          allowOutsideSource,
        ),
      );
      return;
    }
    if (corners === null) return;
    const point = operationalReviewPointInSourceImage(
      pointer.point,
      viewport,
      context.sourceWidth,
      context.sourceHeight,
      allowOutsideSource,
    );
    const next = [...corners] as OperationalReviewGeometryCorners;
    next[index] = point;
    replaceCorners(next);
  }

  function startCanvasGesture(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (corners === null || viewport === null) return;
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
    if (candidate !== undefined && candidate.distance <= threshold) {
      dragIndexRef.current = candidate.index;
    } else if (viewportPanningEnabled) {
      panViewportRef.current = { point: pointer.point, viewport };
    } else {
      return;
    }
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
    updateCanvasGesture(event);
  }

  function finishCanvasGesture(event: ReactPointerEvent<HTMLCanvasElement>) {
    updateCanvasGesture(event);
    dragIndexRef.current = null;
    panViewportRef.current = null;
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

  const unavailable =
    corners === null
      ? []
      : manualGridUnavailable(
          flags,
          corners,
          context.sourceWidth,
          context.sourceHeight,
        );
  const automaticUnavailable =
    corners === null
      ? []
      : automaticUnavailableGridCells(
          corners,
          context.sourceWidth,
          context.sourceHeight,
        );

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
                Przeciągnij numerowany narożnik, aby zmienić siatkę. Obraz
                pozostaje statyczny; włącz aktywne przesuwanie, aby przeciągać
                tło i zmienić wyłącznie kadr widoku. Szare punkty są wyliczane
                automatycznie.
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
            <button
              className="textButton"
              disabled={context === null || corners === null || saving}
              onClick={centerViewport}
              type="button"
            >
              Wycentruj widok na siatce
            </button>
          </div>
          <label className="deferredGeometryPanToggle">
            <input
              checked={viewportPanningEnabled}
              disabled={saving}
              onChange={(event) => {
                panViewportRef.current = null;
                setViewportPanningEnabled(event.target.checked);
              }}
              type="checkbox"
            />{' '}
            Aktywne przesuwanie
          </label>
          {loadingSource ? <p>Wczytywanie obrazu…</p> : null}
          <canvas
            aria-label="Odroczona plansza z edytowalną siatką 5 na 3"
            className="operationalReviewGeometryCanvas deferredGeometryCanvas"
            onLostPointerCapture={() => {
              dragIndexRef.current = null;
              panViewportRef.current = null;
            }}
            onPointerCancel={() => {
              dragIndexRef.current = null;
              panViewportRef.current = null;
            }}
            onPointerDown={startCanvasGesture}
            onPointerMove={updateCanvasGesture}
            onPointerUp={finishCanvasGesture}
            ref={canvasRef}
            style={{
              aspectRatio:
                viewport === null
                  ? undefined
                  : `${viewport.width} / ${viewport.height}`,
            }}
          />
          <fieldset
            disabled={saving}
            style={{ border: 0, fontSize: '0.85rem' }}
          >
            <legend>Dostępne {15 - unavailable.length}/15</legend>
            <label>
              <input
                checked={flags.partial}
                onChange={(event) =>
                  updateFlags({
                    ...flags,
                    exclude: event.target.checked || flags.exclude,
                    includeInPartialGridTraining: event.target.checked
                      ? flags.includeInPartialGridTraining
                      : false,
                    manualUnavailable: event.target.checked
                      ? flags.manualUnavailable
                      : [],
                    partial: event.target.checked,
                  })
                }
                type="checkbox"
              />{' '}
              Niepełna plansza
            </label>
            {flags.partial ? (
              <p className="mutedText">
                Przeciągnij rogi poza zdjęcie (szary obszar) i zaznacz pola,
                których naprawdę nie ma na zdjęciu — trafią do Weryfikacji
                symboli jako „Nierozpoznany ?”.
              </p>
            ) : null}
            {flags.partial ? (
              <div aria-label="Niedostępne pola">
                {Array.from({ length: 15 }, (_, index) => (
                  <label key={index}>
                    <input
                      aria-label={`Pole ${index + 1} poza zdjęciem`}
                      checked={unavailable.includes(index)}
                      disabled={automaticUnavailable.includes(index)}
                      onChange={(event) =>
                        updateFlags({
                          ...flags,
                          manualUnavailable: event.target.checked
                            ? [...flags.manualUnavailable, index]
                            : flags.manualUnavailable.filter(
                                (value) => value !== index,
                              ),
                        })
                      }
                      type="checkbox"
                    />
                    {index + 1}{' '}
                  </label>
                ))}
              </div>
            ) : null}
          </fieldset>
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

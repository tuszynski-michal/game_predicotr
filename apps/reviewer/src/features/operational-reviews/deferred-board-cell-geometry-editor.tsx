'use client';

import type { OperationalImageReviewGeometryPoint } from '@game-predictor/admin-api-client';
import {
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
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
  type BoardGeometryCorrectionTarget,
  type BoardGeometryCorrectionView,
  copyCorners,
  deferredBoardGeometryTarget,
} from './board-geometry-correction-target';
import { gridCellsWithoutPixels } from './board-geometry-correction-state';
import type { DeferredBoardCellGeometryClient } from './deferred-board-cell-geometry-actions';
import {
  deferredBoardCellGeometryIdempotency,
  type DeferredBoardCellGeometryIdempotency,
} from './deferred-board-cell-geometry-state';
import {
  operationalReviewGeometryEdgeHandles,
  operationalReviewGeometryContainsPoint,
  operationalReviewGeometryViewport,
  operationalReviewPointInCanvas,
  operationalReviewPointInGeometryViewport,
  operationalReviewPointInLattice,
  operationalReviewPointInSourceImage,
  operationalReviewTranslatedGeometryCorners,
  type OperationalReviewGeometryCorners,
  type OperationalReviewGeometryViewport,
} from './operational-review-state';

type LoadState = 'error' | 'loading' | 'ready';

/** One active symbol the operator can assign to a previewed cell (D-488). */
export interface CorrectionSymbol {
  readonly id: string;
  readonly label: string;
}

const NO_SYMBOLS: readonly CorrectionSymbol[] = [];
const UNKNOWN_SYMBOL_LABEL = '?';

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
  const target = useMemo(
    () =>
      deferredBoardGeometryTarget({
        api,
        apiBaseUrl,
        pendingId: itemId,
        scope,
      }),
    [api, apiBaseUrl, itemId, scope],
  );
  return (
    <BoardGeometryCorrectionEditor
      canvasLabel="Odroczona plansza z edytowalną siatką 5 na 3"
      onConflict={onConflict}
      onSaved={onMaterialized}
      target={target}
    />
  );
}

/**
 * Corrects the grid of exactly one board (D-462): a deferred slot or a
 * current board with `Zła siatka` reports. Saving the geometry finishes the
 * correction; it never approves the board or its photo. With `symbols` and a
 * target that supports them, the operator may assign a symbol to a previewed
 * cell; only those cells are approved by the save (D-488).
 */
export function BoardGeometryCorrectionEditor({
  canvasLabel = 'Plansza z edytowalną siatką 5 na 3',
  onConflict,
  onSaved,
  saveLabel = 'Zapisz geometrię i dalej',
  symbols = NO_SYMBOLS,
  target,
}: {
  readonly canvasLabel?: string;
  readonly onConflict: (message: string) => Promise<void>;
  readonly onSaved: (reviewItemId: string | null) => Promise<void>;
  readonly saveLabel?: string;
  readonly symbols?: readonly CorrectionSymbol[];
  readonly target: BoardGeometryCorrectionTarget;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [sourceImage, setSourceImage] = useState<{
    image: HTMLImageElement;
    url: string;
  } | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const dragIndexRef = useRef<number | null>(null);
  const translateGridRef = useRef<{
    readonly corners: OperationalReviewGeometryCorners;
    readonly point: OperationalImageReviewGeometryPoint;
  } | null>(null);
  const gestureRef = useRef<{
    readonly pointerId: number;
    readonly viewport: OperationalReviewGeometryViewport;
    readonly rect: DOMRect;
  } | null>(null);
  const latestCornersRef = useRef<OperationalReviewGeometryCorners | null>(
    null,
  );
  const previewRequestRef = useRef(0);
  const currentCommandKeyRef = useRef('');
  const idempotencyRef = useRef<DeferredBoardCellGeometryIdempotency | null>(
    null,
  );
  const [context, setContext] = useState<BoardGeometryCorrectionView | null>(
    null,
  );
  const [contextState, setContextState] = useState<LoadState>('loading');
  const [corners, setCorners] =
    useState<OperationalReviewGeometryCorners | null>(null);
  const [viewport, setViewport] =
    useState<OperationalReviewGeometryViewport | null>(null);
  const [dragging, setDragging] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewKey, setPreviewKey] = useState('');
  const [loadingSource, setLoadingSource] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [flags, setFlags] = useState<ManualGridFlags>(completeManualGridFlags);
  // D-488: symbols the operator assigned, the cell being edited and the
  // read-only suggestions of the previewed cut.
  // A `null` value is the explicit "cannot tell": the cell is saved as
  // unreadable instead of getting a guessed symbol.
  const [chosenSymbols, setChosenSymbols] = useState<
    Readonly<Record<number, string | null>>
  >({});
  const [selectedCell, setSelectedCell] = useState<number | null>(null);
  const [suggestedSymbols, setSuggestedSymbols] = useState<{
    readonly key: string;
    readonly byCell: Readonly<Record<number, string | null>>;
  } | null>(null);
  const [symbolNotice, setSymbolNotice] = useState('');
  const canAssignSymbols = symbols.length > 0 && target.symbols !== undefined;
  const allowOutsideSource = flags.partial;
  const commandKey = useMemo(() => {
    if (context === null || corners === null) return '';
    try {
      return target.commandKey(corners, flags);
    } catch {
      // Invalid qualification (e.g. "Niepełna plansza" without any field
      // marked as missing) never matches a preview; save() surfaces it.
      return '';
    }
  }, [context, corners, flags, target]);
  const previewIsCurrent = previewUrl !== null && previewKey === commandKey;

  useEffect(() => {
    currentCommandKeyRef.current = commandKey;
  }, [commandKey]);

  const clearPreview = useCallback(() => {
    previewRequestRef.current += 1;
    setLoadingPreview(false);
    if (previewUrlRef.current !== null) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
    setPreviewUrl(null);
    setPreviewKey('');
  }, []);

  const replaceCorners = useCallback(
    (
      next: OperationalReviewGeometryCorners,
      {
        recenterViewport = false,
      }: { readonly recenterViewport?: boolean } = {},
    ) => {
      clearPreview();
      idempotencyRef.current = null;
      setCorners(next);
      latestCornersRef.current = next;
      if (recenterViewport && context !== null) {
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
      setDragging(false);
      dragIndexRef.current = null;
      gestureRef.current = null;
      translateGridRef.current = null;
      const result = await target.load();
      if (!active) return;
      if (!result.ok) {
        if (result.isConflict) {
          await onConflict(result.error);
          // The queue may keep this board (no reload); never stay loading.
          if (active) {
            setContextState('error');
            setError(result.error);
          }
          return;
        }
        setContextState('error');
        setError(result.error);
        return;
      }
      setLoadingSource(true);
      setContext(result.view);
      // A board that is already partial keeps its qualification and may keep
      // corners outside the photo.
      setFlags(result.view.initialFlags);
      const initialCorners = copyCorners(result.view.suggestedCorners);
      setCorners(initialCorners);
      latestCornersRef.current = initialCorners;
      setViewport(
        operationalReviewGeometryViewport(
          initialCorners,
          result.view.sourceWidth,
          result.view.sourceHeight,
          0.35,
          result.view.initialFlags.partial,
        ),
      );
      setContextState('ready');
    }
    void load();
    return () => {
      active = false;
      previewRequestRef.current += 1;
    };
  }, [clearPreview, onConflict, target]);

  const sourceUrl = context?.sourceUrl ?? null;

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
    let active = true;
    const image = new window.Image();
    image.crossOrigin = 'anonymous';
    image.decoding = 'async';
    image.onload = () => {
      if (!active) return;
      setSourceImage({ image, url: sourceUrl });
      setLoadingSource(false);
    };
    image.onerror = () => {
      if (!active) return;
      setSourceImage(null);
      setLoadingSource(false);
      setError('Nie udało się wczytać checksum-bound obrazu źródłowego.');
    };
    image.src = sourceUrl;
    return () => {
      active = false;
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
    const image = sourceImage?.url === sourceUrl ? sourceImage.image : null;
    if (canvas === null || corners === null || viewport === null) return;
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const context2d = canvas.getContext('2d');
    if (context2d === null) return;
    context2d.clearRect(0, 0, canvas.width, canvas.height);
    if (image === null) return;
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
  }, [corners, viewport, allowOutsideSource, sourceImage, sourceUrl]);

  // A new canvas can mount with unchanged image/geometry dependencies (for
  // example after a context reload). Always paint that DOM node before display.
  useLayoutEffect(() => {
    drawSource();
  });

  const refreshPreview = useCallback(async () => {
    if (
      context === null ||
      corners === null ||
      saving ||
      dragging ||
      loadingSource ||
      contextState !== 'ready'
    )
      return;
    try {
      target.commandKey(corners, flags);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Sprawdź oznaczenia niedostępnych pól.',
      );
      return;
    }
    const requestedKey = commandKey;
    const requestId = ++previewRequestRef.current;
    setLoadingPreview(true);
    setError('');
    const result = await target.preview(corners, flags);
    if (
      requestId !== previewRequestRef.current ||
      requestedKey !== currentCommandKeyRef.current
    )
      return;
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
  }, [
    clearPreview,
    commandKey,
    context,
    contextState,
    corners,
    dragging,
    flags,
    loadingSource,
    onConflict,
    saving,
    target,
  ]);

  useEffect(() => {
    // A current preview needs no refresh; refreshing it would also clear the
    // error of a failed save before the operator could read it.
    if (
      previewIsCurrent ||
      dragging ||
      loadingSource ||
      contextState !== 'ready'
    )
      return;
    // Coalesce rapid releases/qualification changes; never request mid-drag.
    const timer = window.setTimeout(() => void refreshPreview(), 150);
    return () => window.clearTimeout(timer);
  }, [contextState, dragging, loadingSource, previewIsCurrent, refreshPreview]);

  useEffect(() => {
    if (
      !canAssignSymbols ||
      !previewIsCurrent ||
      corners === null ||
      target.symbols === undefined ||
      suggestedSymbols?.key === commandKey
    )
      return;
    let active = true;
    const requestedKey = commandKey;
    void target.symbols(corners, flags).then((result) => {
      if (!active || requestedKey !== currentCommandKeyRef.current) return;
      // A failed suggestion never blocks the correction or the save.
      setSymbolNotice(result.ok ? '' : result.error);
      setSuggestedSymbols({
        byCell: result.ok
          ? Object.fromEntries(
              result.cells.map((cell) => [cell.cellIndex, cell.symbolId]),
            )
          : {},
        key: requestedKey,
      });
    });
    return () => {
      active = false;
    };
  }, [
    canAssignSymbols,
    commandKey,
    corners,
    flags,
    previewIsCurrent,
    suggestedSymbols,
    target,
  ]);

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
    const result = await target.save(
      corners,
      flags,
      idempotency.idempotencyKey,
      canAssignSymbols
        ? Object.entries(chosenSymbols)
            .map(([cellIndex, symbolId]) => ({
              cellIndex: Number(cellIndex),
              symbolId,
            }))
            .filter((cell) => !withoutPixels.includes(cell.cellIndex))
        : undefined,
    );
    setSaving(false);
    if (!result.ok) {
      setError(result.error);
      if (result.isConflict) await onConflict(result.error);
      return;
    }
    idempotencyRef.current = null;
    clearPreview();
    await onSaved(result.reviewItemId);
  }

  // Cells with no area inside the photo have no crop to label.
  const withoutPixels =
    context === null || corners === null
      ? []
      : gridCellsWithoutPixels(
          corners,
          context.sourceWidth,
          context.sourceHeight,
        );

  function updateCanvasGesture(event: ReactPointerEvent<HTMLCanvasElement>) {
    const gesture = gestureRef.current;
    if (gesture === null || gesture.pointerId !== event.pointerId) return;
    const viewport = gesture.viewport;
    const index = dragIndexRef.current;
    const canvas = canvasRef.current;
    if (canvas === null || context === null || viewport === null) return;
    const rect = gesture.rect;
    const pointer = operationalReviewPointInCanvas(
      { x: event.clientX, y: event.clientY },
      rect,
      canvas.width,
      canvas.height,
    );
    if (index === null) {
      const translation = translateGridRef.current;
      if (translation !== null) {
        const point = operationalReviewPointInSourceImage(
          pointer.point,
          viewport,
          context.sourceWidth,
          context.sourceHeight,
          allowOutsideSource,
        );
        replaceCorners(
          operationalReviewTranslatedGeometryCorners(
            translation.corners,
            {
              x: point.x - translation.point.x,
              y: point.y - translation.point.y,
            },
            context.sourceWidth,
            context.sourceHeight,
            allowOutsideSource,
          ),
        );
        return;
      }
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
    if (
      context === null ||
      corners === null ||
      viewport === null ||
      saving ||
      loadingSource ||
      sourceImage === null ||
      gestureRef.current !== null ||
      event.button !== 0
    )
      return;
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
    } else {
      const point = operationalReviewPointInSourceImage(
        pointer.point,
        viewport,
        context.sourceWidth,
        context.sourceHeight,
        allowOutsideSource,
      );
      if (!operationalReviewGeometryContainsPoint(corners, point)) return;
      translateGridRef.current = { corners, point };
    }
    event.preventDefault();
    gestureRef.current = { pointerId: event.pointerId, viewport, rect };
    setDragging(true);
    clearPreview();
    canvas.setPointerCapture(event.pointerId);
  }

  function finishCanvasGesture(
    event: ReactPointerEvent<HTMLCanvasElement>,
    cancelled = false,
  ) {
    if (gestureRef.current?.pointerId !== event.pointerId) return;
    if (!cancelled) updateCanvasGesture(event);
    dragIndexRef.current = null;
    translateGridRef.current = null;
    gestureRef.current = null;
    setDragging(false);
    const next = latestCornersRef.current;
    if (next !== null && context !== null) {
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
  const symbolLabel = (symbolId: string | null | undefined) =>
    symbols.find((symbol) => symbol.id === symbolId)?.label ?? null;
  const currentSuggestions =
    suggestedSymbols?.key === commandKey ? suggestedSymbols.byCell : {};
  // `undefined` clears the choice, `null` records "cannot tell".
  const assignSymbol = (symbolId: string | null | undefined) => {
    if (selectedCell === null) return;
    setChosenSymbols((current) => {
      const next = { ...current };
      if (symbolId === undefined) delete next[selectedCell];
      else next[selectedCell] = symbolId;
      return next;
    });
  };

  return (
    <div className="deferredGeometryEditor">
      <div className="deferredGeometryMetadata">
        {context.metadata.map((fact) => (
          <div key={fact.label}>
            <span>{fact.label}</span>
            <strong title={fact.title}>{fact.value}</strong>
          </div>
        ))}
      </div>

      <div className="operationalReviewGeometryBody deferredGeometryBody">
        <section>
          <div className="deferredGeometrySectionHeader">
            <div>
              <h3>Oryginał i edytowalna siatka</h3>
              <p>
                Przeciągnij numerowany narożnik, aby skorygować perspektywę,
                albo wnętrze siatki, aby przesunąć cały obrys bez jej zmiany.
                Podczas trzymania przycisku obraz pozostaje statyczny. Po
                puszczeniu kadr dopasuje się do siatki, a podgląd cropów
                odświeży się automatycznie. Szare punkty są wyliczane
                automatycznie.
              </p>
            </div>
            <button
              className="textButton"
              disabled={saving || dragging}
              onClick={() =>
                replaceCorners(copyCorners(context.suggestedCorners), {
                  recenterViewport: true,
                })
              }
              type="button"
            >
              Przywróć sugestię
            </button>
            <button
              className="textButton"
              disabled={
                context === null || corners === null || saving || dragging
              }
              onClick={centerViewport}
              type="button"
            >
              Wycentruj widok na siatce
            </button>
          </div>
          {loadingSource ? <p>Wczytywanie obrazu…</p> : null}
          <canvas
            aria-label={canvasLabel}
            className="operationalReviewGeometryCanvas deferredGeometryCanvas"
            onLostPointerCapture={(event) => finishCanvasGesture(event, true)}
            onPointerCancel={(event) => finishCanvasGesture(event, true)}
            onPointerDown={startCanvasGesture}
            onPointerMove={updateCanvasGesture}
            onPointerUp={(event) => finishCanvasGesture(event)}
            ref={canvasRef}
            style={{
              visibility: sourceImage?.url === sourceUrl ? 'visible' : 'hidden',
              aspectRatio:
                viewport === null
                  ? undefined
                  : `${viewport.width} / ${viewport.height}`,
            }}
          />
          <fieldset
            disabled={saving || dragging}
            hidden={!context.supportsPartial}
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
              <p>
                Podgląd odświeża się po puszczeniu siatki. Niczego nie zapisuje.
              </p>
            </div>
            <button
              className="secondaryButton"
              disabled={
                corners === null ||
                loadingPreview ||
                saving ||
                loadingSource ||
                dragging
              }
              onClick={() => void refreshPreview()}
              type="button"
            >
              {loadingPreview ? 'Generowanie…' : 'Ponów podgląd'}
            </button>
          </div>
          {previewUrl === null ? (
            <p className="operationalReviewGeometryPlaceholder">
              Ustaw narożniki i wygeneruj aktualny podgląd przed zapisem.
            </p>
          ) : (
            // Checksum-bound Blob URL zwrócony przez lokalny backend; każdy
            // kafelek pokazuje swój fragment tego jednego arkusza.
            <div
              aria-label="Podgląd 15 cropów planszy"
              className="operationalReviewGeometryCrops"
            >
              {Array.from({ length: 15 }, (_, index) => {
                const row = Math.floor(index / 5);
                const column = index % 5;
                const reported = context.reportedCellIndices.includes(index);
                // TASK-0798: a field outside the photo has no render; the
                // tile says so instead of showing an empty crop.
                const missing = unavailable.includes(index);
                const label = reported
                  ? `Crop ${index + 1} — zgłoszona zła siatka`
                  : missing
                    ? `Crop ${index + 1} — poza zdjęciem`
                    : `Crop ${index + 1}`;
                const style = {
                  backgroundImage: `url("${previewUrl}")`,
                  backgroundPosition: `${column * 25}% ${row * 50}%`,
                  backgroundSize: '500% 300%',
                  opacity: missing ? 0.3 : undefined,
                  outline: reported ? '3px solid #b42318' : undefined,
                };
                if (!canAssignSymbols || withoutPixels.includes(index)) {
                  return (
                    <div
                      aria-label={label}
                      key={index}
                      role="img"
                      style={style}
                    />
                  );
                }
                const chosen =
                  chosenSymbols[index] === null
                    ? UNKNOWN_SYMBOL_LABEL
                    : symbolLabel(chosenSymbols[index]);
                const suggested = symbolLabel(currentSuggestions[index]);
                return (
                  <button
                    aria-label={
                      chosen !== null
                        ? `${label} — wybrany symbol: ${chosen}`
                        : suggested !== null
                          ? `${label} — podpowiedź: ${suggested}`
                          : label
                    }
                    aria-pressed={selectedCell === index}
                    className="operationalReviewGeometryCropButton"
                    disabled={saving}
                    key={index}
                    onClick={() =>
                      setSelectedCell(selectedCell === index ? null : index)
                    }
                    style={{
                      ...style,
                      // A partly visible cell stays readable while assigning.
                      opacity: missing ? 0.6 : undefined,
                    }}
                    type="button"
                  >
                    {chosen !== null ? (
                      <strong>{chosen}</strong>
                    ) : suggested !== null ? (
                      <span>{suggested}</span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          )}
          {canAssignSymbols && previewUrl !== null ? (
            <div
              aria-label="Symbol wybranego pola"
              className="operationalReviewGeometrySymbolPicker"
              role="group"
            >
              <p>
                {selectedCell === null
                  ? 'Kliknij kafelek, aby narzucić jego symbol. Pogrubiona etykieta to Twój wybór, zwykła — podpowiedź. Jeśli nie widzisz symbolu, wybierz „Nie wiem”. Zapis zatwierdzi tylko wybrane pola.'
                  : `Pole ${selectedCell + 1}: wybierz symbol.`}
              </p>
              <div>
                {symbols.map((symbol) => (
                  <button
                    aria-pressed={
                      selectedCell !== null &&
                      chosenSymbols[selectedCell] === symbol.id
                    }
                    className="secondaryButton"
                    disabled={selectedCell === null || saving}
                    key={symbol.id}
                    onClick={() => assignSymbol(symbol.id)}
                    type="button"
                  >
                    {symbol.label}
                  </button>
                ))}
                <button
                  aria-pressed={
                    selectedCell !== null &&
                    chosenSymbols[selectedCell] === null
                  }
                  className="secondaryButton"
                  disabled={selectedCell === null || saving}
                  onClick={() => assignSymbol(null)}
                  title="Nie widzisz symbolu (np. jest zasłonięty)? Pole zostanie zapisane jako nieczytelne, bez zgadywania."
                  type="button"
                >
                  {UNKNOWN_SYMBOL_LABEL} Nie wiem
                </button>
                <button
                  className="textButton"
                  disabled={
                    selectedCell === null ||
                    saving ||
                    chosenSymbols[selectedCell] === undefined
                  }
                  onClick={() => assignSymbol(undefined)}
                  type="button"
                >
                  Usuń wybór
                </button>
              </div>
              {symbolNotice ? (
                <p className="mutedText">{symbolNotice}</p>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>

      {error ? (
        <p className="operationalReviewSaveError" role="alert">
          {error}
        </p>
      ) : null}

      <div className="deferredGeometrySaveBar">
        <span>{context.saveHint}</span>
        <button
          className="primaryButton"
          disabled={!previewIsCurrent || saving || loadingPreview}
          onClick={() => void saveGeometry()}
          type="button"
        >
          {saving ? 'Zapisywanie…' : saveLabel}
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

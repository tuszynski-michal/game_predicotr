'use client';

import type { ImageGridReviewItemResponse } from '@game-predictor/admin-api-client';
import {
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  operationalReviewPointInCanvas,
  operationalReviewPointInLattice,
  type OperationalReviewGeometryCorners,
} from '@/features/operational-reviews/operational-review-state';

import {
  previewGridReviewGeometry,
  saveGridReviewGeometry,
  type GridReviewsClient,
} from './grid-review-actions';
import {
  addGridGeometryPoint,
  GRID_CORNER_LABELS,
  gridGeometryDragTarget,
  gridReviewCorners,
  moveGridGeometry,
  moveGridGeometryCorner,
  undoGridGeometryPoint,
  type GridGeometryDragTarget,
  type GridGeometryDraft,
} from './grid-review-state';

interface GridReviewEditorProps {
  readonly api: GridReviewsClient;
  readonly item: ImageGridReviewItemResponse;
  readonly onSaved: () => void;
}

interface ActiveDrag {
  readonly lastPoint: { readonly x: number; readonly y: number };
  readonly target: Exclude<GridGeometryDragTarget, null>;
}

export function GridReviewEditor({
  api,
  item,
  onSaved,
}: GridReviewEditorProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sourceImageRef = useRef<HTMLImageElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const dragRef = useRef<ActiveDrag | null>(null);
  const [draft, setDraft] = useState<GridGeometryDraft>(() =>
    gridReviewCorners(item),
  );
  const [editing, setEditing] = useState(false);
  const [loadingSource, setLoadingSource] = useState(true);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewKey, setPreviewKey] = useState('');
  const [error, setError] = useState('');
  const sourceUrl = api.imageGridReviewSourceAssetUrl(
    item.reviewItemId,
    item.gameId,
    item.sourceChecksumSha256,
  );
  const draftKey = JSON.stringify(draft);
  const completeCorners =
    draft.length === 4 ? (draft as OperationalReviewGeometryCorners) : null;
  const previewIsCurrent = previewUrl !== null && previewKey === draftKey;
  const cellCount = item.gridRows * item.gridColumns;

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const image = sourceImageRef.current;
    if (canvas === null || image === null) return;
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext('2d');
    if (context === null) return;
    context.drawImage(image, 0, 0);
    context.lineWidth = Math.max(3, canvas.width / 600);
    context.strokeStyle = '#f4d35e';
    context.fillStyle = '#fffaf0';
    if (completeCorners !== null) {
      for (let column = 0; column <= item.gridColumns; column += 1) {
        const ratio = column / item.gridColumns;
        drawLine(
          context,
          operationalReviewPointInLattice(completeCorners, ratio, 0),
          operationalReviewPointInLattice(completeCorners, ratio, 1),
        );
      }
      for (let row = 0; row <= item.gridRows; row += 1) {
        const ratio = row / item.gridRows;
        drawLine(
          context,
          operationalReviewPointInLattice(completeCorners, 0, ratio),
          operationalReviewPointInLattice(completeCorners, 1, ratio),
        );
      }
    } else if (draft.length > 1) {
      context.beginPath();
      context.moveTo(draft[0]?.x ?? 0, draft[0]?.y ?? 0);
      draft.slice(1).forEach((point) => context.lineTo(point.x, point.y));
      context.stroke();
    }
    draft.forEach((point, index) => {
      const radius = Math.max(10, canvas.width / 140);
      context.beginPath();
      context.fillStyle = '#fffaf0';
      context.strokeStyle = '#b42318';
      context.arc(point.x, point.y, radius, 0, Math.PI * 2);
      context.fill();
      context.stroke();
      context.fillStyle = '#7a271a';
      context.font = `bold ${Math.max(20, canvas.width / 55)}px sans-serif`;
      context.fillText(
        GRID_CORNER_LABELS[index] ?? '',
        point.x + radius,
        point.y - radius,
      );
    });
  }, [completeCorners, draft, item.gridColumns, item.gridRows]);

  useEffect(() => draw(), [draw, loadingSource]);

  useEffect(() => {
    const image = new window.Image();
    image.crossOrigin = 'anonymous';
    image.onload = () => {
      sourceImageRef.current = image;
      setLoadingSource(false);
    };
    image.onerror = () => {
      setLoadingSource(false);
      setError('Nie udało się wczytać oryginalnego obrazu planszy.');
    };
    image.src = sourceUrl;
    return () => {
      image.onload = null;
      image.onerror = null;
      sourceImageRef.current = null;
    };
  }, [sourceUrl]);

  useEffect(
    () => () => {
      if (previewUrlRef.current !== null) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
    },
    [],
  );

  const invalidatePreview = useCallback(() => {
    setPreviewKey('');
  }, []);

  function sourcePoint(event: ReactPointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (canvas === null) return null;
    return operationalReviewPointInCanvas(
      { x: event.clientX, y: event.clientY },
      canvas.getBoundingClientRect(),
      canvas.width,
      canvas.height,
    );
  }

  function pointerDown(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (!editing || saving || loadingPreview) return;
    event.preventDefault();
    const pointer = sourcePoint(event);
    if (pointer === null) return;
    if (draft.length < 4) {
      setDraft((current) =>
        addGridGeometryPoint(
          current,
          pointer.point,
          item.sourceWidth,
          item.sourceHeight,
        ),
      );
      invalidatePreview();
      return;
    }
    const target = gridGeometryDragTarget(
      draft,
      pointer.point,
      44 / pointer.scale,
    );
    if (target === null) return;
    dragRef.current = { lastPoint: pointer.point, target };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function pointerMove(event: ReactPointerEvent<HTMLCanvasElement>) {
    const active = dragRef.current;
    if (active === null) return;
    const pointer = sourcePoint(event);
    if (pointer === null) return;
    setDraft((current) =>
      active.target.kind === 'corner'
        ? moveGridGeometryCorner(
            current,
            active.target.index,
            pointer.point,
            item.sourceWidth,
            item.sourceHeight,
          )
        : moveGridGeometry(
            current,
            {
              x: pointer.point.x - active.lastPoint.x,
              y: pointer.point.y - active.lastPoint.y,
            },
            item.sourceWidth,
            item.sourceHeight,
          ),
    );
    dragRef.current = { ...active, lastPoint: pointer.point };
    invalidatePreview();
  }

  function pointerUp(event: ReactPointerEvent<HTMLCanvasElement>) {
    pointerMove(event);
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  async function refreshPreview() {
    if (completeCorners === null || loadingPreview || saving) return;
    setLoadingPreview(true);
    setError('');
    const requestedKey = JSON.stringify(completeCorners);
    const result = await previewGridReviewGeometry(api, item, completeCorners);
    setLoadingPreview(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    if (previewUrlRef.current !== null) {
      URL.revokeObjectURL(previewUrlRef.current);
    }
    const url = URL.createObjectURL(result.blob);
    previewUrlRef.current = url;
    setPreviewUrl(url);
    setPreviewKey(requestedKey);
  }

  async function save() {
    if (completeCorners === null || !previewIsCurrent || saving) return;
    setSaving(true);
    setError('');
    const result = await saveGridReviewGeometry(
      api,
      item,
      completeCorners,
      globalThis.crypto.randomUUID(),
    );
    setSaving(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    onSaved();
  }

  const cropIndices = useMemo(
    () => Array.from({ length: cellCount }, (_, index) => index),
    [cellCount],
  );

  return (
    <section className="gridReviewEditor">
      <div className="gridReviewCanvasPanel">
        <div className="gridReviewCanvasHeading">
          <div>
            <span className="eyebrow">Oryginalny obraz i overlay</span>
            <h2>
              Plansza {item.sequenceNumber} · {item.gridColumns} ×{' '}
              {item.gridRows}
            </h2>
          </div>
          <button
            className="secondaryButton"
            disabled={loadingSource || saving}
            onClick={() => setEditing((value) => !value)}
            type="button"
          >
            {editing ? 'Zakończ edycję' : 'Zmień siatkę'}
          </button>
        </div>
        {loadingSource ? <p>Wczytywanie obrazu…</p> : null}
        <canvas
          aria-label="Oryginalny obraz planszy z edytowalną siatką"
          className={
            editing ? 'gridReviewCanvas isEditing' : 'gridReviewCanvas'
          }
          onLostPointerCapture={() => {
            dragRef.current = null;
          }}
          onPointerCancel={() => {
            dragRef.current = null;
          }}
          onPointerDown={pointerDown}
          onPointerMove={pointerMove}
          onPointerUp={pointerUp}
          ref={canvasRef}
        />
        {editing ? (
          <div className="gridReviewEditControls">
            <p>
              {draft.length < 4
                ? `Kliknij narożnik ${GRID_CORNER_LABELS[draft.length]} (${draft.length + 1}/4).`
                : 'Przeciągnij narożnik albo środek siatki, aby przesunąć całość.'}
            </p>
            <div>
              <button
                className="textButton"
                disabled={draft.length === 0 || saving}
                onClick={() => {
                  setDraft((current) => undoGridGeometryPoint(current));
                  invalidatePreview();
                }}
                type="button"
              >
                Cofnij punkt
              </button>
              <button
                className="textButton"
                disabled={saving}
                onClick={() => {
                  setDraft([]);
                  invalidatePreview();
                }}
                type="button"
              >
                Resetuj
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {editing ? (
        <section className="gridReviewPreviewPanel">
          <div className="gridReviewCanvasHeading">
            <div>
              <span className="eyebrow">Source-direct</span>
              <h3>Podgląd {cellCount} cropów</h3>
            </div>
            <button
              className="secondaryButton"
              disabled={completeCorners === null || loadingPreview || saving}
              onClick={() => void refreshPreview()}
              type="button"
            >
              {loadingPreview ? 'Generowanie…' : 'Generuj podgląd'}
            </button>
          </div>
          {previewUrl === null ? (
            <p className="mutedText">
              Ustaw cztery narożniki i wygeneruj podgląd.
            </p>
          ) : (
            <div
              className="gridReviewCropPreview"
              style={{
                gridTemplateColumns: `repeat(${item.gridColumns}, minmax(64px, 1fr))`,
              }}
            >
              {cropIndices.map((index) => {
                const row = Math.floor(index / item.gridColumns);
                const column = index % item.gridColumns;
                return (
                  <div
                    aria-label={`Crop ${index + 1}`}
                    key={index}
                    role="img"
                    style={{
                      backgroundImage: `url("${previewUrl}")`,
                      backgroundPosition: `${item.gridColumns === 1 ? 0 : (column * 100) / (item.gridColumns - 1)}% ${item.gridRows === 1 ? 0 : (row * 100) / (item.gridRows - 1)}%`,
                      backgroundSize: `${item.gridColumns * 100}% ${item.gridRows * 100}%`,
                    }}
                  />
                );
              })}
            </div>
          )}
          <button
            className="primaryButton"
            disabled={!previewIsCurrent || saving || loadingPreview}
            onClick={() => void save()}
            type="button"
          >
            {saving ? 'Zapisywanie…' : 'Zapisz i zatwierdź geometrię'}
          </button>
        </section>
      ) : null}
      {error ? (
        <p className="reviewerAccessError" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function drawLine(
  context: CanvasRenderingContext2D,
  start: { readonly x: number; readonly y: number },
  end: { readonly x: number; readonly y: number },
) {
  context.beginPath();
  context.moveTo(start.x, start.y);
  context.lineTo(end.x, end.y);
  context.stroke();
}

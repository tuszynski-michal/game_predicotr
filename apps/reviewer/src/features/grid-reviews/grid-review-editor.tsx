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
  type GridGeometryDragTarget,
  type GridGeometryDraft,
} from './grid-review-state';

interface GridReviewEditorProps {
  readonly api: GridReviewsClient;
  readonly items: readonly ImageGridReviewItemResponse[];
  readonly onEditingChange: (editing: boolean) => void;
  readonly onSaved: () => void;
  readonly onSelect: (reviewItemId: string) => void;
  readonly selectedReviewItemId: string;
}

interface ActiveDrag {
  readonly lastPoint: { readonly x: number; readonly y: number };
  readonly target: Exclude<GridGeometryDragTarget, null>;
}

export function GridReviewEditor({
  api,
  items,
  onEditingChange,
  onSaved,
  onSelect,
  selectedReviewItemId,
}: GridReviewEditorProps) {
  const item =
    items.find(
      (candidate) => candidate.reviewItemId === selectedReviewItemId,
    ) ?? items[0];
  if (item === undefined) return null;

  return (
    <GridReviewEditorContent
      api={api}
      item={item}
      items={items}
      onEditingChange={onEditingChange}
      onSaved={onSaved}
      onSelect={onSelect}
    />
  );
}

function GridReviewEditorContent({
  api,
  item,
  items,
  onEditingChange,
  onSaved,
  onSelect,
}: Omit<GridReviewEditorProps, 'selectedReviewItemId'> & {
  readonly item: ImageGridReviewItemResponse;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sourceImageRef = useRef<HTMLImageElement | null>(null);
  const previewUrlsRef = useRef<Set<string>>(new Set());
  const dragRef = useRef<ActiveDrag | null>(null);
  const automaticCorners = useMemo(() => gridReviewCorners(item), [item]);
  const [draft, setDraft] = useState<GridGeometryDraft>(automaticCorners);
  const [editing, setEditing] = useState(false);
  const [loadingSource, setLoadingSource] = useState(true);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [autoPreviewUrl, setAutoPreviewUrl] = useState<string | null>(null);
  const [draftPreviewUrl, setDraftPreviewUrl] = useState<string | null>(null);
  const [previewKey, setPreviewKey] = useState('');
  const [previewMode, setPreviewMode] = useState<'automatic' | 'edited'>(
    'edited',
  );
  const [selectedCellIndex, setSelectedCellIndex] = useState(0);
  const [showOverlay, setShowOverlay] = useState(true);
  const [zoomPercent, setZoomPercent] = useState(100);
  const [error, setError] = useState('');
  const sourceAssetItem = items[0] ?? item;
  const sourceUrl = api.imageGridReviewSourceAssetUrl(
    sourceAssetItem.reviewItemId,
    sourceAssetItem.gameId,
    sourceAssetItem.sourceChecksumSha256,
  );
  const draftKey = JSON.stringify(draft);
  const completeCorners = asCompleteCorners(draft);
  const previewIsCurrent = draftPreviewUrl !== null && previewKey === draftKey;
  const cellCount = item.gridRows * item.gridColumns;
  const shownPreviewUrl =
    previewMode === 'automatic' ? autoPreviewUrl : draftPreviewUrl;

  useEffect(() => {
    onEditingChange(editing);
  }, [editing, onEditingChange]);

  useEffect(
    () => () => {
      onEditingChange(false);
      previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      previewUrlsRef.current.clear();
    },
    [onEditingChange],
  );

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const image = sourceImageRef.current;
    if (canvas === null || image === null) return;
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext('2d');
    if (context === null) return;
    context.drawImage(image, 0, 0);
    if (!showOverlay) return;

    for (const candidate of items) {
      const selected = candidate.reviewItemId === item.reviewItemId;
      const corners = selected
        ? (completeCorners ?? draft)
        : gridReviewCorners(candidate);
      drawBoardOverlay(context, {
        cellIndex: selected ? selectedCellIndex : null,
        corners,
        gridColumns: candidate.gridColumns,
        gridRows: candidate.gridRows,
        label: String(candidate.positionIndex + 1),
        selected,
      });
    }
  }, [
    completeCorners,
    draft,
    item.reviewItemId,
    items,
    selectedCellIndex,
    showOverlay,
  ]);

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
      setError('Nie udało się wczytać oryginalnego obrazu źródłowego.');
    };
    image.src = sourceUrl;
    return () => {
      image.onload = null;
      image.onerror = null;
      sourceImageRef.current = null;
    };
  }, [sourceUrl]);

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
    if (saving || loadingPreview) return;
    const pointer = sourcePoint(event);
    if (pointer === null) return;
    if (!editing) {
      const selected = [...items]
        .reverse()
        .find((candidate) =>
          pointInQuad(pointer.point, gridReviewCorners(candidate)),
        );
      if (selected !== undefined) onSelect(selected.reviewItemId);
      return;
    }
    event.preventDefault();
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

  function replacePreviewUrls(automatic: Blob, edited: Blob) {
    previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    previewUrlsRef.current.clear();
    const automaticUrl = URL.createObjectURL(automatic);
    const editedUrl = URL.createObjectURL(edited);
    previewUrlsRef.current.add(automaticUrl);
    previewUrlsRef.current.add(editedUrl);
    setAutoPreviewUrl(automaticUrl);
    setDraftPreviewUrl(editedUrl);
  }

  async function refreshPreview() {
    if (completeCorners === null || loadingPreview || saving) return;
    setLoadingPreview(true);
    setError('');
    const requestedKey = JSON.stringify(completeCorners);
    const automaticResult = await previewGridReviewGeometry(
      api,
      item,
      automaticCorners,
    );
    if (!automaticResult.ok) {
      setLoadingPreview(false);
      setError(automaticResult.error);
      return;
    }
    const editedResult =
      JSON.stringify(automaticCorners) === requestedKey
        ? automaticResult
        : await previewGridReviewGeometry(api, item, completeCorners);
    setLoadingPreview(false);
    if (!editedResult.ok) {
      setError(editedResult.error);
      return;
    }
    replacePreviewUrls(automaticResult.blob, editedResult.blob);
    setPreviewKey(requestedKey);
    setPreviewMode('edited');
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
  const selectedRow = Math.floor(selectedCellIndex / item.gridColumns);
  const selectedColumn = selectedCellIndex % item.gridColumns;

  return (
    <section className="gridReviewEditor">
      <div className="gridReviewCanvasPanel">
        <div className="gridReviewCanvasHeading">
          <div>
            <span className="eyebrow">Oryginalne zdjęcie i aktywne sloty</span>
            <h2>
              Plansza {item.positionIndex + 1} · sekwencja {item.sequenceNumber}
            </h2>
          </div>
          <div className="gridReviewCanvasTools">
            <label>
              Zoom
              <select
                aria-label="Powiększenie obrazu źródłowego"
                disabled={saving}
                onChange={(event) => setZoomPercent(Number(event.target.value))}
                value={zoomPercent}
              >
                {[100, 125, 150, 200].map((value) => (
                  <option key={value} value={value}>
                    {value}%
                  </option>
                ))}
              </select>
            </label>
            <button
              aria-pressed={showOverlay}
              className="secondaryButton"
              disabled={loadingSource || saving}
              onClick={() => setShowOverlay((value) => !value)}
              type="button"
            >
              {showOverlay ? 'Ukryj overlay' : 'Pokaż overlay'}
            </button>
            <button
              className="secondaryButton"
              disabled={loadingSource || saving}
              onClick={() => setEditing((value) => !value)}
              type="button"
            >
              {editing ? 'Zakończ edycję' : 'Zmień siatkę'}
            </button>
          </div>
        </div>
        <p className="gridReviewMetadata">
          {item.geometryEngineName ?? 'Brak silnika'} ·{' '}
          {item.geometryEngineVersion ?? 'brak wersji'} · confidence{' '}
          {(item.boardConfidence * 100).toFixed(1)}%
          {item.reasonCodes.length > 0
            ? ` · ${item.reasonCodes.join(', ')}`
            : ''}
        </p>
        {loadingSource ? <p>Wczytywanie obrazu…</p> : null}
        <div className="gridReviewSourceViewport">
          <canvas
            aria-label="Oryginalny obraz źródłowy z aktywnymi siatkami plansz"
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
            style={{ width: `${zoomPercent}%` }}
          />
        </div>
        <div
          className="gridReviewSlotList"
          role="list"
          aria-label="Aktywne plansze źródła"
        >
          {items.map((candidate) => (
            <button
              aria-pressed={candidate.reviewItemId === item.reviewItemId}
              className={
                candidate.reviewItemId === item.reviewItemId
                  ? 'isSelected'
                  : undefined
              }
              key={candidate.reviewItemId}
              onClick={() => onSelect(candidate.reviewItemId)}
              type="button"
            >
              #{candidate.positionIndex + 1} · {candidate.sequenceNumber} ·{' '}
              {candidate.state === 'approved'
                ? 'zatwierdzona'
                : candidate.state === 'needs_correction'
                  ? 'do poprawy'
                  : 'do walidacji'}
            </button>
          ))}
        </div>
        {editing ? (
          <div className="gridReviewEditControls">
            <p>
              {draft.length < 4
                ? `Kliknij narożnik ${GRID_CORNER_LABELS[draft.length]} (${draft.length + 1}/4).`
                : 'Przeciągnij narożnik albo środek wybranej siatki.'}
            </p>
            <div>
              <button
                className="textButton"
                disabled={draft.length === 0 || saving}
                onClick={() => {
                  setDraft((current) => current.slice(0, -1));
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
                  setDraft(automaticCorners);
                  invalidatePreview();
                }}
                type="button"
              >
                Resetuj do automatu
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
                Wskaż od nowa
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {editing ? (
        <section className="gridReviewPreviewPanel">
          <div className="gridReviewCanvasHeading">
            <div>
              <span className="eyebrow">A/B source-direct</span>
              <h3>Podgląd {cellCount} cropów wybranej planszy</h3>
            </div>
            <button
              className="secondaryButton"
              disabled={completeCorners === null || loadingPreview || saving}
              onClick={() => void refreshPreview()}
              type="button"
            >
              {loadingPreview ? 'Generowanie…' : 'Generuj porównanie A/B'}
            </button>
          </div>
          {shownPreviewUrl === null ? (
            <p className="mutedText">
              Ustaw cztery narożniki i wygeneruj porównanie automatu z edycją.
            </p>
          ) : (
            <>
              <div className="gridReviewPreviewTabs" role="tablist">
                <button
                  aria-selected={previewMode === 'automatic'}
                  className={
                    previewMode === 'automatic' ? 'isActive' : undefined
                  }
                  onClick={() => setPreviewMode('automatic')}
                  role="tab"
                  type="button"
                >
                  A · Automat
                </button>
                <button
                  aria-selected={previewMode === 'edited'}
                  className={previewMode === 'edited' ? 'isActive' : undefined}
                  onClick={() => setPreviewMode('edited')}
                  role="tab"
                  type="button"
                >
                  B · Edycja
                </button>
              </div>
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
                    <button
                      aria-label={`Crop ${index + 1}`}
                      aria-pressed={selectedCellIndex === index}
                      className={
                        selectedCellIndex === index ? 'isSelected' : undefined
                      }
                      key={index}
                      onClick={() => setSelectedCellIndex(index)}
                      style={cropBackgroundStyle(
                        shownPreviewUrl,
                        item.gridColumns,
                        item.gridRows,
                        column,
                        row,
                      )}
                      type="button"
                    />
                  );
                })}
              </div>
              <div
                aria-label={`Powiększony crop ${selectedCellIndex + 1}`}
                className="gridReviewCropEnlarged"
                role="img"
                style={cropBackgroundStyle(
                  shownPreviewUrl,
                  item.gridColumns,
                  item.gridRows,
                  selectedColumn,
                  selectedRow,
                )}
              />
            </>
          )}
          <button
            className="primaryButton"
            disabled={!previewIsCurrent || saving || loadingPreview}
            onClick={() => void save()}
            type="button"
          >
            {saving ? 'Zapisywanie…' : 'Zapisz i przejdź do następnego zdjęcia'}
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

function drawBoardOverlay(
  context: CanvasRenderingContext2D,
  input: {
    readonly cellIndex: number | null;
    readonly corners: GridGeometryDraft;
    readonly gridColumns: number;
    readonly gridRows: number;
    readonly label: string;
    readonly selected: boolean;
  },
) {
  const width = context.canvas.width;
  const completeCorners = asCompleteCorners(input.corners);
  context.save();
  context.lineWidth = Math.max(2, width / 800);
  context.strokeStyle = input.selected
    ? '#f4d35e'
    : 'rgba(125, 211, 252, 0.72)';
  context.fillStyle = input.selected
    ? 'rgba(244, 211, 94, 0.12)'
    : 'rgba(125, 211, 252, 0.06)';
  context.beginPath();
  context.moveTo(input.corners[0].x, input.corners[0].y);
  input.corners.slice(1).forEach((point) => context.lineTo(point.x, point.y));
  if (completeCorners !== null) {
    context.closePath();
    context.fill();
  }
  context.stroke();
  if (completeCorners !== null) {
    for (let column = 0; column <= input.gridColumns; column += 1) {
      const ratio = column / input.gridColumns;
      drawLine(
        context,
        operationalReviewPointInLattice(completeCorners, ratio, 0),
        operationalReviewPointInLattice(completeCorners, ratio, 1),
      );
    }
    for (let row = 0; row <= input.gridRows; row += 1) {
      const ratio = row / input.gridRows;
      drawLine(
        context,
        operationalReviewPointInLattice(completeCorners, 0, ratio),
        operationalReviewPointInLattice(completeCorners, 1, ratio),
      );
    }
  }
  if (completeCorners !== null && input.selected && input.cellIndex !== null) {
    const row = Math.floor(input.cellIndex / input.gridColumns);
    const column = input.cellIndex % input.gridColumns;
    const topLeft = operationalReviewPointInLattice(
      completeCorners,
      column / input.gridColumns,
      row / input.gridRows,
    );
    const bottomRight = operationalReviewPointInLattice(
      completeCorners,
      (column + 1) / input.gridColumns,
      (row + 1) / input.gridRows,
    );
    context.fillStyle = 'rgba(255, 255, 255, 0.22)';
    context.fillRect(
      Math.min(topLeft.x, bottomRight.x),
      Math.min(topLeft.y, bottomRight.y),
      Math.abs(bottomRight.x - topLeft.x),
      Math.abs(bottomRight.y - topLeft.y),
    );
  }
  const center =
    completeCorners === null
      ? input.corners[0]
      : operationalReviewPointInLattice(completeCorners, 0.5, 0.5);
  context.fillStyle = input.selected ? '#fffaf0' : '#d9f4ff';
  context.font = `bold ${Math.max(20, width / 45)}px sans-serif`;
  context.fillText(input.label, center.x, center.y);
  if (input.selected) {
    input.corners.forEach((point, index) => {
      const radius = Math.max(8, width / 180);
      context.beginPath();
      context.fillStyle = '#fffaf0';
      context.strokeStyle = '#b42318';
      context.arc(point.x, point.y, radius, 0, Math.PI * 2);
      context.fill();
      context.stroke();
      context.fillStyle = '#7a271a';
      context.font = `bold ${Math.max(16, width / 65)}px sans-serif`;
      context.fillText(
        GRID_CORNER_LABELS[index] ?? '',
        point.x + radius,
        point.y - radius,
      );
    });
  }
  context.restore();
}

function asCompleteCorners(
  draft: GridGeometryDraft,
): OperationalReviewGeometryCorners | null {
  return draft.length === 4
    ? (draft as OperationalReviewGeometryCorners)
    : null;
}

function cropBackgroundStyle(
  previewUrl: string,
  columns: number,
  rows: number,
  column: number,
  row: number,
) {
  return {
    backgroundImage: `url("${previewUrl}")`,
    backgroundPosition: `${columns === 1 ? 0 : (column * 100) / (columns - 1)}% ${rows === 1 ? 0 : (row * 100) / (rows - 1)}%`,
    backgroundSize: `${columns * 100}% ${rows * 100}%`,
  };
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

function pointInQuad(
  point: { readonly x: number; readonly y: number },
  quad: GridGeometryDraft,
): boolean {
  let inside = false;
  for (
    let index = 0, previous = quad.length - 1;
    index < quad.length;
    previous = index++
  ) {
    const current = quad[index];
    const previousPoint = quad[previous];
    if (current === undefined || previousPoint === undefined) continue;
    const crosses =
      current.y > point.y !== previousPoint.y > point.y &&
      point.x <
        ((previousPoint.x - current.x) * (point.y - current.y)) /
          (previousPoint.y - current.y) +
          current.x;
    if (crosses) inside = !inside;
  }
  return inside;
}

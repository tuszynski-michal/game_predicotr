'use client';

import type { ImageGridReviewItemResponse } from '@game-predictor/admin-api-client';
import {
  forwardRef,
  type ForwardedRef,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useImperativeHandle,
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
  saveGridReviewSourceGeometry,
  type GridReviewsClient,
} from './grid-review-actions';
import {
  addGridGeometryPoint,
  completeGridGeometrySourceDrafts,
  currentGridGeometrySourceDrafts,
  emptyGridGeometrySourceDrafts,
  firstIncompleteGridGeometrySourceItem,
  GRID_CORNER_LABELS,
  gridGeometryDraftAnchor,
  gridGeometryDraftsEqual,
  gridGeometrySourceDraft,
  gridGeometrySourceItemAtPoint,
  gridGeometryDragTarget,
  gridReviewAnalysisCorners,
  gridReviewCorners,
  gridReviewLatticeReason,
  moveGridGeometry,
  moveGridGeometryCorner,
  nextIncompleteGridGeometrySourceItem,
  replaceGridGeometrySourceDraft,
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

export interface GridReviewEditorHandle {
  readonly submitEdits: () => Promise<'invalid' | 'saved' | 'unchanged'>;
}

interface ActiveDrag {
  readonly automaticCorners: OperationalReviewGeometryCorners;
  readonly draft: GridGeometryDraft;
  readonly imageHeight: number;
  readonly imageWidth: number;
  readonly lastPoint: { readonly x: number; readonly y: number };
  readonly slotId: string;
  readonly sourceWide: boolean;
  readonly target: Exclude<GridGeometryDragTarget, null>;
}

interface GridGeometryItemDraft {
  readonly corners: GridGeometryDraft;
  readonly slotId: string;
}

interface GridReviewCellSelection {
  readonly cellIndex: number;
  readonly slotId: string;
}

export const GridReviewEditor = forwardRef<
  GridReviewEditorHandle,
  GridReviewEditorProps
>(function GridReviewEditor(
  { api, items, onEditingChange, onSaved, onSelect, selectedReviewItemId },
  ref,
) {
  const item =
    items.find((candidate) => candidate.slotId === selectedReviewItemId) ??
    items[0];
  if (item === undefined) return null;

  return (
    <GridReviewEditorContent
      api={api}
      editorRef={ref}
      item={item}
      items={items}
      onEditingChange={onEditingChange}
      onSaved={onSaved}
      onSelect={onSelect}
    />
  );
});

function GridReviewEditorContent({
  api,
  editorRef,
  item,
  items,
  onEditingChange,
  onSaved,
  onSelect,
}: Omit<GridReviewEditorProps, 'selectedReviewItemId'> & {
  readonly editorRef: ForwardedRef<GridReviewEditorHandle>;
  readonly item: ImageGridReviewItemResponse;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sourceImageRef = useRef<HTMLImageElement | null>(null);
  const previewUrlsRef = useRef<Set<string>>(new Set());
  const dragRef = useRef<ActiveDrag | null>(null);
  const automaticCorners = useMemo(() => gridReviewCorners(item), [item]);
  const latticeReason = useMemo(() => gridReviewLatticeReason(item), [item]);
  const [draft, setDraft] = useState<GridGeometryItemDraft>(() => ({
    corners: automaticCorners,
    slotId: item.slotId,
  }));
  const [editing, setEditing] = useState(false);
  const [sourceEditing, setSourceEditing] = useState(false);
  const [sourceRedefining, setSourceRedefining] = useState(false);
  const [modifiedSourceItems, setModifiedSourceItems] = useState<
    ReadonlySet<string>
  >(new Set());
  const [sourceDrafts, setSourceDrafts] = useState(
    currentGridGeometrySourceDrafts(items),
  );
  const [loadingSource, setLoadingSource] = useState(true);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [autoPreviewUrl, setAutoPreviewUrl] = useState<string | null>(null);
  const [draftPreviewUrl, setDraftPreviewUrl] = useState<string | null>(null);
  const [previewKey, setPreviewKey] = useState('');
  const [previewMode, setPreviewMode] = useState<'automatic' | 'edited'>(
    'edited',
  );
  const [selectedCell, setSelectedCell] = useState<GridReviewCellSelection>(
    () => ({ cellIndex: 0, slotId: item.slotId }),
  );
  const [zoomPercent, setZoomPercent] = useState(100);
  const [error, setError] = useState('');
  const sourceAssetItem = items[0] ?? item;
  const sourceUrl = api.imageGridReviewSourceAssetUrl(
    sourceAssetItem.slotId,
    sourceAssetItem.gameId,
    sourceAssetItem.sourceChecksumSha256,
  );
  const storedSourceDraft = gridGeometrySourceDraft(sourceDrafts, item.slotId);
  const currentItemDraft =
    draft.slotId === item.slotId ? draft.corners : automaticCorners;
  const hasPendingIndividualDraft =
    draft.slotId === item.slotId &&
    !gridGeometryDraftsEqual(draft.corners, automaticCorners);
  const activeDraft =
    sourceEditing ||
    (!editing && !hasPendingIndividualDraft && storedSourceDraft.length > 0)
      ? storedSourceDraft
      : currentItemDraft;
  const draftKey = sourceEditing
    ? JSON.stringify(
        items.map((candidate) => [
          candidate.slotId,
          gridGeometrySourceDraft(sourceDrafts, candidate.slotId),
        ]),
      )
    : JSON.stringify([item.slotId, activeDraft]);
  const completeCorners = asCompleteCorners(activeDraft);
  const completeSourceDrafts = useMemo(
    () => completeGridGeometrySourceDrafts(items, sourceDrafts),
    [items, sourceDrafts],
  );
  const previewIsCurrent = draftPreviewUrl !== null && previewKey === draftKey;
  const cellCount = item.gridRows * item.gridColumns;
  const selectedCellIndex =
    selectedCell.slotId === item.slotId ? selectedCell.cellIndex : 0;
  const shownPreviewUrl =
    previewMode === 'automatic' ? autoPreviewUrl : draftPreviewUrl;
  const sourceBatchEnabled = items.every(
    (candidate) => candidate.assetMode === 'virtual_source',
  );
  const isEditing = editing || sourceEditing;
  const hasPendingSourceDraft =
    sourceRedefining || modifiedSourceItems.size > 0;
  const showDraftReview =
    isEditing || hasPendingIndividualDraft || hasPendingSourceDraft;
  const sourceEditingProgress =
    sourceDrafts.size === 0
      ? 0
      : items.filter(
          (candidate) =>
            gridGeometrySourceDraft(sourceDrafts, candidate.slotId).length ===
            4,
        ).length;

  useEffect(() => {
    onEditingChange(
      isEditing || hasPendingIndividualDraft || hasPendingSourceDraft,
    );
  }, [
    hasPendingIndividualDraft,
    hasPendingSourceDraft,
    isEditing,
    onEditingChange,
  ]);

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
    for (const candidate of items) {
      const selected = candidate.slotId === item.slotId;
      const candidateAnalysisCorners = gridReviewAnalysisCorners(candidate);
      if (candidateAnalysisCorners !== null) {
        drawAnalysisOverlay(context, candidateAnalysisCorners, selected);
      }
      const storedCandidateDraft = gridGeometrySourceDraft(
        sourceDrafts,
        candidate.slotId,
      );
      const corners = selected
        ? (completeCorners ?? activeDraft)
        : storedCandidateDraft.length > 0
          ? storedCandidateDraft
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
    activeDraft,
    item.slotId,
    items,
    selectedCellIndex,
    sourceDrafts,
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

  const beginDirectEditing = useCallback(
    (slotId: string) => {
      if (sourceBatchEnabled) {
        setEditing(false);
        setSourceEditing(true);
      } else {
        setEditing(true);
      }
      onSelect(slotId);
      invalidatePreview();
    },
    [invalidatePreview, onSelect, sourceBatchEnabled],
  );

  const replaceSourceItemDraft = useCallback(
    (
      slotId: string,
      next: GridGeometryDraft,
      baseline: OperationalReviewGeometryCorners,
    ) => {
      setSourceDrafts((current) =>
        replaceGridGeometrySourceDraft(current, slotId, next),
      );
      setModifiedSourceItems((current) => {
        const updated = new Set(current);
        if (gridGeometryDraftsEqual(next, baseline)) {
          updated.delete(slotId);
        } else {
          updated.add(slotId);
        }
        return updated;
      });
      invalidatePreview();
    },
    [invalidatePreview],
  );

  const replaceActiveDraft = useCallback(
    (next: GridGeometryDraft) => {
      if (sourceEditing) {
        replaceSourceItemDraft(item.slotId, next, automaticCorners);
      } else {
        setDraft({ corners: next, slotId: item.slotId });
        invalidatePreview();
      }
    },
    [
      automaticCorners,
      invalidatePreview,
      item.slotId,
      replaceSourceItemDraft,
      sourceEditing,
    ],
  );

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
    const cornerThreshold = 44 / pointer.scale;
    if (!editing && !sourceEditing) {
      if (hasPendingIndividualDraft) return;
      const selected = gridGeometrySourceItemAtPoint(
        items,
        sourceDrafts,
        item.slotId,
        activeDraft,
        pointer.point,
        cornerThreshold,
      );
      if (selected === null) return;
      const selectedDraft =
        gridGeometrySourceDraft(sourceDrafts, selected.slotId).length > 0
          ? gridGeometrySourceDraft(sourceDrafts, selected.slotId)
          : gridReviewCorners(selected);
      const target = gridGeometryDragTarget(
        selectedDraft,
        pointer.point,
        cornerThreshold,
      );
      beginDirectEditing(selected.slotId);
      if (target !== null) {
        event.preventDefault();
        dragRef.current = {
          automaticCorners: gridReviewCorners(selected),
          draft: selectedDraft,
          imageHeight: selected.sourceHeight,
          imageWidth: selected.sourceWidth,
          lastPoint: pointer.point,
          slotId: selected.slotId,
          sourceWide: sourceBatchEnabled,
          target,
        };
        event.currentTarget.setPointerCapture(event.pointerId);
      }
      return;
    }
    if (sourceEditing && !sourceRedefining) {
      const selected = gridGeometrySourceItemAtPoint(
        items,
        sourceDrafts,
        item.slotId,
        activeDraft,
        pointer.point,
        cornerThreshold,
      );
      if (selected === null) return;
      const selectedDraft =
        gridGeometrySourceDraft(sourceDrafts, selected.slotId).length > 0
          ? gridGeometrySourceDraft(sourceDrafts, selected.slotId)
          : gridReviewCorners(selected);
      const target = gridGeometryDragTarget(
        selectedDraft,
        pointer.point,
        cornerThreshold,
      );
      if (target === null) return;
      if (selected.slotId !== item.slotId) {
        onSelect(selected.slotId);
      }
      event.preventDefault();
      dragRef.current = {
        automaticCorners: gridReviewCorners(selected),
        draft: selectedDraft,
        imageHeight: selected.sourceHeight,
        imageWidth: selected.sourceWidth,
        lastPoint: pointer.point,
        slotId: selected.slotId,
        sourceWide: true,
        target,
      };
      event.currentTarget.setPointerCapture(event.pointerId);
      return;
    }
    if (sourceEditing && sourceRedefining) {
      const selected = gridGeometrySourceItemAtPoint(
        items,
        sourceDrafts,
        item.slotId,
        activeDraft,
        pointer.point,
        cornerThreshold,
      );
      if (selected !== null && selected.slotId !== item.slotId) {
        onSelect(selected.slotId);
        return;
      }
    }
    event.preventDefault();
    if (activeDraft.length < 4) {
      const next = addGridGeometryPoint(
        activeDraft,
        pointer.point,
        item.sourceWidth,
        item.sourceHeight,
      );
      replaceActiveDraft(next);
      if (sourceEditing && next.length === 4) {
        const nextDrafts = replaceGridGeometrySourceDraft(
          sourceDrafts,
          item.slotId,
          next,
        );
        const following = nextIncompleteGridGeometrySourceItem(
          items,
          nextDrafts,
          item.slotId,
        );
        if (following !== null) onSelect(following.slotId);
      }
      return;
    }
    const target = gridGeometryDragTarget(
      activeDraft,
      pointer.point,
      cornerThreshold,
    );
    if (target === null) return;
    dragRef.current = {
      automaticCorners,
      draft: activeDraft,
      imageHeight: item.sourceHeight,
      imageWidth: item.sourceWidth,
      lastPoint: pointer.point,
      slotId: item.slotId,
      sourceWide: sourceEditing,
      target,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function pointerMove(event: ReactPointerEvent<HTMLCanvasElement>) {
    const active = dragRef.current;
    if (active === null) return;
    const pointer = sourcePoint(event);
    if (pointer === null) return;
    const next =
      active.target.kind === 'corner'
        ? moveGridGeometryCorner(
            active.draft,
            active.target.index,
            pointer.point,
            active.imageWidth,
            active.imageHeight,
          )
        : moveGridGeometry(
            active.draft,
            {
              x: pointer.point.x - active.lastPoint.x,
              y: pointer.point.y - active.lastPoint.y,
            },
            active.imageWidth,
            active.imageHeight,
          );
    if (active.sourceWide) {
      replaceSourceItemDraft(active.slotId, next, active.automaticCorners);
    } else {
      setDraft({ corners: next, slotId: active.slotId });
    }
    dragRef.current = { ...active, draft: next, lastPoint: pointer.point };
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
    const requestedPreviewKey = draftKey;
    const requestedCornersKey = JSON.stringify(completeCorners);
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
      JSON.stringify(automaticCorners) === requestedCornersKey
        ? automaticResult
        : await previewGridReviewGeometry(api, item, completeCorners);
    setLoadingPreview(false);
    if (!editedResult.ok) {
      setError(editedResult.error);
      return;
    }
    replacePreviewUrls(automaticResult.blob, editedResult.blob);
    setPreviewKey(requestedPreviewKey);
    setPreviewMode('edited');
  }

  async function save(): Promise<'invalid' | 'saved' | 'unchanged'> {
    if (saving) return 'invalid';
    if (
      (sourceEditing && !hasPendingSourceDraft) ||
      (editing && !hasPendingIndividualDraft)
    ) {
      return 'unchanged';
    }
    if (sourceEditing || hasPendingSourceDraft) {
      if (completeSourceDrafts === null) {
        setError('Wyznacz po cztery narożniki dla każdej planszy zdjęcia.');
        return 'invalid';
      }
      setSaving(true);
      setError('');
      const result = await saveGridReviewSourceGeometry(api, {
        cornersByReviewItemId: new Map(
          completeSourceDrafts.map((value) => [
            value.item.slotId,
            value.corners,
          ]),
        ),
        idempotencyKey: globalThis.crypto.randomUUID(),
        items,
      });
      setSaving(false);
      if (!result.ok) {
        setError(result.error);
        return 'invalid';
      }
      onSaved();
      return 'saved';
    }
    if (completeCorners === null || !previewIsCurrent) return 'invalid';
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
      return 'invalid';
    }
    onSaved();
    return 'saved';
  }

  useImperativeHandle(editorRef, () => ({ submitEdits: save }));

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
            {sourceBatchEnabled ? (
              <button
                className="secondaryButton"
                disabled={
                  loadingSource ||
                  saving ||
                  editing ||
                  hasPendingIndividualDraft
                }
                onClick={() => {
                  if (sourceEditing) {
                    setSourceEditing(false);
                  } else {
                    if (!sourceRedefining) {
                      setSourceDrafts(emptyGridGeometrySourceDrafts(items));
                      setModifiedSourceItems(new Set());
                      setSourceRedefining(true);
                    }
                    setSourceEditing(true);
                    const next = firstIncompleteGridGeometrySourceItem(
                      items,
                      sourceDrafts,
                    );
                    if (next !== null) {
                      onSelect(next.slotId);
                    }
                  }
                  invalidatePreview();
                }}
                type="button"
              >
                {sourceEditing
                  ? 'Wstrzymaj edycję plansz'
                  : sourceRedefining && sourceEditingProgress > 0
                    ? 'Kontynuuj plansze osobno'
                    : 'Wyznacz plansze osobno'}
              </button>
            ) : null}
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
        {item.localLatticeVersion ? (
          <p className="gridReviewMetadata">
            Dopasowanie lokalne: {item.localLatticeVersion} ·{' '}
            {item.localLatticeStatus === 'estimated'
              ? 'bezpieczna propozycja siatki'
              : `wymaga korekty${latticeReason ? ` · ${latticeReason}` : ''}`}
          </p>
        ) : null}
        {item.slotKind === 'deferred_geometry' ? (
          <p className="reviewerAccessError" role="status">
            Automat nie utworzył tej planszy. Slot #{item.positionIndex + 1} ·{' '}
            {item.sequenceNumber} jest obowiązkowy — popraw roboczy szablon i
            zapisz komplet plansz zdjęcia.
          </p>
        ) : null}
        {loadingSource ? <p>Wczytywanie obrazu…</p> : null}
        <div className="gridReviewSourceViewport">
          <canvas
            aria-label="Oryginalny obraz źródłowy z aktywnymi siatkami plansz"
            className={
              isEditing
                ? 'gridReviewCanvas isEditing'
                : 'gridReviewCanvas isSelecting'
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
        <p className="gridReviewCanvasHint">
          Kliknij siatkę na zdjęciu, aby od razu wybrać i edytować planszę.
          Poprawki wszystkich plansz pozostają w szkicu do zatwierdzenia całego
          zdjęcia.
        </p>
        <div
          className="gridReviewSlotList"
          role="list"
          aria-label="Aktywne plansze źródła"
        >
          {items.map((candidate) => (
            <button
              aria-pressed={candidate.slotId === item.slotId}
              className={
                candidate.slotId === item.slotId ? 'isSelected' : undefined
              }
              key={candidate.slotId}
              disabled={
                hasPendingIndividualDraft && candidate.slotId !== item.slotId
              }
              onClick={() => beginDirectEditing(candidate.slotId)}
              type="button"
            >
              #{candidate.positionIndex + 1} · {candidate.sequenceNumber} ·{' '}
              {candidate.state === 'approved'
                ? 'zatwierdzona'
                : candidate.slotKind === 'deferred_geometry'
                  ? 'obowiązkowa ręczna geometria'
                  : candidate.state === 'needs_correction'
                    ? 'do poprawy'
                    : 'do walidacji'}
            </button>
          ))}
        </div>
        {isEditing ? (
          <div className="gridReviewEditControls">
            <p>
              {sourceEditing && sourceRedefining
                ? activeDraft.length < 4
                  ? `Plansza ${item.positionIndex + 1}/${items.length} · kliknij narożnik ${GRID_CORNER_LABELS[activeDraft.length]} (${activeDraft.length + 1}/4).`
                  : `Plansza ${item.positionIndex + 1}/${items.length} jest gotowa. Wybierz kolejną albo popraw narożnik.`
                : activeDraft.length < 4
                  ? `Kliknij narożnik ${GRID_CORNER_LABELS[activeDraft.length]} (${activeDraft.length + 1}/4).`
                  : 'Przeciągnij narożnik albo środek wybranej siatki.'}
            </p>
            {sourceEditing ? (
              <p className="mutedText">
                {sourceRedefining
                  ? `Ręcznie ustawiono ${sourceEditingProgress}/${items.length} plansz w kolejności wierszami.`
                  : `Zmieniono ${modifiedSourceItems.size}/${items.length} plansz. Zatwierdź całe zdjęcie, aby zapisać komplet.`}
              </p>
            ) : null}
            <div>
              <button
                className="textButton"
                disabled={activeDraft.length === 0 || saving}
                onClick={() => {
                  replaceActiveDraft(activeDraft.slice(0, -1));
                }}
                type="button"
              >
                Cofnij punkt
              </button>
              <button
                className="textButton"
                disabled={saving}
                onClick={() => {
                  replaceActiveDraft(sourceRedefining ? [] : automaticCorners);
                }}
                type="button"
              >
                {sourceRedefining ? 'Wyczyść planszę' : 'Resetuj do automatu'}
              </button>
              <button
                className="textButton"
                disabled={saving}
                onClick={() => {
                  replaceActiveDraft([]);
                }}
                type="button"
              >
                Wskaż od nowa
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {showDraftReview ? (
        <section className="gridReviewPreviewPanel">
          <div className="gridReviewCanvasHeading">
            <div>
              <span className="eyebrow">A/B source-direct</span>
              <h3>
                {sourceEditing && sourceRedefining
                  ? `Ręczne plansze ${sourceEditingProgress}/${items.length}`
                  : `Podgląd ${cellCount} cropów wybranej planszy`}
              </h3>
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
                      onClick={() =>
                        setSelectedCell({
                          cellIndex: index,
                          slotId: item.slotId,
                        })
                      }
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
          <p className="mutedText">
            Zapis całego kompletu wykonasz przyciskiem „Zatwierdź całe zdjęcie”
            albo skrótem Enter / F.
          </p>
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
  const anchor = gridGeometryDraftAnchor(input.corners);
  context.save();
  // A newly selected source slot deliberately starts without any manual
  // points.  There is no outline or label to draw yet, but other slots must
  // remain visible and the editor must keep accepting the first click.
  if (anchor === null) {
    context.restore();
    return;
  }
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

function drawAnalysisOverlay(
  context: CanvasRenderingContext2D,
  corners: OperationalReviewGeometryCorners,
  selected: boolean,
) {
  context.save();
  context.beginPath();
  context.moveTo(corners[0].x, corners[0].y);
  corners.slice(1).forEach((point) => context.lineTo(point.x, point.y));
  context.closePath();
  context.lineWidth = Math.max(1, context.canvas.width / 1400);
  context.setLineDash([10, 8]);
  context.strokeStyle = selected
    ? 'rgba(203, 213, 225, 0.9)'
    : 'rgba(148, 163, 184, 0.48)';
  context.stroke();
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

'use client';

import type { OperationalImageReviewItemResponse } from '@game-predictor/admin-api-client';
import {
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  previewOperationalReviewGeometry,
  saveOperationalReviewGeometry,
  type OperationalReviewsClient,
} from './operational-review-actions';
import {
  buildOperationalReviewGeometryCommand,
  buildOperationalReviewGeometryPreviewCommand,
  operationalReviewAssetUrl,
  operationalReviewGeometryCorners,
  operationalReviewGeometryViewport,
  operationalReviewPointInGeometryViewport,
  operationalReviewPointInSourceImage,
  type OperationalReviewGeometryCorners,
  type OperationalReviewGeometryViewport,
} from './operational-review-state';

interface OperationalReviewGeometryEditorProps {
  readonly api: OperationalReviewsClient;
  readonly apiBaseUrl: string;
  readonly importJobId: string;
  readonly item: OperationalImageReviewItemResponse;
  readonly onSaved: () => void;
}

export function OperationalReviewGeometryEditor({
  api,
  apiBaseUrl,
  importJobId,
  item,
  onSaved,
}: OperationalReviewGeometryEditorProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sourceImageRef = useRef<HTMLImageElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const dragIndexRef = useRef<number | null>(null);
  const [open, setOpen] = useState(false);
  const [imageSize, setImageSize] = useState({ height: 0, width: 0 });
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
  const context = useMemo(
    () => ({ gameId: item.gameId, importJobId }),
    [importJobId, item.gameId],
  );
  const sourceUrl = operationalReviewAssetUrl(
    apiBaseUrl,
    context,
    item.id,
    'source',
  );
  const cornersKey = corners === null ? '' : JSON.stringify(corners);
  const previewIsCurrent = previewUrl !== null && previewKey === cornersKey;

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
    const visibleCorners = corners.map((point) =>
      operationalReviewPointInGeometryViewport(point, viewport),
    );
    context2d.lineWidth = Math.max(2, canvas.width / 500);
    context2d.strokeStyle = '#f4d35e';
    for (let column = 0; column <= 5; column += 1) {
      const ratio = column / 5;
      const top = interpolate(visibleCorners[0], visibleCorners[1], ratio);
      const bottom = interpolate(visibleCorners[3], visibleCorners[2], ratio);
      drawLine(context2d, top, bottom);
    }
    for (let row = 0; row <= 3; row += 1) {
      const ratio = row / 3;
      const left = interpolate(visibleCorners[0], visibleCorners[3], ratio);
      const right = interpolate(visibleCorners[1], visibleCorners[2], ratio);
      drawLine(context2d, left, right);
    }
    visibleCorners.forEach((point, index) => {
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

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const image = new window.Image();
    image.crossOrigin = 'anonymous';
    image.onload = () => {
      sourceImageRef.current = image;
      setImageSize({ height: image.naturalHeight, width: image.naturalWidth });
      const initialCorners = operationalReviewGeometryCorners(
        item,
        image.naturalWidth,
        image.naturalHeight,
      );
      setCorners(initialCorners);
      setViewport(
        operationalReviewGeometryViewport(
          initialCorners,
          image.naturalWidth,
          image.naturalHeight,
        ),
      );
      setLoadingSource(false);
    };
    image.onerror = () => {
      setLoadingSource(false);
      setError('Nie udało się wczytać oryginalnego obrazu.');
    };
    image.src = sourceUrl;
    return () => {
      image.onload = null;
      image.onerror = null;
    };
  }, [item, open, sourceUrl]);

  useEffect(
    () => () => {
      if (previewUrlRef.current !== null) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
    },
    [],
  );

  const refreshPreview = useCallback(async () => {
    if (corners === null || loadingPreview || saving) return;
    setLoadingPreview(true);
    setError('');
    const requestedKey = JSON.stringify(corners);
    const result = await previewOperationalReviewGeometry(api, {
      command: buildOperationalReviewGeometryPreviewCommand(item, corners),
      gameId: item.gameId,
      importJobId,
      reviewItemId: item.id,
    });
    setLoadingPreview(false);
    if (!result.ok) {
      setError(
        result.isRevisionConflict
          ? `${result.error} Zamknij edytor i przeładuj planszę.`
          : result.error,
      );
      return;
    }
    if (previewUrlRef.current !== null) {
      URL.revokeObjectURL(previewUrlRef.current);
    }
    const url = URL.createObjectURL(result.blob);
    previewUrlRef.current = url;
    setPreviewUrl(url);
    setPreviewKey(requestedKey);
  }, [api, corners, importJobId, item, loadingPreview, saving]);

  async function saveGeometry() {
    if (corners === null || !previewIsCurrent || saving) return;
    setSaving(true);
    setError('');
    const result = await saveOperationalReviewGeometry(api, {
      command: buildOperationalReviewGeometryCommand(
        item,
        corners,
        globalThis.crypto.randomUUID(),
      ),
      gameId: item.gameId,
      importJobId,
      reviewItemId: item.id,
    });
    setSaving(false);
    if (!result.ok) {
      setError(
        result.isRevisionConflict
          ? `${result.error} Przeładuj planszę przed kolejną korektą.`
          : result.error,
      );
      return;
    }
    setOpen(false);
    onSaved();
  }

  function updateDraggedCorner(event: ReactPointerEvent<HTMLCanvasElement>) {
    const index = dragIndexRef.current;
    const canvas = canvasRef.current;
    if (
      index === null ||
      canvas === null ||
      corners === null ||
      viewport === null ||
      imageSize.width === 0
    ) {
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const point = operationalReviewPointInSourceImage(
      {
        x: ((event.clientX - rect.left) / rect.width) * viewport.width,
        y: ((event.clientY - rect.top) / rect.height) * viewport.height,
      },
      viewport,
      imageSize.width,
      imageSize.height,
    );
    const next = [...corners] as [
      (typeof corners)[0],
      (typeof corners)[1],
      (typeof corners)[2],
      (typeof corners)[3],
    ];
    next[index] = point;
    setCorners(next);
  }

  function startDragging(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (corners === null || viewport === null) return;
    const canvas = event.currentTarget;
    const rect = canvas.getBoundingClientRect();
    const point = {
      x: ((event.clientX - rect.left) / rect.width) * canvas.width,
      y: ((event.clientY - rect.top) / rect.height) * canvas.height,
    };
    const threshold = (28 / rect.width) * canvas.width;
    const candidate = corners
      .map((corner) =>
        operationalReviewPointInGeometryViewport(corner, viewport),
      )
      .map((corner, index) => ({
        distance: Math.hypot(corner.x - point.x, corner.y - point.y),
        index,
      }))
      .sort((left, right) => left.distance - right.distance)[0];
    if (candidate === undefined || candidate.distance > threshold) return;
    dragIndexRef.current = candidate.index;
    canvas.setPointerCapture(event.pointerId);
  }

  function closeEditor() {
    if (saving) return;
    dragIndexRef.current = null;
    setOpen(false);
    setCorners(null);
    setViewport(null);
    setError('');
  }

  function openEditor() {
    if (previewUrlRef.current !== null) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
    setLoadingSource(true);
    setError('');
    setPreviewUrl(null);
    setPreviewKey('');
    setViewport(null);
    setOpen(true);
  }

  return (
    <>
      <button
        className="textButton operationalReviewGeometryOpen"
        onClick={openEditor}
        type="button"
      >
        Edytuj siatkę
      </button>
      <dialog
        aria-labelledby="operational-review-geometry-title"
        className="operationalReviewGeometryDialog"
        onCancel={(event) => {
          event.preventDefault();
          closeEditor();
        }}
        ref={dialogRef}
      >
        <header>
          <div>
            <span className="eyebrow">Rewizja geometrii</span>
            <h2 id="operational-review-geometry-title">
              Ustaw cztery narożniki planszy
            </h2>
            <p>
              Przesuwaj narożniki pojedynczego layoutu: lewy górny, prawy górny,
              prawy dolny, lewy dolny.
            </p>
          </div>
          <button
            aria-label="Zamknij edytor siatki"
            disabled={saving}
            onClick={closeEditor}
            type="button"
          >
            ×
          </button>
        </header>

        <div className="operationalReviewGeometryBody">
          <section>
            <h3>Pojedynczy layout z marginesem i siatką 5 × 3</h3>
            {loadingSource ? <p>Wczytywanie obrazu…</p> : null}
            <canvas
              aria-label="Pojedynczy layout z edytowalną siatką"
              className="operationalReviewGeometryCanvas"
              onPointerCancel={() => {
                dragIndexRef.current = null;
              }}
              onPointerDown={startDragging}
              onPointerMove={updateDraggedCorner}
              onPointerUp={() => {
                dragIndexRef.current = null;
              }}
              ref={canvasRef}
              style={{
                aspectRatio:
                  viewport !== null
                    ? `${viewport.width} / ${viewport.height}`
                    : undefined,
              }}
            />
          </section>

          <section className="operationalReviewGeometryPreview">
            <div>
              <h3>Wyprostowana plansza</h3>
              <button
                className="secondaryButton"
                disabled={corners === null || loadingPreview || saving}
                onClick={() => void refreshPreview()}
                type="button"
              >
                {loadingPreview ? 'Generowanie…' : 'Aktualizuj podgląd'}
              </button>
            </div>
            {previewUrl === null ? (
              <p className="operationalReviewGeometryPlaceholder">
                Wygeneruj podgląd przed zapisem.
              </p>
            ) : (
              <>
                {/* This is a checksum-bound local Blob URL, not a public image asset. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img alt="Wyprostowana plansza po korekcie" src={previewUrl} />
                <div
                  aria-label="Podgląd 15 nowych cropów"
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
                          backgroundPosition: `${((column * 100 + 5) / 410) * 100}% ${((row * 100 + 5) / 210) * 100}%`,
                          backgroundSize: '555.556% 333.333%',
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
        <footer>
          <span>
            Zapis utworzy nową rewizję i ponownie otworzy wybór symboli.
          </span>
          <div>
            <button
              className="secondaryButton"
              disabled={saving}
              onClick={closeEditor}
              type="button"
            >
              Anuluj
            </button>
            <button
              className="primaryButton"
              disabled={!previewIsCurrent || saving}
              onClick={() => void saveGeometry()}
              type="button"
            >
              {saving ? 'Zapisywanie…' : 'Zapisz nową rewizję'}
            </button>
          </div>
        </footer>
      </dialog>
    </>
  );
}

function interpolate(
  start: { readonly x: number; readonly y: number },
  end: { readonly x: number; readonly y: number },
  ratio: number,
) {
  return {
    x: start.x + (end.x - start.x) * ratio,
    y: start.y + (end.y - start.y) * ratio,
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

'use client';

import type { SymbolCellReviewListItemResponse } from '@game-predictor/admin-api-client';
import { useEffect, useRef, useState } from 'react';
import {
  loadSymbolReviewSourceContext,
  type SymbolReviewSourceClient,
} from './symbol-review-source-context';

export function SymbolReviewSourceModal({
  api,
  gameId,
  item,
  onClose,
}: {
  readonly api: SymbolReviewSourceClient;
  readonly gameId: string;
  readonly item: SymbolCellReviewListItemResponse;
  readonly onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    url: string;
    cells: readonly (readonly { x: number; y: number }[])[];
  } | null>(null);
  const [size, setSize] = useState<{ width: number; height: number } | null>(
    null,
  );
  const [error, setError] = useState('');
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    queueMicrotask(async () => {
      if (cancelled) return;
      setState(null);
      setError('');
      setSize(null);
      const result = await loadSymbolReviewSourceContext(api, gameId, item);
      if (cancelled) return;
      if (!result.ok) {
        setError(result.error);
        return;
      }
      objectUrl = URL.createObjectURL(result.blob);
      setState({ url: objectUrl, cells: result.cells });
    });
    return () => {
      cancelled = true;
      if (objectUrl !== null) URL.revokeObjectURL(objectUrl);
    };
  }, [api, gameId, item, attempt]);
  const [zoom, setZoom] = useState(100);
  const points = state?.cells.flat() ?? [];
  const minX = Math.min(0, ...points.map((p) => p.x));
  const minY = Math.min(0, ...points.map((p) => p.y));
  const maxX = Math.max(size?.width ?? 1, ...points.map((p) => p.x));
  const maxY = Math.max(size?.height ?? 1, ...points.map((p) => p.y));
  return (
    <dialog
      ref={dialog}
      aria-labelledby="symbol-source-title"
      className="symbolImagePickerDialog"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="symbolImagePickerCard">
        <header className="symbolImagePickerHeader">
          <div>
            <h2 id="symbol-source-title">
              Źródło · plansza {item.sequenceNumber}
            </h2>
            <p>
              Pole {item.cellIndex + 1} · wiersz {item.rowIndex + 1}, kolumna{' '}
              {item.columnIndex + 1}. Zaznaczona pozycja na zapisanej siatce.
            </p>
          </div>
          <button className="secondaryButton" onClick={onClose} type="button">
            Zamknij podgląd źródła
          </button>
        </header>
        {error ? (
          <div role="alert">
            <p>{error}</p>
            <button
              className="secondaryButton"
              onClick={() => setAttempt((value) => value + 1)}
              type="button"
            >
              Spróbuj ponownie
            </button>
          </div>
        ) : null}
        {!error && (state === null || size === null) ? (
          <p role="status">Wczytywanie zdjęcia źródłowego…</p>
        ) : null}
        {state !== null && !error ? (
          <>
            {/* The same blob supplies native dimensions and the SVG source image. */}
            {/* eslint-disable-next-line @next/next/no-img-element -- checksum-verified local blob */}
            <img
              alt=""
              src={state.url}
              hidden
              onLoad={(event) =>
                setSize({
                  width: event.currentTarget.naturalWidth,
                  height: event.currentTarget.naturalHeight,
                })
              }
              onError={() => setError('Nie można odczytać obrazu źródłowego.')}
            />
            {size !== null ? (
              <>
                <label className="symbolImagePickerZoom">
                  Przybliżenie
                  <input
                    max={700}
                    min={100}
                    onChange={(event) => setZoom(Number(event.target.value))}
                    step={10}
                    type="range"
                    value={zoom}
                  />
                  <span>{zoom}%</span>
                </label>
                <div
                  style={{
                    overflow: 'auto',
                    maxHeight: '65vh',
                    background: '#14202d',
                    borderRadius: 10,
                  }}
                >
                  <svg
                    role="img"
                    aria-label={`Zdjęcie z siatką planszy ${item.sequenceNumber}, wyróżnione pole ${item.cellIndex + 1}`}
                    viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`}
                    style={{
                      width: `${zoom}%`,
                      height: 'auto',
                      display: 'block',
                      background: '#14202d',
                    }}
                  >
                    <image
                      href={state.url}
                      x="0"
                      y="0"
                      width={size.width}
                      height={size.height}
                    />
                    {state.cells.map((cell, index) => (
                      <polygon
                        key={index}
                        points={cell.map((p) => `${p.x},${p.y}`).join(' ')}
                        fill={index === item.cellIndex ? '#ffb30055' : 'none'}
                        stroke={
                          index === item.cellIndex ? '#ffb300' : '#00d4ff'
                        }
                        strokeWidth={1}
                        vectorEffect="non-scaling-stroke"
                      />
                    ))}
                  </svg>
                </div>
              </>
            ) : null}
          </>
        ) : null}
        <p>
          Obszar poza zdjęciem nie zawiera pikseli. Podgląd nie zmienia
          geometrii ani decyzji.
        </p>
      </div>
    </dialog>
  );
}

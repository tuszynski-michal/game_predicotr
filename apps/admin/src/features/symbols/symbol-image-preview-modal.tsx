'use client';

import type { SymbolResponse } from '@game-predictor/admin-api-client';
import Image from 'next/image';
import { useEffect, useMemo, useRef, useState } from 'react';

interface SymbolImagePreviewModalProps {
  readonly imageUrl: string;
  readonly onClose: () => void;
  readonly symbol: SymbolResponse;
}

export function SymbolImagePreviewModal({
  imageUrl,
  onClose,
  symbol,
}: SymbolImagePreviewModalProps) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previewUrl = useMemo(() => {
    const separator = imageUrl.includes('?') ? '&' : '?';
    return `${imageUrl}${separator}preview=${attempt}`;
  }, [attempt, imageUrl]);

  useEffect(() => {
    closeButtonRef.current?.focus();
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  function retry() {
    setState('loading');
    setAttempt((current) => current + 1);
  }

  return (
    <dialog
      aria-labelledby="symbol-image-preview-title"
      aria-modal="true"
      className="paylineDialog"
      data-testid="symbol-image-preview"
      open
    >
      <div className="paylineDialogCard symbolImagePreviewCard">
        <header className="paylineDialogHeader">
          <div>
            <p className="eyebrow">Grafika referencyjna · {symbol.code}</p>
            <h2 id="symbol-image-preview-title">{symbol.name}</h2>
          </div>
          <button
            aria-label="Zamknij podgląd grafiki"
            className="iconButton"
            onClick={onClose}
            ref={closeButtonRef}
            type="button"
          >
            ×
          </button>
        </header>

        <div className="symbolImagePreviewFrame">
          {state === 'loading' ? (
            <div className="symbolImagePreviewState" role="status">
              <span aria-hidden="true" className="loadingMark" />
              <span>Wczytywanie grafiki…</span>
            </div>
          ) : null}
          {state !== 'error' ? (
            <Image
              alt={`Grafika referencyjna symbolu ${symbol.name}`}
              className={state === 'ready' ? 'isReady' : ''}
              height={640}
              onError={() => setState('error')}
              onLoad={() => setState('ready')}
              src={previewUrl}
              unoptimized
              width={640}
            />
          ) : (
            <div className="symbolImagePreviewState" role="alert">
              <strong>Nie udało się wczytać grafiki.</strong>
              <span>
                Plik mógł zostać przeniesiony albo nie odpowiada zapisanej sumie
                kontrolnej.
              </span>
              <button className="secondaryButton" onClick={retry} type="button">
                Spróbuj ponownie
              </button>
            </div>
          )}
        </div>

        <div className="symbolImagePreviewMetadata">
          <span>Zapisana ścieżka</span>
          <code>{symbol.imagePath}</code>
        </div>

        <footer className="symbolImagePreviewActions">
          <button className="primaryButton" onClick={onClose} type="button">
            Zamknij
          </button>
        </footer>
      </div>
    </dialog>
  );
}

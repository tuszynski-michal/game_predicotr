'use client';

import type {
  SymbolImageCandidateResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import Image from 'next/image';
import { useCallback, useEffect, useRef, useState } from 'react';

import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import type { SymbolsClient } from '@/features/symbols/symbol-catalog-actions';
import { appendUniqueCandidates } from '@/features/symbols/symbol-image-picker-state';

interface SymbolImagePickerModalProps {
  readonly api: SymbolsClient;
  readonly gameId: string;
  readonly onClose: () => void;
  readonly onSelected: (symbol: SymbolResponse) => void;
  readonly symbol: SymbolResponse;
}

export function SymbolImagePickerModal({
  api,
  gameId,
  onClose,
  onSelected,
  symbol,
}: SymbolImagePickerModalProps) {
  const [candidates, setCandidates] = useState<
    readonly SymbolImageCandidateResponse[]
  >([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selectedObservationId, setSelectedObservationId] = useState<
    string | null
  >(null);
  const [name, setName] = useState(symbol.name);
  const [loading, setLoading] = useState<'initial' | 'more' | null>('initial');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const requestId = useRef(0);

  const loadCandidates = useCallback(
    async (cursor?: string) => {
      const currentRequest = ++requestId.current;
      setLoading(cursor === undefined ? 'initial' : 'more');
      setError('');
      try {
        const result = await api.listSymbolImageCandidates(
          gameId,
          symbol.id,
          cursor,
        );
        if (currentRequest !== requestId.current) return;
        if (result.error !== undefined || result.data === undefined) {
          setError(
            apiErrorMessage(
              result.error,
              'Nie udało się pobrać propozycji grafiki.',
            ),
          );
          return;
        }
        setCandidates((current) =>
          appendUniqueCandidates(
            cursor === undefined ? [] : current,
            result.data.items,
          ),
        );
        setNextCursor(result.data.nextCursor);
      } catch {
        if (currentRequest === requestId.current) {
          setError('Połączenie z lokalnym Admin API zostało przerwane.');
        }
      } finally {
        if (currentRequest === requestId.current) setLoading(null);
      }
    },
    [api, gameId, symbol.id],
  );

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void loadCandidates();
    });
    return () => {
      cancelled = true;
      requestId.current += 1;
    };
  }, [loadCandidates]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !saving) onClose();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose, saving]);

  async function saveSelection() {
    if (selectedObservationId === null || saving || !name.trim()) return;
    setSaving(true);
    setError('');
    try {
      const result = await api.selectSymbolImageCandidate(
        gameId,
        symbol.id,
        selectedObservationId,
        { name: name.trim() },
      );
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się zapisać grafiki reprezentatywnej.',
          ),
        );
        return;
      }
      onSelected(result.data);
    } catch {
      setError(
        'Połączenie z lokalnym Admin API zostało przerwane podczas zapisu.',
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <dialog
      aria-labelledby="symbol-image-picker-title"
      aria-modal="true"
      className="paylineDialog"
      data-testid="symbol-image-picker"
      open
    >
      <div className="paylineDialogCard symbolImagePickerCard">
        <header className="paylineDialogHeader">
          <div>
            <p className="eyebrow">
              Symbol {symbol.mobileCode} · {symbol.code}
            </p>
            <h2 id="symbol-image-picker-title">Wybierz grafikę symbolu</h2>
          </div>
          <button
            aria-label="Zamknij wybór grafiki"
            className="iconButton"
            disabled={saving}
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>

        <label className="symbolImageNameField">
          <span>Nazwa symbolu</span>
          <input
            disabled={saving}
            maxLength={200}
            onChange={(event) => setName(event.currentTarget.value)}
            value={name}
          />
          <small>
            Kod {symbol.code} i mobileCode {symbol.mobileCode} pozostaną bez
            zmian.
          </small>
        </label>

        {loading === 'initial' ? (
          <div className="modalState">
            <span aria-hidden="true" className="loadingMark" />
            <div>
              <h3>Wczytywanie grafik</h3>
              <p>Pobieram pierwszych 10 rzeczywistych cropów tej grupy.</p>
            </div>
          </div>
        ) : null}

        {loading !== 'initial' && candidates.length === 0 && !error ? (
          <div className="modalState">
            <span aria-hidden="true" className="stateIcon">
              0
            </span>
            <div>
              <h3>Brak kandydatów</h3>
              <p>Ten symbol nie ma dostępnych cropów do wyboru.</p>
            </div>
          </div>
        ) : null}

        {candidates.length > 0 ? (
          <div
            aria-label="Kandydaci na grafikę reprezentatywną"
            className="symbolImageCandidateGrid"
          >
            {candidates.map((candidate) => {
              const selected =
                selectedObservationId === candidate.observationId;
              return (
                <button
                  aria-pressed={selected}
                  className={
                    selected
                      ? 'symbolImageCandidate symbolImageCandidateSelected'
                      : 'symbolImageCandidate'
                  }
                  disabled={saving}
                  key={candidate.observationId}
                  onClick={() =>
                    setSelectedObservationId(candidate.observationId)
                  }
                  type="button"
                >
                  <Image
                    alt={`Kandydat dla ${symbol.name}`}
                    height={160}
                    src={api.symbolImageCandidateAssetUrl(
                      gameId,
                      symbol.id,
                      candidate.observationId,
                    )}
                    unoptimized
                    width={160}
                  />
                  <span>{Math.round(candidate.confidence * 100)}%</span>
                </button>
              );
            })}
          </div>
        ) : null}

        {error ? (
          <div className="symbolImagePickerError" role="alert">
            <p>{error}</p>
            {candidates.length === 0 ? (
              <button
                className="secondaryButton"
                disabled={loading !== null}
                onClick={() => void loadCandidates()}
                type="button"
              >
                Spróbuj ponownie
              </button>
            ) : null}
          </div>
        ) : null}

        <footer className="symbolImagePickerActions">
          {nextCursor ? (
            <button
              className="secondaryButton"
              disabled={loading !== null || saving}
              onClick={() => void loadCandidates(nextCursor)}
              type="button"
            >
              {loading === 'more' ? 'Wczytywanie…' : 'Załaduj kolejne grafiki'}
            </button>
          ) : (
            <span className="symbolImagePickerEnd">
              {candidates.length > 0
                ? 'Wyświetlono wszystkie kandydatury.'
                : ''}
            </span>
          )}
          <button
            className="primaryButton"
            disabled={selectedObservationId === null || saving || !name.trim()}
            onClick={() => void saveSelection()}
            type="button"
          >
            {saving ? 'Zapisywanie…' : 'Zapisz grafikę i nazwę'}
          </button>
        </footer>
      </div>
    </dialog>
  );
}

'use client';

import type {
  ApprovedSymbolReferenceCandidateResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import Image from 'next/image';
import { useCallback, useEffect, useRef, useState } from 'react';

import { apiErrorMessage } from '@/features/catalog/catalog-api-error';

import type { SymbolsClient } from './symbol-catalog-actions';
import {
  appendSymbolReferenceCandidatePage,
  canGoToNextSymbolReferencePage,
  canGoToPreviousSymbolReferencePage,
  currentSymbolReferenceCandidatePage,
  type SymbolReferenceCandidatePage,
} from './symbol-image-picker-state';

type LoadState = 'loading' | 'ready' | 'error';

interface SymbolImagePickerModalProps {
  readonly api: Pick<
    SymbolsClient,
    | 'approvedSymbolReferenceCandidateAssetUrl'
    | 'listApprovedSymbolReferenceCandidates'
    | 'selectApprovedSymbolReferenceCandidate'
  >;
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
  const [pages, setPages] = useState<readonly SymbolReferenceCandidatePage[]>(
    [],
  );
  const [pageIndex, setPageIndex] = useState(0);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [message, setMessage] = useState('');
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [unavailableAssetIds, setUnavailableAssetIds] = useState<
    ReadonlySet<string>
  >(new Set());
  const requestId = useRef(0);

  const loadInitial = useCallback(async () => {
    const currentRequestId = ++requestId.current;
    setLoadState('loading');
    setMessage('');
    setUnavailableAssetIds(new Set());
    try {
      const result = await api.listApprovedSymbolReferenceCandidates(
        gameId,
        symbol.id,
      );
      if (currentRequestId !== requestId.current) return;
      if (result.error !== undefined || result.data === undefined) {
        setMessage(
          apiErrorMessage(
            result.error,
            'Nie udało się pobrać zatwierdzonych propozycji grafiki.',
          ),
        );
        setLoadState('error');
        return;
      }
      setPages([result.data]);
      setPageIndex(0);
      setLoadState('ready');
    } catch {
      if (currentRequestId === requestId.current) {
        setMessage(
          'Połączenie z lokalnym Admin API zostało przerwane podczas pobierania propozycji.',
        );
        setLoadState('error');
      }
    }
  }, [api, gameId, symbol.id]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void loadInitial();
    });
    return () => {
      cancelled = true;
      requestId.current += 1;
    };
  }, [loadInitial]);

  const currentPage = currentSymbolReferenceCandidatePage(pages, pageIndex);
  const candidates = currentPage?.items ?? [];
  const canGoPrevious = canGoToPreviousSymbolReferencePage(pageIndex);
  const canGoNext = canGoToNextSymbolReferencePage(pages, pageIndex);

  async function nextPage() {
    if (selectingId !== null || !canGoNext) return;
    if (pageIndex < pages.length - 1) {
      setPageIndex((current) => current + 1);
      return;
    }
    const afterCursor = currentPage?.nextCursor;
    if (afterCursor === null || afterCursor === undefined) return;

    const currentRequestId = ++requestId.current;
    setLoadState('loading');
    setMessage('');
    try {
      const result = await api.listApprovedSymbolReferenceCandidates(
        gameId,
        symbol.id,
        afterCursor,
      );
      if (currentRequestId !== requestId.current) return;
      if (result.error !== undefined || result.data === undefined) {
        setMessage(
          apiErrorMessage(
            result.error,
            'Nie udało się pobrać kolejnej strony propozycji.',
          ),
        );
        setLoadState('error');
        return;
      }
      setPages((current) =>
        appendSymbolReferenceCandidatePage(current, result.data),
      );
      setPageIndex((current) => current + 1);
      setLoadState('ready');
    } catch {
      if (currentRequestId === requestId.current) {
        setMessage(
          'Połączenie z lokalnym Admin API zostało przerwane podczas pobierania kolejnej strony.',
        );
        setLoadState('error');
      }
    }
  }

  async function selectCandidate(
    candidate: ApprovedSymbolReferenceCandidateResponse,
  ) {
    if (selectingId !== null) return;
    setSelectingId(candidate.observationId);
    setMessage('');
    try {
      const result = await api.selectApprovedSymbolReferenceCandidate(
        gameId,
        symbol.id,
        candidate.observationId,
        {
          expectedChecksumSha256: candidate.cropChecksumSha256,
          selectedBy: 'admin-local',
        },
      );
      if (result.error !== undefined || result.data === undefined) {
        const error = apiErrorMessage(
          result.error,
          'Nie udało się zapisać wybranej grafiki symbolu.',
        );
        setMessage(error);
        if (isStaleCandidateError(result.error)) {
          void loadInitial();
        }
        return;
      }
      onSelected(result.data);
    } catch {
      setMessage(
        'Połączenie z lokalnym Admin API zostało przerwane. Wybór nie został potwierdzony.',
      );
    } finally {
      setSelectingId(null);
    }
  }

  return (
    <dialog
      aria-labelledby="symbol-image-picker-title"
      aria-modal="true"
      className="symbolImagePickerDialog"
      data-testid="symbol-image-picker"
      open
    >
      <div className="symbolImagePickerCard">
        <header className="symbolImagePickerHeader">
          <div>
            <p className="eyebrow">Zatwierdzone cropy</p>
            <h2 id="symbol-image-picker-title">
              Wybierz grafikę: {symbol.name}
            </h2>
            <p>
              Pokazujemy wyłącznie cropy z plansz zatwierdzonych przez
              człowieka.
            </p>
          </div>
          <button
            aria-label="Zamknij wybór grafiki"
            className="iconButton"
            disabled={selectingId !== null}
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>

        {message ? (
          <p
            className={
              loadState === 'error'
                ? 'feedbackBanner feedbackBannerError'
                : 'formError'
            }
            role="alert"
          >
            {message}
          </p>
        ) : null}

        {loadState === 'loading' && pages.length === 0 ? (
          <p className="symbolImagePickerLoading" role="status">
            Wczytywanie zatwierdzonych cropów…
          </p>
        ) : null}

        {loadState === 'ready' && candidates.length === 0 ? (
          <div className="symbolImagePickerEmpty">
            <span aria-hidden="true">?</span>
            <p>Najpierw zatwierdź planszę zawierającą ten symbol.</p>
          </div>
        ) : null}

        {candidates.length > 0 ? (
          <div className="symbolImageCandidateGrid">
            {candidates.map((candidate) => {
              const unavailable = unavailableAssetIds.has(
                candidate.observationId,
              );
              const selecting = selectingId === candidate.observationId;
              return (
                <button
                  aria-busy={selecting}
                  className="symbolImageCandidate"
                  disabled={selectingId !== null}
                  key={candidate.observationId}
                  onClick={() => void selectCandidate(candidate)}
                  type="button"
                >
                  <span className="symbolImageCandidatePreview">
                    {unavailable ? (
                      <span className="symbolImageCandidateUnavailable">
                        Plik niedostępny
                      </span>
                    ) : (
                      <Image
                        alt={`Crop symbolu ${symbol.name}, sekwencja ${candidate.sequenceNumber}, pozycja ${candidate.cellIndex + 1}`}
                        height={128}
                        onError={() => {
                          setUnavailableAssetIds((current) =>
                            new Set(current).add(candidate.observationId),
                          );
                        }}
                        src={api.approvedSymbolReferenceCandidateAssetUrl(
                          gameId,
                          symbol.id,
                          candidate.observationId,
                        )}
                        unoptimized
                        width={128}
                      />
                    )}
                  </span>
                  <span>
                    Sekwencja {candidate.sequenceNumber} · pole{' '}
                    {candidate.cellIndex + 1}
                  </span>
                  <small>
                    {candidate.geometryRevision > 0
                      ? 'Ręcznie poprawiona geometria'
                      : 'Zatwierdzona plansza'}
                  </small>
                  {selecting ? <strong>Zapisywanie…</strong> : null}
                </button>
              );
            })}
          </div>
        ) : null}

        <footer className="symbolImagePickerFooter">
          <p>
            Strona {pages.length === 0 ? 0 : pageIndex + 1}
            {loadState === 'loading' && pages.length > 0
              ? ' · pobieranie kolejnej…'
              : ''}
          </p>
          <div className="rowActions">
            <button
              className="secondaryButton"
              disabled={!canGoPrevious || selectingId !== null}
              onClick={() => setPageIndex((current) => current - 1)}
              type="button"
            >
              Poprzednia
            </button>
            <button
              className="secondaryButton"
              disabled={
                !canGoNext || selectingId !== null || loadState === 'loading'
              }
              onClick={() => void nextPage()}
              type="button"
            >
              Następna
            </button>
            <button
              className="textButton"
              disabled={selectingId !== null || loadState === 'loading'}
              onClick={() => void loadInitial()}
              type="button"
            >
              Odśwież propozycje
            </button>
          </div>
        </footer>
      </div>
    </dialog>
  );
}

function isStaleCandidateError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    error.code === 'SYMBOL_REFERENCE_CANDIDATE_STALE'
  );
}

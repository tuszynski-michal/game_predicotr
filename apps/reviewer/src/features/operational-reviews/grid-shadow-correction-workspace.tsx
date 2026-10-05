'use client';

import type {
  AdminApiClient,
  GridShadowResultResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { apiErrorMessage } from '../catalog/catalog-api-error';

import {
  BoardGeometryCorrectionEditor,
  type CorrectionSymbol,
} from './deferred-board-cell-geometry-editor';
import {
  type GridShadowCorrectionClient,
  gridShadowBoardGeometryTarget,
} from './grid-shadow-correction-target';
import { buildOperationalReviewSymbolShortcuts } from './operational-review-state';

type Client = GridShadowCorrectionClient & Pick<AdminApiClient, 'listSymbols'>;

export function GridShadowCorrectionWorkspace({
  api,
  apiBaseUrl,
  gameId,
  resultId,
  positionIndex,
}: {
  readonly api: Client;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly resultId: string;
  readonly positionIndex: number;
}) {
  const [result, setResult] = useState<GridShadowResultResponse | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [symbols, setSymbols] = useState<readonly CorrectionSymbol[]>([]);
  const mounted = useRef(false);
  const request = useRef(0);
  const invalidatePendingRequests = useCallback(() => {
    mounted.current = false;
    request.current++;
  }, []);
  const load = useCallback(async () => {
    const current = ++request.current;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const read = await api.getGridShadowResult(gameId, resultId);
      if (!mounted.current || current !== request.current) return;
      if (read.error !== undefined || !read.data)
        setError(
          apiErrorMessage(read.error, 'Nie udało się wczytać propozycji.'),
        );
      else setResult(read.data);
    } catch {
      if (mounted.current && current === request.current)
        setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      if (mounted.current && current === request.current) setLoading(false);
    }
  }, [api, gameId, resultId]);

  useEffect(() => {
    mounted.current = true;
    let active = true;
    queueMicrotask(() => void load());
    void api
      .listSymbols(gameId)
      .then((read) => {
        if (!active) return;
        if (read.error !== undefined || !read.data) {
          setError(
            apiErrorMessage(
              read.error,
              'Nie udało się pobrać katalogu symboli.',
            ),
          );
          return;
        }
        setSymbols(
          buildOperationalReviewSymbolShortcuts(read.data, {
            reservedKeys: ['9'],
          }).map(({ key, symbol }) => ({
            id: symbol.id,
            label: symbol.namePl ?? symbol.name,
            shortcut: key,
          })),
        );
      })
      .catch(() => {
        if (active) setError('Nie udało się pobrać katalogu symboli.');
      });
    return () => {
      active = false;
      invalidatePendingRequests();
    };
  }, [api, gameId, load, invalidatePendingRequests]);

  const target = useMemo(() => {
    const slot = result?.output.slots.find(
      (entry) => entry.positionIndex === positionIndex,
    );
    return result && slot
      ? gridShadowBoardGeometryTarget({ api, apiBaseUrl, result, slot })
      : null;
  }, [api, apiBaseUrl, result, positionIndex]);

  return (
    <section
      className="deferredGeometryQueue"
      aria-label="Korekta propozycji sieci"
    >
      <h2>Korekta propozycji sieci</h2>
      <p>
        Jedna plansza. Zapis działa jak zwykła korekta i zatwierdza tylko jawnie
        wybrane symbole.
      </p>
      {notice ? <p role="status">{notice}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {loading ? (
        <p>Wczytywanie propozycji…</p>
      ) : target ? (
        <BoardGeometryCorrectionEditor
          key={target.key}
          target={target}
          autoSelectFirstCell
          previewWhileSourceLoads
          unknownSymbolShortcut="9"
          saveLabel="Zapisz siatkę"
          symbols={symbols}
          onSaved={async () => {
            setNotice(
              'Siatka zapisana. Ta propozycja jest już nieaktualna; pozostałe pola przejdą zwykłą Weryfikację symboli.',
            );
            await load();
          }}
          onConflict={async (message) => {
            setNotice(message);
            await load();
          }}
        />
      ) : (
        <p>
          Propozycja jest nieaktualna albo brak aktualnej planszy do korekty.
          Wróć do porównania w Adminie.
        </p>
      )}
      <button
        className="secondaryButton"
        type="button"
        disabled={loading}
        onClick={() => void load()}
      >
        Odśwież propozycję
      </button>
    </section>
  );
}

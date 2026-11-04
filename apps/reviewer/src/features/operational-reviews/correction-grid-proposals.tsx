'use client';

import type {
  AdminApiClient,
  ImageGridReviewItemResponse,
  OperationalImageReviewItemResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useState } from 'react';
import { apiErrorMessage } from '../catalog/catalog-api-error';
import {
  GridGeometryProposals,
  type GridGeometryProposalsClient,
} from './grid-geometry-proposals';

/** Optional for older correction clients; no mutation is performed on entry. */
export type CorrectionGridProposalsClient = Partial<
  GridGeometryProposalsClient &
    Pick<AdminApiClient, 'getOperationalImageReviewItem'>
>;

export function CorrectionGridProposals({
  api,
  apiBaseUrl,
  item,
  onChanged,
  onEditingChange,
  onRejected,
  onReloadQueue,
}: {
  readonly api: CorrectionGridProposalsClient;
  readonly apiBaseUrl: string;
  readonly item: ImageGridReviewItemResponse;
  readonly onChanged: () => void;
  readonly onRejected?: () => void;
  readonly onReloadQueue?: () => void;
  readonly onEditingChange?: (editing: boolean) => void;
}) {
  const [loaded, setLoaded] = useState<{
    key: string;
    item: OperationalImageReviewItemResponse;
  } | null>(null);
  const [error, setError] = useState('');
  const [stale, setStale] = useState(false);
  const [retry, setRetry] = useState(0);
  const [finishedRead, setFinishedRead] = useState<string | null>(null);
  const key = `${item.gameId}:${item.importJobId}:${item.reviewItemId}:${item.sourceChecksumSha256}:${item.geometryRevision}:${item.resolutionRevision}`;
  const readKey = `${key}:${retry}`;
  const reading = finishedRead !== readKey;
  const supported =
    api.getOperationalImageReviewItem !== undefined &&
    api.listOperationalGridGeometryProposals !== undefined &&
    api.createOperationalGridGeometryProposal !== undefined &&
    api.acceptOperationalGridGeometryProposal !== undefined &&
    api.rejectOperationalGridGeometryProposal !== undefined &&
    api.createOperationalImageReviewGeometryRevision !== undefined &&
    api.previewOperationalImageReviewGeometry !== undefined;
  useEffect(() => {
    let active = true;
    if (!supported || item.reviewItemId === null) return;
    void api.getOperationalImageReviewItem!(item.reviewItemId, {
      gameId: item.gameId,
      importJobId: item.importJobId,
    })
      .then((result) => {
        if (!active) return;
        const current = result.data;
        if (result.error !== undefined || !current) {
          setStale(false);
          setError(
            apiErrorMessage(
              result.error,
              'Nie udało się pobrać propozycji. Ponów odczyt.',
            ),
          );
          return;
        }
        if (
          current.id !== item.reviewItemId ||
          current.gameId !== item.gameId ||
          current.importJobId !== item.importJobId ||
          current.sourceChecksumSha256 !== item.sourceChecksumSha256 ||
          current.geometryRevision !== item.geometryRevision ||
          current.resolutionRevision !== item.resolutionRevision
        ) {
          setStale(true);
          setError(
            'Propozycje wymagają aktualnej wersji planszy. Odśwież kolejkę lub ponów odczyt.',
          );
          return;
        }
        setStale(false);
        setLoaded({ key, item: current });
        setError('');
      })
      .catch(() => {
        if (active) {
          setStale(false);
          setError('Nie udało się pobrać propozycji. Ponów odczyt.');
        }
      })
      .finally(() => {
        if (active) setFinishedRead(readKey);
      });
    return () => {
      active = false;
    };
  }, [
    api,
    item.reviewItemId,
    item.gameId,
    item.importJobId,
    item.sourceChecksumSha256,
    item.geometryRevision,
    item.resolutionRevision,
    key,
    retry,
    supported,
    readKey,
  ]);
  if (!supported || item.reviewItemId === null) return null;
  return (
    <section aria-label="Propozycje w korekcie">
      <p>
        Nowe propozycje przygotujesz w panelu Geometria V3 → Propozycje siatek
        do ręcznej oceny. Każdą możesz przyjąć, edytować albo odrzucić. Dopiero
        przyjęcie lub zapis własnej korekty zatwierdza punkty do uczenia.
      </p>
      {error ? (
        <p role="alert">{error}</p>
      ) : loaded?.key !== key ? (
        <p role="status">Pobieram propozycje dla tej planszy.</p>
      ) : null}
      {stale && onReloadQueue ? (
        <button
          className="secondaryButton"
          type="button"
          onClick={onReloadQueue}
        >
          Odśwież kolejkę
        </button>
      ) : null}
      <button
        className="secondaryButton"
        type="button"
        disabled={reading}
        aria-busy={reading}
        onClick={() => {
          setError('');
          setLoaded(null);
          setRetry((value) => value + 1);
        }}
      >
        {reading ? 'Odświeżanie propozycji…' : 'Odśwież propozycje'}
      </button>
      {loaded?.key === key && !error ? (
        <GridGeometryProposals
          key={`${key}:${retry}`}
          api={api as GridGeometryProposalsClient}
          apiBaseUrl={apiBaseUrl}
          importJobId={item.importJobId}
          item={loaded.item}
          onChanged={onChanged}
          onRejected={onRejected ?? onChanged}
          onEditingChange={onEditingChange}
        />
      ) : null}
    </section>
  );
}

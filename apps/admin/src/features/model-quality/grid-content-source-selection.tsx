'use client';

import type { ContentTargetResponse } from '@game-predictor/admin-api-client';
import { useEffect, useState } from 'react';
import { apiErrorMessage } from '../catalog/catalog-api-error';
import { GridContentOrdinary } from './grid-content-ordinary';
import type { GridContentClient } from './grid-content-reference-workspace';
import { reasonLabel } from './grid-model-state';

/** Read-only sampling choices enter the ordinary editor without freezing roles. */
export function GridContentSourceSelection({
  api,
  gameId,
  apiBaseUrl,
  sourceIds,
}: {
  readonly api: GridContentClient;
  readonly gameId: string;
  readonly apiBaseUrl: string;
  readonly sourceIds: readonly string[];
}) {
  const [batch, setBatch] = useState(0);
  const [offset, setOffset] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [targets, setTargets] = useState<ContentTargetResponse[]>([]);
  const [chosen, setChosen] = useState<ContentTargetResponse | null>(null);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setReading(true);
      setTargets([]);
      setChosen(null);
      setError('');
      setNextOffset(null);
      try {
        const selected = sourceIds.slice(batch * 20, (batch + 1) * 20);
        if (!selected.length) return;
        const result = await api.listGridContentTargets(gameId, {
          sourceIds: [...selected],
          offset,
          limit: 20,
        });
        if (!active) return;
        if (!result.data)
          throw new Error(
            apiErrorMessage(
              result.error,
              'Nie udało się odczytać wybranych zdjęć.',
            ),
          );
        if (
          result.data.gameId !== gameId ||
          result.data.cohortId !== null ||
          result.data.manifestSha256 !== null ||
          result.data.items.some(
            (t) => !selected.includes(t.source.sourceId) || t.role !== null,
          )
        )
          throw new Error('Odrzucono cele innego zakresu oznaczeń.');
        setTargets(result.data.items);
        setNextOffset(result.data.nextOffset);
      } catch (failure) {
        if (active) setError(String(failure));
      } finally {
        if (active) setReading(false);
      }
    });
    return () => {
      active = false;
    };
  }, [api, gameId, sourceIds, batch, offset, refresh]);
  return (
    <section
      className="gridContentWorkflow"
      aria-label="Zdjęcia przed zamrożeniem"
    >
      <h3>Oznacz wybrane zdjęcia przed zamrożeniem</h3>
      <p>
        To zdjęcia wskazane przez podgląd do niezależnego testu. Zapis etykiet
        nie rezerwuje roli. Po zakończeniu odśwież podgląd w panelu uczenia.
      </p>
      <p>
        Pokazujemy oryginał i etykiety zawartości, bez podpowiedzi modelu i
        zapisanej siatki.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      <button
        type="button"
        className="secondaryButton"
        disabled={reading}
        onClick={() => setRefresh((v) => v + 1)}
      >
        {reading ? 'Odczytywanie…' : 'Odśwież wybrane zdjęcia'}
      </button>
      <ul className="gridContentTargets" aria-label="Wybrane zdjęcia i plansze">
        {targets.map((t) => (
          <li key={`${t.source.sourceId}:${t.positionIndex}`}>
            <span>
              {t.displayName || 'Zdjęcie bez nazwy'} · pozycja{' '}
              {t.positionIndex + 1} · numer planszy{' '}
              {t.sequenceNumber ?? 'nieustalony'}
            </span>
            {t.state === 'ready' && t.sequenceNumber != null ? (
              <button
                type="button"
                className="secondaryButton"
                disabled={reading}
                onClick={() => setChosen(t)}
              >
                Oznacz {t.displayName || 'zdjęcie'} — pozycja{' '}
                {t.positionIndex + 1}
              </button>
            ) : (
              <span>
                Nie można wybrać: {t.reasonCodes.map(reasonLabel).join('; ')}
              </span>
            )}
          </li>
        ))}
      </ul>
      {!targets.length && !reading && !error ? (
        <p>Brak zdjęć wymagających oznaczenia.</p>
      ) : null}
      <div className="gridContentActions">
        {offset > 0 ? (
          <button
            type="button"
            disabled={reading}
            onClick={() => setOffset(Math.max(0, offset - 20))}
          >
            Poprzednie plansze
          </button>
        ) : null}
        {nextOffset !== null ? (
          <button
            type="button"
            disabled={reading}
            onClick={() => setOffset(nextOffset)}
          >
            Kolejne plansze
          </button>
        ) : null}
        {batch > 0 ? (
          <button
            type="button"
            disabled={reading}
            onClick={() => {
              setBatch((v) => v - 1);
              setOffset(0);
            }}
          >
            Poprzednie zdjęcia
          </button>
        ) : null}
        {(batch + 1) * 20 < sourceIds.length ? (
          <button
            type="button"
            disabled={reading}
            onClick={() => {
              setBatch((v) => v + 1);
              setOffset(0);
            }}
          >
            Kolejne zdjęcia
          </button>
        ) : null}
      </div>
      {chosen ? (
        <GridContentOrdinary
          key={`${chosen.source.sourceId}:${chosen.positionIndex}:${chosen.source.sourceSha256}`}
          api={api}
          apiBaseUrl={apiBaseUrl}
          gameId={gameId}
          target={chosen}
        />
      ) : null}
    </section>
  );
}

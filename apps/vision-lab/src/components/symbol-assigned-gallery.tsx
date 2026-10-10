'use client';
/* eslint-disable @next/next/no-img-element -- exact protected crop bytes */
import { useEffect, useRef, useState } from 'react';
import {
  symbolQueue,
  SYMBOL_QUEUE_VIEW_SIZE,
  type DictionaryView,
  type LabQueuePreview,
  type Source,
} from '../../../../packages/vision-lab-api-client/src/index';
import { queueSourceCaption } from '../lib/symbol-queue-workflow';
import { symbolErrorCode } from '../lib/symbol-workflow';

type Props = {
  game: string;
  sources: Source[];
  active: DictionaryView | null;
  readVersion: number;
  onError: (message: string) => void;
};

export function SymbolAssignedGallery({
  game,
  sources,
  active,
  readVersion,
  onError,
}: Props) {
  const [symbolId, setSymbolId] = useState('');
  const [page, setPage] = useState<LabQueuePreview | null>(null);
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(false);
  const serial = useRef(0);
  const names = Object.fromEntries(
    sources.map((source) => [source.id, source.filename]),
  );
  const selectedId = active?.entries?.some((entry) => entry.id === symbolId)
    ? symbolId
    : '';

  useEffect(() => {
    const generation = ++serial.current;
    if (!game || !selectedId) return;
    void Promise.resolve()
      .then(() => {
        if (generation !== serial.current) return null;
        setLoading(true);
        return symbolQueue(game, offset, undefined, selectedId);
      })
      .then((result) => {
        if (!result) return;
        if (generation === serial.current) setPage(result);
      })
      .catch((error) => {
        if (generation !== serial.current) return;
        setPage(null);
        onError(
          `Nie można odczytać przypisanych cropów: ${symbolErrorCode(error)}`,
        );
      })
      .finally(() => {
        if (generation === serial.current) setLoading(false);
      });
    return () => {
      serial.current = generation + 1;
    };
  }, [game, selectedId, offset, readVersion, refresh, onError]);

  return (
    <section className="symbol-queue" aria-label="Przypisane cropy">
      <h2>Przypisane cropy</h2>
      <p>
        Wybierz symbol, aby obejrzeć wszystkie aktualne przypisania. Nieaktualne
        po zmianie siatki, zdjęcia lub słownika wracają do poczekalni „Do
        ponownej oceny”.
      </p>
      <div className="symbol-queue-actions">
        <label>
          Symbol
          <select
            value={selectedId}
            disabled={!active || loading}
            onChange={(event) => {
              setSymbolId(event.target.value);
              setOffset(0);
              setPage(null);
            }}
          >
            <option value="">Wybierz symbol</option>
            {active?.entries?.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.display_name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={!selectedId || loading}
          onClick={() => setRefresh((value) => value + 1)}
        >
          Odśwież listę
        </button>
      </div>
      {!active ? (
        <p>Najpierw zatwierdź słownik gry.</p>
      ) : !selectedId ? (
        <p>Wybierz symbol z listy.</p>
      ) : loading ? (
        <p>Wczytywanie przypisanych cropów…</p>
      ) : !page ? (
        <p>Brak aktualnego odczytu.</p>
      ) : page.total === 0 ? (
        <p>Nie ma jeszcze aktualnie przypisanych cropów do tego symbolu.</p>
      ) : (
        <>
          <div className="symbol-queue-grid">
            {page.items.map((item) => {
              const sourceName =
                names[item.binding.source_id] ?? item.binding.source_id;
              return (
                <article
                  className="symbol-queue-item"
                  key={item.binding.crop_id}
                >
                  <img
                    src={`data:image/png;base64,${item.png_base64}`}
                    alt={`Crop: ${sourceName}, plansza ${item.binding.board_index + 1}, pole ${item.binding.cell_index + 1}`}
                    loading="lazy"
                    width={96}
                    height={96}
                  />
                  <span className="symbol-queue-filename" title={sourceName}>
                    {queueSourceCaption(sourceName)}
                  </span>
                  <span>
                    Plansza {item.binding.board_index + 1} · pole{' '}
                    {item.binding.cell_index + 1}
                  </span>
                </article>
              );
            })}
          </div>
          <p>
            {offset + 1}–{offset + page.items.length} z {page.total}
          </p>
          <button
            type="button"
            disabled={loading || offset === 0}
            onClick={() =>
              setOffset(Math.max(0, offset - SYMBOL_QUEUE_VIEW_SIZE))
            }
          >
            Poprzednia strona
          </button>
          <button
            type="button"
            disabled={loading || offset + page.items.length >= page.total}
            onClick={() => setOffset(offset + page.items.length)}
          >
            Następna strona
          </button>
        </>
      )}
    </section>
  );
}

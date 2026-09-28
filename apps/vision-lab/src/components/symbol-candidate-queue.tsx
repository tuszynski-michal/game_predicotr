'use client';
/* eslint-disable @next/next/no-img-element -- exact protected crop bytes */
import { useEffect, useRef, useState } from 'react';
import {
  symbolQueue,
  type DictionaryView,
  type LabQueuePreview,
  type Source,
  type SymbolRequest,
} from '../../../../packages/vision-lab-api-client/src/index';
import { queueDecision, queueSourceCaption, selectableQueueItems } from '../lib/symbol-queue-workflow';
import { symbolErrorCode } from '../lib/symbol-workflow';

type Props = {
  game: string;
  sources: Source[];
  active: DictionaryView | null;
  readVersion: number;
  enabled: boolean;
  disabled: boolean;
  onBusy: (value: boolean) => void;
  onSubmit: (body: SymbolRequest) => Promise<void>;
  onError: (message: string) => void;
};

export function SymbolCandidateQueue({ game, sources, active, readVersion, enabled,
  disabled, onBusy, onSubmit, onError }: Props) {
  const [page, setPage] = useState<LabQueuePreview | null>(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [failed, setFailed] = useState<Set<string>>(new Set());
  const [loaded, setLoaded] = useState<Set<string>>(new Set());
  const [selectedSymbol, setSelectedSymbol] = useState({ digest: '', id: '' });
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [pageGeneration, setPageGeneration] = useState(0);
  const serial = useRef(0);
  const offsetRef = useRef(0);
  const pageIdentity = useRef('');
  const imageSerial = useRef(0);
  const symbolId = selectedSymbol.digest === active?.digest ? selectedSymbol.id : '';

  useEffect(() => {
    const generation = ++serial.current;
    if (!game || !enabled) return;
    onBusy(true);
    void symbolQueue(game).then(async (first) => {
      const desired = offsetRef.current;
      const result = desired > 0 && desired < first.total
        ? await symbolQueue(game, desired, first.read_token) : first;
      if (generation !== serial.current) return;
      offsetRef.current = result === first ? 0 : desired;
      setOffset(offsetRef.current);
      pageIdentity.current = `${result.read_token}:${offsetRef.current}:${++imageSerial.current}`;
      setPageGeneration(imageSerial.current);
      setPage(result);
      setSelected(new Set());
      setFailed(new Set());
      setLoaded(new Set());
    }).catch((error) => {
      if (generation !== serial.current) return;
      setPage(null);
      onError(`Nie można odczytać poczekalni: ${symbolErrorCode(error)}`);
    }).finally(() => {
      if (generation === serial.current) onBusy(false);
    });
    return () => { serial.current = generation + 1; onBusy(false); };
  }, [game, enabled, readVersion, refresh, onBusy, onError]);

  async function changePage(next: number) {
    if (!page || disabled || loading) return;
    setLoading(true);
    onBusy(true);
    try {
      const result = await symbolQueue(game, next, page.read_token);
      offsetRef.current = next;
      setOffset(next);
      pageIdentity.current = `${result.read_token}:${next}:${++imageSerial.current}`;
      setPageGeneration(imageSerial.current);
      setPage(result);
      setSelected(new Set());
      setFailed(new Set());
      setLoaded(new Set());
    } catch (error) {
      setPage(null);
      onError(`Strona poczekalni utraciła aktualność: ${symbolErrorCode(error)}. Odczytaj stan.`);
    } finally {
      setLoading(false);
      onBusy(false);
    }
  }

  function assign() {
    if (!page || !active?.version || !symbolId || disabled || loading) return;
    const request = queueDecision(page, selected, loaded, failed,
      active, symbolId, crypto.randomUUID());
    if (request) void onSubmit(request);
  }

  const names = Object.fromEntries(sources.map((s) => [s.id, s.filename]));
  const selectable = selectableQueueItems(page, loaded, failed);
  const classSelected = Boolean(active?.entries?.some((entry) => entry.id === symbolId));
  const identity = page ? `${page.read_token}:${offset}:${pageGeneration}` : '';
  return <section className="symbol-queue">
    <h2>Poczekalnia cropów</h2>
    <p>Nieprzypisane pola czekają na decyzję. „Do ponownej oceny” oznacza zmianę siatki, obrazu lub słownika. Sam podgląd nie zatwierdza etykiet.</p>
    <button type="button" disabled={disabled || loading || !game} onClick={() => {
      offsetRef.current = 0;
      setSelected(new Set());
      setRefresh((value) => value + 1);
    }}>Odśwież poczekalnię</button>
    {!game ? <p>Wybierz grę.</p> : !page ? <p>Wczytywanie poczekalni albo brak aktualnego odczytu.</p> : <>
      {page.total === 0 ? <p>Brak cropów oczekujących na przypisanie.</p> : <>
        <div className="symbol-queue-actions">
          <button type="button" disabled={disabled || loading || selectable.length === 0}
            onClick={() => setSelected(new Set(selectable.map((item) => item.binding.crop_id)))}>Zaznacz widoczne</button>
          <button type="button" disabled={disabled || loading || selected.size === 0}
            onClick={() => setSelected(new Set())}>Wyczyść wybór</button>
          <label>Symbol
            <select value={symbolId} disabled={disabled || loading || !active}
              onChange={(event) => setSelectedSymbol({ digest: active?.digest ?? '', id: event.target.value })}>
              <option value="">Wybierz symbol</option>
              {active?.entries?.map((entry) => <option key={entry.id} value={entry.id}>{entry.display_name}</option>)}
            </select>
          </label>
          <button type="button" disabled={disabled || loading || !classSelected || selected.size === 0}
            onClick={assign}>Przypisz zaznaczone ({selected.size})</button>
        </div>
        {!active && <p>Utwórz i zatwierdź słownik gry, aby przypisywać cropy.</p>}
        <div className="symbol-queue-grid">
          {page.items.map((item) => {
            const id = item.binding.crop_id;
            const sourceName = names[item.binding.source_id] ?? item.binding.source_id;
            return <label className="symbol-queue-item" key={`${pageGeneration}:${id}`}
              aria-label={`${sourceName}, plansza ${item.binding.board_index + 1}, pole ${item.binding.cell_index + 1}`}>
              <input type="checkbox" checked={selected.has(id)} disabled={disabled || loading || failed.has(id) || !loaded.has(id)}
                onChange={(event) => setSelected((current) => {
                  const next = new Set(current);
                  if (event.target.checked) next.add(id); else next.delete(id);
                  return next;
                })} />
              <img src={`data:image/png;base64,${item.png_base64}`} alt={`Crop pola ${item.binding.cell_index + 1}`}
                width={96} height={96} onLoad={() => {
                  if (pageIdentity.current === identity)
                    setLoaded((current) => new Set(current).add(id));
                }} onError={() => {
                  if (pageIdentity.current !== identity) return;
                  setFailed((current) => new Set(current).add(id));
                  setSelected((current) => { const next = new Set(current); next.delete(id); return next; });
                  onError('Nie udało się wyświetlić cropa. Odśwież poczekalnię.');
                }} />
              <span className="symbol-queue-filename" title={sourceName}>{queueSourceCaption(sourceName)}</span>
              <span>Plansza {item.binding.board_index + 1} · pole {item.binding.cell_index + 1}</span>
              <small>{item.status === 'unassigned' ? 'Nieprzypisany' : 'Do ponownej oceny'}</small>
            </label>;
          })}
        </div>
        <p>{offset + 1}–{offset + page.items.length} z {page.total}</p>
        <button type="button" disabled={disabled || loading || offset === 0}
          onClick={() => void changePage(Math.max(0, offset - 30))}>Poprzednia strona</button>
        <button type="button" disabled={disabled || loading || offset + page.items.length >= page.total}
          onClick={() => void changePage(offset + page.items.length)}>Następna strona</button>
      </>}
    </>}
  </section>;
}

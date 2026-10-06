'use client';
/* eslint-disable @next/next/no-img-element -- exact frozen RGB96 PNGs */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useToast } from '../../../../packages/ui/src/toasts';
import {
  symbolBatchQueue,
  writeSymbol,
  type BatchLabelDecide,
  type BatchQueuePreview,
  type SymbolResult,
} from '../../../../packages/vision-lab-api-client/src/index';
import {
  batchDecision,
  confirmedBatchPage,
} from '../lib/symbol-batch-workflow';
import { symbolWriteSession, symbolErrorCode } from '../lib/symbol-workflow';

export function SymbolBatchEditor() {
  const toast = useToast();
  const [page, setPage] = useState<BatchQueuePreview | null>(null);
  const [selected, setSelected] = useState('');
  const [symbol, setSymbol] = useState<string | null>(null);
  const [action, setAction] = useState<BatchLabelDecide['action']>('approve');
  const [loaded, setLoaded] = useState<Set<string>>(new Set());
  const [reading, setReading] = useState(false);
  const [imageEpoch, setImageEpoch] = useState(0);
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(false);
  const [requiresRead, setRequiresRead] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const session = useRef(
    symbolWriteSession<BatchLabelDecide, SymbolResult>(async (request) => {
      const result = await writeSymbol(request);
      if (!result) throw new Error('SYMBOL_RESPONSE_MISSING');
      return result;
    }),
  );
  const readingRef = useRef(false);
  const editorPanel = useRef<HTMLElement>(null);

  const read = useCallback(async () => {
    if (session.current.busy || readingRef.current) return;
    readingRef.current = true;
    setReading(true);
    setError('');
    try {
      const result = await symbolBatchQueue();
      session.current.reload();
      setPage(result);
      const initial = new URLSearchParams(window.location.search).get('case');
      setSelected((previous) =>
        result.items.some((item) => item.case_id === previous)
          ? previous
          : (result.items.find((item) => item.case_id === initial)?.case_id ??
            result.items[0].case_id),
      );
      setLoaded(new Set());
      setImageEpoch((epoch) => epoch + 1);
      setSymbol(null);
      setAction('approve');
      setRetry(false);
      setRequiresRead(false);
      setMessage('');
    } catch (failure) {
      setError(symbolErrorCode(failure));
    } finally {
      readingRef.current = false;
      setReading(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    queueMicrotask(() => {
      if (mounted) void read();
    });
    return () => {
      mounted = false;
    };
  }, [read]);
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (!session.current.navigationAllowed) event.preventDefault();
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, []);

  const choose = useCallback(
    (id: string) => {
      if (requiresRead || (retry && !busy)) return;
      setSymbol(id);
      setAction('approve');
      setMessage('');
    },
    [requiresRead, retry, busy],
  );
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (
        event.ctrlKey ||
        event.altKey ||
        event.metaKey ||
        event.repeat ||
        (event.target instanceof HTMLElement &&
          event.target.closest('input,select,textarea'))
      )
        return;
      const index =
        event.key === '0'
          ? 9
          : /^[1-9]$/.test(event.key)
            ? Number(event.key) - 1
            : -1;
      const entry = page?.dictionary.entries?.[index];
      if (entry) {
        event.preventDefault();
        choose(entry.id);
      }
    };
    window.addEventListener('keydown', keyboard);
    return () => window.removeEventListener('keydown', keyboard);
  }, [page, choose]);

  async function submit() {
    if (!page || busy || requiresRead || reading) return;
    const request =
      session.current.pending ??
      batchDecision(
        page,
        selected,
        loaded,
        action,
        symbol,
        crypto.randomUUID(),
      );
    if (!request) return;
    setBusy(true);
    setRetry(false);
    setError('');
    setMessage('');
    try {
      const result = await session.current.submit(request);
      const updated = confirmedBatchPage(page, request, result);
      if (!updated) {
        setRequiresRead(true);
        throw new Error('SYMBOL_RECEIPT_MISMATCH');
      }
      setPage(updated);
      const target = page.items.find(
        (item) => item.case_id === request.case_id,
      )!;
      const name = page.dictionary.entries?.find(
        (entry) => entry.id === request.symbol_id,
      )?.display_name;
      const text = `Zapisano: plansza ${target.board}, pole ${target.field} — ${name ?? (request.action === 'unreadable' ? 'Nieczytelny' : 'Błąd siatki')}.`;
      setMessage(text);
      toast({ kind: 'success', message: text });
    } catch (failure) {
      setError(symbolErrorCode(failure));
      setRetry(session.current.pending !== null);
    } finally {
      setBusy(false);
    }
  }

  const current = page?.items.find((item) => item.case_id === selected);
  const entries = page?.dictionary.entries ?? [];
  const valid =
    page && batchDecision(page, selected, loaded, action, symbol, 'preview');
  const blocked = requiresRead || (retry && !busy);
  const savedName = entries.find(
    (entry) => entry.id === current?.symbol_id,
  )?.display_name;
  return (
    <main style={{ maxWidth: 1320, margin: '0 auto', padding: 24 }}>
      <h1>Korekta symboli — Mumie</h1>
      <p>
        Kliknij wycinek, wybierz symbol i naciśnij „Zapisz symbol”. Poprawna
        siatka nie wymaga zmiany.
      </p>
      <button disabled={busy || reading} onClick={() => void read()}>
        Odczytaj zapisane poprawki
      </button>
      {reading && <p role="status">Wczytywanie wycinków…</p>}
      {error && (
        <div role="alert" style={{ color: '#fca5a5', marginTop: 12 }}>
          <p>
            {error === 'SYMBOL_BATCH_REVIEW_NOT_CONFIGURED'
              ? 'Ta partia nie jest jeszcze podłączona do edytora.'
              : error === 'SYMBOL_REVISION_CONFLICT'
                ? 'Stan został zmieniony. Odczytaj zapisane poprawki i wybierz symbol ponownie.'
                : 'Brak potwierdzenia zapisu lub odczytu. Ponów ten sam zapis albo odczytaj zapisane poprawki.'}
          </p>
          <details>
            <summary>Szczegóły błędu</summary>
            {error}
          </details>
        </div>
      )}
      {retry && (
        <button
          disabled={busy || reading || requiresRead}
          onClick={() => void submit()}
        >
          Ponów ten sam zapis
        </button>
      )}
      {message && (
        <p role="status" style={{ color: '#86efac' }}>
          {message}
        </p>
      )}
      {page && (
        <>
          <p>
            {page.items.filter((item) => item.decision_id).length} z{' '}
            {page.items.length} ocenionych.
          </p>
          <div className="symbol-batch-layout">
            <section
              aria-label="Wycinki do poprawy"
              className="symbol-batch-crops"
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit,minmax(135px,1fr))',
                gap: 10,
              }}
            >
              {page.items.map((item, index) => (
                <button
                  key={item.case_id}
                  type="button"
                  aria-label={`Wycinek ${index + 1}, plansza ${item.board}, pole ${item.field}`}
                  aria-pressed={selected === item.case_id}
                  disabled={blocked || reading}
                  onClick={() => {
                    setSelected(item.case_id);
                    setSymbol(null);
                    setAction('approve');
                    setMessage('');
                    editorPanel.current?.scrollIntoView({
                      behavior: 'smooth',
                      block: 'nearest',
                    });
                  }}
                  style={{
                    padding: 10,
                    borderRadius: 8,
                    border: `2px solid ${selected === item.case_id ? '#60a5fa' : '#475569'}`,
                    background:
                      selected === item.case_id ? '#172554' : '#111827',
                    color: '#f8fafc',
                    cursor: 'pointer',
                  }}
                >
                  <img
                    key={`${item.case_id}:${imageEpoch}`}
                    src={`data:image/png;base64,${item.png_base64}`}
                    width={96}
                    height={96}
                    alt={`Plansza ${item.board}, pole ${item.field}`}
                    onLoad={() =>
                      setLoaded((old) => new Set(old).add(item.case_id))
                    }
                    onError={() => {
                      setLoaded((old) => {
                        const next = new Set(old);
                        next.delete(item.case_id);
                        return next;
                      });
                      setError('SYMBOL_IMAGE_FAILED');
                    }}
                  />
                  <div>
                    #{index + 1} · P{item.board} / {item.field}
                  </div>
                  <div
                    style={{
                      color: item.decision_id ? '#86efac' : '#cbd5e1',
                      fontSize: 13,
                    }}
                  >
                    {item.decision_id
                      ? `Zapisany: ${entries.find((entry) => entry.id === item.symbol_id)?.display_name ?? (item.action === 'grid_issue' ? 'Błąd siatki' : 'Nieczytelny')}`
                      : 'Do oceny'}
                  </div>
                </button>
              ))}
            </section>
            {current && (
              <section
                ref={editorPanel}
                className="symbol-batch-panel"
                style={{
                  padding: 16,
                  background: '#111827',
                  border: '1px solid #475569',
                  borderRadius: 8,
                }}
              >
                <h2>
                  Plansza {current.board}, pole {current.field}
                </h2>
                <p>
                  {current.filename} · {current.category}
                </p>
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 24,
                    alignItems: 'flex-start',
                  }}
                >
                  <img
                    key={`${current.case_id}:${imageEpoch}`}
                    src={`data:image/png;base64,${current.png_base64}`}
                    width={96}
                    height={96}
                    alt="Wybrany wycinek"
                  />
                  <div style={{ flex: 1, minWidth: 250 }}>
                    {current.decision_id && (
                      <p>
                        Zapisana ocena:{' '}
                        {savedName ??
                          (current.action === 'grid_issue'
                            ? 'Błąd siatki'
                            : 'Nieczytelny')}
                        . Możesz poprawić ją ponownie.
                      </p>
                    )}
                    <div
                      aria-label="Wybierz właściwy symbol"
                      style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}
                    >
                      {entries.map((entry, index) => (
                        <button
                          key={entry.id}
                          type="button"
                          aria-pressed={
                            action === 'approve' && symbol === entry.id
                          }
                          disabled={blocked || reading}
                          onClick={() => choose(entry.id)}
                          style={{
                            padding: '10px 14px',
                            border: `2px solid ${action === 'approve' && symbol === entry.id ? '#60a5fa' : '#64748b'}`,
                            borderRadius: 6,
                          }}
                        >
                          {index < 10 && (
                            <kbd>{index === 9 ? '0' : index + 1}</kbd>
                          )}{' '}
                          {entry.display_name}
                        </button>
                      ))}
                    </div>
                    <p>
                      Wybór klasy potwierdza symbol w tym widocznym wycięciu.
                    </p>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      <button
                        disabled={blocked || reading}
                        aria-pressed={action === 'unreadable'}
                        onClick={() => {
                          setAction('unreadable');
                          setSymbol(null);
                        }}
                      >
                        Nieczytelny
                      </button>
                      <button
                        disabled={blocked || reading}
                        aria-pressed={action === 'grid_issue'}
                        onClick={() => {
                          setAction('grid_issue');
                          setSymbol(null);
                        }}
                      >
                        Błąd siatki
                      </button>
                      <button
                        disabled={
                          !valid || busy || retry || requiresRead || reading
                        }
                        onClick={() => void submit()}
                        style={{
                          padding: '12px 20px',
                          background: '#2563eb',
                          color: 'white',
                          borderRadius: 6,
                        }}
                      >
                        {busy
                          ? 'Zapisywanie…'
                          : action === 'approve'
                            ? 'Zapisz symbol'
                            : 'Zapisz ocenę'}
                      </button>
                    </div>
                    <p>
                      <a
                        href={current.photo_url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(event) => {
                          if (!session.current.navigationAllowed)
                            event.preventDefault();
                        }}
                      >
                        Pokaż całe zdjęcie i siatkę
                      </a>
                    </p>
                  </div>
                </div>
              </section>
            )}
          </div>
        </>
      )}
    </main>
  );
}

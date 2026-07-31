'use client';

import type {
  SymbolBootstrapDefinitionCommand,
  SymbolBootstrapRunResponse,
} from '@game-predictor/admin-api-client';
import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';

import { apiErrorMessage } from '@/features/catalog/catalog-api-error';

interface BootstrapClient {
  getLatestSymbolBootstrap(gameId: string): Promise<{
    data?: SymbolBootstrapRunResponse | null;
    error?: unknown;
  }>;
  resolveSymbolBootstrap(
    gameId: string,
    bootstrapId: string,
    body: { symbols: SymbolBootstrapDefinitionCommand[] },
  ): Promise<{ data?: SymbolBootstrapRunResponse; error?: unknown }>;
  startSymbolBootstrap(
    gameId: string,
    body: { createdBy: string; expectedSymbolCount: number },
  ): Promise<{ data?: SymbolBootstrapRunResponse; error?: unknown }>;
}

interface Props {
  readonly client: BootstrapClient;
  readonly gameId: string;
  readonly hasSymbols: boolean;
  readonly onApplied: () => void;
}

type ResolutionRow = SymbolBootstrapDefinitionCommand;

export function SymbolBootstrapPanel({ client, gameId, hasSymbols, onApplied }: Props) {
  const [expectedCount, setExpectedCount] = useState('8');
  const [run, setRun] = useState<SymbolBootstrapRunResponse | null>(null);
  const [rows, setRows] = useState<ResolutionRow[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'submitting'>('loading');
  const [error, setError] = useState('');
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const current = ++requestId.current;
    setState('loading');
    setError('');
    try {
      const result = await client.getLatestSymbolBootstrap(gameId);
      if (current !== requestId.current) return;
      if (result.error !== undefined) {
        setError(apiErrorMessage(result.error, 'Nie udało się pobrać bootstrapu symboli.'));
      } else {
        setRun(result.data ?? null);
        if (result.data?.status === 'conflict') {
          setExpectedCount(String(result.data.expectedSymbolCount));
          setRows(initialRows(result.data));
        }
      }
    } catch {
      if (current === requestId.current) setError('Połączenie z Admin API zostało przerwane.');
    } finally {
      if (current === requestId.current) setState('ready');
    }
  }, [client, gameId]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void load();
    });
    return () => {
      cancelled = true;
      requestId.current += 1;
    };
  }, [load]);

  async function start() {
    const count = Number(expectedCount);
    if (!Number.isInteger(count) || count < 1 || count > 32767) {
      setError('Oczekiwana liczba symboli musi być liczbą od 1 do 32767.');
      return;
    }
    setState('submitting');
    setError('');
    const result = await client.startSymbolBootstrap(gameId, {
      createdBy: 'local-admin',
      expectedSymbolCount: count,
    });
    if (result.error !== undefined || result.data === undefined) {
      setError(apiErrorMessage(result.error, 'Nie udało się przeanalizować cropów.'));
      setState('ready');
      return;
    }
    setRun(result.data);
    setRows(result.data.status === 'conflict' ? initialRows(result.data) : []);
    setState('ready');
    if (result.data.status === 'applied') onApplied();
  }

  async function resolve() {
    if (!run || run.status !== 'conflict') return;
    setState('submitting');
    setError('');
    const result = await client.resolveSymbolBootstrap(gameId, run.id, { symbols: rows });
    if (result.error !== undefined || result.data === undefined) {
      setError(apiErrorMessage(result.error, 'Nie udało się zapisać rozstrzygnięcia.'));
      setState('ready');
      return;
    }
    setRun(result.data);
    setState('ready');
    onApplied();
  }

  if (hasSymbols && run?.status !== 'conflict') return null;

  return (
    <section className="editorPanel" data-testid="symbol-bootstrap-panel">
      <p className="eyebrow">Automatyczny katalog</p>
      <h2>Utwórz symbole z zaimportowanych cropów</h2>
      <p>Analiza zachowuje rzeczywisty obraz, checksumę, liczność i confidence każdej grupy.</p>
      {error ? <p className="formError" role="alert">{error}</p> : null}
      {state === 'loading' ? <p role="status">Wczytywanie bootstrapu…</p> : null}
      {state !== 'loading' && run?.status !== 'conflict' ? (
        <div className="formActions">
          <label>
            <span>Oczekiwana liczba symboli</span>
            <input min={1} max={32767} onChange={(event) => setExpectedCount(event.currentTarget.value)} type="number" value={expectedCount} />
          </label>
          <button className="primaryButton" disabled={state === 'submitting'} onClick={() => void start()} type="button">
            {state === 'submitting' ? 'Analizowanie…' : 'Wykryj symbole'}
          </button>
        </div>
      ) : null}
      {run?.status === 'conflict' ? (
        <div>
          <p role="alert">Wykryto {run.detectedClusterCount} grup, oczekiwano {run.expectedSymbolCount}. Przypisz każdą grupę; tę samą można wybrać ponownie tylko przy rozdzielaniu.</p>
          <div className="symbolsList">
            {rows.map((row, index) => (
              <div className="symbolCard" key={row.mobileCode}>
                <strong>Symbol {row.mobileCode}</strong>
                <label><span>Kod</span><input value={row.code} onChange={(event) => updateRow(setRows, index, { code: event.currentTarget.value })} /></label>
                <label><span>Nazwa</span><input value={row.name} onChange={(event) => updateRow(setRows, index, { name: event.currentTarget.value })} /></label>
                <label>
                  <span>Grupy źródłowe</span>
                  <select multiple value={row.candidateIds} onChange={(event) => updateRow(setRows, index, { candidateIds: [...event.currentTarget.selectedOptions].map((option) => option.value) })}>
                    {run.candidates.map((candidate) => <option key={candidate.candidateId} value={candidate.candidateId}>{candidate.proposedName} · {candidate.sampleCount} cropów · {(candidate.meanConfidence * 100).toFixed(1)}%</option>)}
                  </select>
                </label>
              </div>
            ))}
          </div>
          <button className="primaryButton" disabled={state === 'submitting'} onClick={() => void resolve()} type="button">Zapisz rozstrzygnięcie</button>
        </div>
      ) : null}
    </section>
  );
}

function initialRows(run: SymbolBootstrapRunResponse): ResolutionRow[] {
  const result = Array.from({ length: run.expectedSymbolCount }, (_, index) => {
    const source = run.candidates[Math.min(index, run.candidates.length - 1)];
    return { mobileCode: index + 1, code: source?.proposedCode ?? `SYMBOL_${index + 1}`, name: source?.proposedName ?? `Symbol ${index + 1}`, candidateIds: source ? [source.candidateId] : [] };
  });
  run.candidates.slice(run.expectedSymbolCount).forEach((candidate) => {
    result[result.length - 1]?.candidateIds.push(candidate.candidateId);
  });
  return result;
}

function updateRow(setRows: Dispatch<SetStateAction<ResolutionRow[]>>, index: number, patch: Partial<ResolutionRow>) {
  setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row));
}

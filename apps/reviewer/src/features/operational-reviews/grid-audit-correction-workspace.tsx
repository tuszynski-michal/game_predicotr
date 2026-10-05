'use client';

import type {
  AdminApiClient,
  GridAuditProposalResponse,
  GridAuditQueuePageResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { apiErrorMessage } from '../catalog/catalog-api-error';

import {
  type BoardGeometryCorrectionTarget,
  gridAuditBoardGeometryTarget,
} from './board-geometry-correction-target';
import {
  BoardGeometryCorrectionEditor,
  type CorrectionSymbol,
} from './deferred-board-cell-geometry-editor';
import { gridAuditProgressText } from './grid-audit-correction-state';
import { buildOperationalReviewSymbolShortcuts } from './operational-review-state';

type LoadState = 'error' | 'loading' | 'ready';

export type GridAuditCorrectionClient = Pick<
  AdminApiClient,
  | 'createImageGridReviewGeometryRevision'
  | 'getGridAuditProposal'
  | 'imageGridReviewSourceAssetUrl'
  | 'listGridAuditProposals'
  | 'listSymbols'
  | 'previewImageGridReviewGeometry'
>;

interface QueuePosition {
  readonly afterOrdinal: number | undefined;
  readonly page: GridAuditQueuePageResponse;
  readonly proposal: GridAuditProposalResponse | null;
}

/**
 * TASK-0840: the boards of the grid-audit list, one at a time, in list order
 * (boards with human symbol decisions first). Each board opens on the existing
 * correction screen with the audit's network grid as the suggestion; the save
 * is the existing geometry save of the board. The queue state is derived by
 * the API from the boards' current geometry revisions — a saved board leaves
 * the queue, also after a restart; skipping only moves on in this session.
 */
export function GridAuditCorrectionWorkspace({
  api,
  gameId,
}: {
  readonly api: GridAuditCorrectionClient;
  readonly gameId: string;
}) {
  const [position, setPosition] = useState<QueuePosition | null>(null);
  const [history, setHistory] = useState<readonly QueuePosition[]>([]);
  const [state, setState] = useState<LoadState>('loading');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [symbols, setSymbols] = useState<readonly CorrectionSymbol[]>([]);
  const [symbolsLoading, setSymbolsLoading] = useState(true);
  const [symbolsError, setSymbolsError] = useState('');
  const mounted = useRef(true);
  const requestId = useRef(0);
  const reloadedForConflictRef = useRef<string | null>(null);
  const targetKeyRef = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    void api
      .listSymbols(gameId)
      .then((result) => {
        if (!active) return;
        setSymbolsLoading(false);
        if (result.error !== undefined || !result.data) {
          setSymbolsError(
            'Nie udało się wczytać symboli. Odśwież stronę przed zatwierdzeniem propozycji.',
          );
          return;
        }
        setSymbols(
          buildOperationalReviewSymbolShortcuts(result.data, {
            reservedKeys: ['9'],
          }).map(({ key, symbol }) => ({
            id: symbol.id,
            label: symbol.namePl ?? symbol.name,
            shortcut: key,
          })),
        );
      })
      .catch(() => {
        if (!active) return;
        setSymbolsLoading(false);
        setSymbolsError(
          'Nie udało się wczytać symboli. Odśwież stronę przed zatwierdzeniem propozycji.',
        );
      });
    return () => {
      active = false;
    };
  }, [api, gameId]);

  const load = useCallback(
    async (
      afterOrdinal: number | undefined,
      options: { readonly preserveNotice?: boolean } = {},
    ): Promise<QueuePosition | null> => {
      const current = ++requestId.current;
      setState('loading');
      setError('');
      if (!options.preserveNotice) setNotice('');
      try {
        const listed = await api.listGridAuditProposals({
          gameId,
          limit: 1,
          ...(afterOrdinal === undefined ? {} : { afterOrdinal }),
        });
        if (!mounted.current || current !== requestId.current) return null;
        if (listed.error !== undefined || listed.data === undefined) {
          setState('error');
          setError(
            apiErrorMessage(
              listed.error,
              'Nie udało się pobrać listy poprawek z audytu siatek.',
            ),
          );
          return null;
        }
        const first = listed.data.items[0];
        let proposal: GridAuditProposalResponse | null = null;
        if (first !== undefined) {
          const read = await api.getGridAuditProposal(gameId, first.itemId);
          if (!mounted.current || current !== requestId.current) return null;
          if (read.error !== undefined || read.data === undefined) {
            setState('error');
            setError(
              apiErrorMessage(
                read.error,
                'Nie udało się pobrać propozycji siatki.',
              ),
            );
            return null;
          }
          proposal = read.data;
        }
        const next = { afterOrdinal, page: listed.data, proposal };
        setPosition(next);
        setState('ready');
        return next;
      } catch {
        if (!mounted.current || current !== requestId.current) return null;
        setState('error');
        setError('Połączenie z lokalnym Admin API zostało przerwane.');
        return null;
      }
    },
    [api, gameId],
  );

  useEffect(() => {
    mounted.current = true;
    queueMicrotask(() => void load(undefined));
    return () => {
      mounted.current = false;
    };
  }, [load]);

  const proposal = position?.proposal ?? null;
  const entry = position?.page.items[0] ?? null;
  const target: BoardGeometryCorrectionTarget | null = useMemo(
    () =>
      proposal === null
        ? null
        : gridAuditBoardGeometryTarget({ api, proposal }),
    [api, proposal],
  );
  useEffect(() => {
    targetKeyRef.current = target?.key ?? null;
  }, [target]);

  async function skip() {
    if (position === null || entry === null) return;
    const previous = position;
    if ((await load(entry.ordinal)) !== null) {
      setHistory((current) => [...current, previous]);
    }
  }

  async function goBack() {
    const previous = history.at(-1);
    if (previous === undefined) return;
    // Re-read: the previous board may have been corrected meanwhile.
    if ((await load(previous.afterOrdinal)) !== null) {
      setHistory((current) => current.slice(0, -1));
    }
  }

  async function restart() {
    if ((await load(undefined)) !== null) setHistory([]);
  }

  const handleSaved = useCallback(async () => {
    reloadedForConflictRef.current = null;
    setNotice(
      'Siatka zapisana. Plansza zniknęła z listy; pola ze zmienionym wycinkiem wróciły do Weryfikacji symboli.',
    );
    // The saved board has a newer geometry revision and leaves the queue;
    // reading from the same place shows the next board.
    await load(position?.afterOrdinal, { preserveNotice: true });
  }, [load, position]);

  const handleConflict = useCallback(
    async (message: string) => {
      const key = targetKeyRef.current;
      if (key !== null && reloadedForConflictRef.current === key) {
        setNotice(`${message} Lista nadal wskazuje tę planszę — pomiń ją.`);
        return;
      }
      reloadedForConflictRef.current = key;
      setNotice(`${message} Wczytano aktualny stan listy.`);
      await load(position?.afterOrdinal, { preserveNotice: true });
    },
    [load, position],
  );

  const counts = position?.page.counts ?? null;
  const hasNext = position?.page.nextAfterOrdinal != null;

  return (
    <section
      aria-label="Poprawki z audytu siatek"
      className="deferredGeometryQueue"
    >
      <header className="deferredGeometryHeader">
        <div>
          <span className="eyebrow">Jedna plansza naraz</span>
          <h2>Poprawki z audytu siatek</h2>
          <p>
            Plansze, których zapisana siatka według audytu jest przesunięta albo
            przekrzywiona. Siatka sieci jest wczytana jako propozycja: sprawdź
            podgląd, w razie potrzeby popraw narożniki i zapisz. Jeśli
            propozycja jest zła, pomiń planszę. Symbole są nowymi podpowiedziami
            dla tej propozycji siatki i są wstępnie wybrane. Przejrzyj wszystkie
            pola i zmień błędne symbole. Znak ? przy nazwie oznacza niepewną
            propozycję. Zapis zatwierdzi widoczne wybory.
          </p>
          {counts !== null ? (
            <p className="mutedText">{gridAuditProgressText(counts)}</p>
          ) : null}
        </div>
      </header>

      {notice ? (
        <p className="operationalReviewNotice" role="status">
          {notice}
        </p>
      ) : null}

      {symbolsLoading || symbolsError ? (
        <p className="operationalReviewNotice" role="status">
          {symbolsError || 'Wczytywanie symboli…'}
        </p>
      ) : null}

      {state === 'loading' ? (
        <AuditState text="Pobieram planszę z listy audytu." />
      ) : state === 'error' ? (
        <AuditState
          action={() => void load(position?.afterOrdinal)}
          error
          text={error}
        />
      ) : entry === null || target === null ? (
        <div className="deferredGeometryComplete">
          <h3>
            {position?.afterOrdinal === undefined
              ? 'Lista poprawek jest pusta'
              : 'Koniec listy'}
          </h3>
          <p>
            {position?.afterOrdinal === undefined
              ? 'Wszystkie plansze z audytu zostały poprawione albo są nieaktualne.'
              : 'Za tą pozycją nie ma już plansz do poprawy. Pominięte plansze są na początku listy.'}
          </p>
          {position?.afterOrdinal !== undefined ? (
            <button
              className="secondaryButton"
              onClick={() => void restart()}
              type="button"
            >
              Od początku
            </button>
          ) : null}
        </div>
      ) : (
        <>
          <BoardGeometryCorrectionEditor
            autoSelectFirstCell
            key={target.key}
            onConflict={handleConflict}
            onSaved={handleSaved}
            previewWhileSourceLoads
            symbols={symbols}
            symbolsLoading={symbolsLoading || symbolsError !== ''}
            target={target}
            unknownSymbolShortcut="9"
          />
          <footer className="deferredGeometryNavigation">
            <button
              className="secondaryButton"
              disabled={history.length === 0}
              onClick={() => void goBack()}
              type="button"
            >
              ← Poprzednia
            </button>
            <span>
              Pozycja{' '}
              <strong>{(entry.ordinal + 1).toLocaleString('pl-PL')}</strong> z{' '}
              {counts?.total.toLocaleString('pl-PL') ?? '—'} · Do poprawy:{' '}
              <strong>{counts?.open.toLocaleString('pl-PL') ?? '—'}</strong>
            </span>
            {hasNext ? (
              <button
                className="secondaryButton"
                onClick={() => void skip()}
                type="button"
              >
                Pomiń na razie →
              </button>
            ) : (
              <button
                className="secondaryButton"
                disabled={position?.afterOrdinal === undefined}
                onClick={() => void restart()}
                type="button"
              >
                Od początku
              </button>
            )}
          </footer>
        </>
      )}
    </section>
  );
}

function AuditState({
  action,
  error = false,
  text,
}: {
  readonly action?: () => void;
  readonly error?: boolean;
  readonly text: string;
}) {
  return (
    <div className={error ? 'emptyState errorState' : 'emptyState'}>
      <h3>
        {error ? 'Nie udało się wczytać listy audytu' : 'Wczytywanie listy'}
      </h3>
      <p>{text}</p>
      {action ? (
        <button className="secondaryButton" onClick={action} type="button">
          Spróbuj ponownie
        </button>
      ) : null}
    </div>
  );
}

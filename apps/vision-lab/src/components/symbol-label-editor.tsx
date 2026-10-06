'use client';
/* eslint-disable @next/next/no-img-element -- exact approved bytes; no optimizer */
import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useToast } from '../../../../packages/ui/src/toasts';
import { useAnnotations } from './annotation-context';
import { SymbolBoardEditor } from './symbol-board-editor';
import { SymbolCandidateQueue } from './symbol-candidate-queue';
import { SymbolAssignedGallery } from './symbol-assigned-gallery';
import type { QueueConfirmation } from '../lib/symbol-queue-workflow';
import { gameDisplayName } from '../lib/game-display-name';
import {
  symbolWriteSession,
  canMutateSymbolRow,
  createSymbolDictionaryEntry,
  hasBlankSymbolDictionaryName,
  normalizeSymbolDictionaryEntries,
  symbolErrorCode as errorCode,
} from '../lib/symbol-workflow';
import {
  listSources,
  symbolLabels,
  symbolDictionaries,
  symbolDictionary,
  symbolCrop,
  writeSymbol,
  backupSymbols,
  type Source,
  type SymbolPage,
  type SymbolRequest,
  type DictionaryEntry,
  type DictionaryView,
  type DbCropPreview,
  type SymbolResult,
} from '../../../../packages/vision-lab-api-client/src/index';

export function SymbolLabelEditor() {
  const notify = useToast();
  const { state, refresh } = useAnnotations();
  const [sources, setSources] = useState<Source[]>([]);
  const [game, setGame] = useState('');
  const [page, setPage] = useState<SymbolPage | null>(null);
  const [versions, setVersions] = useState<DictionaryView[]>([]);
  const [active, setActive] = useState<DictionaryView | null>(null);
  const [entries, setEntries] = useState<DictionaryEntry[]>([]);
  const [preview, setPreview] = useState<DbCropPreview | null>(null);
  const [pending, setPending] = useState<SymbolRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [boardBusy, setBoardBusy] = useState(false);
  const [queueBusy, setQueueBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  const [boardReadVersion, setBoardReadVersion] = useState(0);
  const [boardRevision, setBoardRevision] = useState(0);
  const [confirmation, setConfirmation] = useState<QueueConfirmation | null>(
    null,
  );
  const [labelsStale, setLabelsStale] = useState(false);
  const order = useRef(0);
  const writing = useRef(false);
  const writeSession = useRef(
    symbolWriteSession<SymbolRequest, SymbolResult>(writeSymbol),
  );
  const unavailable = busy || boardBusy || queueBusy || pending !== null;
  const report = useCallback(
    (message: string) => notify({ kind: 'error', message }),
    [notify],
  );

  const load = useCallback(
    async (selectedGame: string) => {
      const generation = ++order.current;
      setBusy(true);
      setPreview(null);
      try {
        const labels = await symbolLabels(selectedGame || undefined);
        const dictionaries: DictionaryView[] = [];
        let start = 0;
        let token: string | undefined;
        do {
          const result = await symbolDictionaries(
            selectedGame || undefined,
            start,
            token,
          );
          dictionaries.push(...result.items);
          token = result.read_token;
          start += result.items.length;
          if (start >= result.total) break;
        } while (true);
        const locals = dictionaries.filter((d) => d.origin === 'lab');
        const latest = locals.at(-1);
        const approved = locals.find((d) => d.active);
        const latestFull = latest?.version
          ? await symbolDictionary(selectedGame, latest.version)
          : null;
        const approvedFull = approved?.version
          ? approved.version === latest?.version
            ? latestFull
            : await symbolDictionary(selectedGame, approved.version)
          : null;
        if (generation !== order.current) return;
        setPage(labels);
        setBoardRevision(labels.revision);
        setLabelsStale(false);
        setConfirmation(null);
        setOffset(0);
        setVersions(dictionaries);
        setEntries(latestFull?.entries ?? []);
        setActive(approvedFull);
        setBoardReadVersion((value) => value + 1);
      } catch (e) {
        if (generation === order.current) {
          setPage(null);
          report(`Nie można odczytać symboli: ${errorCode(e)}`);
        }
      } finally {
        if (generation === order.current) setBusy(false);
      }
    },
    [report],
  );

  useEffect(() => {
    let disposed = false;
    const requestOrder = order;
    void (async () => {
      const all: Source[] = [];
      let start = 0;
      while (true) {
        const result = await listSources(start);
        all.push(...result.sources);
        start += result.sources.length;
        if (start >= result.total) break;
      }
      if (!disposed) setSources(all);
    })().catch(() => report('Nie można pobrać katalogu źródeł.'));
    return () => {
      disposed = true;
      requestOrder.current++;
    };
  }, [report]);

  async function submit(body: SymbolRequest) {
    if (writing.current) return;
    writing.current = true;
    setBusy(true);
    setPending(body);
    try {
      const result = await writeSession.current.submit(body);
      setPending(null);
      notify({
        kind: 'success',
        message: 'Decyzja zapisana. Nie oznacza zgody na trening.',
      });
      if (body.op === 'label_cells_decide') {
        setPage(
          (current) => current && { ...current, revision: result.revision },
        );
        setLabelsStale(true);
        setConfirmation({ request: body, result });
      } else await load(game);
    } catch (error) {
      report(
        `Zapis niepotwierdzony: ${errorCode(error)}. Ponów dokładnie to żądanie lub odczytaj stan po konflikcie.`,
      );
    } finally {
      writing.current = false;
      setBusy(false);
    }
  }
  const mutation = () => ({
    request_id: crypto.randomUUID(),
    expected_revision: page?.revision ?? 0,
    actor: 'operator' as const,
  });
  const localVersions = versions.filter((d) => d.origin === 'lab');
  const latest = localVersions.at(-1);
  const games = Object.fromEntries(
    sources.map((s) => [s.game_id, s.game_name]),
  );

  function saveDictionaryDraft() {
    const normalizedEntries = normalizeSymbolDictionaryEntries(entries);
    if (hasBlankSymbolDictionaryName(normalizedEntries)) {
      report('Nazwa symbolu nie może być pusta.');
      return;
    }
    setEntries(normalizedEntries);
    void submit({
      ...mutation(),
      op: 'dictionary_draft',
      game_id: game,
      base_version: latest?.version ?? null,
      entries: normalizedEntries,
    });
  }
  async function nextPage() {
    if (!page || unavailable) return;
    setBusy(true);
    try {
      const next = offset + page.items.length;
      setPage(await symbolLabels(game, undefined, next, page.read_token));
      setOffset(next);
    } catch (error) {
      setPage(null);
      report(
        `Nie można odczytać strony: ${errorCode(error)}. Odczytaj listę od początku.`,
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="symbol-panel">
      <h1>Etykiety symboli</h1>
      <p>
        Słownik określa klasy danej gry. Zatwierdzenie etykiety dotyczy tylko
        pokazanych pikseli komórki. Żadna z tych decyzji nie uruchamia treningu.
      </p>
      {!unavailable && <Link href="/">Wróć do geometrii</Link>}
      <label>
        Gra{' '}
        <select
          value={game}
          disabled={unavailable}
          onChange={(e) => {
            const value = e.target.value;
            setGame(value);
            setPreview(null);
            void load(value);
          }}
        >
          <option value="">Wybierz grę</option>
          {Object.entries(games).map(([id, name]) => (
            <option value={id} key={id}>
              {gameDisplayName(id, name)}
            </option>
          ))}
        </select>
      </label>
      <button
        disabled={busy || boardBusy || queueBusy || !game}
        onClick={() => {
          writeSession.current.reload();
          setPending(null);
          void refresh()
            .then(() => load(game))
            .catch((error) => report(errorCode(error)));
        }}
      >
        Odczytaj stan
      </button>
      {pending && (
        <button disabled={busy} onClick={() => void submit(pending)}>
          Ponów identyczny zapis
        </button>
      )}
      <fieldset disabled={unavailable || !game || !page}>
        <legend>Słownik gry</legend>
        <p>
          Nowa wersja nie zmienia zatwierdzonej wersji, dopóki jej jawnie nie
          zatwierdzisz. Aby dodać inny symbol, dodaj nową pozycję; korekta nazwy
          nie zmienia klasy.
        </p>
        {entries.map((entry) => (
          <div key={entry.id}>
            <label>
              Nazwa{' '}
              <input
                value={entry.display_name}
                maxLength={128}
                onChange={(e) =>
                  setEntries(
                    entries.map((v) =>
                      v.id === entry.id
                        ? { ...v, display_name: e.target.value }
                        : v,
                    ),
                  )
                }
              />
            </label>
            <button
              onClick={() =>
                setEntries(entries.filter((value) => value.id !== entry.id))
              }
            >
              Usuń z nowej wersji
            </button>
          </div>
        ))}
        <button
          disabled={entries.length >= 256}
          onClick={() =>
            setEntries([...entries, createSymbolDictionaryEntry()])
          }
        >
          Dodaj klasę
        </button>
        <button onClick={saveDictionaryDraft}>Zapisz nową wersję</button>
        <button
          disabled={!latest?.version || latest.status === 'approved'}
          onClick={() =>
            latest?.version &&
            void submit({
              ...mutation(),
              op: 'dictionary_approve',
              game_id: game,
              version: latest.version,
              digest: latest.digest,
            })
          }
        >
          Zatwierdź zapisaną wersję {latest?.version}
        </button>
        <p>Aktywna zatwierdzona wersja: {active?.version ?? 'brak'}</p>
      </fieldset>
      <SymbolCandidateQueue
        key={`queue-${game}`}
        game={game}
        sources={sources}
        active={active}
        readVersion={boardReadVersion}
        enabled={page !== null}
        disabled={
          queueBusy ||
          !page ||
          (busy && pending?.op !== 'label_cells_decide') ||
          (pending !== null && !busy)
        }
        saving={busy}
        submittedIds={
          pending?.op === 'label_cells_decide'
            ? pending.bindings.map((binding) => binding.crop_id)
            : []
        }
        confirmation={confirmation}
        onBusy={setQueueBusy}
        onSubmit={submit}
        onError={report}
      />
      <SymbolAssignedGallery
        key={`assigned-${game}`}
        game={game}
        sources={sources}
        active={active}
        readVersion={boardReadVersion}
        onError={report}
      />
      {labelsStale && (
        <p>
          Listę przypisań odświeżysz przyciskiem „Odśwież listę”. Aby edytować
          całą planszę, kliknij „Odczytaj stan”.
        </p>
      )}
      <SymbolBoardEditor
        key={`board-${game}`}
        game={game}
        sources={sources}
        annotations={state}
        revision={boardRevision}
        readVersion={boardReadVersion}
        disabled={unavailable || labelsStale || !page}
        onBusy={setBoardBusy}
        onSubmit={submit}
        onError={report}
      />
      <section>
        <h2>Zapisane etykiety</h2>
        <p>
          Trening zablokowany: nie zamrożono podziału danych symboli. Brak
          danych DB w snapshotcie folderowym jest oczekiwany.
        </p>
        {labelsStale && (
          <p>
            Nowe decyzje zapisane. Kliknij „Odczytaj stan”, aby zaktualizować
            listę etykiet.
          </p>
        )}
        {!labelsStale &&
          page?.items.map((row) => (
            <article key={row.sample_id}>
              <p>
                {row.source_id.slice(0, 12)} · plansza{' '}
                {row.origin === 'lab_human_approved'
                  ? Number(row.board_id) + 1
                  : row.board_id}{' '}
                · komórka {row.cell_index + 1}: {row.symbol_id ?? row.action} —{' '}
                {row.label_valid ? 'ważna decyzja' : 'wymaga przeglądu'}
              </p>
              <p>{[...row.reasons, ...row.training_blockers].join(', ')}</p>
              {canMutateSymbolRow(row.origin) ? (
                <button
                  disabled={unavailable || row.action === 'withdraw'}
                  onClick={() =>
                    void submit({
                      ...mutation(),
                      op: 'label_withdraw',
                      decision_id: row.sample_id,
                    })
                  }
                >
                  Wycofaj etykietę
                </button>
              ) : (
                <button
                  disabled={unavailable}
                  onClick={async () => {
                    setBusy(true);
                    setPreview(null);
                    try {
                      const crop = await symbolCrop({
                        kind: 'db_approved',
                        sample_id: row.sample_id,
                      });
                      if (crop.kind === 'db_approved') setPreview(crop);
                    } catch (error) {
                      report(
                        `Eksportowany crop jest niedostępny: ${errorCode(error)}`,
                      );
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Podgląd eksportowanej etykiety
                </button>
              )}
            </article>
          ))}
        {preview?.kind === 'db_approved' && (
          <div>
            <p>
              Oryginalne zatwierdzenie DB — tylko odczyt. Słownik{' '}
              {preview.dictionary.digest}
            </p>
            <img
              alt="Oryginalny zatwierdzony crop DB"
              src={`data:${preview.media_type};base64,${preview.crop_bytes_base64}`}
            />
            <ul>
              {preview.dictionary.entries?.map((e) => (
                <li key={e.id}>
                  {e.code}: {e.display_name}
                </li>
              ))}
            </ul>
          </div>
        )}
        <p>
          {labelsStale
            ? 'Lista wymaga aktualnego odczytu'
            : page
              ? page.total === 0
                ? '0 z 0'
                : `${offset + 1}–${offset + page.items.length} z ${page.total}`
              : 'Brak odczytu'}
        </p>
        <button
          disabled={
            unavailable ||
            labelsStale ||
            !page ||
            offset + page.items.length >= page.total
          }
          onClick={() => void nextPage()}
        >
          Następna strona
        </button>
        <button
          disabled={unavailable || !page}
          onClick={async () => {
            setBusy(true);
            try {
              const b = await backupSymbols();
              notify({
                kind: 'success',
                message: `Zapisano backup ${b.backup_id}`,
              });
            } catch (error) {
              report(`Backup nie został potwierdzony: ${errorCode(error)}`);
            } finally {
              setBusy(false);
            }
          }}
        >
          Utwórz backup symboli
        </button>
      </section>
    </main>
  );
}

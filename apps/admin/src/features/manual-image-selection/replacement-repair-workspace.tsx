'use client';

import { useMemo, useRef, useState } from 'react';
import { createConfiguredAdminApiClient } from '../../api/admin-api-client';
import {
  pickLocalDirectory,
  isLocalDirectoryPickerActive,
  subscribeLocalDirectoryPickerActive,
} from '../../lib/local-directory-picker.ts';
import { useEffect } from 'react';
import type { AdminApiClient } from '@game-predictor/admin-api-client';
import type {
  ReplacementRepairManifest,
  ReplacementRequest,
} from '@game-predictor/manual-image-selection-core/replacement-repair';
import { ManualImageViewer, useManualImageViewer } from './manual-image-viewer';
import {
  assertSeparateReplacementDirectories,
  inspectReplacementOutput,
  listReplacementSources,
  readReplacementRequest,
  writeReplacementPhoto,
  type ReplacementSource,
} from './replacement-repair-storage.ts';

export function ReplacementRepairWorkspace({
  apiBaseUrl,
  client,
}: {
  readonly apiBaseUrl: string;
  readonly client?: Pick<
    AdminApiClient,
    'getGame' | 'getSourceReplacementBatch'
  >;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [request, setRequest] = useState<ReplacementRequest | null>(null);
  const [gameLabel, setGameLabel] = useState('');
  const [sourceDirectory, setSourceDirectory] =
    useState<FileSystemDirectoryHandle | null>(null);
  const [sourceIdentity, setSourceIdentity] = useState('');
  const [output, setOutput] = useState<FileSystemDirectoryHandle | null>(null);
  const [sources, setSources] = useState<readonly ReplacementSource[]>([]);
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [manifest, setManifest] = useState<ReplacementRepairManifest | null>(
    null,
  );
  const [entryId, setEntryId] = useState('');
  const [phase, setPhase] = useState<string | null>(null);
  const busyRef = useRef(false);
  const [pickerActive, setPickerActive] = useState(
    isLocalDirectoryPickerActive,
  );
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(
    () =>
      subscribeLocalDirectoryPickerActive(() =>
        setPickerActive(isLocalDirectoryPickerActive()),
      ),
    [],
  );
  const source = sources.find(
    (item) => item.entryId === entryId && item.fileName === chosen[entryId],
  );
  const images = useMemo(
    () =>
      source
        ? [
            {
              name: source.fileName,
              relativePath: source.fileName,
              handle: source.handle,
            },
          ]
        : [],
    [source],
  );
  const viewer = useManualImageViewer(
    images,
    0,
    setError,
    undefined,
    undefined,
    `${request?.digest ?? ''}:${sourceIdentity}:${entryId}:${source?.fileName ?? ''}`,
  );
  useEffect(() => {
    queueMicrotask(() => setReady(false));
    if (!viewer.visibleImageUrl || !viewer.sourceImageSize) return;
    const timer = window.setTimeout(() => setReady(true), 300);
    return () => window.clearTimeout(timer);
  }, [viewer.visibleImageUrl, viewer.sourceImageSize, source]);

  async function run(label: string, action: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setPhase(label);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(replacementErrorMessage(cause));
    } finally {
      busyRef.current = false;
      setPhase(null);
    }
  }

  async function openOutput() {
    if (!request) return;
    const directory = await pickLocalDirectory({
      mode: 'readwrite',
      id: 'replacement-output',
    });
    if (sourceDirectory)
      await assertSeparateReplacementDirectories(sourceDirectory, directory);
    const restored = await inspectReplacementOutput(directory, request);
    setOutput(directory);
    setManifest(restored);
  }
  const busy = phase !== null || pickerActive;
  const committed =
    manifest?.journal.filter((write) => write.state === 'committed').length ??
    0;
  const pending = manifest?.journal.find((write) => write.state === 'intent');
  const done =
    manifest?.journal.some(
      (write) => write.entryId === entryId && write.state === 'committed',
    ) ?? false;

  return (
    <details className="manualImageSelectionSetup">
      <summary>Uzupełnij luki z manifestu wymiany zdjęć</summary>
      <p>
        Wczytaj żądanie otwartych luk z panelu wymiany. Nowe zdjęcia pozostają
        tylko do odczytu. Wybierz osobny pusty katalog wyniku albo ponownie
        otwórz własny wynik v3 po przerwaniu.
      </p>
      <label>
        Żądanie wymiany (JSON)
        <input
          type="file"
          accept="application/json,.json"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (!file) return;
            void run('Sprawdzam żądanie…', async () => {
              setRequest(null);
              const next = await readReplacementRequest(
                JSON.parse(await file.text()),
              );
              const game = await api.getGame(next.gameId);
              if (game.error || !game.data || game.data.id !== next.gameId)
                throw new Error('REPLACEMENT_CURRENT_GAME_REQUIRED');
              setGameLabel(`${game.data.name} (${game.data.code})`);
              setRequest(next);
              setEntryId(next.entries[0]!.entryId);
              setManifest(null);
              setOutput(null);
              setSourceDirectory(null);
              setSources([]);
              setChosen({});
            });
          }}
        />
      </label>
      {request ? (
        <>
          <p>
            Gra: {gameLabel} · {request.entries.length} zdjęć. Stan sprawdza
            aktualnie skonfigurowane API.
          </p>
          <button
            type="button"
            className="secondaryButton"
            disabled={busy}
            onClick={() =>
              void run('Listuję nowe zdjęcia…', async () => {
                const directory = await pickLocalDirectory({
                  mode: 'read',
                  id: 'replacement-source',
                });
                if (output)
                  await assertSeparateReplacementDirectories(directory, output);
                const listed = await listReplacementSources(directory, request);
                const defaults: Record<string, string> = {};
                for (const entry of request.entries) {
                  const matches = listed.filter(
                    (row) => row.entryId === entry.entryId,
                  );
                  if (matches.length === 1)
                    defaults[entry.entryId] = matches[0]!.fileName;
                }
                setSourceDirectory(directory);
                setSourceIdentity(crypto.randomUUID());
                setSources(listed);
                setChosen(defaults);
              })
            }
          >
            Wybierz nowe zdjęcia seq_* (tylko odczyt)
          </button>
          <button
            type="button"
            className="secondaryButton"
            disabled={busy}
            onClick={() =>
              void run('Sprawdzam wynik i odzyskuję journal…', openOutput)
            }
          >
            Wybierz osobny wynik / wznów
          </button>
          <p>
            {sourceDirectory
              ? `Źródło: ${sourceDirectory.name} (${sources.length} zdjęć)`
              : 'Nie wybrano nowych zdjęć.'}{' '}
            {output ? `Wynik: ${output.name}` : 'Nie wybrano katalogu wyniku.'}
          </p>
          {sourceDirectory && sources.length === 0 ? (
            <p role="status">
              Brak pasujących zdjęć JPEG na wybranym poziomie katalogu.
            </p>
          ) : null}
          <label>
            Całe zdjęcie / dokładny zakres
            <select
              value={entryId}
              disabled={busy}
              onChange={(event) => setEntryId(event.target.value)}
            >
              {request.allowedRanges.map((range) => (
                <option key={range.entryId} value={range.entryId}>
                  {range.sequenceStart}–{range.sequenceEnd}
                  {manifest?.journal.some(
                    (write) =>
                      write.entryId === range.entryId &&
                      write.state === 'committed',
                  )
                    ? ' · przygotowano'
                    : ''}
                </option>
              ))}
            </select>
          </label>
          <label>
            Nowy plik (przy duplikacie wybierz ręcznie)
            <select
              value={chosen[entryId] ?? ''}
              disabled={busy || done}
              onChange={(event) =>
                setChosen((old) => ({ ...old, [entryId]: event.target.value }))
              }
            >
              <option value="">Wybierz dokładnie jeden plik</option>
              {sources
                .filter((item) => item.entryId === entryId)
                .map((item) => (
                  <option key={item.fileName} value={item.fileName}>
                    {item.fileName}
                  </option>
                ))}
            </select>
          </label>
          {source ? (
            <ManualImageViewer
              state={viewer}
              busy={busy}
              currentLabel={source.fileName}
              currentPosition={1}
              currentRelativePath={source.fileName}
              imageCount={1}
              navigationStepLabel="Całe zdjęcie"
              nextDisabled
              previousDisabled
              onNext={() => undefined}
              onPrevious={() => undefined}
            />
          ) : null}
          <button
            type="button"
            className="primaryButton"
            disabled={
              busy || !source || !sourceDirectory || !output || done || !ready
            }
            onClick={() =>
              void run('Sprawdzam lukę w API i zapisuję zdjęcie…', async () => {
                if (!source || !sourceDirectory || !output) return;
                const saved = await writeReplacementPhoto({
                  sourceDirectory,
                  output,
                  request,
                  source,
                  api,
                });
                setManifest(saved);
              })
            }
          >
            Przygotuj wybrane zdjęcie
          </button>
          {pending ? (
            <p role="status">
              Zapis {pending.sourcePath} przerwano przed ukończeniem JPEG.
              Wybierz ponownie ten sam plik i przygotuj zdjęcie. Zmieniony lub
              częściowy cel blokuje zapis.
            </p>
          ) : null}
          <p role="status">
            Przygotowano lokalnie {committed}/{request.entries.length} zdjęć.
            Backendowa luka pozostaje otwarta do importu i przeglądu zamiennika.
          </p>
        </>
      ) : null}
      {phase ? <p role="status">{phase}</p> : null}
      {error ? (
        <p role="alert" className="formError">
          {error}. Wskaż ponownie katalog wyniku, aby sprawdzić stan po
          przerwaniu.
        </p>
      ) : null}
    </details>
  );
}

function replacementErrorMessage(cause: unknown): string {
  const message = cause instanceof Error ? cause.message : String(cause);
  const code = message.split(':')[0]!;
  const labels: Record<string, string> = {
    REPLACEMENT_CURRENT_GAME_REQUIRED:
      'Nie można potwierdzić gry w aktualnym API',
    REPLACEMENT_CURRENT_API_REQUIRED:
      'Nie można potwierdzić otwartej luki w aktualnym API',
    REPLACEMENT_ENTRY_STALE:
      'Luka lub jej zakres zmieniły się. Pobierz aktualne żądanie wymiany',
    REPLACEMENT_REQUEST_DIGEST_MISMATCH:
      'Żądanie wymiany ma niezgodny skrót kontrolny',
    REPLACEMENT_EXACT_RANGE_REQUIRED:
      'Nazwa zdjęcia nie pasuje do dokładnego zakresu wybranej luki',
    REPLACEMENT_OUTPUT_MUST_BE_SEPARATE:
      'Wynik musi być osobnym katalogiem poza źródłem i jego podfolderami',
    REPLACEMENT_FOREIGN_FILE:
      'Katalog wyniku zawiera obcy plik. Wybierz pusty katalog albo własny wynik v3',
    REPLACEMENT_TEMPORARY_WRITE_REMAINS:
      'Przerwany zapis pozostawił plik tymczasowy. Zachowaj katalog do sprawdzenia i wybierz nowy pusty wynik; narzędzie nie usuwa pozostałości',
    REPLACEMENT_FOREIGN_MANIFEST:
      'Katalog wyniku należy do innego żądania wymiany',
    REPLACEMENT_FOREIGN_HANDOFF:
      'Manifest uzupełnień należy do innego wyniku albo zawiera obce wpisy',
    REPLACEMENT_FILE_CHANGED:
      'Plik wyniku został zmieniony lub zapisany tylko częściowo',
    REPLACEMENT_RETIRED_SHA:
      'Nowe zdjęcie ma tę samą zawartość co wycofane źródło',
    REPLACEMENT_PENDING_SOURCE_REQUIRED:
      'Wznów zapis dokładnie tego samego zdjęcia wskazanego w journalu',
    REPLACEMENT_INVALID_JPEG: 'Wybrany plik nie jest poprawnym zdjęciem JPEG',
    REPLACEMENT_ENTRY_ALREADY_PREPARED:
      'To zdjęcie ma już inny przygotowany wynik',
    REPLACEMENT_TARGET_EXISTS:
      'Plik docelowy już istnieje. Sprawdź katalog wyniku przed ponowieniem',
    REPLACEMENT_COMMITTED_FILE_MISSING:
      'Brakuje wcześniej przygotowanego zdjęcia. Sprawdź katalog wyniku',
    REPLACEMENT_WRITTEN_CHECKSUM_MISMATCH:
      'Zapisane zdjęcie ma inną zawartość. Sprawdź dysk i zachowaj katalog do weryfikacji',
    REPLACEMENT_EMPTY_JPEG:
      'Wybrane zdjęcie jest puste. Wskaż poprawny plik JPEG',
    REPLACEMENT_DIRECTORY_CHANGED:
      'Nazwa katalogu wyniku zmieniła się. Wskaż pierwotny katalog',
  };
  return (
    labels[code] ??
    (code.startsWith('REPLACEMENT_')
      ? `Nie można przygotować zdjęcia. Sprawdź żądanie i katalog wyniku (${code})`
      : message)
  );
}

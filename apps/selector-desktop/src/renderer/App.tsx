import React, { useEffect, useRef, useState } from 'react';
import {
  adjacentManualNavigationStep,
  MANUAL_IMAGE_NAVIGATION_STEPS,
  rangeForStart,
} from '@game-predictor/manual-image-selection-core';
import type {
  DesktopWorkspace,
  DesktopCommand,
  NativeResult,
  RecentProjectSummary,
  RestartSummary,
  ViewPreferences,
  LegacyPreviewSummary,
  NewProjectDraft,
} from '../contracts.ts';
import { ImageViewer } from './image-viewer.tsx';
import { resolveDesktopShortcut } from './desktop-shortcuts.ts';
function unwrap<T>(result: NativeResult<T>): T {
  if (!result.ok)
    throw new Error(`${result.error.message} (${result.error.code})`);
  return result.value;
}
export function App() {
  const [workspace, setWorkspace] = useState<DesktopWorkspace | null>(null);
  const latest = useRef(workspace);
  latest.current = workspace;
  const [recent, setRecent] = useState<RecentProjectSummary[]>([]);
  const [draft, setDraft] = useState<NewProjectDraft | null>(null);
  const [gameName, setGameName] = useState('');
  const [recentId, setRecentId] = useState('');
  const [legacy, setLegacy] = useState<LegacyPreviewSummary | null>(null);
  const [first, setFirst] = useState('1');
  const [last, setLast] = useState('');
  const [direction, setDirection] = useState<'ascending' | 'descending'>(
    'ascending',
  );
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [error, setError] = useState('');
  const [decoded, setDecoded] = useState<string | null>(null);
  const [rangeEditor, setRangeEditor] = useState(false);
  const [rangeStart, setRangeStart] = useState('');
  const [restart, setRestart] = useState<RestartSummary | null>(null);
  function applyFullscreen(active: boolean) {
    setFullscreen(active);
    if (active) {
      setRangeEditor(false);
      setRestart(null);
    }
  }
  useEffect(() => window.selector.onFullscreenChanged(applyFullscreen), []);
  async function toggleFullscreen() {
    try {
      applyFullscreen(unwrap(await window.selector.fullscreen()));
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : 'Nie można zmienić ekranu.',
      );
    }
  }
  useEffect(() => {
    void window.selector
      .recent()
      .then((result) => setRecent(unwrap(result)))
      .catch((e) => setError(e.message));
  }, []);
  async function run(work: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    try {
      await work();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : 'Operacja nie powiodła się.',
      );
      const snapshot = await window.selector.snapshot();
      if (snapshot.ok) setWorkspace(snapshot.value);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }
  async function install(value: DesktopWorkspace | null) {
    if (!value) return;
    setWorkspace(value);
    latest.current = value;
    setDecoded(null);
    setDraft(null);
    setRangeEditor(false);
    setRestart(null);
    setLegacy(null);
  }
  function changeView(view: ViewPreferences) {
    const current = latest.current;
    if (!current) return;
    const updated = { ...current, view };
    latest.current = updated;
    setWorkspace(updated);
    void window.selector
      .saveView(current.projectId, view)
      .then((result) => {
        unwrap(result);
      })
      .catch((cause) =>
        setError(`Widok nie został zapisany: ${cause.message}`),
      );
  }
  function execute(command: DesktopCommand) {
    const current = latest.current;
    if (!current || current.issue || busyRef.current) return;
    void run(async () => {
      const result = unwrap(
        await window.selector.execute({
          projectId: current.projectId,
          operationId: crypto.randomUUID(),
          command,
        }),
      );
      const updated = {
        ...result,
        view:
          latest.current?.projectId === result.projectId
            ? latest.current.view
            : result.view,
      };
      setWorkspace(updated);
      latest.current = updated;
      setRangeEditor(false);
      setRestart(null);
    });
  }
  const source = workspace?.source;
  const ordinal =
    source?.images.findIndex((i) => i.id === workspace?.currentImageId) ?? -1;
  const image = source?.images[ordinal];
  const accepted = image
    ? workspace?.acceptedImageIds.includes(image.id)
    : false;
  const canAccept = Boolean(
    image &&
    decoded === image.id &&
    !accepted &&
    !workspace?.selectionComplete &&
    !workspace?.issue &&
    !busy,
  );
  const blocked = busy || Boolean(workspace?.issue);
  function accept() {
    if (canAccept && image) execute({ kind: 'accept', imageId: image.id });
  }
  function skip() {
    if (workspace && !workspace.selectionComplete && !blocked)
      execute({ kind: 'skip' });
  }
  function move(delta: number) {
    if (!source || blocked || rangeEditor || restart) return;
    const target = Math.max(
      0,
      Math.min(source.images.length - 1, ordinal + delta),
    );
    if (target !== ordinal)
      execute({ kind: 'navigate', imageId: source.images[target].id });
  }
  function undo() {
    if (workspace?.decisionCount && !blocked) execute({ kind: 'undo' });
  }
  useEffect(() => {
    function keyboard(event: KeyboardEvent) {
      if (event.key === 'F11' && !event.repeat) {
        event.preventDefault();
        void toggleFullscreen();
        return;
      }
      if (event.key === 'Escape' && fullscreen && !event.repeat) {
        event.preventDefault();
        void toggleFullscreen();
        return;
      }
      if (!workspace || blocked || rangeEditor || restart || draft || legacy)
        return;
      const shortcut = resolveDesktopShortcut({
        key: event.key,
        ctrlKey: event.ctrlKey,
        altKey: event.altKey,
        metaKey: event.metaKey,
        repeat: event.repeat,
        target: event.target instanceof HTMLElement ? event.target : null,
      });
      if (shortcut.preventDefault) event.preventDefault();
      const action = shortcut.action;
      if (!action) return;
      if (action === 'accept') accept();
      else if (action === 'skip') skip();
      else if (action === 'undo') undo();
      else if (action === 'previous_image')
        move(-workspace.view.navigationStep);
      else if (action === 'next_image') move(workspace.view.navigationStep);
      else
        changeView({
          ...workspace.view,
          navigationStep: adjacentManualNavigationStep(
            workspace.view.navigationStep,
            action === 'previous_step' ? -1 : 1,
          ),
        });
    }
    window.addEventListener('keydown', keyboard);
    return () => window.removeEventListener('keydown', keyboard);
  });
  let range: { start: number; end: number } | null = null;
  try {
    if (workspace && !workspace.selectionComplete)
      range = rangeForStart(
        workspace.nextRangeStart,
        workspace.sequenceUpperBound,
      );
  } catch {
    /* A terminal project has no next range. */
  }
  return (
    <main
      className={workspace && fullscreen ? 'fullscreen' : ''}
      aria-busy={busy}
    >
      <header>
        <div>
          <h1>Selektor zdjęć</h1>
          <p>Zdjęcia i wyniki pozostają na tym komputerze.</p>
        </div>
        <button
          onClick={() =>
            void window.selector
              .openLogs()
              .then(unwrap)
              .catch((e) => setError(e.message))
          }
        >
          Otwórz logi
        </button>
      </header>
      {legacy && (
        <section className="legacy-preview">
          <h2>Podgląd sesji Reviewera</h2>
          <p>
            Źródło: {legacy.sourceName} · Stary wynik: {legacy.oldOutputName}
          </p>
          <p>
            Zdjęcia: {legacy.fileCount} · Wybrane: {legacy.acceptedCount} ·
            Pominięte zakresy: {legacy.skippedCount}
          </p>
          <p>
            Pierwsza plansza: {legacy.firstLayout} · Ostatnia plansza:{' '}
            {legacy.sequenceUpperBound ?? 'bez granicy'} · Kierunek:{' '}
            {legacy.direction === 'ascending' ? 'rosnący' : 'malejący'}
          </p>
          <p>
            Aktualne zdjęcie: {legacy.currentPhoto} ·{' '}
            {legacy.selectionComplete
              ? 'Selekcja zakończona'
              : `Następny zakres od: ${legacy.nextRangeStart}`}
          </p>
          {legacy.legacyCursor && (
            <p>
              Pozycja zdjęcia została odtworzona według historycznych zasad
              Reviewera.
            </p>
          )}
          <p>
            Sprawdzono źródło i sumy kontrolne JPEG-ów. Powstanie osobny projekt
            i nowy wynik. Oryginały pozostaną bez zmian.
          </p>
          <nav>
            <button
              disabled={busy}
              onClick={() =>
                void run(async () =>
                  install(
                    unwrap(
                      await window.selector.legacyAdopt(legacy.previewToken),
                    ),
                  ),
                )
              }
            >
              Utwórz nowy projekt z tej sesji
            </button>
            <button disabled={busy} onClick={() => setLegacy(null)}>
              Anuluj przejęcie
            </button>
          </nav>
        </section>
      )}
      {!workspace ? (
        <section className="start">
          <nav>
            <button
              className="primary"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const result = unwrap(await window.selector.begin());
                  if (!result) return;
                  if (result.kind === 'existing') {
                    await install(result.workspace);
                  } else {
                    setDraft(result.draft);
                    setLegacy(null);
                    setGameName('');
                    setFirst('1');
                    setLast('');
                    setDirection('ascending');
                    setConfirmed(false);
                  }
                })
              }
            >
              Wybierz folder zdjęć
            </button>
            <button
              disabled={busy}
              onClick={() =>
                void run(async () =>
                  install(unwrap(await window.selector.open())),
                )
              }
            >
              Otwórz projekt
            </button>
            <button
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  setDraft(null);
                  setLegacy(unwrap(await window.selector.legacyPreview()));
                })
              }
            >
              Przejmij sesję Reviewera
            </button>
          </nav>
          {!draft && (
            <p>
              Wybierz zdjęcia, aby zacząć lub wrócić do zapisanej pracy. Wyniki
              zapisujemy automatycznie obok tego folderu.
            </p>
          )}
          {draft && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void run(async () =>
                  install(
                    unwrap(
                      await window.selector.create({
                        sourceToken: draft.sourceToken,
                        gameName,
                        firstLayout: Number(first),
                        direction,
                        sequenceUpperBound: last === '' ? null : Number(last),
                        customLocations: false,
                        localStorageConfirmed: confirmed,
                      }),
                    ),
                  ),
                );
              }}
            >
              <h2>Nowa partia zdjęć</h2>
              <p>
                Zdjęcia: <strong>{draft.sourceName}</strong>
              </p>
              <label>
                Nazwa gry
                <input
                  autoFocus
                  aria-label="Nazwa gry"
                  required
                  maxLength={80}
                  placeholder="np. Mumie lub Siódemki"
                  value={gameName}
                  onChange={(e) => setGameName(e.target.value)}
                />
              </label>
              <label>
                Pierwsza plansza
                <input
                  aria-label="Pierwsza plansza"
                  type="number"
                  min="1"
                  required
                  value={first}
                  onChange={(e) => setFirst(e.target.value)}
                />
              </label>
              <label>
                Ostatnia plansza (opcjonalnie)
                <input
                  aria-label="Ostatnia plansza"
                  type="number"
                  min={first}
                  value={last}
                  onChange={(e) => setLast(e.target.value)}
                />
              </label>
              <label>
                Kierunek numeracji
                <select
                  aria-label="Kierunek numeracji"
                  value={direction}
                  onChange={(e) =>
                    setDirection(e.target.value as typeof direction)
                  }
                >
                  <option value="ascending">Rosnący</option>
                  <option value="descending">Malejący</option>
                </select>
              </label>
              <div className="folder-summary">
                <p>Zdjęcia: {draft.sourcePath}</p>
                <p>Wybrane zdjęcia: {draft.outputPath}</p>
                <p>Postęp: {draft.projectPath}</p>
                <p>
                  Foldery utworzymy automatycznie. Nie musisz zapisywać ręcznie.
                </p>
              </div>
              <label className="check">
                <input
                  type="checkbox"
                  required
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                Projekt i wynik będą na lokalnym dysku, poza synchronizacją i
                udziałami sieciowymi.
              </label>
              <nav>
                <button
                  className="primary"
                  disabled={busy || !confirmed || !gameName.trim()}
                  type="submit"
                >
                  Rozpocznij wybieranie
                </button>
                <button
                  disabled={busy}
                  type="button"
                  onClick={() => setDraft(null)}
                >
                  Anuluj
                </button>
              </nav>
            </form>
          )}
          {!draft && recent.length > 0 && (
            <section className="history">
              <h2>Historia wyboru zdjęć</h2>
              <label>
                Ostatnie projekty
                <select
                  aria-label="Ostatnie projekty"
                  disabled={busy}
                  value={recentId}
                  onChange={(event) => setRecentId(event.target.value)}
                >
                  <option value="">Wybierz grę i partię zdjęć</option>
                  {recent.map((project) => (
                    <option key={project.projectId} value={project.projectId}>
                      {project.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                disabled={busy || !recentId}
                onClick={() =>
                  void run(async () =>
                    install(unwrap(await window.selector.continue(recentId))),
                  )
                }
              >
                Kontynuuj
              </button>
            </section>
          )}
        </section>
      ) : (
        <>
          <div className="project-info">
            <strong>
              {workspace.gameName
                ? `${workspace.gameName} — ${workspace.sourceName}`
                : workspace.sourceName}
            </strong>
            <span>
              Projekt: {workspace.projectName} · Wynik: {workspace.outputName}
            </span>
            <span data-testid="counts">
              Wybrane: {workspace.acceptedCount} · Pominięte zakresy:{' '}
              {workspace.skippedCount}
            </span>
          </div>
          <nav className="toolbar selection-actions">
            <button disabled={!canAccept} onClick={accept}>
              Wybierz (Enter / F)
            </button>
            <button
              disabled={blocked || workspace.selectionComplete}
              onClick={skip}
            >
              Pomiń zakres (Tab)
            </button>
            <button
              disabled={blocked || !workspace.decisionCount}
              onClick={undo}
            >
              Cofnij (A / Ctrl+Z)
            </button>
            <strong data-testid="range">
              {workspace.selectionComplete
                ? 'Numeracja zakończona'
                : `Zakres: ${range?.start}–${range?.end}`}
            </strong>
            <button
              disabled={blocked || workspace.selectionComplete}
              onClick={() => {
                setRangeStart(String(workspace.nextRangeStart));
                setRangeEditor(true);
              }}
            >
              Zmień zakres
            </button>
          </nav>
          {rangeEditor && (
            <form
              className="inline-form"
              onSubmit={(event) => {
                event.preventDefault();
                execute({ kind: 'range', start: Number(rangeStart) });
              }}
            >
              <label>
                Początek zakresu
                <input
                  autoFocus
                  aria-label="Początek zakresu"
                  type="number"
                  min="1"
                  required
                  value={rangeStart}
                  onChange={(e) => setRangeStart(e.target.value)}
                />
              </label>
              <span>
                Koniec wyliczany automatycznie: 9 plansz lub końcówka.
              </span>
              <button disabled={busy}>Zapisz zakres</button>
              <button type="button" onClick={() => setRangeEditor(false)}>
                Anuluj zakres
              </button>
            </form>
          )}
          <nav
            className="toolbar viewer-toolbar"
            aria-label="Sterowanie podglądem"
          >
            <button
              disabled={blocked || ordinal <= 0}
              onClick={() => move(-workspace.view.navigationStep)}
            >
              Poprzednie
            </button>
            <span data-testid="cursor">
              {image
                ? `${ordinal + 1} / ${source!.images.length} · ${image.relativePath}`
                : 'Źródło niedostępne'}
            </span>
            {fullscreen && (
              <>
                <span data-testid="fullscreen-counts">
                  Wybrane: {workspace.acceptedCount}
                </span>
                <strong data-testid="fullscreen-range">
                  {workspace.selectionComplete
                    ? 'Numeracja zakończona'
                    : `Zakres: ${range?.start}–${range?.end}`}
                </strong>
              </>
            )}
            <button
              disabled={
                blocked || !source || ordinal >= source.images.length - 1
              }
              onClick={() => move(workspace.view.navigationStep)}
            >
              Następne
            </button>
            <label>
              Skok
              <select
                aria-label="Skok"
                value={workspace.view.navigationStep}
                onChange={(e) =>
                  changeView({
                    ...workspace.view,
                    navigationStep: Number(e.target.value),
                  })
                }
              >
                {MANUAL_IMAGE_NAVIGATION_STEPS.map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
            <label>
              Zoom
              <select
                aria-label="Zoom"
                value={workspace.view.zoom}
                onChange={(e) =>
                  changeView({
                    ...workspace.view,
                    zoom: Number(e.target.value),
                  })
                }
              >
                {[100, 150, 200, 300, 500, 1000, 1500, 2000, 3000].map((n) => (
                  <option key={n} value={n}>
                    {n}%
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={() => void toggleFullscreen()}
              aria-pressed={fullscreen}
            >
              {fullscreen
                ? 'Wyjdź z pełnego ekranu (F11)'
                : 'Pełny ekran (F11)'}
            </button>
          </nav>
          {source && image ? (
            <ImageViewer
              key={source.id}
              source={source}
              image={image}
              view={workspace.view}
              changeView={changeView}
              ready={setDecoded}
            />
          ) : (
            <p>
              Nie można wczytać źródła. Wskaż katalog ponownie; projekt
              zachowuje postęp.
            </p>
          )}
          <nav>
            <button
              disabled={blocked}
              onClick={() =>
                void window.selector
                  .openOutput()
                  .then(unwrap)
                  .catch((e) => setError(e.message))
              }
            >
              Otwórz folder wynikowy
            </button>
            <button
              disabled={blocked || !workspace.decisionCount}
              onClick={() =>
                void run(async () =>
                  setRestart(unwrap(await window.selector.restartPreview())),
                )
              }
            >
              Restart partii
            </button>
            <button
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  unwrap(await window.selector.close());
                  setWorkspace(null);
                  latest.current = null;
                  setRecent(unwrap(await window.selector.recent()));
                })
              }
            >
              Zamknij projekt
            </button>
          </nav>
          {!workspace.issue && (
            <details>
              <summary>Inne lokalizacje źródła i wyniku</summary>
              <p>
                Po otwarciu kopii projektu wskaż też kopię źródła i wyniku.
                Powiązania nie zmieniają się automatycznie.
              </p>
              <nav>
                <button
                  disabled={busy}
                  onClick={() =>
                    void run(async () =>
                      install(unwrap(await window.selector.relink('source'))),
                    )
                  }
                >
                  Wskaż ponownie źródło
                </button>
                <button
                  disabled={busy}
                  onClick={() =>
                    void run(async () =>
                      install(unwrap(await window.selector.relink('output'))),
                    )
                  }
                >
                  Wskaż ponownie wynik
                </button>
              </nav>
            </details>
          )}
          {restart && (
            <section
              className="restart"
              role="dialog"
              aria-label="Potwierdzenie restartu"
            >
              <h2>Restart partii</h2>
              <p>
                Usunąć {restart.acceptedFiles} własnych JPEG-ów wynikowych i
                wyzerować {restart.decisions} decyzji? Źródłowe zdjęcia
                pozostaną.
              </p>
              <button
                disabled={busy}
                onClick={() =>
                  execute({
                    kind: 'restart',
                    expectedRevision: restart.revision,
                    previewChecksum: restart.checksum,
                  })
                }
              >
                Potwierdź restart partii
              </button>
              <button disabled={busy} onClick={() => setRestart(null)}>
                Anuluj restart
              </button>
            </section>
          )}
        </>
      )}
      <footer className="feedback">
        {workspace?.issue && !fullscreen && (
          <section className="issue" role="alert">
            <strong>
              Zapis zatrzymany: {workspace.issue.message} (
              {workspace.issue.code})
            </strong>
            <p>
              {workspace.issue.code === 'OUTPUT_MISSING_FILE'
                ? 'Przywróć brakujący JPEG z zgodnej kopii wyniku do tego samego katalogu, potem wznów. Bez kopii otwórz logi i przekaż diagnostykę. Nie resetuj projektu ani nie edytuj manifestu.'
                : 'Usuń przyczynę i wznów. Wcześniejsze decyzje pozostają w projekcie.'}
            </p>
            <nav>
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () =>
                    install(unwrap(await window.selector.resume())),
                  )
                }
              >
                Wznów po naprawie
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () =>
                    install(unwrap(await window.selector.relink('source'))),
                  )
                }
              >
                Wskaż ponownie źródło
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () =>
                    install(unwrap(await window.selector.relink('output'))),
                  )
                }
              >
                Wskaż ponownie wynik
              </button>
            </nav>
          </section>
        )}

        {busy && !workspace && (
          <p role="status">Weryfikacja źródła i sum kontrolnych JPEG-ów…</p>
        )}
        {error && <p role="alert">{error}</p>}
        {workspace?.issue && fullscreen && (
          <p role="alert">
            Zapis zatrzymany: {workspace.issue.message}. Wyjdź z pełnego ekranu,
            aby naprawić problem.
          </p>
        )}
        {accepted && !error && !workspace?.issue && (
          <p role="status">
            To zdjęcie jest już wybrane. Aby wybrać je ponownie, cofnij jego
            decyzję.
          </p>
        )}
      </footer>
    </main>
  );
}

import React, { useEffect, useRef, useState } from 'react';
import {
  adjacentManualNavigationStep,
  MANUAL_IMAGE_NAVIGATION_STEPS,
  rangeForStart,
  resolveManualSelectionShortcut,
} from '@game-predictor/manual-image-selection-core';
import type {
  DesktopWorkspace,
  DesktopCommand,
  NativeResult,
  RecentProjectSummary,
  RestartSummary,
  ViewPreferences,
} from '../contracts.ts';
import { ImageViewer } from './image-viewer.tsx';
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
  const [newProject, setNewProject] = useState(false);
  const [first, setFirst] = useState('1');
  const [last, setLast] = useState('');
  const [direction, setDirection] = useState<'ascending' | 'descending'>(
    'ascending',
  );
  const [custom, setCustom] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [decoded, setDecoded] = useState<string | null>(null);
  const [rangeEditor, setRangeEditor] = useState(false);
  const [rangeStart, setRangeStart] = useState('');
  const [restart, setRestart] = useState<RestartSummary | null>(null);
  const pendingView = useRef(Promise.resolve());
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
    setNotice('');
    try {
      await pendingView.current;
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
    setNewProject(false);
    setRangeEditor(false);
    setRestart(null);
  }
  function changeView(view: ViewPreferences) {
    const current = latest.current;
    if (!current) return;
    const updated = { ...current, view };
    latest.current = updated;
    setWorkspace(updated);
    pendingView.current = window.selector
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
      setWorkspace(result);
      latest.current = result;
      setRangeEditor(false);
      setRestart(null);
      setNotice('Zapisano trwale.');
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
        void window.selector.fullscreen();
        return;
      }
      if (!workspace || blocked || rangeEditor || restart || newProject) return;
      const action = resolveManualSelectionShortcut({
        key: event.key,
        ctrlKey: event.ctrlKey,
        altKey: event.altKey,
        metaKey: event.metaKey,
        repeat: event.repeat,
        target: event.target instanceof HTMLElement ? event.target : null,
      });
      if (!action) return;
      event.preventDefault();
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
    <main>
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
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!workspace ? (
        <section className="start">
          <nav>
            <button disabled={busy} onClick={() => setNewProject(true)}>
              Nowy projekt
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
          </nav>
          {newProject && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void run(async () =>
                  install(
                    unwrap(
                      await window.selector.create({
                        firstLayout: Number(first),
                        direction,
                        sequenceUpperBound: last === '' ? null : Number(last),
                        customLocations: custom,
                        localStorageConfirmed: confirmed,
                      }),
                    ),
                  ),
                );
              }}
            >
              <h2>Nowa partia zdjęć</h2>
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
                  value={direction}
                  onChange={(e) =>
                    setDirection(e.target.value as typeof direction)
                  }
                >
                  <option value="ascending">Rosnący</option>
                  <option value="descending">Malejący</option>
                </select>
              </label>
              <p>
                Domyślne foldery obok źródła: „nazwa selekcja” dla projektu i
                „nazwa wybrane” dla wyników.
              </p>
              <label className="check">
                <input
                  type="checkbox"
                  checked={custom}
                  onChange={(e) => setCustom(e.target.checked)}
                />
                Wybiorę osobne katalogi projektu i wyniku
              </label>
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
                <button disabled={busy || !confirmed} type="submit">
                  Wybierz zdjęcia i utwórz projekt
                </button>
                <button
                  disabled={busy}
                  type="button"
                  onClick={() => setNewProject(false)}
                >
                  Anuluj
                </button>
              </nav>
            </form>
          )}
          {!newProject && recent.length > 0 && (
            <>
              <h2>Ostatnie projekty</h2>
              {recent.map((project) => (
                <button
                  className="recent"
                  key={project.projectId}
                  disabled={busy}
                  onClick={() =>
                    void run(async () =>
                      install(
                        unwrap(
                          await window.selector.continue(project.projectId),
                        ),
                      ),
                    )
                  }
                >
                  Kontynuuj: {project.name}
                </button>
              ))}
            </>
          )}
          {busy && <p role="status">Otwieranie projektu…</p>}
        </section>
      ) : (
        <>
          <div className="project-info">
            <strong>{workspace.sourceName}</strong>
            <span>
              Projekt: {workspace.projectName} · Wynik: {workspace.outputName}
            </span>
            <span data-testid="counts">
              Wybrane: {workspace.acceptedCount} · Pominięte zakresy:{' '}
              {workspace.skippedCount}
            </span>
          </div>
          {workspace.issue && (
            <section className="issue" role="alert">
              <strong>
                Zapis zatrzymany: {workspace.issue.message} (
                {workspace.issue.code})
              </strong>
              <p>
                Usuń przyczynę i wznów. Wcześniejsze decyzje pozostają w
                projekcie.
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
          <nav className="toolbar">
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
          <nav className="toolbar">
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
            <button onClick={() => void window.selector.fullscreen()}>
              Pełny ekran (F11)
            </button>
          </nav>
          {accepted && (
            <p>
              To zdjęcie jest już wybrane. Aby wybrać je ponownie, cofnij jego
              decyzję.
            </p>
          )}
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
          <p className="save-state" role="status">
            {busy
              ? 'Trwały zapis w toku…'
              : workspace.issue
                ? 'Zapis zablokowany'
                : `Projekt zapisany · rewizja ${workspace.revision} · ${workspace.direction === 'ascending' ? 'numeracja rosnąca' : 'numeracja malejąca'}`}
          </p>
        </>
      )}
    </main>
  );
}

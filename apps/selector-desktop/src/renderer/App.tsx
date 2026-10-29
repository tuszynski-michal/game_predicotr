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
import { GameSelect } from './game-select.tsx';
import {
  MAX_SEQUENCE_NUMBER,
  GAME_UPDATE_PATTERN,
  outputDirectoryName,
} from '../contracts.ts';
import { ImageViewer } from './image-viewer.tsx';
import { resolveDesktopShortcut } from './desktop-shortcuts.ts';
import { SelectionIntents } from './selection-intents.ts';
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
  const [gameUpdate, setGameUpdate] = useState('');
  const [games, setGames] = useState<string[]>([]);
  const [first, setFirst] = useState('1');
  const [last, setLast] = useState('');
  let outputPreview = 'Uzupełnij grę, aktualizację i zakres.';
  if (draft) {
    try {
      const folder = outputDirectoryName({
        gameName,
        gameUpdate,
        firstLayout: Number(first),
        sequenceUpperBound: last === '' ? null : Number(last),
      });
      outputPreview = `${draft.outputParentPath.replace(/[\\/]+$/, '')}\\${folder}`;
    } catch (cause) {
      if (gameName && gameUpdate && first)
        outputPreview = cause instanceof Error ? cause.message : outputPreview;
    }
  }
  const [recentId, setRecentId] = useState('');
  const [legacy, setLegacy] = useState<LegacyPreviewSummary | null>(null);
  const [direction, setDirection] = useState<'ascending' | 'descending'>(
    'ascending',
  );
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const closingProject = useRef(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [error, setError] = useState('');
  const [, setDecoded] = useState<string | null>(null);
  const [rangeEditor, setRangeEditor] = useState(false);
  const [rangeStart, setRangeStart] = useState('');
  const [rangeDirection, setRangeDirection] = useState<
    'ascending' | 'descending'
  >('ascending');
  const [restart, setRestart] = useState<RestartSummary | null>(null);
  const [, refreshIntents] = useState(0);
  const [displayedImageId, setDisplayedImageId] = useState<string | null>(null);
  const [failedImageId, setFailedImageId] = useState<string | null>(null);
  const intentsRef = useRef<SelectionIntents | null>(null);
  if (!intentsRef.current) {
    let paintScheduled = false;
    intentsRef.current = new SelectionIntents({
      execute: (request) => window.selector.execute(request),
      snapshot: () => window.selector.snapshot(),
      operationId: () => crypto.randomUUID(),
      frame: (callback) => requestAnimationFrame(callback),
      changed: () => {
        const machine = intentsRef.current!;
        latest.current = machine.workspace;
        setWorkspace(machine.workspace);
        refreshIntents((version) => version + 1);
        if (!paintScheduled) {
          paintScheduled = true;
          requestAnimationFrame(() => {
            paintScheduled = false;
            setDisplayedImageId(intentsRef.current!.displayedImageId);
          });
        }
      },
    });
  }
  const intents = intentsRef.current;
  const operationBlocked = busy || intents.mutating || intents.closing;
  useEffect(() => {
    let activeToken: string | null = null;
    const unsubscribe = window.selector.onShutdownRequested((request) => {
      activeToken = request.token;
      void (async () => {
        try {
          if (
            busyRef.current ||
            (latest.current?.projectId ?? null) !== request.projectId
          )
            throw new Error(
              'Operacja projektu nadal trwa. Spróbuj zamknąć ponownie.',
            );
          await intents.flushForClose();
          if (activeToken !== request.token) return;
          unwrap(
            await window.selector.shutdownReady({ ...request, ready: true }),
          );
        } catch (cause) {
          if (activeToken !== request.token) return;
          const message =
            cause instanceof Error
              ? cause.message
              : 'Nie można zamknąć projektu.';
          intents.cancelClose(message);
          try {
            unwrap(
              await window.selector.shutdownReady({
                ...request,
                ready: false,
                message: message.slice(0, 500),
              }),
            );
          } catch (replyError) {
            setError(
              replyError instanceof Error ? replyError.message : message,
            );
          }
        }
      })();
    });
    const cancelled = window.selector.onShutdownCancelled((message) => {
      activeToken = null;
      intents.cancelClose(message);
    });
    return () => {
      unsubscribe();
      cancelled();
    };
  }, [intents]);
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
      .games()
      .then((result) => setGames(unwrap(result)))
      .catch((e) => setError(e.message));
    void window.selector
      .recent()
      .then((result) => setRecent(unwrap(result)))
      .catch((e) => setError(e.message));
  }, []);
  async function run(work: () => Promise<void>, recovery = false) {
    if (
      busyRef.current ||
      (intents.mutating && !(recovery && intents.recoverableError)) ||
      intents.closing
    )
      return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    try {
      await work();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : 'Operacja nie powiodła się.',
      );
      try {
        const snapshot = unwrap(await window.selector.snapshot());
        intents.install(snapshot);
      } catch (snapshotError) {
        setError(
          `Nie można odczytać projektu: ${snapshotError instanceof Error ? snapshotError.message : 'brak odpowiedzi'}`,
        );
      }
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }
  async function install(value: DesktopWorkspace | null) {
    if (!value) return;
    setWorkspace(value);
    latest.current = value;
    intents.install(value);
    setDisplayedImageId(value.currentImageId);
    setFailedImageId(null);
    setDecoded(null);
    setDraft(null);
    setRangeEditor(false);
    setRestart(null);
    setLegacy(null);
    setGames(unwrap(await window.selector.games()));
  }
  function beginSelection(keepGame = false) {
    void run(async () => {
      const result = unwrap(await window.selector.begin());
      if (!result) return;
      if (result.kind === 'existing') await install(result.workspace);
      else if (result.kind === 'legacy') {
        setDraft(null);
        setLegacy(result.preview);
      } else {
        setDraft(result.draft);
        setLegacy(null);
        setGameName(keepGame ? (workspace?.gameName ?? '') : '');
        setGameUpdate(keepGame ? (workspace?.gameUpdate ?? '') : '');
        setFirst(keepGame ? '' : '1');
        setLast('');
        setDirection(
          keepGame ? (workspace?.direction ?? 'ascending') : 'ascending',
        );
      }
    });
  }
  function changeView(view: ViewPreferences) {
    const current = latest.current;
    if (!current || closingProject.current || intents.closing) return;
    const updated = { ...current, view };
    intents.updateView(updated);
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
    if (busyRef.current) return;
    intents.command(command);
    setRangeEditor(false);
    setRestart(null);
  }
  const source = workspace?.source;
  const ordinal =
    source?.images.findIndex((i) => i.id === displayedImageId) ?? -1;
  const image = source?.images[ordinal];
  const accepted = image
    ? workspace?.acceptedImageIds.includes(image.id)
    : false;
  const canAccept = Boolean(
    image &&
    failedImageId !== image.id &&
    !accepted &&
    !workspace?.selectionComplete &&
    !workspace?.issue &&
    !busy &&
    !intents.closing &&
    !intents.blocked &&
    intents.phase !== 'error',
  );
  const blocked =
    operationBlocked || Boolean(workspace?.issue) || intents.phase === 'error';
  function accept() {
    if (!busyRef.current) intents.accept();
  }
  function skip() {
    if (workspace && !workspace.selectionComplete && !blocked)
      execute({ kind: 'skip' });
  }
  function move(delta: number) {
    if (!source || busyRef.current || rangeEditor || restart) return;
    setDecoded(null);
    setFailedImageId(null);
    intents.move(delta);
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
      if (
        !workspace ||
        busy ||
        intents.closing ||
        workspace.issue ||
        rangeEditor ||
        restart ||
        draft ||
        legacy
      )
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
        Math.min(
          workspace.sequenceUpperBound ?? MAX_SEQUENCE_NUMBER,
          MAX_SEQUENCE_NUMBER,
        ),
      );
  } catch {
    /* A terminal project has no next range. */
  }
  return (
    <main
      className={
        workspace && !draft && !legacy
          ? fullscreen
            ? 'selection fullscreen'
            : 'selection'
          : ''
      }
      aria-busy={busy}
    >
      <header className="toolbar viewer-toolbar">
        <h1>Selektor zdjęć</h1>
        {workspace && !draft && !legacy ? (
          <>
            <button
              className="secondaryButton configuration"
              disabled={operationBlocked}
              onClick={() => beginSelection(true)}
            >
              Wybierz kolejny folder
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
            {fullscreen && (
              <span data-testid="fullscreen-counts">
                <span data-testid="cursor">
                  {ordinal + 1} / {source?.images.length ?? 0}
                </span>{' '}
                · Wybrane: {workspace.acceptedCount}
              </span>
            )}
            <button
              className="secondaryButton"
              onClick={() => void toggleFullscreen()}
              aria-pressed={fullscreen}
            >
              {fullscreen ? 'Wyjdź (F11)' : 'Pełny ekran (F11)'}
            </button>
          </>
        ) : (
          <button
            className="secondaryButton"
            onClick={() =>
              void window.selector
                .openLogs()
                .then(unwrap)
                .catch((e) => setError(e.message))
            }
          >
            Otwórz logi
          </button>
        )}
      </header>
      {legacy && (
        <section className="legacy-preview">
          <h2>Podgląd sesji Reviewera</h2>
          <p>
            Źródło: {legacy.sourceName} · Stary wynik: {legacy.oldOutputName}
          </p>
          {legacy.projectName && (
            <p>
              Nowy projekt: {legacy.projectName} · Nowy wynik:{' '}
              {legacy.outputName}
            </p>
          )}
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
              className="secondaryButton"
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
            <button
              className="secondaryButton"
              disabled={busy}
              onClick={() => setLegacy(null)}
            >
              Anuluj przejęcie
            </button>
          </nav>
        </section>
      )}
      {legacy ? null : !workspace || draft ? (
        <section className="start">
          <nav>
            <button
              className="primaryButton"
              disabled={busy}
              onClick={() => beginSelection(Boolean(workspace))}
            >
              Wybierz folder zdjęć
            </button>
          </nav>
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
                        gameUpdate,
                        firstLayout: Number(first),
                        direction,
                        sequenceUpperBound: last === '' ? null : Number(last),
                        customLocations: false,
                        localStorageConfirmed: true,
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
              <GameSelect
                value={gameName}
                games={games}
                disabled={busy}
                onChange={setGameName}
                onAdd={(name) =>
                  run(async () => {
                    const updated = unwrap(await window.selector.addGame(name));
                    setGames(updated);
                    setGameName(
                      updated.find(
                        (game) =>
                          game.toLowerCase() === name.trim().toLowerCase(),
                      ) ?? name.trim(),
                    );
                  })
                }
              />
              <label>
                Aktualizacja
                <input
                  aria-label="Aktualizacja"
                  required
                  pattern={GAME_UPDATE_PATTERN}
                  placeholder="a1 lub z_a1"
                  title="Wpisz a i cyfry albo z_a i cyfry, np. a1, z_a2."
                  value={gameUpdate}
                  onChange={(e) => setGameUpdate(e.target.value)}
                />
              </label>
              <label>
                Pierwsza plansza
                <input
                  aria-label="Pierwsza plansza"
                  type="number"
                  min="1"
                  max={MAX_SEQUENCE_NUMBER}
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
                  max={MAX_SEQUENCE_NUMBER}
                  placeholder={String(MAX_SEQUENCE_NUMBER)}
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
                <p>Wybrane zdjęcia: {outputPreview}</p>
                <p>Postęp: {draft.projectPath}</p>
              </div>
              <nav>
                <button
                  className="primaryButton"
                  disabled={busy || !gameName.trim()}
                  type="submit"
                >
                  Rozpocznij wybieranie
                </button>
                <button
                  className="secondaryButton"
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
                className="secondaryButton"
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
                ? `${workspace.gameName}${workspace.gameUpdate ? ` ${workspace.gameUpdate}` : ''} — ${workspace.sourceName}`
                : workspace.sourceName}
            </strong>
            <span data-testid="counts">
              Wybrane: {workspace.acceptedCount} · Pominięte zakresy:{' '}
              {workspace.skippedCount}
            </span>
          </div>
          <nav className="toolbar selection-actions">
            <button
              className="primaryButton"
              disabled={!canAccept}
              onClick={accept}
            >
              Wybierz (Enter / F)
            </button>
            <button
              className="secondaryButton"
              title="Pomiń zakres (Tab)"
              disabled={blocked || workspace.selectionComplete}
              onClick={skip}
            >
              Pomiń
            </button>
            <button
              className="secondaryButton"
              title="Cofnij ostatnią decyzję (A / Ctrl+Z)"
              disabled={blocked || !workspace.decisionCount}
              onClick={undo}
            >
              Cofnij
            </button>
            <button
              className="secondaryButton"
              disabled={blocked}
              onClick={() => {
                setRangeStart(
                  String(
                    Math.min(
                      workspace.nextRangeStart,
                      workspace.sequenceUpperBound ?? MAX_SEQUENCE_NUMBER,
                      MAX_SEQUENCE_NUMBER,
                    ),
                  ),
                );
                setRangeDirection(workspace.direction);
                setRangeEditor(true);
              }}
            >
              Zakres
            </button>
          </nav>
          {rangeEditor && (
            <form
              className="inline-form"
              onSubmit={(event) => {
                event.preventDefault();
                execute({
                  kind: 'range',
                  start: Number(rangeStart),
                  direction: rangeDirection,
                });
              }}
            >
              <label>
                Początek zakresu
                <input
                  autoFocus
                  aria-label="Początek zakresu"
                  type="number"
                  min="1"
                  max={Math.min(
                    workspace.sequenceUpperBound ?? MAX_SEQUENCE_NUMBER,
                    MAX_SEQUENCE_NUMBER,
                  )}
                  required
                  value={rangeStart}
                  onChange={(e) => setRangeStart(e.target.value)}
                />
              </label>
              <label>
                Kierunek numeracji
                <select
                  aria-label="Kierunek numeracji"
                  value={rangeDirection}
                  onChange={(e) =>
                    setRangeDirection(e.target.value as typeof rangeDirection)
                  }
                >
                  <option value="ascending">Rosnący</option>
                  <option value="descending">Malejący</option>
                </select>
              </label>
              <button className="secondaryButton" disabled={busy}>
                Zapisz
              </button>
              <button
                className="secondaryButton"
                type="button"
                onClick={() => setRangeEditor(false)}
              >
                Anuluj
              </button>
            </form>
          )}
          <div
            className="photo-caption"
            data-testid={fullscreen ? undefined : 'cursor'}
          >
            {image
              ? `${ordinal + 1} / ${source!.images.length} · ${image.relativePath}`
              : 'Źródło niedostępne'}
          </div>
          <div className="range-indicator">
            <strong data-testid={fullscreen ? 'fullscreen-range' : 'range'}>
              {workspace.selectionComplete
                ? 'Numeracja zakończona'
                : `Zakres: ${range?.start}–${range?.end}`}
            </strong>
          </div>
          {source && image ? (
            <ImageViewer
              key={source.id}
              source={source}
              image={image}
              view={workspace.view}
              changeView={changeView}
              ready={(id) => {
                setDecoded(id);
                intents.decoded(id);
              }}
              failed={(id) => {
                setFailedImageId(id);
                intents.decoded(null, id);
              }}
            />
          ) : (
            <p>
              Nie można wczytać źródła. Wskaż katalog ponownie; projekt
              zachowuje postęp.
            </p>
          )}
          <nav>
            <button
              className="secondaryButton"
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
              className="secondaryButton"
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
              className="secondaryButton"
              disabled={busy || intents.closing}
              onClick={() => {
                void (async () => {
                  closingProject.current = true;
                  try {
                    await intents.flushForClose();
                    unwrap(await window.selector.close());
                    intents.install(null);
                    setWorkspace(null);
                    latest.current = null;
                    setRecent(unwrap(await window.selector.recent()));
                  } catch (cause) {
                    setError(
                      cause instanceof Error
                        ? cause.message
                        : 'Nie można zamknąć projektu.',
                    );
                  } finally {
                    closingProject.current = false;
                    intents.cancelClose();
                  }
                })();
              }}
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
                  className="secondaryButton"
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
                  className="secondaryButton"
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
                className="secondaryButton"
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
              <button
                className="secondaryButton"
                disabled={busy}
                onClick={() => setRestart(null)}
              >
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
                className="secondaryButton"
                disabled={busy}
                onClick={() =>
                  void run(
                    async () => install(unwrap(await window.selector.resume())),
                    true,
                  )
                }
              >
                Wznów po naprawie
              </button>
              <button
                className="secondaryButton"
                disabled={busy}
                onClick={() =>
                  void run(
                    async () =>
                      install(unwrap(await window.selector.relink('source'))),
                    true,
                  )
                }
              >
                Wskaż ponownie źródło
              </button>
              <button
                className="secondaryButton"
                disabled={busy}
                onClick={() =>
                  void run(
                    async () =>
                      install(unwrap(await window.selector.relink('output'))),
                    true,
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
        {intents.message && (
          <p role={intents.phase === 'error' ? 'alert' : 'status'}>
            {intents.message}
          </p>
        )}
        {intents.acceptIntent && !intents.acceptIntent.dispatched && (
          <button
            className="secondaryButton"
            onClick={() => intents.cancelAccept()}
          >
            Anuluj oczekiwanie
          </button>
        )}
        {intents.phase === 'accepting' && <p role="status">Zapis trwa…</p>}
        {intents.phase === 'error' && (
          <button className="secondaryButton" onClick={() => intents.retry()}>
            Wznów zapis
          </button>
        )}
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
